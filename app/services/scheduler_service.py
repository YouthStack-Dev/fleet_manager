"""
Scheduler Service
=================
Wraps APScheduler's BackgroundScheduler to run periodic background jobs.

Current jobs
------------
- reminder_job  : fires every 5 minutes → run_reminder_job()

Lifecycle
---------
Call SchedulerService.start() inside the FastAPI lifespan startup block and
SchedulerService.stop() inside the shutdown block.  Both methods are
idempotent: calling start() on an already-running scheduler is a no-op,
calling stop() on an already-stopped scheduler is a no-op.

Thread safety
-------------
APScheduler's BackgroundScheduler manages its own thread pool.  Each job
invocation runs in a daemon thread, so the thread will be cleaned up
automatically on process exit even if shutdown() is not called explicitly.
We still call shutdown() explicitly to allow in-flight jobs to complete
(wait=True default).
"""

from __future__ import annotations

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.interval import IntervalTrigger

from app.core.logging_config import get_logger
from app.services.reminder_service import run_reminder_job
from app.services.stale_driver_service import run_stale_driver_check_job

logger = get_logger(__name__)

# How often the reminder job fires (seconds).
_REMINDER_INTERVAL_SECONDS: int = 5 * 60  # 5 minutes

# How often the stale-driver check fires (seconds).
_STALE_DRIVER_INTERVAL_SECONDS: int = 2 * 60  # 2 minutes


class SchedulerService:
    """
    Singleton-style wrapper around APScheduler's BackgroundScheduler.

    Usage::

        scheduler = SchedulerService()
        scheduler.start()   # called in FastAPI lifespan startup
        ...
        scheduler.stop()    # called in FastAPI lifespan shutdown
    """

    def __init__(self) -> None:
        self._scheduler = BackgroundScheduler(
            job_defaults={
                # Prevent job pile-up: if the previous run is still going
                # when the next trigger fires, skip the new trigger.
                "coalesce": True,
                # Only allow 1 concurrent execution of each job.
                "max_instances": 1,
                # Tolerate up to 60 seconds of misfire before dropping.
                "misfire_grace_time": 60,
            },
            timezone="UTC",
        )
        self._running = False

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def start(self) -> None:
        """
        Register all jobs and start the background scheduler thread.
        Idempotent — safe to call multiple times.
        """
        if self._running:
            logger.warning("[scheduler_service] start() called but scheduler is already running.")
            return

        self._register_jobs()
        self._scheduler.start()
        self._running = True
        logger.info(
            "[scheduler_service] Started. reminder_job interval=%ds, stale_driver_job interval=%ds",
            _REMINDER_INTERVAL_SECONDS,
            _STALE_DRIVER_INTERVAL_SECONDS,
        )

    def stop(self, wait: bool = True) -> None:
        """
        Gracefully shut down the scheduler.

        Args:
            wait: If True (default), block until all currently executing jobs
                  finish before returning.  Set to False for fast shutdown.
        Idempotent — safe to call even if the scheduler was never started.
        """
        if not self._running:
            logger.debug("[scheduler_service] stop() called but scheduler is not running — no-op.")
            return

        try:
            self._scheduler.shutdown(wait=wait)
            self._running = False
            logger.info("[scheduler_service] Stopped (wait=%s).", wait)
        except Exception as exc:
            logger.error("[scheduler_service] Error during shutdown: %s", exc, exc_info=True)

    # ------------------------------------------------------------------
    # Job registration
    # ------------------------------------------------------------------

    def _register_jobs(self) -> None:
        """Add all recurring jobs to the scheduler."""
        self._scheduler.add_job(
            func=run_reminder_job,
            trigger=IntervalTrigger(seconds=_REMINDER_INTERVAL_SECONDS, timezone="UTC"),
            id="reminder_job",
            name="Schedule Reminder Notifications",
            replace_existing=True,
        )
        logger.debug(
            "[scheduler_service] Registered reminder_job (every %ds).",
            _REMINDER_INTERVAL_SECONDS,
        )

        self._scheduler.add_job(
            func=run_stale_driver_check_job,
            trigger=IntervalTrigger(seconds=_STALE_DRIVER_INTERVAL_SECONDS, timezone="UTC"),
            id="stale_driver_job",
            name="Stale Driver Location Alerting",
            replace_existing=True,
        )
        logger.debug(
            "[scheduler_service] Registered stale_driver_job (every %ds).",
            _STALE_DRIVER_INTERVAL_SECONDS,
        )

    # ------------------------------------------------------------------
    # Introspection helpers (useful for health-check endpoints)
    # ------------------------------------------------------------------

    @property
    def is_running(self) -> bool:
        """Return True if the scheduler is currently active."""
        return self._running

    def get_jobs(self) -> list:
        """Return a list of all registered APScheduler Job objects."""
        return self._scheduler.get_jobs()
