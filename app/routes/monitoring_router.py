"""
Monitoring API endpoints for Fleet Manager
Provides health checks, performance metrics, and system monitoring
"""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from app.database.session import get_db
from app.utils.database_monitor import get_db_metrics, get_connection_health
from app.utils.cache_manager import get_cache_stats
from app.core.logging_config import get_logger
from app.schemas.base import BaseResponse

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