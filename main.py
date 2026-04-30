# ── stdlib ────────────────────────────────────────────────────
import asyncio
import os
import sys
from contextlib import asynccontextmanager

# ── Alembic migrations ─────────────────────────────────────────
from alembic.config import Config as AlembicConfig
from alembic import command as alembic_command

# Ensure project root is on sys.path before any local imports
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# ── Web framework ──────────────────────────────────────────────
import uvicorn
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

# ── App internals ──────────────────────────────────────────────
from app.api import api_router
from app.config import settings
from app.core.logging_config import get_logger, setup_logging
from app.middleware import ErrorTrackingMiddleware, MetricsAuthMiddleware, RequestTrackingMiddleware
from app.middleware.url_validation import URLValidationMiddleware

# ── Prometheus ─────────────────────────────────────────────────
from prometheus_fastapi_instrumentator import Instrumentator

# ── Rate limiting ──────────────────────────────────────────────
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from app.core.limiter import limiter


# ──────────────────────────────────────────────────────────────
# Logging — configure before anything else runs
# ──────────────────────────────────────────────────────────────
setup_logging(force_configure=True)
logger = get_logger(__name__)
logger.info(
    "Fleet Manager starting — app=%s version=%s env=%s debug=%s",
    settings.APP_NAME,
    settings.APP_VERSION,
    settings.ENV,
    settings.DEBUG,
)


# ──────────────────────────────────────────────────────────────
# Auto-migration on startup
# ──────────────────────────────────────────────────────────────
def run_migrations() -> None:
    """
    Apply all pending Alembic migrations before the app accepts traffic.
    Crashes the process on failure so the container restarts instead of
    serving requests against a stale schema.
    """
    import sys, traceback as tb
    try:
        logger.info("⏳ Running database migrations…")
        cfg = AlembicConfig("alembic.ini")
        alembic_command.upgrade(cfg, "head")
        logger.info("✅ Migrations are up to date")
    except Exception as exc:
        # Print directly to stderr with flush — ensures the error is always
        # visible in `docker logs` even if the custom logger buffer is lost
        # on crash.
        print("\n" + "="*60, file=sys.stderr, flush=True)
        print(f"❌ MIGRATION FAILED: {exc}", file=sys.stderr, flush=True)
        tb.print_exc(file=sys.stderr)
        sys.stderr.flush()
        print("="*60 + "\n", file=sys.stderr, flush=True)
        logger.critical("❌ Migration failed — aborting startup: %s", exc)
        raise  # let the container crash & restart


# ──────────────────────────────────────────────────────────────
# Lifespan — startup & shutdown
# ──────────────────────────────────────────────────────────────
@asynccontextmanager
async def lifespan(app: FastAPI):
    """Handle application startup and graceful shutdown."""
    # Re-initialise logging HERE — uvicorn resets Python's logging config
    # during its own startup (via dictConfig), wiping our StreamHandler.
    # Calling setup_logging() inside lifespan guarantees our handler is
    # restored *after* uvicorn has finished its own log setup, so every
    # logger.info/debug/warning call at request-time actually reaches stdout.
    setup_logging(force_configure=True)
    logger.info("Application starting up")
    if settings.RUN_MIGRATIONS_ON_STARTUP:
        run_migrations()
        # Alembic's fileConfig() call inside migrations resets Python's logging config
        # (disable_existing_loggers=True by default), wiping all our handlers and
        # disabling every pre-existing logger.  Restore our config immediately after.
        setup_logging(force_configure=True)
        logger.info("Logging restored after migrations")
    else:
        logger.info("RUN_MIGRATIONS_ON_STARTUP=false — skipping inline migration (init container handles this)")

    # Database monitoring disabled - uncomment to re-enable
    # from app.database.session import engine
    # from app.utils.database_monitor import db_monitor, monitor_database_periodically
    # db_monitor.setup_monitoring(engine)
    # logger.info("📊 Database monitoring enabled")
    # asyncio.create_task(monitor_database_periodically())
    # logger.info("🔄 Background monitoring task started")

    yield  # ← application runs here

    logger.info("🛑 Application shutting down…")


# ──────────────────────────────────────────────────────────────
# Application instance
# ──────────────────────────────────────────────────────────────
app = FastAPI(
    title="Fleet Manager API",
    description="API for Fleet Management System",
    version="1.0.0",
    lifespan=lifespan,
)

# ──────────────────────────────────────────────────────────────
# Rate limiter — backed by Redis when available, otherwise in-memory
# ──────────────────────────────────────────────────────────────
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)
logger.info("✅ Rate limiter initialised")


# ──────────────────────────────────────────────────────────────
# Prometheus  (must be registered before middleware)
# ──────────────────────────────────────────────────────────────
Instrumentator(
    should_group_status_codes=True,
    should_ignore_untemplated=True,
    should_respect_env_var=False,
    should_instrument_requests_inprogress=True,
    excluded_handlers=["^/metrics$"],
    inprogress_name="http_requests_inprogress",
    inprogress_labels=True,
).instrument(app).expose(app, endpoint="/metrics", include_in_schema=False)

logger.info("✅ Prometheus metrics enabled at /metrics")


# ──────────────────────────────────────────────────────────────
# Middleware  (registered in reverse execution order)
#   CORS            → executes 1st  (outermost)
#   ErrorTracking   → executes 2nd
#   RequestTracking → executes 3rd
#   URLValidation   → executes 4th  (innermost, first to see a request)
# ──────────────────────────────────────────────────────────────
app.add_middleware(URLValidationMiddleware)
app.add_middleware(RequestTrackingMiddleware)
app.add_middleware(ErrorTrackingMiddleware)
app.add_middleware(MetricsAuthMiddleware)   # outermost: guards /metrics before any inner handler
logger.info("✅ Monitoring middleware registered (URL → Request → Error → MetricsAuth)")

_cors_origins: list = os.getenv("CORS_ORIGINS", "*").split(",")
if _cors_origins == ["*"]:
    _cors_origins = [
        "*",
        "http://localhost:3000",
        "http://localhost:5173",
        "https://test.euronext.gocab.tech",
        "https://euronext.gocab.tech",
        "https://api.gocab.tech",
    ]

app.add_middleware(
    CORSMiddleware,
    allow_origins=_cors_origins,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE", "PATCH", "OPTIONS"],
    allow_headers=["*"],
    expose_headers=["*"],
    max_age=3600,
)
logger.info("✅ CORS enabled for origins: %s", _cors_origins)


# ──────────────────────────────────────────────────────────────
# API Router — all routes registered in app/api.py
# ──────────────────────────────────────────────────────────────
app.include_router(api_router)


if __name__ == "__main__":
    # log_config=None prevents uvicorn from calling logging.config.dictConfig(),
    # which would otherwise wipe our StreamHandler and disable all existing loggers
    # after the lifespan startup hook completes.
    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=8000,
        log_config=None,
    )
