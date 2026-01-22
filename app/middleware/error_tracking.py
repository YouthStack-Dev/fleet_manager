"""
Enhanced Error Tracking Middleware
Captures all errors, request details, and stores them for debugging
"""
import traceback
import time
import json
from typing import Dict, List, Optional
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware
from app.core.logging_config import get_logger
from app.utils.cache_manager import cache

logger = get_logger(__name__)
IST = ZoneInfo("Asia/Kolkata")


class ErrorTracker:
    """Centralized error tracking system"""
    
    def __init__(self):
        self.errors: List[Dict] = []
        self.max_errors = 1000  # Keep last 1000 errors in memory
        
    def log_error(
        self,
        error: Exception,
        request: Request,
        response_time: float,
        user_info: Optional[Dict] = None
    ):
        """Log error with full context"""
        error_entry = {
            "timestamp": datetime.now(IST).isoformat(),
            "error_type": type(error).__name__,
            "error_message": str(error),
            "traceback": traceback.format_exc(),
            "request": {
                "method": request.method,
                "url": str(request.url),
                "path": request.url.path,
                "query_params": dict(request.query_params),
                "headers": {
                    key: value for key, value in request.headers.items()
                    if key.lower() not in ['authorization', 'cookie', 'x-api-key']
                },
                "client_host": request.client.host if request.client else None,
            },
            "response_time": response_time,
            "user_info": user_info or {},
        }
        
        # Add to in-memory list
        self.errors.append(error_entry)
        if len(self.errors) > self.max_errors:
            self.errors.pop(0)
        
        # Cache in Redis (1 hour TTL)
        cache_key = f"error:{datetime.now(IST).timestamp()}"
        cache.set(cache_key, error_entry, ttl_seconds=3600)
        
        # Log to file
        logger.error(
            f"ERROR TRACKED: {error_entry['error_type']} - {error_entry['error_message']}\n"
            f"Path: {request.url.path}\n"
            f"Method: {request.method}\n"
            f"User: {user_info}\n"
            f"Traceback:\n{traceback.format_exc()}",
            extra={"error_entry": error_entry}
        )
        
    def get_recent_errors(self, limit: int = 50) -> List[Dict]:
        """Get recent errors"""
        return self.errors[-limit:]
    
    def get_errors_by_type(self, error_type: str) -> List[Dict]:
        """Get errors by type"""
        return [e for e in self.errors if e["error_type"] == error_type]
    
    def get_errors_by_path(self, path: str) -> List[Dict]:
        """Get errors by endpoint path"""
        return [e for e in self.errors if e["request"]["path"] == path]
    
    def get_error_stats(self) -> Dict:
        """Get error statistics"""
        if not self.errors:
            return {
                "total_errors": 0,
                "error_types": {},
                "error_paths": {},
                "last_error": None
            }
        
        # Count by type
        error_types = {}
        for error in self.errors:
            error_type = error["error_type"]
            error_types[error_type] = error_types.get(error_type, 0) + 1
        
        # Count by path
        error_paths = {}
        for error in self.errors:
            path = error["request"]["path"]
            error_paths[path] = error_paths.get(path, 0) + 1
        
        return {
            "total_errors": len(self.errors),
            "error_types": error_types,
            "error_paths": error_paths,
            "last_error": self.errors[-1] if self.errors else None,
            "timestamp": datetime.now(IST).isoformat()
        }


# Global error tracker instance
error_tracker = ErrorTracker()


class ErrorTrackingMiddleware(BaseHTTPMiddleware):
    """Middleware to track all errors and requests"""
    
    async def dispatch(self, request: Request, call_next):
        start_time = time.time()
        
        try:
            response = await call_next(request)
            return response
            
        except Exception as e:
            # Calculate response time
            response_time = time.time() - start_time
            
            # Try to extract user info from request state
            user_info = {}
            if hasattr(request.state, "user"):
                user_info = {
                    "user_id": getattr(request.state.user, "user_id", None),
                    "user_type": getattr(request.state.user, "user_type", None),
                    "tenant_id": getattr(request.state.user, "tenant_id", None),
                }
            
            # Log error with full context
            error_tracker.log_error(e, request, response_time, user_info)
            
            # Re-raise the exception to be handled by FastAPI's exception handlers
            raise
