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
from app.middleware import ErrorTrackingMiddleware, RequestTrackingMiddleware
from app.middleware.url_validation import URLValidationMiddleware

# ── Prometheus ─────────────────────────────────────────────────
from prometheus_fastapi_instrumentator import Instrumentator


# ──────────────────────────────────────────────────────────────
# Logging — configure before anything else runs
# ──────────────────────────────────────────────────────────────
setup_logging(force_configure=True)
logger = get_logger(__name__)
logger.info("🚀 Fleet Manager starting — env: %s", settings)


# ──────────────────────────────────────────────────────────────
# Auto-migration on startup
# ──────────────────────────────────────────────────────────────
def run_migrations() -> None:
    """
    Apply all pending Alembic migrations before the app accepts traffic.
    Crashes the process on failure so the container restarts instead of
    serving requests against a stale schema.
    """
    try:
        logger.info("⏳ Running database migrations…")
        cfg = AlembicConfig("alembic.ini")
        alembic_command.upgrade(cfg, "head")
        logger.info("✅ Migrations are up to date")
    except Exception as exc:
        logger.critical("❌ Migration failed — aborting startup: %s", exc)
        raise  # let the container crash & restart


# ──────────────────────────────────────────────────────────────
# Lifespan — startup & shutdown
# ──────────────────────────────────────────────────────────────
@asynccontextmanager
async def lifespan(app: FastAPI):
    """Handle application startup and graceful shutdown."""
    logger.info("🌟 Application starting up…")
    run_migrations()

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
logger.info("✅ Monitoring middleware registered (URL → Request → Error)")

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
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
