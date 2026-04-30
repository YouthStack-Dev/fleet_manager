"""
Enhanced Error Tracking Middleware
Captures all errors, request details, and stores them for debugging
"""
import asyncio
import traceback
import time
import json
from typing import Dict, List, Optional
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
from fastapi import Request, Response, HTTPException as FastAPIHTTPException
from starlette.middleware.base import BaseHTTPMiddleware
from app.core.logging_config import get_logger
from app.utils.cache_manager import cache

logger = get_logger(__name__)
IST = ZoneInfo("Asia/Kolkata")

# Redis sorted-set key — score = Unix timestamp, member = JSON-encoded error
_ERRORS_KEY = "fleet:error_tracker"
_MAX_ERRORS = 1000  # keep the most recent N entries


class ErrorTracker:
    """
    Centralized error tracking backed by Redis sorted set.

    Using a sorted set (ZADD score=timestamp, member=json) means:
    - Errors survive process restarts.
    - Multiple gunicorn/uvicorn workers share the same store.
    - ZREMRANGEBYRANK keeps the set bounded at MAX_ERRORS automatically.
    - ZREVRANGE returns the N most-recent entries in O(log n + k).
    """

    # ------------------------------------------------------------------
    # Write path
    # ------------------------------------------------------------------
    def log_error(
        self,
        error: Exception,
        request: Request,
        response_time: float,
        user_info: Optional[Dict] = None,
    ) -> None:
        """Log error with full context, persisting to Redis sorted set."""
        ts = time.time()
        error_entry = {
            "timestamp": datetime.now(IST).isoformat(),
            "error_type": type(error).__name__,
            "error_message": str(error),
            "traceback": traceback.format_exc(),
            "request": {
                "method": request.method,
                "url": str(request.url),
                "path": request.url.path,
                "query_params": dict(request.query_params),
                "headers": {
                    key: value for key, value in request.headers.items()
                    if key.lower() not in {"authorization", "cookie", "x-api-key"}
                },
                "client_host": request.client.host if request.client else None,
            },
            "response_time": response_time,
            "user_info": user_info or {},
        }

        # Persist in Redis sorted set (score = Unix timestamp).
        try:
            rc = cache.redis_client
            rc.zadd(_ERRORS_KEY, {json.dumps(error_entry, ensure_ascii=False): ts})
            # Trim to MAX_ERRORS most-recent entries (index 0 is oldest).
            rc.zremrangebyrank(_ERRORS_KEY, 0, -(_MAX_ERRORS + 1))
        except Exception as redis_exc:
            # Never let Redis failure hide the original error.
            logger.warning("ErrorTracker: Redis write failed: %s", redis_exc)

        logger.error(
            "ERROR TRACKED: %s - %s\nPath: %s\nMethod: %s\nUser: %s\nTraceback:\n%s",
            error_entry["error_type"],
            error_entry["error_message"],
            request.url.path,
            request.method,
            user_info,
            traceback.format_exc(),
            extra={"error_entry": error_entry},
        )

    # ------------------------------------------------------------------
    # Read path
    # ------------------------------------------------------------------
    def get_recent_errors(self, limit: int = 50) -> List[Dict]:
        """Return up to `limit` most-recent errors (newest first)."""
        try:
            raw = cache.redis_client.zrevrange(_ERRORS_KEY, 0, limit - 1)
            return [json.loads(r) for r in raw]
        except Exception as exc:
            logger.warning("ErrorTracker: Redis read failed: %s", exc)
            return []

    def get_errors_by_type(self, error_type: str) -> List[Dict]:
        """Filter recent errors by error type (reads all, filters in Python)."""
        return [e for e in self.get_recent_errors(limit=_MAX_ERRORS) if e.get("error_type") == error_type]

    def get_errors_by_path(self, path: str) -> List[Dict]:
        """Filter recent errors by request path."""
        return [e for e in self.get_recent_errors(limit=_MAX_ERRORS) if e.get("request", {}).get("path") == path]

    def get_error_stats(self) -> Dict:
        """Aggregate statistics over the stored errors."""
        errors = self.get_recent_errors(limit=_MAX_ERRORS)
        if not errors:
            return {
                "total_errors": 0,
                "error_types": {},
                "error_paths": {},
                "last_error": None,
            }

        error_types: Dict[str, int] = {}
        error_paths: Dict[str, int] = {}
        for error in errors:
            t = error.get("error_type", "Unknown")
            p = error.get("request", {}).get("path", "unknown")
            error_types[t] = error_types.get(t, 0) + 1
            error_paths[p] = error_paths.get(p, 0) + 1

        return {
            "total_errors": len(errors),
            "error_types": error_types,
            "error_paths": error_paths,
            "last_error": errors[0] if errors else None,
            "timestamp": datetime.now(IST).isoformat(),
        }


# Global error tracker instance
error_tracker = ErrorTracker()


class ErrorTrackingMiddleware(BaseHTTPMiddleware):
    """Middleware to track all errors and requests"""

    async def dispatch(self, request: Request, call_next):
        start_time = time.time()

        try:
            response = await call_next(request)
            return response

        except Exception as e:
            # Calculate response time
            response_time = time.time() - start_time

            # Try to extract user info from request state
            user_info = {}
            if hasattr(request.state, "user"):
                user_info = {
                    "user_id": getattr(request.state.user, "user_id", None),
                    "user_type": getattr(request.state.user, "user_type", None),
                    "tenant_id": getattr(request.state.user, "tenant_id", None),
                }

            # Log error with full context
            error_tracker.log_error(e, request, response_time, user_info)

            # ── Auto-report unhandled exceptions to GitHub ──────────────
            # HTTPExceptions are intentional (4xx / known 5xx) — skip them.
            if not isinstance(e, FastAPIHTTPException):
                try:
                    from app.utils.github_issue_reporter import report_error_to_github
                    asyncio.create_task(
                        report_error_to_github(
                            title=f"[Auto] {type(e).__name__}: {str(e)[:120]}",
                            traceback_str=traceback.format_exc(),
                            error_type=type(e).__name__,
                            path=request.url.path,
                            method=request.method,
                            extra={"user": str(user_info) if user_info else "unknown"},
                        )
                    )
                except Exception:
                    pass  # Never let the reporter crash the request cycle

            # Re-raise the exception to be handled by FastAPI's exception handlers
            raise
