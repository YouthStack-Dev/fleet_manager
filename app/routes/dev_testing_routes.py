from fastapi import APIRouter, Depends, HTTPException, status
from app.database.session import get_db
from sqlalchemy.orm import Session
from common_utils.auth.permission_checker import PermissionChecker
from app.utils.response_utils import ResponseWrapper
from app.core.logging_config import get_logger

logger = get_logger(__name__)
router = APIRouter(prefix="/dev", tags=["development"])

@router.post("/clear-cache")
async def clear_redis_cache(
    pattern: str = "*",
    db: Session = Depends(get_db),
    user_data=Depends(PermissionChecker(["admin_tenant.create"], check_tenant=False)),
):
    """
    Clear Redis cache - Admin only endpoint for testing and maintenance.
    
    Args:
        pattern: Redis key pattern to delete (default: "*" deletes all)
                 Examples: "tenant_config:*", "shift:*", "cutoff:*"
    
    Returns:
        Count of keys deleted and cache statistics
    """
    try:
        from app.utils import cache_manager
        from app.core.logging_config import get_logger
        logger = get_logger(__name__)
        
        # Validate user is admin
        user_type = user_data.get("user_type")
        if user_type != "admin":
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=ResponseWrapper.error(
                    message="Only admin users can clear cache",
                    error_code="ADMIN_ONLY"
                )
            )
        
        logger.warning(f"🗑️ [CACHE CLEAR] Admin {user_data.get('user_id')} clearing cache with pattern: {pattern}")
        
        # Get cache manager instance
        redis_client = cache_manager.cache.redis_client
        
        # Get all keys matching pattern
        keys = redis_client.keys(pattern)
        deleted_count = 0
        
        if keys:
            deleted_count = redis_client.delete(*keys)
            logger.info(f"✅ [CACHE CLEAR] Deleted {deleted_count} keys matching pattern '{pattern}'")
        else:
            logger.info(f"⚠️ [CACHE CLEAR] No keys found matching pattern '{pattern}'")
        
        # Get cache statistics
        try:
            info = redis_client.info('stats')
            cache_stats = {
                "total_connections_received": info.get('total_connections_received', 0),
                "total_commands_processed": info.get('total_commands_processed', 0),
                "keyspace_hits": info.get('keyspace_hits', 0),
                "keyspace_misses": info.get('keyspace_misses', 0),
                "used_memory_human": redis_client.info('memory').get('used_memory_human', 'N/A'),
            }
            
            # Calculate hit rate
            hits = cache_stats['keyspace_hits']
            misses = cache_stats['keyspace_misses']
            total = hits + misses
            hit_rate = (hits / total * 100) if total > 0 else 0
            cache_stats['hit_rate_percentage'] = round(hit_rate, 2)
            
        except Exception as stats_error:
            logger.warning(f"Could not retrieve cache stats: {stats_error}")
            cache_stats = {}
        
        return ResponseWrapper.success(
            message=f"Cache cleared successfully. Deleted {deleted_count} keys.",
            data={
                "pattern": pattern,
                "keys_deleted": deleted_count,
                "cache_stats": cache_stats,
                "cleared_by": user_data.get("user_id"),
            }
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.exception(f"❌ [CACHE CLEAR ERROR] Failed to clear cache: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=ResponseWrapper.error(
                message=f"Failed to clear cache: {str(e)}",
                error_code="CACHE_CLEAR_FAILED"
            )
        )

@router.get("/cache-stats")
async def get_cache_statistics(
    db: Session = Depends(get_db),
    user_data=Depends(PermissionChecker(["admin_tenant.read"], check_tenant=False)),
):
    """
    Get Redis cache statistics - Admin only endpoint for monitoring.
    
    Returns:
        Detailed cache statistics including hit rate, memory usage, and key counts
    """
    try:
        from app.utils import cache_manager
        
        # Validate user is admin
        user_type = user_data.get("user_type")
        if user_type != "admin":
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=ResponseWrapper.error(
                    message="Only admin users can view cache statistics",
                    error_code="ADMIN_ONLY"
                )
            )
        
        redis_client = cache_manager.cache.redis_client
        
        # Get comprehensive statistics
        stats_info = redis_client.info('stats')
        memory_info = redis_client.info('memory')
        server_info = redis_client.info('server')
        
        # Get key counts by pattern
        key_patterns = {
            "tenant_config": len(redis_client.keys("tenant_config:*")),
            "tenant": len(redis_client.keys("tenant:*")),
            "shift": len(redis_client.keys("shift:*")),
            "cutoff": len(redis_client.keys("cutoff:*")),
            "weekoff": len(redis_client.keys("weekoff:*")),
            "driver_locations": len(redis_client.keys("driver_locations:*")),
            "opaque_tokens": len(redis_client.keys("opaque_token:*")),
            "total": redis_client.dbsize(),
        }
        
        # Calculate hit rate
        hits = stats_info.get('keyspace_hits', 0)
        misses = stats_info.get('keyspace_misses', 0)
        total_requests = hits + misses
        hit_rate = (hits / total_requests * 100) if total_requests > 0 else 0
        
        cache_stats = {
            "server_info": {
                "redis_version": server_info.get('redis_version', 'N/A'),
                "uptime_in_days": server_info.get('uptime_in_days', 0),
            },
            "memory": {
                "used_memory_human": memory_info.get('used_memory_human', 'N/A'),
                "used_memory_peak_human": memory_info.get('used_memory_peak_human', 'N/A'),
                "total_system_memory_human": memory_info.get('total_system_memory_human', 'N/A'),
            },
            "performance": {
                "keyspace_hits": hits,
                "keyspace_misses": misses,
                "hit_rate_percentage": round(hit_rate, 2),
                "total_commands_processed": stats_info.get('total_commands_processed', 0),
                "instantaneous_ops_per_sec": stats_info.get('instantaneous_ops_per_sec', 0),
            },
            "keys": key_patterns,
        }
        
        return ResponseWrapper.success(
            message="Cache statistics retrieved successfully",
            data=cache_stats
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.exception(f"Failed to get cache statistics: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=ResponseWrapper.error(
                message=f"Failed to retrieve cache statistics: {str(e)}",
                error_code="CACHE_STATS_FAILED"
            )
        )
