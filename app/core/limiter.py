"""
Shared rate-limiter instance.

Creating the limiter here (not in main.py) lets route modules import it
without creating a circular dependency through app.api → main.
"""
from slowapi import Limiter
from slowapi.util import get_remote_address
from urllib.parse import quote


def _build_redis_storage_uri(settings) -> str:
    host = settings.REDIS_HOST
    port = settings.REDIS_PORT
    db = settings.REDIS_DB
    password = (settings.REDIS_PASSWORD or "").strip()

    if password:
        encoded_password = quote(password, safe="")
        return f"redis://:{encoded_password}@{host}:{port}/{db}"

    return f"redis://{host}:{port}/{db}"


def _build_limiter() -> Limiter:
    from app.config import settings  # deferred to avoid import-time side-effects

    storage_uri = _build_redis_storage_uri(settings) if settings.USE_REDIS else "memory://"
    return Limiter(key_func=get_remote_address, storage_uri=storage_uri)


limiter: Limiter = _build_limiter()
