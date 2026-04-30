"""
Metrics endpoint authentication middleware.

Protects GET /metrics with HTTP Basic Auth when METRICS_USER and
METRICS_PASSWORD are set in settings.  If either is empty, the endpoint
is left open (useful for local development behind a firewall).
"""
import base64

from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware

from app.core.logging_config import get_logger

logger = get_logger(__name__)

_METRICS_PATH = "/metrics"


class MetricsAuthMiddleware(BaseHTTPMiddleware):
    """
    Intercepts requests to /metrics and enforces HTTP Basic Auth when
    METRICS_USER / METRICS_PASSWORD are configured.

    Deliberately imported lazily from settings inside dispatch() so the
    middleware can be registered before `settings` values are finalised
    in edge-case startup orderings.
    """

    async def dispatch(self, request: Request, call_next: callable) -> Response:
        if request.url.path != _METRICS_PATH:
            return await call_next(request)

        from app.config import settings  # local import avoids circular deps at module level

        # If no credentials are configured, allow the request through.
        if not settings.METRICS_USER or not settings.METRICS_PASSWORD:
            return await call_next(request)

        # Validate Basic Auth header.
        auth_header = request.headers.get("Authorization", "")
        if auth_header.startswith("Basic "):
            try:
                decoded = base64.b64decode(auth_header[6:]).decode("utf-8")
                username, _, password = decoded.partition(":")
                if username == settings.METRICS_USER and password == settings.METRICS_PASSWORD:
                    return await call_next(request)
            except Exception:
                pass  # fall through to 401

        logger.warning("Unauthorised /metrics access from %s", request.client.host if request.client else "unknown")
        return Response(
            status_code=401,
            headers={"WWW-Authenticate": 'Basic realm="metrics"'},
            content="Unauthorized",
        )
