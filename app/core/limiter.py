"""
Shared rate-limiter instance.

Creating the limiter here (not in main.py) lets route modules import it
without creating a circular dependency through app.api → main.
"""
from slowapi import Limiter
from slowapi.util import get_remote_address


def _build_limiter() -> Limiter:
    from app.config import settings  # deferred to avoid import-time side-effects

    storage_uri = (
        f"redis://{settings.REDIS_HOST}:{settings.REDIS_PORT}"
        if settings.USE_REDIS
        else "memory://"
    )
    return Limiter(key_func=get_remote_address, storage_uri=storage_uri)


limiter: Limiter = _build_limiter()
