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
        try:
            shift_dict = serialize_shift_for_cache(shift)
            cache_shift(shift_id, tenant_id, shift_dict)
            logger.info(f"✅ [CACHE WRITE SUCCESS] Shift cached to Redis | tenant_id={tenant_id}, shift_id={shift_id}")
        except Exception as cache_error:
            logger.error(f"❌ [CACHE WRITE FAILED] Could not write to Redis: {str(cache_error)} | tenant_id={tenant_id}, shift_id={shift_id}")
            logger.warning(f"   This is not critical - will work from database, just slower")
        
        return shift
        
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
        try:
            shift_dict = {
                "shift_id": shift.shift_id,
                "shift_time": shift.shift_time.strftime("%H:%M:%S") if shift.shift_time else None,
                "log_type": shift.log_type.value if shift.log_type else None,
                "tenant_id": shift.tenant_id
            }
            cache_shift(shift_id, tenant_id, shift_dict)
            logger.info(f"✅ [FALLBACK COMPLETE] Successfully cached after recovery | tenant_id={tenant_id}, shift_id={shift_id}")
            return shift_dict
        except Exception as cache_retry_error:
            logger.warning(f"⚠️ [FALLBACK - CACHE FAILED] Could not cache after recovery: {str(cache_retry_error)} | tenant_id={tenant_id}, shift_id={shift_id}")
            return None

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

def serialize_tenant_for_cache(tenant_obj) -> dict:
    """
    Convert Tenant object to cacheable dictionary.
    Handles Decimal fields by converting to float.
    """
    from app.core.logging_config import get_logger
    logger = get_logger(__name__)

    try:
        tenant_dict = {c.name: getattr(tenant_obj, c.name) for c in tenant_obj.__table__.columns}

        # Convert Decimal to float for JSON serialization
        if 'latitude' in tenant_dict and tenant_dict['latitude'] is not None:
            tenant_dict['latitude'] = float(tenant_dict['latitude'])
        if 'longitude' in tenant_dict and tenant_dict['longitude'] is not None:
            tenant_dict['longitude'] = float(tenant_dict['longitude'])

        # Convert datetime to ISO string for JSON serialization
        datetime_fields = ['created_at', 'updated_at']
        for field in datetime_fields:
            if field in tenant_dict and tenant_dict[field] is not None:
                tenant_dict[field] = tenant_dict[field].isoformat()

        logger.debug(f"✅ Serialized tenant {tenant_dict.get('tenant_id', 'unknown')} for cache")
        return tenant_dict
    except Exception as e:
        logger.error(f"❌ Failed to serialize tenant for cache: {str(e)}")
        raise

def deserialize_tenant_from_cache(cached_dict: dict):
    """
    Convert cached dictionary back to Tenant object.
    Handles float to Decimal conversion.
    """
    from app.models.tenant import Tenant
    from decimal import Decimal
    from app.core.logging_config import get_logger
    logger = get_logger(__name__)

    try:
        tenant_id = cached_dict.get('tenant_id', 'unknown')

        # Convert float back to Decimal
        if cached_dict.get('latitude') is not None:
            cached_dict['latitude'] = Decimal(str(cached_dict['latitude']))
        if cached_dict.get('longitude') is not None:
            cached_dict['longitude'] = Decimal(str(cached_dict['longitude']))

        # Convert ISO string back to datetime
        from datetime import datetime
        datetime_fields = ['created_at', 'updated_at']
        for field in datetime_fields:
            if cached_dict.get(field) and isinstance(cached_dict[field], str):
                cached_dict[field] = datetime.fromisoformat(cached_dict[field])

        logger.debug(f"✅ Deserialized tenant {tenant_id} from cache")
        return Tenant(**cached_dict)
    except Exception as e:
        logger.error(f"❌ Failed to deserialize tenant from cache: {str(e)}")
        raise

def serialize_cutoff_for_cache(cutoff_obj) -> dict:
    """
    Convert Cutoff object to cacheable dictionary.
    Handles timedelta fields by converting to string.
    """
    from app.core.logging_config import get_logger
    logger = get_logger(__name__)

    try:
        cutoff_dict = {c.name: getattr(cutoff_obj, c.name) for c in cutoff_obj.__table__.columns}

        # Convert timedelta to string for JSON serialization
        time_fields = [
            'booking_login_cutoff', 'cancel_login_cutoff', 'booking_logout_cutoff',
            'cancel_logout_cutoff', 'medical_emergency_booking_cutoff', 'adhoc_booking_cutoff'
        ]

        for field in time_fields:
            if field in cutoff_dict and cutoff_dict[field] is not None:
                cutoff_dict[field] = str(cutoff_dict[field])

        # Convert datetime to ISO string for JSON serialization
        datetime_fields = ['created_at', 'updated_at']
        for field in datetime_fields:
            if field in cutoff_dict and cutoff_dict[field] is not None:
                cutoff_dict[field] = cutoff_dict[field].isoformat()

        logger.debug(f"✅ Serialized cutoff for tenant {cutoff_dict.get('tenant_id', 'unknown')} for cache")
        return cutoff_dict
    except Exception as e:
        logger.error(f"❌ Failed to serialize cutoff for cache: {str(e)}")
        raise

def deserialize_cutoff_from_cache(cached_dict: dict):
    """
    Convert cached dictionary back to Cutoff object.
    Handles string to timedelta conversion.
    """
    from app.models.cutoff import Cutoff
    from datetime import timedelta
    from app.core.logging_config import get_logger
    logger = get_logger(__name__)

    try:
        tenant_id = cached_dict.get('tenant_id', 'unknown')

        # Convert string back to timedelta
        time_fields = [
            'booking_login_cutoff', 'cancel_login_cutoff', 'booking_logout_cutoff',
            'cancel_logout_cutoff', 'medical_emergency_booking_cutoff', 'adhoc_booking_cutoff'
        ]

        for field in time_fields:
            if cached_dict.get(field) and isinstance(cached_dict[field], str):
                # Parse timedelta string like "1 day, 2:30:45" or "2:30:45"
                try:
                    cached_dict[field] = _parse_timedelta_string(cached_dict[field])
                except Exception as parse_error:
                    logger.warning(f"⚠️ Failed to parse {field} '{cached_dict[field]}', setting to None")
                    cached_dict[field] = None

        # Convert ISO string back to datetime
        from datetime import datetime
        datetime_fields = ['created_at', 'updated_at']
        for field in datetime_fields:
            if cached_dict.get(field) and isinstance(cached_dict[field], str):
                cached_dict[field] = datetime.fromisoformat(cached_dict[field])

        logger.debug(f"✅ Deserialized cutoff for tenant {tenant_id} from cache")
        return Cutoff(**cached_dict)
    except Exception as e:
        logger.error(f"❌ Failed to deserialize cutoff from cache: {str(e)}")
        raise

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

def serialize_shift_for_cache(shift_obj) -> dict:
    """
    Convert Shift object to cacheable dictionary.
    Handles time fields by converting to string.
    """
    from app.core.logging_config import get_logger
    logger = get_logger(__name__)

    try:
        shift_dict = {c.name: getattr(shift_obj, c.name) for c in shift_obj.__table__.columns}

        # Convert time to string for JSON serialization
        if 'shift_time' in shift_dict and shift_dict['shift_time'] is not None:
            shift_dict['shift_time'] = str(shift_dict['shift_time'])

        # Convert enum to value for JSON serialization
        if 'log_type' in shift_dict and shift_dict['log_type'] is not None:
            shift_dict['log_type'] = shift_dict['log_type'].value if hasattr(shift_dict['log_type'], 'value') else str(shift_dict['log_type'])
        if 'pickup_type' in shift_dict and shift_dict['pickup_type'] is not None:
            shift_dict['pickup_type'] = shift_dict['pickup_type'].value if hasattr(shift_dict['pickup_type'], 'value') else str(shift_dict['pickup_type'])
        if 'gender' in shift_dict and shift_dict['gender'] is not None:
            shift_dict['gender'] = shift_dict['gender'].value if hasattr(shift_dict['gender'], 'value') else str(shift_dict['gender'])

        # Convert datetime to ISO string for JSON serialization
        datetime_fields = ['created_at', 'updated_at']
        for field in datetime_fields:
            if field in shift_dict and shift_dict[field] is not None:
                shift_dict[field] = shift_dict[field].isoformat()

        logger.debug(f"✅ Serialized shift {shift_dict.get('shift_id', 'unknown')} for cache")
        return shift_dict
    except Exception as e:
        logger.error(f"❌ Failed to serialize shift for cache: {str(e)}")
        raise

def deserialize_shift_from_cache(cached_dict: dict):
    """
    Convert cached dictionary back to Shift object.
    Handles string to time conversion.
    """
    from app.models.shift import Shift
    from datetime import time as datetime_time
    from app.core.logging_config import get_logger
    logger = get_logger(__name__)

    try:
        shift_id = cached_dict.get('shift_id', 'unknown')

        # Convert string back to time
        if cached_dict.get('shift_time') and isinstance(cached_dict['shift_time'], str):
            time_parts = cached_dict['shift_time'].split(':')
            cached_dict['shift_time'] = datetime_time(
                int(time_parts[0]),
                int(time_parts[1]),
                int(time_parts[2]) if len(time_parts) > 2 else 0
            )

        # Convert ISO string back to datetime
        from datetime import datetime
        datetime_fields = ['created_at', 'updated_at']
        for field in datetime_fields:
            if cached_dict.get(field) and isinstance(cached_dict[field], str):
                cached_dict[field] = datetime.fromisoformat(cached_dict[field])

        # Note: Enums will be reconstructed by Shift model from string values

        logger.debug(f"✅ Deserialized shift {shift_id} from cache")
        return Shift(**cached_dict)
    except Exception as e:
        logger.error(f"❌ Failed to deserialize shift from cache: {str(e)}")
        raise

def serialize_weekoff_for_cache(weekoff_obj) -> dict:
    """
    Convert WeekoffConfig object to cacheable dictionary.
    Weekoff configs are mostly boolean fields, should be JSON serializable.
    """
    from app.core.logging_config import get_logger
    logger = get_logger(__name__)

    try:
        weekoff_dict = {c.name: getattr(weekoff_obj, c.name) for c in weekoff_obj.__table__.columns}

        # Convert datetime to ISO string for JSON serialization
        datetime_fields = ['created_at', 'updated_at']
        for field in datetime_fields:
            if field in weekoff_dict and weekoff_dict[field] is not None:
                weekoff_dict[field] = weekoff_dict[field].isoformat()

        logger.debug(f"✅ Serialized weekoff for employee {weekoff_dict.get('employee_id', 'unknown')} for cache")
        return weekoff_dict
    except Exception as e:
        logger.error(f"❌ Failed to serialize weekoff for cache: {str(e)}")
        raise

def deserialize_weekoff_from_cache(cached_dict: dict):
    """
    Convert cached dictionary back to WeekoffConfig object.
    """
    from app.models.weekoff_config import WeekoffConfig
    from app.core.logging_config import get_logger
    logger = get_logger(__name__)

    try:
        employee_id = cached_dict.get('employee_id', 'unknown')

        # Convert ISO string back to datetime
        from datetime import datetime
        datetime_fields = ['created_at', 'updated_at']
        for field in datetime_fields:
            if cached_dict.get(field) and isinstance(cached_dict[field], str):
                cached_dict[field] = datetime.fromisoformat(cached_dict[field])

        logger.debug(f"✅ Deserialized weekoff for employee {employee_id} from cache")
        return WeekoffConfig(**cached_dict)
    except Exception as e:
        logger.error(f"❌ Failed to deserialize weekoff from cache: {str(e)}")
        raise

def serialize_team_for_cache(team_obj) -> dict:
    """
    Convert Team object to cacheable dictionary.
    Handles datetime serialization for JSON compatibility.
    """
    from app.core.logging_config import get_logger
    logger = get_logger(__name__)

    try:
        # Automatically get all columns - works with new columns!
        team_dict = {c.name: getattr(team_obj, c.name) for c in team_obj.__table__.columns}

        # Only convert special types (datetime → ISO string)
        datetime_fields = ['created_at', 'updated_at']
        for field in datetime_fields:
            if team_dict.get(field) and team_dict[field] is not None:
                team_dict[field] = team_dict[field].isoformat()

        logger.debug(f"✅ Serialized team {team_dict.get('team_id', 'unknown')} for cache")
        return team_dict
    except Exception as e:
        logger.error(f"❌ Failed to serialize team for cache: {str(e)}")
        raise

def deserialize_team_from_cache(cached_dict: dict):
    """
    Convert cached dictionary back to Team object.
    Handles ISO string back to datetime.
    """
    from app.models.team import Team
    from datetime import datetime
    from app.core.logging_config import get_logger
    logger = get_logger(__name__)

    try:
        team_id = cached_dict.get('team_id', 'unknown')

        # Convert ISO string back to datetime
        datetime_fields = ['created_at', 'updated_at']
        for field in datetime_fields:
            if cached_dict.get(field) and isinstance(cached_dict[field], str):
                cached_dict[field] = datetime.fromisoformat(cached_dict[field])

        logger.debug(f"✅ Deserialized team {team_id} from cache")
        return Team(**cached_dict)
    except Exception as e:
        logger.error(f"❌ Failed to deserialize team from cache: {str(e)}")
        raise

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

# Export the cache instance as cache_manager for backward compatibility
cache_manager = cache
