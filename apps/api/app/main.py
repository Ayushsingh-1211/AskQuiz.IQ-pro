import threading
import uuid
from contextlib import asynccontextmanager
from typing import Any, AsyncGenerator, Dict, Optional
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from apps.api.app.config import get_settings
from apps.api.app.db.session import close_pool, run_migrations
from apps.api.app.errors import register_error_handlers
from apps.api.app.logging import get_logger, request_id_var, setup_logging
from apps.api.app.routes import api_router

setup_logging()
logger = get_logger("apps.api.main")

_worker_thread: Optional[threading.Thread] = None
_stop_worker_event: Optional[threading.Event] = None
_demo_seeding_lock = threading.Lock()
_demo_seeded = False


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    global _worker_thread, _stop_worker_event, _demo_seeded
    settings = get_settings()
    logger.info(f"Starting AskQuiz.IQ API on {settings.PUBLIC_API_URL}")

    # 1. Run database migrations safely
    try:
        run_migrations()
        logger.info("Database migrations complete")
    except Exception as exc:
        logger.error(f"Failed to apply database migrations at startup: {exc}")

    # 2. Seed default users (idempotent, only if missing)
    try:
        from infra.scripts.seed_users import seed_users
        seed_users()
        logger.info("Default user accounts verified/seeded")
    except Exception as exc:
        logger.warning(f"Could not verify/seed user accounts: {exc}")

    # 3. Seed demo video & chunks if configured (guarded against duplicate runs)
    if settings.AUTO_SEED_DEMO and not _demo_seeded:
        with _demo_seeding_lock:
            if not _demo_seeded:
                try:
                    from infra.scripts.seed_demo_data import seed_demo_data
                    seed_demo_data()
                    _demo_seeded = True
                    logger.info("Demo video and chunks verified/seeded")
                except Exception as exc:
                    logger.warning(f"Could not seed demo video data: {exc}")

    # 4. Start embedded worker thread if enabled (avoid duplicates if reloaded)
    if settings.EMBEDDED_WORKER:
        if _worker_thread is None or not _worker_thread.is_alive():
            try:
                from apps.worker.runner import start_embedded_worker
                _stop_worker_event = threading.Event()
                _worker_thread = start_embedded_worker(_stop_worker_event)
                logger.info("Embedded background worker thread active")
            except Exception as exc:
                logger.warning(f"Could not start embedded worker: {exc}")
        else:
            logger.info("Embedded worker thread is already running")
    else:
        logger.info("Embedded worker thread disabled (EMBEDDED_WORKER=false)")

    logger.info("AskQuiz.IQ API startup complete — ready to accept requests immediately")
    yield

    logger.info("Shutting down AskQuiz.IQ API...")
    if _stop_worker_event:
        _stop_worker_event.set()
    if _worker_thread and _worker_thread.is_alive():
        _worker_thread.join(timeout=3.0)
    close_pool()


def create_app() -> FastAPI:
    settings = get_settings()

    app = FastAPI(
        title="AskQuiz.IQ API",
        version="0.1.0",
        description="Pause & Ask Learning Assistant API",
        lifespan=lifespan,
    )

    # Root health endpoints for fast cloud platform port/health detection
    @app.get("/health", tags=["health"])
    @app.get("/", tags=["health"])
    def root_health() -> Dict[str, Any]:
        return {"status": "ok"}

    # Middleware: Request ID injection
    @app.middleware("http")
    async def request_id_middleware(request: Request, call_next):
        req_id = request.headers.get("X-Request-ID") or str(uuid.uuid4())
        token = request_id_var.set(req_id)
        try:
            response = await call_next(request)
            response.headers["X-Request-ID"] = req_id
            return response
        finally:
            request_id_var.reset(token)

    # CORS configuration
    origins = settings.allowed_origins_list
    default_dev_origins = ["http://localhost:5173", "http://localhost:3000", "http://127.0.0.1:5173"]
    allowed_origins = list(dict.fromkeys(origins + default_dev_origins))

    app.add_middleware(
        CORSMiddleware,
        allow_origins=allowed_origins,
        allow_origin_regex=r"^https://([a-zA-Z0-9-]+\.)*(vercel\.app|trycloudflare\.com|onrender\.com)(:\d+)?$|^http://(localhost|127\.0\.0\.1)(:\d+)?$",
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Register error handlers
    register_error_handlers(app)

    # Mount API routes
    app.include_router(api_router)
    from apps.api.app.routes.videos import router as videos_router
    app.include_router(videos_router)
    from apps.api.app.routes.ask import router as ask_router
    app.include_router(ask_router)
    from apps.api.app.routes.discovery import router as discovery_router
    app.include_router(discovery_router)

    return app


app = create_app()
