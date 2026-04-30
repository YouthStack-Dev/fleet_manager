"""
Redis caching utilities for Fleet Manager
Provides caching decorators and helpers for common operations
"""
import json
from typing import Any, Optional, Callable, TypeVar, Union
from functools import wraps
import redis
from app.config import settings
from app.core.logging_config import get_logger

# Type hints
T = TypeVar('T')

logger = get_logger(__name__)

# Module-level connection pool — created once, shared by all CacheManager instances.
# This avoids opening a new TCP connection on every CacheManager() instantiation.
_redis_pool: Optional[redis.ConnectionPool] = None

def _get_pool() -> redis.ConnectionPool:
    global _redis_pool
    if _redis_pool is None:
        _redis_pool = redis.ConnectionPool(
            host=settings.REDIS_HOST,
            port=settings.REDIS_PORT,
            db=settings.REDIS_DB,
            password=settings.REDIS_PASSWORD or None,
            decode_responses=True,
            socket_connect_timeout=5,
            socket_timeout=5,
        )
    return _redis_pool


class CacheManager:
    """Redis cache manager with TTL and serialization support"""

    def __init__(self):
        self.redis_client = redis.Redis(
            connection_pool=_get_pool(),
            retry_on_timeout=True,
        )

    def get(self, key: str) -> Optional[Any]:
        """Get value from cache"""
        try:
            data = self.redis_client.get(key)
            return json.loads(data) if data else None
        except Exception as e:
            logger.warning("Cache get error for key=%s: %s", key, e)
            return None

    def set(self, key: str, value: Any, ttl_seconds: int = 300) -> bool:
        """Set value in cache with TTL"""
        try:
            return self.redis_client.setex(key, ttl_seconds, json.dumps(value))
        except Exception as e:
            logger.warning("Cache set error for key=%s: %s", key, e)
            return False

    def delete(self, key: str) -> bool:
        """Delete key from cache"""
        try:
            return bool(self.redis_client.delete(key))
        except Exception as e:
            logger.warning("Cache delete error for key=%s: %s", key, e)
            return False

    def exists(self, key: str) -> bool:
        """Check if key exists"""
        try:
            return bool(self.redis_client.exists(key))
        except Exception as e:
            logger.warning("Cache exists error for key=%s: %s", key, e)
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

# Team caching
def cache_team(team_id: int, tenant_id: str, team_data: dict, ttl: int = 3600):
    """Cache team data for 1 hour (rarely changes)"""
    return _cache_entity("team", team_data, ttl, tenant_id, team_id)

def get_cached_team(team_id: int, tenant_id: str) -> Optional[dict]:
    """Get cached team data"""
    return _get_cached_entity("team", tenant_id, team_id)

def invalidate_team(team_id: int, tenant_id: str):
    """Invalidate team cache when data changes"""
    return _invalidate_entity("team", tenant_id, team_id)

# ============================================================
# DRY Helper Functions with Detailed Logging
# ============================================================

def get_tenant_with_cache(db, tenant_id: str):
    """
    Get tenant with automatic caching.
    Tries cache first, falls back to DB, and auto-caches on miss.
    
    Returns: Tenant object or None
    """
    from app.core.logging_config import get_logger
    logger = get_logger(__name__)
    
    try:
        logger.info(f"🔍 [CACHE CHECK] tenant for tenant_id={tenant_id}")
        cached_tenant = get_cached_tenant(tenant_id)
        
        if cached_tenant:
            logger.info(f"✅ [CACHE HIT] tenant found in Redis | tenant_id={tenant_id}")
            try:
                tenant = deserialize_tenant_from_cache(cached_tenant)
                logger.info(f"✅ [CACHE HIT COMPLETE] Successfully deserialized | tenant_id={tenant_id}")
                return tenant
            except Exception as deser_error:
                logger.error(f"❌ [CACHE HIT ERROR] Deserialization failed: {str(deser_error)} | tenant_id={tenant_id}")
                raise
        
        logger.info(f"⚠️ [CACHE MISS] tenant not in Redis | tenant_id={tenant_id}")
        logger.info(f"📊 [CACHE MISS - STEP 1] Querying database... | tenant_id={tenant_id}")
        from app.models.tenant import Tenant
        tenant = db.query(Tenant).filter(Tenant.tenant_id == tenant_id).first()
        
        if not tenant:
            logger.warning(f"⚠️ [CACHE MISS - NO DATA] tenant not found in DB | tenant_id={tenant_id}")
            return None
        
        logger.info(f"✅ [CACHE MISS - STEP 2] DB query successful | tenant_id={tenant_id}")
        logger.info(f"💾 [CACHE MISS - STEP 3] Serializing for cache... | tenant_id={tenant_id}")
        try:
            tenant_dict = serialize_tenant_for_cache(tenant)
            logger.info(f"💾 [CACHE MISS - STEP 4] Writing to Redis... | tenant_id={tenant_id}")
            cache_tenant(tenant_id, tenant_dict)
            logger.info(f"✅ [CACHE MISS COMPLETE] Successfully cached to Redis | tenant_id={tenant_id}")
        except Exception as cache_error:
            logger.error(f"❌ [CACHE MISS - CACHE FAILED] Could not write to Redis: {str(cache_error)} | tenant_id={tenant_id}")
        
        return tenant
        
    except Exception as e:
        logger.error(f"❌ [CACHE ERROR] Exception during cache lookup: {str(e)} | tenant_id={tenant_id}")
        logger.info(f"🔄 [FALLBACK - STEP 1] Querying database directly... | tenant_id={tenant_id}")
        from app.models.tenant import Tenant
        tenant = db.query(Tenant).filter(Tenant.tenant_id == tenant_id).first()
        
        if not tenant:
            logger.warning(f"⚠️ [FALLBACK - NO DATA] tenant not found in DB | tenant_id={tenant_id}")
            return None
        
        logger.info(f"✅ [FALLBACK - STEP 2] DB query successful | tenant_id={tenant_id}")
        logger.info(f"🔄 [FALLBACK - STEP 3] Attempting to cache for recovery... | tenant_id={tenant_id}")
        try:
            tenant_dict = {c.name: getattr(tenant, c.name) for c in tenant.__table__.columns}
            cache_tenant(tenant_id, tenant_dict)
            logger.info(f"✅ [FALLBACK COMPLETE] Successfully cached after recovery | tenant_id={tenant_id}")
        except Exception as cache_retry_error:
            logger.warning(f"⚠️ [FALLBACK - CACHE FAILED] Could not cache after recovery: {str(cache_retry_error)} | tenant_id={tenant_id}")
        
        return tenant

def get_shift_with_cache(db, tenant_id: str, shift_id: int):
    """
    Get shift with automatic caching.
    Returns dict with serialized time values for consistency.
    
    Returns: dict or None
    
    ROOT CAUSE DIAGNOSTICS:
    - Cache miss -> queries database
    - Returns None ONLY if shift doesn't exist in database
    - Not a caching problem if None is returned - it's a data problem
    """
    from app.core.logging_config import get_logger
    logger = get_logger(__name__)
    
    try:
        logger.info(f"🔍 [CACHE CHECK] shift for tenant_id={tenant_id}, shift_id={shift_id}")
        cached_shift = get_cached_shift(shift_id, tenant_id)
        
        if cached_shift:
            logger.info(f"✅ [CACHE HIT] shift found in Redis | tenant_id={tenant_id}, shift_id={shift_id}")
            try:
                shift = deserialize_shift_from_cache(cached_shift)
                logger.info(f"✅ [CACHE HIT COMPLETE] Successfully deserialized | tenant_id={tenant_id}, shift_id={shift_id}")
                return shift
            except Exception as deser_error:
                logger.error(f"❌ [CACHE HIT ERROR] Deserialization failed: {str(deser_error)} | tenant_id={tenant_id}, shift_id={shift_id}")
                logger.warning(f"[FALLBACK] Will query database due to cache corruption")
                # Fall through to database query
        
        logger.info(f"⚠️ [CACHE MISS] shift not in Redis, querying database | tenant_id={tenant_id}, shift_id={shift_id}")
        logger.info(f"📊 [DATABASE QUERY] SELECT * FROM shifts WHERE shift_id={shift_id} AND tenant_id='{tenant_id}'")
        from app.models.shift import Shift
        shift = db.query(Shift).filter(Shift.shift_id == shift_id, Shift.tenant_id == tenant_id).first()
        
        if not shift:
            # ROOT CAUSE: Shift does not exist in database
            logger.error("="*80)
            logger.error(f"❌ [ROOT CAUSE] SHIFT DOES NOT EXIST IN DATABASE")
            logger.error(f"   shift_id: {shift_id}")
            logger.error(f"   tenant_id: {tenant_id}")
            logger.error(f"   Query executed: SELECT * FROM shifts WHERE shift_id={shift_id} AND tenant_id='{tenant_id}'")
            logger.error(f"   Result: No rows found")
            logger.error(f"")
            logger.error(f"   This is NOT a caching problem. This is a DATA INTEGRITY problem.")
            logger.error(f"   The shift_id {shift_id} is referenced somewhere but doesn't exist in the shifts table.")
            logger.error(f"")
            logger.error(f"   POSSIBLE CAUSES:")
            logger.error(f"   1. Shift was deleted but routes/bookings still reference it")
            logger.error(f"   2. Incomplete data migration")
            logger.error(f"   3. Missing foreign key constraints allowing orphaned references")
            logger.error(f"   4. shift_id is incorrect or belongs to different tenant")
            logger.error(f"")
            logger.error(f"   SOLUTIONS:")
            logger.error(f"   1. Check if shift exists: SELECT * FROM shifts WHERE shift_id={shift_id}")
            logger.error(f"   2. Check what references it: SELECT * FROM route_management WHERE shift_id={shift_id}")
            logger.error(f"   3. Either create the missing shift or remove orphaned references")
            logger.error(f"   4. See: docs/ROUTES_ERROR_DEBUG.md")
            logger.error("="*80)
            return None
        
        logger.info(f"✅ [DATABASE QUERY SUCCESS] Shift found in database | tenant_id={tenant_id}, shift_id={shift_id}")
        logger.info(f"💾 [CACHING] Serializing and caching shift for future requests...")
        shift_dict = None
        try:
            shift_dict = serialize_shift_for_cache(shift)
            cache_shift(shift_id, tenant_id, shift_dict)
            logger.info(f"✅ [CACHE WRITE SUCCESS] Shift cached to Redis | tenant_id={tenant_id}, shift_id={shift_id}")
        except Exception as cache_error:
            logger.error(f"❌ [CACHE WRITE FAILED] Could not write to Redis: {str(cache_error)} | tenant_id={tenant_id}, shift_id={shift_id}")
            logger.warning(f"   This is not critical - will work from database, just slower")
            # Build a minimal dict manually so we can still return something serializable
            shift_dict = {
                "shift_id": shift.shift_id,
                "shift_time": shift.shift_time.strftime("%H:%M:%S") if shift.shift_time else None,
                "log_type": shift.log_type.value if shift.log_type else None,
                "tenant_id": shift.tenant_id,
            }
        
        return shift_dict
        
    except Exception as e:
        logger.error(f"❌ [CACHE ERROR] Exception during cache lookup: {str(e)} | tenant_id={tenant_id}, shift_id={shift_id}")
        logger.info(f"🔄 [FALLBACK] Attempting direct database query... | tenant_id={tenant_id}, shift_id={shift_id}")
        from app.models.shift import Shift
        shift = db.query(Shift).filter(Shift.shift_id == shift_id, Shift.tenant_id == tenant_id).first()
        
        if not shift:
            logger.warning(f"⚠️ [FALLBACK - NO DATA] shift not found in DB | tenant_id={tenant_id}, shift_id={shift_id}")
            return None
        
        logger.info(f"✅ [FALLBACK - STEP 2] DB query successful | tenant_id={tenant_id}, shift_id={shift_id}")
        logger.info(f"🔄 [FALLBACK - STEP 3] Attempting to cache for recovery... | tenant_id={tenant_id}, shift_id={shift_id}")
        shift_dict = {
            "shift_id": shift.shift_id,
            "shift_time": shift.shift_time.strftime("%H:%M:%S") if shift.shift_time else None,
            "log_type": shift.log_type.value if shift.log_type else None,
            "tenant_id": shift.tenant_id
        }
        try:
            cache_shift(shift_id, tenant_id, shift_dict)
            logger.info(f"✅ [FALLBACK COMPLETE] Successfully cached after recovery | tenant_id={tenant_id}, shift_id={shift_id}")
        except Exception as cache_retry_error:
            logger.warning(f"⚠️ [FALLBACK - CACHE FAILED] Could not cache after recovery: {str(cache_retry_error)} | tenant_id={tenant_id}, shift_id={shift_id}")

        return shift_dict

def get_cutoff_with_cache(db, tenant_id: str):
    """
    Get cutoff with automatic caching.
    Tries cache first, falls back to DB, and auto-caches on miss.
    
    Returns: Cutoff object or None
    """
    from app.core.logging_config import get_logger
    logger = get_logger(__name__)
    
    try:
        logger.info(f"🔍 [CACHE CHECK] cutoff for tenant_id={tenant_id}")
        cached_cutoff = get_cached_cutoff(tenant_id)
        
        if cached_cutoff:
            logger.info(f"✅ [CACHE HIT] cutoff found in Redis | tenant_id={tenant_id}")
            try:
                cutoff = deserialize_cutoff_from_cache(cached_cutoff)
                logger.info(f"✅ [CACHE HIT COMPLETE] Successfully deserialized | tenant_id={tenant_id}")
                return cutoff
            except Exception as deser_error:
                logger.error(f"❌ [CACHE HIT ERROR] Deserialization failed: {str(deser_error)} | tenant_id={tenant_id}")
                raise
        
        logger.info(f"⚠️ [CACHE MISS] cutoff not in Redis | tenant_id={tenant_id}")
        logger.info(f"📊 [CACHE MISS - STEP 1] Querying database... | tenant_id={tenant_id}")
        from app.models.cutoff import Cutoff
        cutoff = db.query(Cutoff).filter(Cutoff.tenant_id == tenant_id).first()
        
        if not cutoff:
            logger.warning(f"⚠️ [CACHE MISS - NO DATA] cutoff not found in DB | tenant_id={tenant_id}")
            return None
        
        logger.info(f"✅ [CACHE MISS - STEP 2] DB query successful | tenant_id={tenant_id}")
        logger.info(f"💾 [CACHE MISS - STEP 3] Serializing for cache... | tenant_id={tenant_id}")
        try:
            cutoff_dict = serialize_cutoff_for_cache(cutoff)
            logger.info(f"💾 [CACHE MISS - STEP 4] Writing to Redis... | tenant_id={tenant_id}")
            cache_cutoff(tenant_id, cutoff_dict)
            logger.info(f"✅ [CACHE MISS COMPLETE] Successfully cached to Redis | tenant_id={tenant_id}")
        except Exception as cache_error:
            logger.error(f"❌ [CACHE MISS - CACHE FAILED] Could not write to Redis: {str(cache_error)} | tenant_id={tenant_id}")
        
        return cutoff
        
    except Exception as e:
        logger.error(f"❌ [CACHE ERROR] Exception during cache lookup: {str(e)} | tenant_id={tenant_id}")
        logger.info(f"🔄 [FALLBACK - STEP 1] Querying database directly... | tenant_id={tenant_id}")
        from app.models.cutoff import Cutoff
        cutoff = db.query(Cutoff).filter(Cutoff.tenant_id == tenant_id).first()
        
        if not cutoff:
            logger.warning(f"⚠️ [FALLBACK - NO DATA] cutoff not found in DB | tenant_id={tenant_id}")
            return None
        
        logger.info(f"✅ [FALLBACK - STEP 2] DB query successful | tenant_id={tenant_id}")
        logger.info(f"🔄 [FALLBACK - STEP 3] Attempting to cache for recovery... | tenant_id={tenant_id}")
        try:
            cutoff_dict = serialize_cutoff_for_cache(cutoff)
            cache_cutoff(tenant_id, cutoff_dict)
            logger.info(f"✅ [FALLBACK COMPLETE] Successfully cached after recovery | tenant_id={tenant_id}")
        except Exception as cache_retry_error:
            logger.warning(f"⚠️ [FALLBACK - CACHE FAILED] Could not cache after recovery: {str(cache_retry_error)} | tenant_id={tenant_id}")
        
        return cutoff

def get_weekoff_with_cache(db, employee_id: int):
    """
    Get weekoff with automatic caching.
    Tries cache first, falls back to DB, and auto-caches on miss.
    
    Returns: WeekoffConfig object or None
    """
    from app.core.logging_config import get_logger
    logger = get_logger(__name__)
    
    try:
        logger.info(f"🔍 [CACHE CHECK] weekoff for employee_id={employee_id}")
        cached_weekoff = get_cached_weekoff(employee_id)
        
        if cached_weekoff:
            logger.info(f"✅ [CACHE HIT] weekoff found in Redis | employee_id={employee_id}")
            try:
                weekoff = deserialize_weekoff_from_cache(cached_weekoff)
                logger.info(f"✅ [CACHE HIT COMPLETE] Successfully deserialized | employee_id={employee_id}")
                return weekoff
            except Exception as deser_error:
                logger.error(f"❌ [CACHE HIT ERROR] Deserialization failed: {str(deser_error)} | employee_id={employee_id}")
                raise
        
        logger.info(f"⚠️ [CACHE MISS] weekoff not in Redis | employee_id={employee_id}")
        logger.info(f"📊 [CACHE MISS - STEP 1] Querying database... | employee_id={employee_id}")
        from app.models.weekoff_config import WeekoffConfig
        weekoff = db.query(WeekoffConfig).filter(WeekoffConfig.employee_id == employee_id).first()
        
        if not weekoff:
            logger.warning(f"⚠️ [CACHE MISS - NO DATA] weekoff not found in DB | employee_id={employee_id}")
            return None
        
        logger.info(f"✅ [CACHE MISS - STEP 2] DB query successful | employee_id={employee_id}")
        logger.info(f"💾 [CACHE MISS - STEP 3] Serializing for cache... | employee_id={employee_id}")
        try:
            weekoff_dict = serialize_weekoff_for_cache(weekoff)
            logger.info(f"💾 [CACHE MISS - STEP 4] Writing to Redis... | employee_id={employee_id}")
            cache_weekoff(employee_id, weekoff_dict)
            logger.info(f"✅ [CACHE MISS COMPLETE] Successfully cached to Redis | employee_id={employee_id}")
        except Exception as cache_error:
            logger.error(f"❌ [CACHE MISS - CACHE FAILED] Could not write to Redis: {str(cache_error)} | employee_id={employee_id}")
        
        return weekoff
        
    except Exception as e:
        logger.error(f"❌ [CACHE ERROR] Exception during cache lookup: {str(e)} | employee_id={employee_id}")
        logger.info(f"🔄 [FALLBACK - STEP 1] Querying database directly... | employee_id={employee_id}")
        from app.models.weekoff_config import WeekoffConfig
        weekoff = db.query(WeekoffConfig).filter(WeekoffConfig.employee_id == employee_id).first()
        
        if not weekoff:
            logger.warning(f"⚠️ [FALLBACK - NO DATA] weekoff not found in DB | employee_id={employee_id}")
            return None
        
        logger.info(f"✅ [FALLBACK - STEP 2] DB query successful | employee_id={employee_id}")
        logger.info(f"🔄 [FALLBACK - STEP 3] Attempting to cache for recovery... | employee_id={employee_id}")
        try:
            weekoff_dict = serialize_weekoff_for_cache(weekoff)
            cache_weekoff(employee_id, weekoff_dict)
            logger.info(f"✅ [FALLBACK COMPLETE] Successfully cached after recovery | employee_id={employee_id}")
        except Exception as cache_retry_error:
            logger.warning(f"⚠️ [FALLBACK - CACHE FAILED] Could not cache after recovery: {str(cache_retry_error)} | employee_id={employee_id}")
        
        return weekoff

# ============================================================
# TenantConfig Helper Functions (DRY)
# ============================================================

def serialize_tenant_config_for_cache(config_obj) -> dict:
    """Convert TenantConfig object to cache-ready dictionary."""
    return serialize_model_for_cache(config_obj)


def deserialize_tenant_config_from_cache(cached_dict: dict):
    """Convert cached dictionary back to TenantConfig object."""
    from app.models.tenant_config import TenantConfig
    return deserialize_model_from_cache(cached_dict, TenantConfig)


def serialize_tenant_for_cache(tenant_obj) -> dict:
    """Convert Tenant object to cacheable dictionary."""
    return serialize_model_for_cache(tenant_obj)


def deserialize_tenant_from_cache(cached_dict: dict):
    """Convert cached dictionary back to Tenant object."""
    from app.models.tenant import Tenant
    return deserialize_model_from_cache(cached_dict, Tenant)


def serialize_cutoff_for_cache(cutoff_obj) -> dict:
    """Convert Cutoff object to cacheable dictionary."""
    return serialize_model_for_cache(cutoff_obj)


def deserialize_cutoff_from_cache(cached_dict: dict):
    """Convert cached dictionary back to Cutoff object."""
    from app.models.cutoff import Cutoff
    return deserialize_model_from_cache(cached_dict, Cutoff)


def _parse_timedelta_string(time_str: str):
    """Parse timedelta string back to timedelta object"""
    from datetime import timedelta
    # Handle formats like "2:30:45" or "-1 day, 2:30:45"
    if 'day' in time_str:
        # Complex format with days
        parts = time_str.split(', ')
        days = 0
        time_part = time_str
        if len(parts) > 1:
            day_part = parts[0]
            time_part = parts[1]
            if 'day' in day_part:
                days = int(day_part.split()[0])

        time_parts = time_part.split(':')
    else:
        # Simple time format
        time_parts = time_str.split(':')
        days = 0

    hours = int(time_parts[0]) if len(time_parts) > 0 else 0
    minutes = int(time_parts[1]) if len(time_parts) > 1 else 0
    seconds = int(time_parts[2]) if len(time_parts) > 2 else 0

    return timedelta(days=days, hours=hours, minutes=minutes, seconds=seconds)


# ============================================================
# Generic serialize / deserialize engine
# ============================================================

def serialize_model_for_cache(obj, extra_serializers: dict | None = None) -> dict:
    """
    Generic serializer: convert any SQLAlchemy model instance to a JSON-safe dict.

    Built-in type coercions (applied in this order):
      1. Caller-supplied extra_serializers (field_name → callable), if any.
      2. datetime  → ISO-8601 string  (checked *before* date — datetime is a subclass)
      3. date      → ISO-8601 string
      4. time      → "HH:MM:SS"
      5. timedelta → str  (Python default representation)
      6. Decimal   → float
      7. Enum      → .value  (works for both stdlib Enum and SQLAlchemy Enum)

    All existing entity-specific serialize_*_for_cache functions delegate to this.
    """
    from decimal import Decimal
    from datetime import datetime, date, time, timedelta

    result: dict = {c.name: getattr(obj, c.name) for c in obj.__table__.columns}

    if extra_serializers:
        for field, fn in extra_serializers.items():
            if result.get(field) is not None:
                result[field] = fn(result[field])

    for key, value in list(result.items()):
        if value is None:
            continue
        if isinstance(value, datetime):          # must precede `date` check
            result[key] = value.isoformat()
        elif isinstance(value, date):
            result[key] = value.isoformat()
        elif isinstance(value, time):
            result[key] = value.strftime("%H:%M:%S")
        elif isinstance(value, timedelta):
            result[key] = str(value)
        elif isinstance(value, Decimal):
            result[key] = float(value)
        elif hasattr(value, 'value'):            # Python/SQLAlchemy Enum
            result[key] = value.value

    return result


def deserialize_model_from_cache(
    cached_dict: dict,
    model_class,
    extra_deserializers: dict | None = None,
    return_dict: bool = False,
):
    """
    Generic deserializer: convert a Redis-cached dict back to a SQLAlchemy model instance.

    Reads column metadata from model_class.__table__ to determine the Python type for
    each field and applies the inverse coercion of serialize_model_for_cache:

      DateTime / TIMESTAMP → datetime.fromisoformat()
      Date                 → date.fromisoformat()
      Time                 → time object parsed from "HH:MM:SS"
      Interval             → timedelta via _parse_timedelta_string()
      Numeric / DECIMAL    → Decimal (handles float from JSON round-trip)
      Enum                 → left as string (SQLAlchemy coerces on attribute access)

    Parameters
    ----------
    cached_dict        : dict produced by CacheManager.get() — all JSON-parsed values
    model_class        : SQLAlchemy model class (e.g. Tenant, Shift …)
    extra_deserializers: dict mapping field_name → callable, applied before built-ins
    return_dict        : if True, return the converted dict instead of a model instance
                         (useful when callers expect a plain dict, e.g. shifts)
    """
    import sqlalchemy as _sa
    from decimal import Decimal
    from datetime import datetime as _dt, date as _date, time as _time

    data = dict(cached_dict)   # don't mutate caller's dict

    if extra_deserializers:
        for field, fn in extra_deserializers.items():
            if field in data and data[field] is not None:
                data[field] = fn(data[field])

    col_map: dict = {c.name: c for c in model_class.__table__.columns}

    for field, value in list(data.items()):
        if value is None:
            continue
        col = col_map.get(field)
        if col is None:
            continue
        ct = col.type
        try:
            # Numeric from JSON float (Decimal → float → JSON → float)
            if isinstance(ct, _sa.Numeric) and isinstance(value, (int, float)):
                data[field] = Decimal(str(value))
                continue
            if not isinstance(value, str):
                continue   # nothing further to coerce
            if isinstance(ct, _sa.DateTime):
                data[field] = _dt.fromisoformat(value)
            elif isinstance(ct, _sa.Date):
                data[field] = _date.fromisoformat(value)
            elif isinstance(ct, _sa.Time):
                parts = value.split(":")
                data[field] = _time(
                    int(parts[0]),
                    int(parts[1]),
                    int(parts[2].split(".")[0]) if len(parts) > 2 else 0,
                )
            elif isinstance(ct, _sa.Interval):
                result_td = _parse_timedelta_string(value)
                data[field] = result_td
            elif isinstance(ct, _sa.Numeric):
                data[field] = Decimal(str(value))
        except Exception:
            pass   # leave as-is; model validation surfaces real errors

    if return_dict:
        return data
    return model_class(**data)


def serialize_shift_for_cache(shift_obj) -> dict:
    """Convert Shift object to cacheable dictionary."""
    return serialize_model_for_cache(shift_obj)


def deserialize_shift_from_cache(cached_dict: dict):
    """
    Convert cached dictionary back to a shift dict (not a Shift instance).
    Callers access fields by key, so we return the type-converted dict directly.
    """
    from app.models.shift import Shift
    return deserialize_model_from_cache(cached_dict, Shift, return_dict=True)


def serialize_weekoff_for_cache(weekoff_obj) -> dict:
    """Convert WeekoffConfig object to cacheable dictionary."""
    return serialize_model_for_cache(weekoff_obj)


def deserialize_weekoff_from_cache(cached_dict: dict):
    """Convert cached dictionary back to WeekoffConfig object."""
    from app.models.weekoff_config import WeekoffConfig
    return deserialize_model_from_cache(cached_dict, WeekoffConfig)

def serialize_team_for_cache(team_obj) -> dict:
    """Convert Team object to cacheable dictionary."""
    return serialize_model_for_cache(team_obj)


def deserialize_team_from_cache(cached_dict: dict):
    """Convert cached dictionary back to Team object."""
    from app.models.team import Team
    return deserialize_model_from_cache(cached_dict, Team)

def get_team_with_cache(db, tenant_id: str, team_id: int):
    """
    Get team with automatic caching.
    Tries cache first, falls back to DB, and auto-caches on miss.
    
    Returns: Team object or None
    """
    from app.core.logging_config import get_logger
    logger = get_logger(__name__)
    
    try:
        logger.info(f"🔍 [CACHE CHECK] team for tenant_id={tenant_id}, team_id={team_id}")
        cached_team = get_cached_team(team_id, tenant_id)
        
        if cached_team:
            logger.info(f"✅ [CACHE HIT] team found in Redis | tenant_id={tenant_id}, team_id={team_id}")
            try:
                team = deserialize_team_from_cache(cached_team)
                logger.info(f"✅ [CACHE HIT COMPLETE] Successfully deserialized | tenant_id={tenant_id}, team_id={team_id}")
                return team
            except Exception as deser_error:
                logger.error(f"❌ [CACHE HIT ERROR] Deserialization failed: {str(deser_error)} | tenant_id={tenant_id}, team_id={team_id}")
                raise
        
        logger.info(f"⚠️ [CACHE MISS] team not in Redis | tenant_id={tenant_id}, team_id={team_id}")
        logger.info(f"📊 [CACHE MISS - STEP 1] Querying database... | tenant_id={tenant_id}, team_id={team_id}")
        from app.models.team import Team
        team = db.query(Team).filter(Team.team_id == team_id, Team.tenant_id == tenant_id).first()
        
        if not team:
            logger.warning(f"⚠️ [CACHE MISS - NO DATA] team not found in DB | tenant_id={tenant_id}, team_id={team_id}")
            return None
        
        logger.info(f"✅ [CACHE MISS - STEP 2] DB query successful | tenant_id={tenant_id}, team_id={team_id}")
        logger.info(f"💾 [CACHE MISS - STEP 3] Serializing for cache... | tenant_id={tenant_id}, team_id={team_id}")
        try:
            team_dict = serialize_team_for_cache(team)
            logger.info(f"💾 [CACHE MISS - STEP 4] Writing to Redis... | tenant_id={tenant_id}, team_id={team_id}")
            cache_team(team_id, tenant_id, team_dict)
            logger.info(f"✅ [CACHE MISS COMPLETE] Successfully cached to Redis | tenant_id={tenant_id}, team_id={team_id}")
        except Exception as cache_error:
            logger.error(f"❌ [CACHE MISS - CACHE FAILED] Could not write to Redis: {str(cache_error)} | tenant_id={tenant_id}, team_id={team_id}")
        
        return team
        
    except Exception as e:
        logger.error(f"❌ [CACHE ERROR] Exception during cache lookup: {str(e)} | tenant_id={tenant_id}, team_id={team_id}")
        logger.info(f"🔄 [FALLBACK - STEP 1] Querying database directly... | tenant_id={tenant_id}, team_id={team_id}")
        from app.models.team import Team
        team = db.query(Team).filter(Team.team_id == team_id, Team.tenant_id == tenant_id).first()
        
        if not team:
            logger.warning(f"⚠️ [FALLBACK - NO DATA] team not found in DB | tenant_id={tenant_id}, team_id={team_id}")
            return None
        
        logger.info(f"✅ [FALLBACK - STEP 2] DB query successful | tenant_id={tenant_id}, team_id={team_id}")
        logger.info(f"🔄 [FALLBACK - STEP 3] Attempting to cache for recovery... | tenant_id={tenant_id}, team_id={team_id}")
        try:
            team_dict = serialize_team_for_cache(team)
            cache_team(team_id, tenant_id, team_dict)
            logger.info(f"✅ [FALLBACK COMPLETE] Successfully cached after recovery | tenant_id={tenant_id}, team_id={team_id}")
        except Exception as cache_retry_error:
            logger.warning(f"⚠️ [FALLBACK - CACHE FAILED] Could not cache after recovery: {str(cache_retry_error)} | tenant_id={tenant_id}, team_id={team_id}")
        
        return team

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

# ============================================================
# Driver Caching - Multi-Level Cache Strategy
# ============================================================

def serialize_driver_for_cache(driver_obj) -> dict:
    """Convert Driver object to cacheable dictionary."""
    return serialize_model_for_cache(driver_obj)


def deserialize_driver_from_cache(cached_dict: dict):
    """Convert cached dictionary back to Driver object."""
    from app.models.driver import Driver
    return deserialize_model_from_cache(cached_dict, Driver)


# Driver caching - Individual driver by ID
def cache_driver(driver_id: int, driver_data: dict, ttl: int = 300):
    """Cache driver data for 5 minutes"""
    return _cache_entity("driver", driver_data, ttl, driver_id)

def get_cached_driver(driver_id: int) -> Optional[dict]:
    """Get cached driver data"""
    return _get_cached_entity("driver", driver_id)

def invalidate_driver(driver_id: int):
    """Invalidate driver cache when data changes"""
    return _invalidate_entity("driver", driver_id)

# Driver caching - License mapping (for multi-vendor support)
def cache_driver_license(license_number: str, driver_ids: list, ttl: int = 300):
    """Cache license → driver_ids mapping for 5 minutes"""
    return _cache_entity("driver_license", driver_ids, ttl, license_number)

def get_cached_driver_license(license_number: str) -> Optional[list]:
    """Get cached driver IDs for license number"""
    return _get_cached_entity("driver_license", license_number)

def invalidate_driver_license(license_number: str):
    """Invalidate license cache when driver data changes"""
    return _invalidate_entity("driver_license", license_number)

# Driver caching - Android ID mapping (for device authorization)
def cache_driver_android(android_id: str, driver_id: int, ttl: int = 300):
    """Cache android_id → driver_id mapping for 5 minutes"""
    return _cache_entity("driver_android", driver_id, ttl, android_id)

def get_cached_driver_android(android_id: str) -> Optional[int]:
    """Get cached driver ID for android_id"""
    return _get_cached_entity("driver_android", android_id)

def invalidate_driver_android(android_id: str):
    """Invalidate android_id cache (critical for device authorization)"""
    return _invalidate_entity("driver_android", android_id)

# Driver caching - Vendor list
def cache_driver_vendor(vendor_id: int, driver_ids: list, ttl: int = 600):
    """Cache vendor driver list for 10 minutes"""
    return _cache_entity("driver_vendor", driver_ids, ttl, vendor_id)

def get_cached_driver_vendor(vendor_id: int) -> Optional[list]:
    """Get cached driver IDs for vendor"""
    return _get_cached_entity("driver_vendor", vendor_id)

def invalidate_driver_vendor(vendor_id: int):
    """Invalidate vendor driver list cache"""
    return _invalidate_entity("driver_vendor", vendor_id)

# Driver caching - Tenant list
def cache_driver_tenant(tenant_id: str, driver_ids: list, ttl: int = 900):
    """Cache tenant driver list for 15 minutes"""
    return _cache_entity("driver_tenant", driver_ids, ttl, tenant_id)

def get_cached_driver_tenant(tenant_id: str) -> Optional[list]:
    """Get cached driver IDs for tenant"""
    return _get_cached_entity("driver_tenant", tenant_id)

def invalidate_driver_tenant(tenant_id: str):
    """Invalidate tenant driver list cache"""
    return _invalidate_entity("driver_tenant", tenant_id)

# ============================================================
# Driver Helper Functions with Cache + DB Fallback
# ============================================================

def get_driver_with_cache(db, driver_id: int):
    """
    Get driver with automatic caching.
    Tries cache first, falls back to DB, and auto-caches on miss.
    
    Returns: Driver dict or None
    """
    from app.core.logging_config import get_logger
    logger = get_logger(__name__)
    
    try:
        logger.info(f"🔍 [CACHE CHECK] Looking for driver_id={driver_id} in Redis")
        cached_driver = get_cached_driver(driver_id)
        
        if cached_driver:
            logger.info(f"✅ [CACHE HIT] Driver found in Redis | driver_id={driver_id} | No DB query needed")
            return cached_driver
        
        logger.info(f"⚠️ [CACHE MISS] Driver_id={driver_id} not in Redis | Reason: Key doesn't exist or expired | Querying database...")
        from app.models.driver import Driver
        driver = db.query(Driver).filter(Driver.driver_id == driver_id).first()
        
        if not driver:
            logger.warning(f"❌ [DATABASE] Driver not found | driver_id={driver_id} | Reason: Record doesn't exist")
            return None
        
        logger.info(f"✅ [DATABASE QUERY SUCCESS] Driver found in DB | driver_id={driver_id} | Now caching for future requests...")
        try:
            driver_dict = serialize_driver_for_cache(driver)
            cache_driver(driver_id, driver_dict)
            logger.info(f"💾 [CACHE STORED] Driver cached successfully | driver_id={driver_id} | TTL=300s")
            return driver_dict
        except Exception as cache_error:
            logger.error(f"⚠️ [CACHE STORE FAILED] Failed to cache driver | driver_id={driver_id} | Reason: {str(cache_error)} | Returning data anyway")
            return serialize_driver_for_cache(driver)
        
    except Exception as e:
        logger.error(f"❌ [CACHE ERROR] Exception during cache operation | driver_id={driver_id} | Error: {str(e)}")
        logger.info(f"🔄 [FALLBACK] Attempting direct database query without cache...")
        try:
            from app.models.driver import Driver
            driver = db.query(Driver).filter(Driver.driver_id == driver_id).first()
            
            if not driver:
                logger.warning(f"❌ [FALLBACK FAILED] Driver not found in database | driver_id={driver_id}")
                return None
            
            logger.info(f"✅ [FALLBACK SUCCESS] Driver found via direct DB query | driver_id={driver_id}")
            return serialize_driver_for_cache(driver)
        except Exception as fallback_error:
            logger.error(f"❌ [FALLBACK ERROR] Database query failed | driver_id={driver_id} | Error: {str(fallback_error)}")
            return None

def get_drivers_by_license_with_cache(db, license_number: str):
    """
    Get all drivers with license number (multi-vendor support).
    Tries cache first, falls back to DB, and auto-caches on miss.
    
    Returns: List of driver dicts
    """
    from app.core.logging_config import get_logger
    logger = get_logger(__name__)
    
    try:
        logger.info(f"🔍 [CACHE CHECK] Looking for license={license_number} mapping in Redis")
        cached_driver_ids = get_cached_driver_license(license_number)
        
        if cached_driver_ids:
            logger.info(f"✅ [CACHE HIT] License mapping found | license={license_number} | {len(cached_driver_ids)} driver(s) | No DB query needed")
            # Get each driver from cache
            drivers = []
            for driver_id in cached_driver_ids:
                driver_data = get_driver_with_cache(db, driver_id)
                if driver_data:
                    drivers.append(driver_data)
            logger.info(f"✅ [CACHE COMPLETE] Retrieved all {len(drivers)} driver(s) for license={license_number}")
            return drivers
        
        logger.info(f"⚠️ [CACHE MISS] License mapping not in Redis | license={license_number} | Reason: Key doesn't exist or expired | Querying database...")
        from app.models.driver import Driver
        drivers = db.query(Driver).filter(Driver.license_number == license_number).all()
        
        if not drivers:
            logger.warning(f"❌ [DATABASE] No drivers found | license={license_number} | Reason: No records with this license")
            return []
        
        logger.info(f"✅ [DATABASE QUERY SUCCESS] Found {len(drivers)} driver(s) in DB | license={license_number} | Now caching...")
        
        driver_ids = []
        driver_dicts = []
        failed_cache_count = 0
        
        for driver in drivers:
            try:
                driver_dict = serialize_driver_for_cache(driver)
                cache_driver(driver.driver_id, driver_dict)
                driver_ids.append(driver.driver_id)
                driver_dicts.append(driver_dict)
            except Exception as cache_error:
                failed_cache_count += 1
                logger.error(f"⚠️ [CACHE STORE FAILED] Driver {driver.driver_id} not cached | Reason: {str(cache_error)}")
        
        # Cache license → driver_ids mapping
        if driver_ids:
            try:
                cache_driver_license(license_number, driver_ids)
                logger.info(f"💾 [CACHE STORED] License mapping cached | license={license_number} | {len(driver_ids)} driver(s) | TTL=300s | Failed={failed_cache_count}")
            except Exception as mapping_error:
                logger.error(f"⚠️ [CACHE STORE FAILED] License mapping not cached | license={license_number} | Reason: {str(mapping_error)}")
        
        return driver_dicts
        
    except Exception as e:
        logger.error(f"❌ [CACHE ERROR] Exception during license lookup | license={license_number} | Error: {str(e)}")
        logger.info(f"🔄 [FALLBACK] Querying database directly without cache...")
        try:
            from app.models.driver import Driver
            drivers = db.query(Driver).filter(Driver.license_number == license_number).all()
            logger.info(f"✅ [FALLBACK SUCCESS] Found {len(drivers)} driver(s) via direct DB query | license={license_number}")
            return [serialize_driver_for_cache(d) for d in drivers]
        except Exception as fallback_error:
            logger.error(f"❌ [FALLBACK ERROR] Database query failed | license={license_number} | Error: {str(fallback_error)}")
            return []

def get_driver_by_android_id_with_cache(db, android_id: str):
    """
    Get driver by active_android_id (for device authorization).
    Tries cache first, falls back to DB, and auto-caches on miss.
    
    Returns: Driver dict or None
    """
    from app.core.logging_config import get_logger
    logger = get_logger(__name__)
    
    try:
        logger.info(f"🔍 [CACHE CHECK] Looking for android_id={android_id[:8]}...{android_id[-4:]} mapping in Redis")
        cached_driver_id = get_cached_driver_android(android_id)
        
        if cached_driver_id:
            logger.info(f"✅ [CACHE HIT] Android ID mapped to driver_id={cached_driver_id} | android_id={android_id[:8]}...{android_id[-4:]} | No DB query needed")
            return get_driver_with_cache(db, cached_driver_id)
        
        logger.info(f"⚠️ [CACHE MISS] Android ID mapping not in Redis | android_id={android_id[:8]}...{android_id[-4:]} | Reason: Key doesn't exist or expired | Querying database...")
        from app.models.driver import Driver
        driver = db.query(Driver).filter(Driver.active_android_id == android_id).first()
        
        if not driver:
            logger.warning(f"❌ [DATABASE] No driver found | android_id={android_id[:8]}...{android_id[-4:]} | Reason: No driver has this device active")
            return None
        
        logger.info(f"✅ [DATABASE QUERY SUCCESS] Driver found in DB | driver_id={driver.driver_id} | android_id={android_id[:8]}...{android_id[-4:]} | Now caching...")
        
        try:
            driver_dict = serialize_driver_for_cache(driver)
            cache_driver(driver.driver_id, driver_dict)
            cache_driver_android(android_id, driver.driver_id)
            logger.info(f"💾 [CACHE STORED] Android ID mapping cached | driver_id={driver.driver_id} → android_id={android_id[:8]}...{android_id[-4:]} | TTL=300s")
            return driver_dict
        except Exception as cache_error:
            logger.error(f"⚠️ [CACHE STORE FAILED] Android ID mapping not cached | driver_id={driver.driver_id} | Reason: {str(cache_error)} | Returning data anyway")
            return serialize_driver_for_cache(driver)
        
    except Exception as e:
        logger.error(f"❌ [CACHE ERROR] Exception during android_id lookup: {str(e)} | android_id={android_id[:8]}...")
        logger.info(f"🔄 [FALLBACK] Querying database directly...")
        from app.models.driver import Driver
        driver = db.query(Driver).filter(Driver.active_android_id == android_id).first()
        
        if not driver:
            return None
        
        try:
            return serialize_driver_for_cache(driver)
        except:
            return None

def invalidate_driver_complete(driver_id: int, old_data: Optional[dict] = None, new_data: Optional[dict] = None):
    """
    Complete driver cache invalidation - handles all related caches.
    
    ⚡ CRITICAL: Use this for android_id changes to invalidate both old and new android_id caches.
    
    Args:
        driver_id: Driver ID to invalidate
        old_data: Old driver data (before update) - should include old android_id, license_number
        new_data: New driver data (after update) - should include new android_id, license_number
    
    Returns: Success boolean
    """
    from app.core.logging_config import get_logger
    logger = get_logger(__name__)
    
    try:
        # Always invalidate driver cache
        invalidate_driver(driver_id)
        logger.info(f"🗑️ [CACHE INVALIDATE] Driver ID={driver_id}")
        
        # Invalidate old android_id if it changed
        if old_data and old_data.get('active_android_id'):
            if not new_data or old_data.get('active_android_id') != new_data.get('active_android_id'):
                invalidate_driver_android(old_data['active_android_id'])
                logger.info(f"⚡ [ANDROID CHANGE] Invalidated old Android ID: {old_data['active_android_id'][:8]}...")
        
        # Invalidate new android_id
        if new_data and new_data.get('active_android_id'):
            invalidate_driver_android(new_data['active_android_id'])
            logger.info(f"⚡ [ANDROID CHANGE] Invalidated new Android ID: {new_data['active_android_id'][:8]}...")
        
        # Invalidate old license if it changed
        if old_data and old_data.get('license_number'):
            if not new_data or old_data.get('license_number') != new_data.get('license_number'):
                invalidate_driver_license(old_data['license_number'])
                logger.info(f"🗑️ [LICENSE CHANGE] Invalidated old license: {old_data['license_number']}")
        
        # Invalidate current license
        data = new_data or old_data
        if data:
            if data.get('license_number'):
                invalidate_driver_license(data['license_number'])
            if data.get('vendor_id'):
                invalidate_driver_vendor(data['vendor_id'])
            if data.get('tenant_id'):
                invalidate_driver_tenant(data['tenant_id'])
        
        logger.info(f"✅ [CACHE INVALIDATE COMPLETE] Driver ID={driver_id}")
        return True
        
    except Exception as e:
        logger.error(f"❌ [CACHE INVALIDATE ERROR] Failed to invalidate driver caches: {str(e)} | driver_id={driver_id}")
        return False

# ============================================================
# Permission Caching  (hot path: called on every authenticated request)
# TTL = 5 min.  Invalidated when a role is mutated or an employee's role changes.
# ============================================================

PERMISSIONS_TTL = 300  # seconds


def cache_permissions(employee_id: int, tenant_id: str, data: dict, ttl: int = PERMISSIONS_TTL) -> bool:
    """Cache resolved roles+permissions for an employee (key: permissions:{tenant_id}:{employee_id})."""
    return _cache_entity("permissions", data, ttl, tenant_id, employee_id)


def get_cached_permissions(employee_id: int, tenant_id: str) -> Optional[dict]:
    """Return cached {roles, permissions} or None on miss/unavailability."""
    return _get_cached_entity("permissions", tenant_id, employee_id)


def invalidate_permissions(employee_id: int, tenant_id: str) -> bool:
    """Invalidate the permissions cache for a single employee."""
    return _invalidate_entity("permissions", tenant_id, employee_id)


def invalidate_permissions_for_role(db, role_id: int, tenant_id: Optional[str]) -> int:
    """
    Invalidate the permissions cache for every employee currently assigned to *role_id*.

    System roles (tenant_id=None) span all tenants; enumerating all affected employees
    would require a cross-tenant scan.  Instead we log a warning and let the TTL handle
    expiry — acceptable for a 5-minute window on rarely-changed system roles.

    Returns the number of per-employee cache keys deleted.
    """
    if not tenant_id:
        logger.warning(
            "System role %s updated; permission caches will expire via TTL (%ss)",
            role_id, PERMISSIONS_TTL,
        )
        return 0

    from app.models.employee import Employee  # local to avoid circular imports
    emp_ids: list[int] = [
        row[0]
        for row in db.query(Employee.employee_id).filter(
            Employee.role_id == role_id,
            Employee.tenant_id == tenant_id,
        ).all()
    ]
    count = sum(1 for eid in emp_ids if invalidate_permissions(eid, tenant_id))
    logger.info(
        "Invalidated permissions cache for %d employee(s) on role_id=%s tenant=%s",
        count, role_id, tenant_id,
    )
    return count


# Export the cache instance as cache_manager for backward compatibility
cache_manager = cache
