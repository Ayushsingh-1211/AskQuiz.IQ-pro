"""
Manual Migration Script for 004_web_mode.sql
Run this script to apply migration 004 after human approval:
    python infra/scripts/apply_migration_004.py

Guarded execution:
- Verifies target database (127.0.0.1:5434 / askquiz_pro) to prevent accidental execution against wrong/prod targets.
- Uses an atomic transaction: DDL execution and schema_migrations recording succeed or roll back together.
- Safely closes database connections.
- Never executes automatically.
"""
import argparse
import sys
import urllib.parse
from pathlib import Path

repo_root = Path(__file__).resolve().parent.parent.parent
if str(repo_root) not in sys.path:
    sys.path.insert(0, str(repo_root))

import psycopg
from apps.api.app.db.session import get_effective_database_url
from apps.api.app.logging import get_logger

logger = get_logger("infra.migrate_004")

DEV_TARGET_HOSTS = {"127.0.0.1", "localhost"}
DEV_TARGET_PORT = 5434
DEV_TARGET_DBNAME = "askquiz_pro"


def verify_target_database(conninfo: str, allow_custom_target: bool = False) -> None:
    """
    Guards against targeting unintended or production databases.
    Only allows 127.0.0.1:5434/askquiz_pro unless allow_custom_target is explicitly True.
    """
    try:
        parsed = urllib.parse.urlparse(conninfo)
        host = parsed.hostname or "127.0.0.1"
        port = parsed.port or 5432
        dbname = parsed.path.lstrip("/") or "pause"
    except Exception as exc:
        raise RuntimeError(f"Unable to parse database connection URL: {exc}") from exc

    is_dev_target = (host in DEV_TARGET_HOSTS and port == DEV_TARGET_PORT and dbname == DEV_TARGET_DBNAME)

    if not is_dev_target and not allow_custom_target:
        raise RuntimeError(
            f"Target database verification failed: host='{host}', port={port}, dbname='{dbname}'. "
            f"Expected development target: host=127.0.0.1, port={DEV_TARGET_PORT}, dbname='{DEV_TARGET_DBNAME}'. "
            "To target this database explicitly, pass --allow-custom-target or allow_custom_target=True."
        )


def apply_migration_004(allow_custom_target: bool = False) -> bool:
    """
    Applies migration 004 in a safe atomic transaction.
    Returns True if migration was applied, False if already applied.
    """
    migration_file = repo_root / "apps" / "api" / "app" / "db" / "migrations" / "004_web_mode.sql"
    if not migration_file.exists():
        logger.error(f"Migration file not found: {migration_file}")
        raise FileNotFoundError(f"Migration file not found: {migration_file}")

    conninfo = get_effective_database_url()
    verify_target_database(conninfo, allow_custom_target=allow_custom_target)

    version = migration_file.name

    # Safe connection handling: autocommit=False with explicit transaction block
    with psycopg.connect(conninfo, autocommit=False, connect_timeout=5) as conn:
        try:
            with conn.transaction():
                with conn.cursor() as cur:
                    # 1. Ensure schema_migrations exists
                    cur.execute(
                        """
                        CREATE TABLE IF NOT EXISTS schema_migrations (
                            version VARCHAR(100) PRIMARY KEY,
                            applied_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
                        );
                        """
                    )

                    # 2. Check if already applied (with lock to avoid duplicate records)
                    cur.execute(
                        "SELECT 1 FROM schema_migrations WHERE version = %s FOR UPDATE",
                        (version,),
                    )
                    if cur.fetchone():
                        logger.info(f"Migration {version} has already been applied. Nothing to do.")
                        return False

                    # 3. Read and execute migration DDL
                    sql_content = migration_file.read_text(encoding="utf-8")
                    logger.info(f"Applying approved migration: {version}")
                    cur.execute(sql_content)

                    # 4. Record migration version in the SAME atomic transaction
                    cur.execute(
                        "INSERT INTO schema_migrations (version) VALUES (%s)",
                        (version,),
                    )

                # conn.transaction() commits here atomically
                logger.info(f"Migration {version} applied and recorded successfully!")
                return True
        except Exception as exc:
            # conn.transaction() rolls back here atomically
            logger.error(f"Migration {version} failed and was rolled back: {exc}")
            raise


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Apply migration 004 with transaction safety.")
    parser.add_argument(
        "--allow-custom-target",
        action="store_true",
        help="Allow running against a non-dev database target.",
    )
    args = parser.parse_args()

    print("Executing Migration 004 under owner instruction...")
    try:
        success = apply_migration_004(allow_custom_target=args.allow_custom_target)
        if success:
            print("Migration 004 applied successfully.")
        else:
            print("Migration 004 was already applied.")
    except Exception as e:
        print(f"Migration aborted: {e}")
        sys.exit(1)
