"""
Monitoring API endpoints for Fleet Manager
Provides health checks, performance metrics, and system monitoring
"""
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from typing import Optional
from app.database.session import get_db
from app.utils.database_monitor import get_db_metrics, get_connection_health
from app.utils.cache_manager import get_cache_stats
from app.core.logging_config import get_logger
from app.schemas.base import BaseResponse
from app.middleware.error_tracking import error_tracker
from app.middleware.request_tracking import request_tracker

logger = get_logger(__name__)

router = APIRouter(prefix="/monitoring", tags=["monitoring"])

@router.get("/health", response_model=BaseResponse)
async def health_check():
    """Basic health check endpoint"""
    try:
        # Check database connection
        db_health = get_connection_health()

        # Check cache connection
        cache_health = get_cache_stats()

        overall_status = "healthy"
        if db_health["status"] != "healthy" or cache_health.get("status") != "healthy":
            overall_status = "degraded"

        return BaseResponse(
            success=True,
            message="Health check completed",
            data={
                "status": overall_status,
                "database": db_health,
                "cache": cache_health,
                "timestamp": db_health["timestamp"]
            }
        )
    except Exception as e:
        logger.error(f"Health check failed: {e}")
        raise HTTPException(status_code=503, detail="Service unhealthy")

@router.get("/database/metrics", response_model=BaseResponse)
async def get_database_metrics():
    """Get database performance metrics"""
    try:
        metrics = get_db_metrics()
        return BaseResponse(
            success=True,
            message="Database metrics retrieved",
            data=metrics
        )
    except Exception as e:
        logger.error(f"Failed to get database metrics: {e}")
        raise HTTPException(status_code=500, detail="Failed to retrieve metrics")

@router.get("/cache/stats", response_model=BaseResponse)
async def get_cache_statistics():
    """Get Redis cache statistics"""
    try:
        stats = get_cache_stats()
        return BaseResponse(
            success=True,
            message="Cache statistics retrieved",
            data=stats
        )
    except Exception as e:
        logger.error(f"Failed to get cache stats: {e}")
        raise HTTPException(status_code=500, detail="Failed to retrieve cache stats")

@router.get("/system/info", response_model=BaseResponse)
async def get_system_info():
    """Get basic system information"""
    import psutil
    import platform
    from datetime import datetime

    try:
        # Get system metrics
        cpu_percent = psutil.cpu_percent(interval=1)
        memory = psutil.virtual_memory()
        disk = psutil.disk_usage('/')

        system_info = {
            "platform": platform.platform(),
            "python_version": platform.python_version(),
            "cpu_usage": f"{cpu_percent}%",
            "memory": {
                "total": f"{memory.total / (1024**3):.1f}GB",
                "available": f"{memory.available / (1024**3):.1f}GB",
                "percent": f"{memory.percent}%"
            },
            "disk": {
                "total": f"{disk.total / (1024**3):.1f}GB",
                "free": f"{disk.free / (1024**3):.1f}GB",
                "percent": f"{disk.percent}%"
            },
            "timestamp": datetime.utcnow().isoformat()
        }

        return BaseResponse(
            success=True,
            message="System information retrieved",
            data=system_info
        )
    except Exception as e:
        logger.error(f"Failed to get system info: {e}")
        raise HTTPException(status_code=500, detail="Failed to retrieve system info")

@router.get("/tasks/{task_id}", response_model=BaseResponse)
async def get_task_status(task_id: str):
    """Get background task status"""
    from app.utils.task_manager import get_task_status

    try:
        task_info = get_task_status(task_id)
        if not task_info:
            raise HTTPException(status_code=404, detail="Task not found")

        return BaseResponse(
            success=True,
            message="Task status retrieved",
            data=task_info
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get task status: {e}")
        raise HTTPException(status_code=500, detail="Failed to retrieve task status")


# ============================================================
# ERROR TRACKING ENDPOINTS
# ============================================================

@router.get("/errors/recent", response_model=BaseResponse)
async def get_recent_errors(limit: int = Query(50, ge=1, le=500)):
    """
    Get recent errors with full context
    
    Returns error details including:
    - Error type and message
    - Full traceback
    - Request details (method, URL, headers)
    - User information
    - Response time
    """
    try:
        errors = error_tracker.get_recent_errors(limit=limit)
        return BaseResponse(
            success=True,
            message=f"Retrieved {len(errors)} recent errors",
            data={
                "errors": errors,
                "total": len(errors)
            }
        )
    except Exception as e:
        logger.error(f"Failed to get recent errors: {e}")
        raise HTTPException(status_code=500, detail="Failed to retrieve errors")


@router.get("/errors/stats", response_model=BaseResponse)
async def get_error_statistics():
    """
    Get error statistics
    
    Returns:
    - Total error count
    - Errors by type
    - Errors by endpoint
    - Last error details
    """
    try:
        stats = error_tracker.get_error_stats()
        return BaseResponse(
            success=True,
            message="Error statistics retrieved",
            data=stats
        )
    except Exception as e:
        logger.error(f"Failed to get error stats: {e}")
        raise HTTPException(status_code=500, detail="Failed to retrieve error statistics")


@router.get("/errors/by-type/{error_type}", response_model=BaseResponse)
async def get_errors_by_type(error_type: str):
    """Get all errors of a specific type"""
    try:
        errors = error_tracker.get_errors_by_type(error_type)
        return BaseResponse(
            success=True,
            message=f"Retrieved {len(errors)} errors of type {error_type}",
            data={
                "error_type": error_type,
                "errors": errors,
                "total": len(errors)
            }
        )
    except Exception as e:
        logger.error(f"Failed to get errors by type: {e}")
        raise HTTPException(status_code=500, detail="Failed to retrieve errors")


@router.get("/errors/by-path", response_model=BaseResponse)
async def get_errors_by_path(path: str = Query(..., description="Endpoint path")):
    """Get all errors for a specific endpoint"""
    try:
        errors = error_tracker.get_errors_by_path(path)
        return BaseResponse(
            success=True,
            message=f"Retrieved {len(errors)} errors for path {path}",
            data={
                "path": path,
                "errors": errors,
                "total": len(errors)
            }
        )
    except Exception as e:
        logger.error(f"Failed to get errors by path: {e}")
        raise HTTPException(status_code=500, detail="Failed to retrieve errors")


# ============================================================
# REQUEST TRACKING ENDPOINTS
# ============================================================

@router.get("/requests/recent", response_model=BaseResponse)
async def get_recent_requests(limit: int = Query(100, ge=1, le=1000)):
    """
    Get recent API requests
    
    Returns request details including:
    - Request ID
    - Method and path
    - Status code
    - Response time
    - User information
    """
    try:
        requests = request_tracker.get_recent_requests(limit=limit)
        return BaseResponse(
            success=True,
            message=f"Retrieved {len(requests)} recent requests",
            data={
                "requests": requests,
                "total": len(requests)
            }
        )
    except Exception as e:
        logger.error(f"Failed to get recent requests: {e}")
        raise HTTPException(status_code=500, detail="Failed to retrieve requests")


@router.get("/requests/stats", response_model=BaseResponse)
async def get_request_statistics():
    """
    Get comprehensive request statistics
    
    Returns:
    - Total requests
    - Error rate
    - Average response time
    - Requests per minute
    - Top endpoints
    - Status code distribution
    """
    try:
        stats = request_tracker.get_request_stats()
        return BaseResponse(
            success=True,
            message="Request statistics retrieved",
            data=stats
        )
    except Exception as e:
        logger.error(f"Failed to get request stats: {e}")
        raise HTTPException(status_code=500, detail="Failed to retrieve request statistics")


@router.get("/requests/slow", response_model=BaseResponse)
async def get_slow_requests(
    threshold_ms: int = Query(1000, ge=100, description="Response time threshold in milliseconds"),
    limit: int = Query(50, ge=1, le=500)
):
    """Get slow requests above threshold"""
    try:
        slow_requests = request_tracker.get_slow_requests(threshold_ms=threshold_ms, limit=limit)
        return BaseResponse(
            success=True,
            message=f"Retrieved {len(slow_requests)} slow requests (>{threshold_ms}ms)",
            data={
                "threshold_ms": threshold_ms,
                "requests": slow_requests,
                "total": len(slow_requests)
            }
        )
    except Exception as e:
        logger.error(f"Failed to get slow requests: {e}")
        raise HTTPException(status_code=500, detail="Failed to retrieve slow requests")


@router.get("/requests/errors", response_model=BaseResponse)
async def get_error_requests(limit: int = Query(50, ge=1, le=500)):
    """Get failed requests (4xx, 5xx status codes)"""
    try:
        error_requests = request_tracker.get_error_requests(limit=limit)
        return BaseResponse(
            success=True,
            message=f"Retrieved {len(error_requests)} error requests",
            data={
                "requests": error_requests,
                "total": len(error_requests)
            }
        )
    except Exception as e:
        logger.error(f"Failed to get error requests: {e}")
        raise HTTPException(status_code=500, detail="Failed to retrieve error requests")


@router.get("/requests/by-path", response_model=BaseResponse)
async def get_requests_by_path(
    path: str = Query(..., description="Endpoint path"),
    limit: int = Query(50, ge=1, le=500)
):
    """Get requests for a specific endpoint"""
    try:
        requests = request_tracker.get_requests_by_path(path, limit=limit)
        return BaseResponse(
            success=True,
            message=f"Retrieved {len(requests)} requests for path {path}",
            data={
                "path": path,
                "requests": requests,
                "total": len(requests)
            }
        )
    except Exception as e:
        logger.error(f"Failed to get requests by path: {e}")
        raise HTTPException(status_code=500, detail="Failed to retrieve requests")


# ============================================================
# COMPREHENSIVE MONITORING DASHBOARD
# ============================================================

@router.get("/dashboard", response_model=BaseResponse)
async def get_monitoring_dashboard():
    """
    Get comprehensive monitoring dashboard data
    
    Returns all key metrics in one call:
    - System health
    - Database metrics
    - Cache statistics
    - Error statistics
    - Request statistics
    - Recent errors
    - Slow requests
    """
    try:
        dashboard_data = {
            "health": {
                "database": get_connection_health(),
                "cache": get_cache_stats()
            },
            "database_metrics": get_db_metrics(),
            "cache_stats": get_cache_stats(),
            "errors": {
                "stats": error_tracker.get_error_stats(),
                "recent": error_tracker.get_recent_errors(limit=10)
            },
            "requests": {
                "stats": request_tracker.get_request_stats(),
                "recent_errors": request_tracker.get_error_requests(limit=10),
                "slow_requests": request_tracker.get_slow_requests(threshold_ms=1000, limit=10)
            }
        }
        
        return BaseResponse(
            success=True,
            message="Monitoring dashboard data retrieved",
            data=dashboard_data
        )
    except Exception as e:
        logger.error(f"Failed to get dashboard data: {e}")
        raise HTTPException(status_code=500, detail="Failed to retrieve dashboard data")