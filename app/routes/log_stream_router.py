"""
Live log streaming endpoints.

Routes
------
GET /api/v1/logs/stream   — Server-Sent Events (SSE) live tail
GET /api/v1/logs/recent   — Snapshot of the last N buffered log entries

Both endpoints require the ``logs.read`` permission.

Query parameters
----------------
tail        : int   (0-1000, default 200)
    Lines to replay from buffer before going live. 0 = live only.

level       : str   (DEBUG | INFO | WARNING | ERROR | CRITICAL)
    Minimum log level.  Entries below this level are dropped.

path        : str   (partial match, e.g. "/bookings" or "/api/v1/drivers")
    Only stream request log entries whose ``http_path`` contains this
    substring (case-insensitive).  Non-request log lines are hidden when
    this filter is active.

status_code : int   (e.g. 404, 500)
    Only stream request log entries with this exact HTTP status code.
    Can be combined with ``path``.

Examples
--------
# All errors on the bookings API:
GET /api/v1/logs/stream?path=/bookings&status_code=500

# Live tail of WARNING+ logs (no path filter):
GET /api/v1/logs/stream?level=WARNING

# Last 50 404s across the whole API:
GET /api/v1/logs/recent?status_code=404&tail=50
"""

import asyncio
import json
import logging
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status

from fastapi.responses import StreamingResponse

from app.core.logging_config import get_logger, log_stream_handler
from common_utils.auth.token_validation import validate_bearer_token

logger = get_logger(__name__)

router = APIRouter(prefix="/logs", tags=["logs"])


async def _admin_only(user_data=Depends(validate_bearer_token(use_cache=True))):
    """Dependency: allow only admin users."""
    if user_data.get("user_type") != "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only admin users can access logs",
        )
    return user_data

# Map level name → numeric value for min-level filtering
_LEVEL_MAP: dict = {
    "DEBUG":    logging.DEBUG,
    "INFO":     logging.INFO,
    "WARNING":  logging.WARNING,
    "WARN":     logging.WARNING,
    "ERROR":    logging.ERROR,
    "CRITICAL": logging.CRITICAL,
}


def _passes_filters(
    entry: dict,
    min_level: int,
    levelno: int,
    path_filter: Optional[str],
    status_filter: Optional[int],
) -> bool:
    """
    Return True if this log entry should be emitted to the client.

    Rules
    -----
    * Level filter always applies.
    * path / status_code filters only match entries that carry the
      ``http_path`` / ``http_status`` extra fields (i.e. request-end logs).
      When either filter is active, entries that *lack* those fields are
      silently dropped — this keeps the stream focused on API traffic.
    """
    if levelno < min_level:
        return False

    has_request_fields = "http_path" in entry or "http_status" in entry

    # If either request filter is active, drop non-request log lines
    if (path_filter or status_filter is not None) and not has_request_fields:
        return False

    if path_filter and path_filter.lower() not in (entry.get("http_path") or "").lower():
        return False

    if status_filter is not None and entry.get("http_status") != status_filter:
        return False

    return True


# ──────────────────────────────────────────────────────────────
# SSE live stream
# ──────────────────────────────────────────────────────────────

@router.get("/stream", summary="Live log stream (SSE)")
async def stream_logs(
    tail:        int           = Query(200, ge=0, le=1000,
                                       description="Buffered lines to replay first (0 = live only)"),
    level:       Optional[str] = Query(None,
                                       description="Minimum log level: DEBUG / INFO / WARNING / ERROR / CRITICAL"),
    path:        Optional[str] = Query(None,
                                       description="Filter by API path substring, e.g. '/bookings'"),
    status_code: Optional[int] = Query(None,
                                       description="Filter by exact HTTP status code, e.g. 404 or 500"),
    _user = Depends(_admin_only),
):
    """
    Open an SSE connection that tails application logs in real time.

    Each ``data:`` payload is a single-line JSON object with at minimum:
    ``timestamp``, ``level``, ``logger``, ``message``.

    Request-end log entries additionally carry:
    ``http_method``, ``http_path``, ``http_status``, ``duration_ms``.

    A ``: keepalive`` comment is sent every 15 s to keep proxies from
    closing the idle connection.
    """
    min_level   = _LEVEL_MAP.get((level or "DEBUG").upper(), logging.DEBUG)
    path_filter = path.strip() if path else None

    async def event_generator():
        # 1. Replay recent buffer
        if tail > 0:
            for levelno, json_str in log_stream_handler.get_buffer()[-tail:]:
                try:
                    entry = json.loads(json_str)
                except ValueError:
                    continue
                if _passes_filters(entry, min_level, levelno, path_filter, status_code):
                    yield f"data: {json_str}\n\n"

        # 2. Live stream
        queue = log_stream_handler.subscribe()
        try:
            while True:
                try:
                    levelno, json_str = await asyncio.wait_for(
                        queue.get(), timeout=15.0
                    )
                    try:
                        entry = json.loads(json_str)
                    except ValueError:
                        continue
                    if _passes_filters(entry, min_level, levelno, path_filter, status_code):
                        yield f"data: {json_str}\n\n"
                except asyncio.TimeoutError:
                    yield ": keepalive\n\n"
        except asyncio.CancelledError:
            pass
        finally:
            log_stream_handler.unsubscribe(queue)

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control":     "no-cache",
            "X-Accel-Buffering": "no",
            "Connection":        "keep-alive",
        },
    )


# ──────────────────────────────────────────────────────────────
# Snapshot of recent logs
# ──────────────────────────────────────────────────────────────

@router.get("/recent", summary="Recent log snapshot")
async def recent_logs(
    tail:        int           = Query(100, ge=1, le=1000,
                                       description="Max number of entries to return"),
    level:       Optional[str] = Query(None,
                                       description="Minimum log level filter"),
    path:        Optional[str] = Query(None,
                                       description="Filter by API path substring, e.g. '/drivers'"),
    status_code: Optional[int] = Query(None,
                                       description="Filter by exact HTTP status code"),
    _user = Depends(_admin_only),
):
    """
    Return the last *tail* matching log entries from the in-memory buffer
    as a JSON array.  Useful for dashboards or one-shot scripts.
    """
    min_level   = _LEVEL_MAP.get((level or "DEBUG").upper(), logging.DEBUG)
    path_filter = path.strip() if path else None

    filtered = []
    for levelno, json_str in log_stream_handler.get_buffer():
        try:
            entry = json.loads(json_str)
        except ValueError:
            continue
        if _passes_filters(entry, min_level, levelno, path_filter, status_code):
            filtered.append(entry)

    entries = filtered[-tail:]

    return {
        "success": True,
        "total":   len(entries),
        "entries": entries,
    }
