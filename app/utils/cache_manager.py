"""
Redis caching utilities for Fleet Manager
Provides caching decorators and helpers for common operations
"""
import json
import pickle
from typing import Any, Optional, Callable, TypeVar, Union
from functools import wraps
import redis
from app.config import settings

# Type hints
T = TypeVar('T')

class CacheManager:
    """Redis cache manager with TTL and serialization support"""

    def __init__(self):
        self.redis_client = redis.Redis(
            host=settings.REDIS_HOST,
            port=settings.REDIS_PORT,
            db=settings.REDIS_DB,
            password=settings.REDIS_PASSWORD or None,
            decode_responses=True,  # For string data
            socket_connect_timeout=5,
            socket_timeout=5,
            retry_on_timeout=True
        )

    def get(self, key: str) -> Optional[Any]:
        """Get value from cache"""
        try:
            data = self.redis_client.get(key)
            return json.loads(data) if data else None
        except Exception as e:
            print(f"Cache get error: {e}")
            return None

    def set(self, key: str, value: Any, ttl_seconds: int = 300) -> bool:
        """Set value in cache with TTL"""
        try:
            return self.redis_client.setex(key, ttl_seconds, json.dumps(value))
        except Exception as e:
            print(f"Cache set error: {e}")
            return False

    def delete(self, key: str) -> bool:
        """Delete key from cache"""
        try:
            return bool(self.redis_client.delete(key))
        except Exception as e:
            print(f"Cache delete error: {e}")
            return False

    def exists(self, key: str) -> bool:
        """Check if key exists"""
        try:
            return bool(self.redis_client.exists(key))
        except Exception as e:
            print(f"Cache exists error: {e}")
            return False

# Global cache instance
cache = CacheManager()

def cached(ttl_seconds: int = 300, key_prefix: str = ""):
    """
    Decorator to cache function results

    @cached(ttl_seconds=600, key_prefix="driver_locations")
    def get_driver_locations(tenant_id: str, vendor_id: int):
        return fetch_from_db(tenant_id, vendor_id)
    """
    def decorator(func: Callable[..., T]) -> Callable[..., T]:
        @wraps(func)
        def wrapper(*args, **kwargs) -> T:
            # Generate cache key from function name and arguments
            key_parts = [key_prefix or func.__name__]
            key_parts.extend(str(arg) for arg in args)
            key_parts.extend(f"{k}:{v}" for k, v in kwargs.items())
            cache_key = ":".join(key_parts)

            # Try to get from cache first
            cached_result = cache.get(cache_key)
            if cached_result is not None:
                return cached_result

            # Execute function and cache result
            result = func(*args, **kwargs)
            cache.set(cache_key, result, ttl_seconds)
            return result

        return wrapper
    return decorator

# Specific caching functions for common operations

def cache_driver_locations(tenant_id: str, vendor_id: int, locations: list, ttl: int = 30):
    """Cache driver locations for 30 seconds (real-time data)"""
    key = f"driver_locations:{tenant_id}:{vendor_id}"
    return cache.set(key, locations, ttl)

def get_cached_driver_locations(tenant_id: str, vendor_id: int) -> Optional[list]:
    """Get cached driver locations"""
    key = f"driver_locations:{tenant_id}:{vendor_id}"
    return cache.get(key)

def cache_booking_stats(tenant_id: str, date: str, stats: dict, ttl: int = 300):
    """Cache booking statistics for 5 minutes"""
    key = f"booking_stats:{tenant_id}:{date}"
    return cache.set(key, stats, ttl)

def get_cached_booking_stats(tenant_id: str, date: str) -> Optional[dict]:
    """Get cached booking statistics"""
    key = f"booking_stats:{tenant_id}:{date}"
    return cache.get(key)

def invalidate_driver_locations(tenant_id: str, vendor_id: int):
    """Invalidate driver location cache when location updates"""
    key = f"driver_locations:{tenant_id}:{vendor_id}"
    return cache.delete(key)

def invalidate_booking_stats(tenant_id: str, date: str):
    """Invalidate booking stats cache when bookings change"""
    key = f"booking_stats:{tenant_id}:{date}"
    return cache.delete(key)

# Session management
def set_user_session(session_id: str, user_data: dict, ttl: int = 3600):
    """Store user session data (1 hour default)"""
    key = f"session:{session_id}"
    return cache.set(key, user_data, ttl)

def get_user_session(session_id: str) -> Optional[dict]:
    """Get user session data"""
    key = f"session:{session_id}"
    return cache.get(key)

def delete_user_session(session_id: str):
    """Delete user session"""
    key = f"session:{session_id}"
    return cache.delete(key)

# OTP storage (temporary, short TTL)
def set_otp(phone: str, otp: str, ttl: int = 300):
    """Store OTP for phone number (5 minutes)"""
    key = f"otp:{phone}"
    return cache.set(key, otp, ttl)

def get_otp(phone: str) -> Optional[str]:
    """Get OTP for phone number"""
    key = f"otp:{phone}"
    return cache.get(key)

def verify_otp(phone: str, otp: str) -> bool:
    """Verify OTP and delete it (one-time use)"""
    stored_otp = get_otp(phone)
    if stored_otp and stored_otp == otp:
        cache.delete(f"otp:{phone}")
        return True
    return False

def get_cache_stats() -> dict:
    """Get Redis cache statistics"""
    try:
        info = cache.redis_client.info()
        return {
            "status": "healthy",
            "connected_clients": info.get("connected_clients", 0),
            "used_memory": info.get("used_memory_human", "0B"),
            "total_connections_received": info.get("total_connections_received", 0),
            "total_commands_processed": info.get("total_commands_processed", 0),
            "uptime_in_seconds": info.get("uptime_in_seconds", 0),
            "keyspace_hits": info.get("keyspace_hits", 0),
            "keyspace_misses": info.get("keyspace_misses", 0),
            "hit_rate": calculate_hit_rate(info.get("keyspace_hits", 0), info.get("keyspace_misses", 0))
        }
    except Exception as e:
        return {
            "status": "unhealthy",
            "error": str(e)
        }

def calculate_hit_rate(hits: int, misses: int) -> float:
    """Calculate cache hit rate percentage"""
    total = hits + misses
    return (hits / total * 100) if total > 0 else 0.0