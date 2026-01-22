"""
Request Tracking Middleware
Tracks all API requests with timing, response codes, and user information
"""
import time
import uuid
from typing import Dict, List
from datetime import datetime
from zoneinfo import ZoneInfo
from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware
from app.core.logging_config import get_logger
from app.utils.cache_manager import cache

logger = get_logger(__name__)
IST = ZoneInfo("Asia/Kolkata")


class RequestTracker:
    """Centralized request tracking system"""
    
    def __init__(self):
        self.requests: List[Dict] = []
        self.max_requests = 10000  # Keep last 10k requests
        self.stats = {
            "total_requests": 0,
            "total_errors": 0,
            "total_response_time": 0.0,
        }
        
    def log_request(
        self,
        request: Request,
        response: Response,
        response_time: float,
        request_id: str
    ):
        """Log request with details"""
        request_entry = {
            "request_id": request_id,
            "timestamp": datetime.now(IST).isoformat(),
            "method": request.method,
            "path": request.url.path,
            "full_url": str(request.url),
            "status_code": response.status_code,
            "response_time": round(response_time * 1000, 2),  # Convert to ms
            "client_host": request.client.host if request.client else None,
            "user_agent": request.headers.get("user-agent", ""),
            "is_error": response.status_code >= 400,
        }
        
        # Add user info if available
        if hasattr(request.state, "user"):
            request_entry["user_id"] = getattr(request.state.user, "user_id", None)
            request_entry["user_type"] = getattr(request.state.user, "user_type", None)
            request_entry["tenant_id"] = getattr(request.state.user, "tenant_id", None)
        
        # Update stats
        self.stats["total_requests"] += 1
        self.stats["total_response_time"] += response_time
        if response.status_code >= 400:
            self.stats["total_errors"] += 1
        
        # Add to list
        self.requests.append(request_entry)
        if len(self.requests) > self.max_requests:
            self.requests.pop(0)
        
        # Cache recent request (10 minute TTL)
        cache_key = f"request:{request_id}"
        cache.set(cache_key, request_entry, ttl_seconds=600)
        
        # Log slow requests (>1 second)
        if response_time > 1.0:
            logger.warning(
                f"SLOW REQUEST: {request.method} {request.url.path} - "
                f"{response_time*1000:.0f}ms - Status: {response.status_code}"
            )
        
    def get_recent_requests(self, limit: int = 100) -> List[Dict]:
        """Get recent requests"""
        return self.requests[-limit:]
    
    def get_requests_by_path(self, path: str, limit: int = 50) -> List[Dict]:
        """Get requests by endpoint"""
        matching = [r for r in self.requests if r["path"] == path]
        return matching[-limit:]
    
    def get_slow_requests(self, threshold_ms: int = 1000, limit: int = 50) -> List[Dict]:
        """Get slow requests above threshold"""
        slow = [r for r in self.requests if r["response_time"] > threshold_ms]
        return slow[-limit:]
    
    def get_error_requests(self, limit: int = 50) -> List[Dict]:
        """Get failed requests (4xx, 5xx)"""
        errors = [r for r in self.requests if r["is_error"]]
        return errors[-limit:]
    
    def get_request_stats(self) -> Dict:
        """Get comprehensive request statistics"""
        if not self.requests:
            return {
                "total_requests": 0,
                "total_errors": 0,
                "avg_response_time": 0,
                "requests_per_minute": 0,
            }
        
        # Calculate metrics
        total = len(self.requests)
        errors = sum(1 for r in self.requests if r["is_error"])
        total_time = sum(r["response_time"] for r in self.requests)
        avg_time = total_time / total if total > 0 else 0
        
        # Calculate requests per minute (last 5 minutes)
        five_min_ago = datetime.now(IST).timestamp() - 300
        recent_requests = [
            r for r in self.requests
            if datetime.fromisoformat(r["timestamp"]).timestamp() > five_min_ago
        ]
        rpm = len(recent_requests) / 5 if recent_requests else 0
        
        # Top endpoints
        endpoint_counts = {}
        for r in self.requests:
            path = r["path"]
            endpoint_counts[path] = endpoint_counts.get(path, 0) + 1
        
        top_endpoints = sorted(
            endpoint_counts.items(),
            key=lambda x: x[1],
            reverse=True
        )[:10]
        
        # Status code distribution
        status_codes = {}
        for r in self.requests:
            code = r["status_code"]
            status_codes[code] = status_codes.get(code, 0) + 1
        
        return {
            "total_requests": total,
            "total_errors": errors,
            "error_rate": round((errors / total * 100), 2) if total > 0 else 0,
            "avg_response_time_ms": round(avg_time, 2),
            "requests_per_minute": round(rpm, 2),
            "top_endpoints": top_endpoints,
            "status_code_distribution": status_codes,
            "timestamp": datetime.now(IST).isoformat()
        }


# Global request tracker instance
request_tracker = RequestTracker()


class RequestTrackingMiddleware(BaseHTTPMiddleware):
    """Middleware to track all requests"""
    
    async def dispatch(self, request: Request, call_next):
        # Generate unique request ID
        request_id = str(uuid.uuid4())
        request.state.request_id = request_id
        
        # Add request ID to response headers
        start_time = time.time()
        
        try:
            response = await call_next(request)
            response_time = time.time() - start_time
            
            # Add request ID header
            response.headers["X-Request-ID"] = request_id
            response.headers["X-Response-Time"] = f"{response_time*1000:.2f}ms"
            
            # Log request
            request_tracker.log_request(request, response, response_time, request_id)
            
            return response
            
        except Exception as e:
            # Even if there's an error, track it
            response_time = time.time() - start_time
            
            # Create a mock response for tracking
            from fastapi.responses import JSONResponse
            error_response = JSONResponse(
                status_code=500,
                content={"detail": "Internal server error"}
            )
            
            request_tracker.log_request(request, error_response, response_time, request_id)
            
            # Re-raise the exception
            raise
