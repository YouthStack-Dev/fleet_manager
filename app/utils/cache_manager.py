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
# ============================================================
# Static/Slow-Changing Data Caching (Long TTL)
# ============================================================

def _build_cache_key(entity_type: str, *identifiers) -> str:
    """
    Build a cache key from entity type and identifiers
    
    Example:
        _build_cache_key("tenant", "abc123") -> "tenant:abc123"
        _build_cache_key("shift", "abc123", 5) -> "shift:abc123:5"
    """
    parts = [entity_type] + [str(identifier) for identifier in identifiers]
    return ":".join(parts)

def _cache_entity(entity_type: str, data: dict, ttl: int, *identifiers) -> bool:
    """Generic cache setter for any entity"""
    key = _build_cache_key(entity_type, *identifiers)
    return cache.set(key, data, ttl)

def _get_cached_entity(entity_type: str, *identifiers) -> Optional[dict]:
    """Generic cache getter for any entity"""
    key = _build_cache_key(entity_type, *identifiers)
    return cache.get(key)

def _invalidate_entity(entity_type: str, *identifiers) -> bool:
    """Generic cache invalidation for any entity"""
    key = _build_cache_key(entity_type, *identifiers)
    return cache.delete(key)

# Tenant caching
def cache_tenant(tenant_id: str, tenant_data: dict, ttl: int = 3600):
    """Cache tenant data for 1 hour (rarely changes)"""
    return _cache_entity("tenant", tenant_data, ttl, tenant_id)

def get_cached_tenant(tenant_id: str) -> Optional[dict]:
    """Get cached tenant data"""
    return _get_cached_entity("tenant", tenant_id)

def invalidate_tenant(tenant_id: str):
    """Invalidate tenant cache when data changes"""
    return _invalidate_entity("tenant", tenant_id)

# Shift caching
def cache_shift(shift_id: int, tenant_id: str, shift_data: dict, ttl: int = 3600):
    """Cache shift configuration for 1 hour (rarely changes)"""
    return _cache_entity("shift", shift_data, ttl, tenant_id, shift_id)

def get_cached_shift(shift_id: int, tenant_id: str) -> Optional[dict]:
    """Get cached shift configuration"""
    return _get_cached_entity("shift", tenant_id, shift_id)

def invalidate_shift(shift_id: int, tenant_id: str):
    """Invalidate shift cache when configuration changes"""
    return _invalidate_entity("shift", tenant_id, shift_id)

# Cutoff caching
def cache_cutoff(tenant_id: str, cutoff_data: dict, ttl: int = 3600):
    """Cache cutoff configuration for 1 hour (rarely changes)"""
    return _cache_entity("cutoff", cutoff_data, ttl, tenant_id)

def get_cached_cutoff(tenant_id: str) -> Optional[dict]:
    """Get cached cutoff configuration"""
    return _get_cached_entity("cutoff", tenant_id)

def invalidate_cutoff(tenant_id: str):
    """Invalidate cutoff cache when configuration changes"""
    return _invalidate_entity("cutoff", tenant_id)

# Weekoff caching
def cache_weekoff(employee_id: int, weekoff_data: dict, ttl: int = 3600):
    """Cache weekoff configuration for 1 hour (rarely changes)"""
    return _cache_entity("weekoff", weekoff_data, ttl, employee_id)

def get_cached_weekoff(employee_id: int) -> Optional[dict]:
    """Get cached weekoff configuration"""
    return _get_cached_entity("weekoff", employee_id)

def invalidate_weekoff(employee_id: int):
    """Invalidate weekoff cache when configuration changes"""
    return _invalidate_entity("weekoff", employee_id)

# ============================================================
# TenantConfig Helper Functions (DRY)
# ============================================================

def serialize_tenant_config_for_cache(config_obj) -> dict:
    """
    Convert TenantConfig object to cache-ready dictionary.
    Handles time and datetime serialization for JSON compatibility.
    """
    from app.core.logging_config import get_logger
    logger = get_logger(__name__)
    
    try:
        config_dict = {column.name: getattr(config_obj, column.name) for column in config_obj.__table__.columns}
        tenant_id = config_dict.get('tenant_id', 'unknown')
        
        # Convert time objects to strings
        if config_dict.get('escort_required_start_time'):
            config_dict['escort_required_start_time'] = str(config_dict['escort_required_start_time'])
        if config_dict.get('escort_required_end_time'):
            config_dict['escort_required_end_time'] = str(config_dict['escort_required_end_time'])
        
        # Convert datetime objects to ISO format strings
        if config_dict.get('created_at'):
            config_dict['created_at'] = config_dict['created_at'].isoformat()
        if config_dict.get('updated_at'):
            config_dict['updated_at'] = config_dict['updated_at'].isoformat()
        
        logger.debug(f"✅ Serialized tenant_config for tenant {tenant_id}")
        return config_dict
    except Exception as e:
        logger.error(f"❌ Failed to serialize tenant_config: {str(e)}")
        raise

def deserialize_tenant_config_from_cache(cached_dict: dict):
    """
    Convert cached dictionary back to TenantConfig object.
    Handles time string parsing back to time objects.
    """
    from app.models.tenant_config import TenantConfig
    from datetime import time as datetime_time
    from app.core.logging_config import get_logger
    logger = get_logger(__name__)
    
    try:
        tenant_id = cached_dict.get('tenant_id', 'unknown')
        
        # Parse time strings back to time objects
        if cached_dict.get('escort_required_start_time') and isinstance(cached_dict['escort_required_start_time'], str):
            time_parts = cached_dict['escort_required_start_time'].split(':')
            cached_dict['escort_required_start_time'] = datetime_time(
                int(time_parts[0]), 
                int(time_parts[1]), 
                int(time_parts[2]) if len(time_parts) > 2 else 0
            )
        
        if cached_dict.get('escort_required_end_time') and isinstance(cached_dict['escort_required_end_time'], str):
            time_parts = cached_dict['escort_required_end_time'].split(':')
            cached_dict['escort_required_end_time'] = datetime_time(
                int(time_parts[0]), 
                int(time_parts[1]), 
                int(time_parts[2]) if len(time_parts) > 2 else 0
            )
        
        logger.debug(f"✅ Deserialized tenant_config for tenant {tenant_id}")
        return TenantConfig(**cached_dict)
    except Exception as e:
        logger.error(f"❌ Failed to deserialize tenant_config: {str(e)}")
        raise

def get_tenant_config_with_cache(db, tenant_id: str):
    """
    Get tenant_config with automatic caching.
    Tries cache first, falls back to DB, and auto-caches on miss.
    
    Returns: TenantConfig object or None
    """
    from app.core.logging_config import get_logger
    logger = get_logger(__name__)
    
    try:
        # Try cache first
        logger.info(f"🔍 [CACHE CHECK] tenant_config for tenant_id={tenant_id}")
        cached_config = get_cached_tenant_config(tenant_id)
        
        if cached_config:
            logger.info(f"✅ [CACHE HIT] tenant_config found in Redis | tenant_id={tenant_id}")
            try:
                config = deserialize_tenant_config_from_cache(cached_config)
                logger.info(f"✅ [CACHE HIT COMPLETE] Successfully deserialized | tenant_id={tenant_id}")
                return config
            except Exception as deser_error:
                logger.error(f"❌ [CACHE HIT ERROR] Deserialization failed: {str(deser_error)} | tenant_id={tenant_id}")
                raise
        
        # Cache miss - query database
        logger.info(f"⚠️ [CACHE MISS] tenant_config not in Redis | tenant_id={tenant_id}")
        logger.info(f"📊 [CACHE MISS - STEP 1] Querying database... | tenant_id={tenant_id}")
        from app.models.tenant_config import TenantConfig
        config = db.query(TenantConfig).filter(TenantConfig.tenant_id == tenant_id).first()
        
        if not config:
            logger.warning(f"⚠️ [CACHE MISS - NO DATA] tenant_config not found in DB | tenant_id={tenant_id}")
            return None
        
        logger.info(f"✅ [CACHE MISS - STEP 2] DB query successful | tenant_id={tenant_id}")
        
        # Cache it for next time
        logger.info(f"💾 [CACHE MISS - STEP 3] Serializing config for cache... | tenant_id={tenant_id}")
        try:
            config_dict = serialize_tenant_config_for_cache(config)
            logger.info(f"💾 [CACHE MISS - STEP 4] Writing to Redis... | tenant_id={tenant_id}")
            cache_tenant_config(tenant_id, config_dict)
            logger.info(f"✅ [CACHE MISS COMPLETE] Successfully cached to Redis | tenant_id={tenant_id}")
        except Exception as cache_error:
            logger.error(f"❌ [CACHE MISS - CACHE FAILED] Could not write to Redis: {str(cache_error)} | tenant_id={tenant_id}")
        
        return config
        
    except Exception as e:
        # Fallback to DB if cache fails
        logger.error(f"❌ [CACHE ERROR] Exception during cache lookup: {str(e)} | tenant_id={tenant_id}")
        logger.info(f"🔄 [FALLBACK - STEP 1] Querying database directly... | tenant_id={tenant_id}")
        from app.models.tenant_config import TenantConfig
        config = db.query(TenantConfig).filter(TenantConfig.tenant_id == tenant_id).first()
        
        if not config:
            logger.warning(f"⚠️ [FALLBACK - NO DATA] tenant_config not found in DB | tenant_id={tenant_id}")
            return None
        
        logger.info(f"✅ [FALLBACK - STEP 2] DB query successful | tenant_id={tenant_id}")
        
        # Try to cache the DB result for recovery
        logger.info(f"🔄 [FALLBACK - STEP 3] Attempting to cache for recovery... | tenant_id={tenant_id}")
        try:
            config_dict = serialize_tenant_config_for_cache(config)
            cache_tenant_config(tenant_id, config_dict)
            logger.info(f"✅ [FALLBACK COMPLETE] Successfully cached after recovery | tenant_id={tenant_id}")
        except Exception as cache_retry_error:
            logger.warning(f"⚠️ [FALLBACK - CACHE FAILED] Could not cache after recovery (Redis may be down): {str(cache_retry_error)} | tenant_id={tenant_id}")
        
        return config

# TenantConfig caching
def cache_tenant_config(tenant_id: str, config_data: dict, ttl: int = 3600):
    """Cache tenant_config for 1 hour (rarely changes)"""
    return _cache_entity("tenant_config", config_data, ttl, tenant_id)

def get_cached_tenant_config(tenant_id: str) -> Optional[dict]:
    """Get cached tenant_config"""
    return _get_cached_entity("tenant_config", tenant_id)

def invalidate_tenant_config(tenant_id: str):
    """Invalidate tenant_config cache when configuration changes"""
    return _invalidate_entity("tenant_config", tenant_id)

def refresh_tenant_config(tenant_id: str, config_data: dict, ttl: int = 3600):
    """Invalidate and refresh tenant_config cache (used after updates)"""
    from app.core.logging_config import get_logger
    logger = get_logger(__name__)
    
    try:
        logger.debug(f"🔄 Refreshing tenant_config cache for tenant {tenant_id}...")
        invalidate_tenant_config(tenant_id)
        result = cache_tenant_config(tenant_id, config_data, ttl)
        logger.info(f"✅ Successfully refreshed tenant_config cache for tenant {tenant_id}")
        return result
    except Exception as e:
        logger.error(f"❌ Failed to refresh tenant_config cache for tenant {tenant_id}: {str(e)}")
        raise
