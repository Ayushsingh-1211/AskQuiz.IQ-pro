import os
from contextlib import contextmanager
from functools import lru_cache
from pathlib import Path
from typing import Generator, Optional
import psycopg
from psycopg.rows import dict_row
from psycopg_pool import ConnectionPool
from apps.api.app.config import get_settings
from apps.api.app.logging import get_logger

logger = get_logger("apps.api.db")

_pool: Optional[ConnectionPool] = None


@lru_cache()
def get_effective_database_url() -> str:
    """
    Returns the normalized database connection string.
    - Normalizes postgres:// to postgresql://
    - Preserves remote database URLs (e.g. Neon, Render, Supabase) and SSL settings exactly
    - Ensures sslmode=require for Neon databases if not explicitly provided
    - Only attempts local port 5432 -> 5433 fallback for localhost/127.0.0.1 Docker instances
    """
    settings = get_settings()
    url = settings.DATABASE_URL.strip()

    if url.startswith("postgres://"):
        url = url.replace("postgres://", "postgresql://", 1)

    # For remote databases (Neon, Render, AWS, etc.), never rewrite port to 5433
    if "localhost" not in url and "127.0.0.1" not in url:
        if ".neon.tech" in url and "sslmode" not in url:
            delimiter = "&" if "?" in url else "?"
            url = f"{url}{delimiter}sslmode=require"
        return url

    # For local Docker setup: test port 5432, fallback to 5433 if needed
    try:
        with psycopg.connect(url, connect_timeout=1):
            return url
    except Exception:
        if ":5432" in url:
            alt_url = url.replace(":5432", ":5433")
            try:
                with psycopg.connect(alt_url, connect_timeout=1):
                    logger.info("Using alternate database port 5433")
                    return alt_url
            except Exception:
                pass
    return url


def get_pool() -> ConnectionPool:
    """
    Returns the connection pool configured for high-resilience serverless operation.
    - check_connection validates idle connections before returning them
    - max_idle and reconnect_timeout allow safe recovery when Neon compute wakes up
    """
    global _pool
    if _pool is None:
        conninfo = get_effective_database_url()
        _pool = ConnectionPool(
            conninfo=conninfo,
            min_size=1,
            max_size=10,
            open=True,
            timeout=30.0,
            max_idle=300.0,
            reconnect_timeout=30.0,
            check=ConnectionPool.check_connection,
            kwargs={"row_factory": dict_row},
        )
    return _pool


def close_pool() -> None:
    global _pool
    if _pool is not None:
        try:
            _pool.close()
        except Exception as e:
            logger.warning(f"Error closing DB pool: {e}")
        _pool = None


@contextmanager
def get_db_context() -> Generator[psycopg.Connection, None, None]:
    pool = get_pool()
    with pool.connection() as conn:
        yield conn


def get_db() -> Generator[psycopg.Connection, None, None]:
    with get_db_context() as conn:
        yield conn


def check_db_health() -> bool:
    try:
        conninfo = get_effective_database_url()
        with psycopg.connect(conninfo, connect_timeout=3) as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT 1")
                return True
    except Exception as exc:
        logger.error(f"Database health check failed: {exc}")
        return False


def run_migrations(auto_apply_pending: bool = False) -> None:
    """
    Runs database migrations safely.
    Pending migrations requiring manual human approval (>= 004) are skipped unless
    auto_apply_pending=True is explicitly passed.
    """
    conninfo = get_effective_database_url()
    logger.info("Running database migrations...")
    migrations_dir = Path(__file__).parent / "migrations"
    if not migrations_dir.exists():
        logger.warning(f"Migrations directory does not exist: {migrations_dir}")
        return

    sql_files = sorted(migrations_dir.glob("*.sql"))

    with psycopg.connect(conninfo, autocommit=True, connect_timeout=5) as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                CREATE TABLE IF NOT EXISTS schema_migrations (
                    version VARCHAR(100) PRIMARY KEY,
                    applied_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
                );
                """
            )

        for sql_file in sql_files:
            version = sql_file.name

            # Enforce rule: Never execute new database migrations without approval
            if version >= "004" and not auto_apply_pending:
                logger.info(f"Skipping migration {version}: pending manual human approval.")
                continue

            with conn.cursor() as cur:
                cur.execute("SELECT 1 FROM schema_migrations WHERE version = %s", (version,))
                if cur.fetchone():
                    logger.debug(f"Migration {version} already applied")
                    continue

            logger.info(f"Applying migration: {version}")
            sql_content = sql_file.read_text(encoding="utf-8")
            with conn.cursor() as cur:
                cur.execute(sql_content)
                cur.execute("INSERT INTO schema_migrations (version) VALUES (%s)", (version,))
            logger.info(f"Migration {version} applied successfully")
