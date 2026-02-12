"""
URL Validation Middleware
Validates URL format and provides helpful error messages for malformed requests
"""
from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse
from app.core.logging_config import get_logger
from app.utils.response_utils import ResponseWrapper

logger = get_logger(__name__)


class URLValidationMiddleware(BaseHTTPMiddleware):
    """
    Middleware to validate URL format and catch common mistakes like:
    - Starting query string with '?&' instead of '?'
    - Multiple '?' in URL
    - Malformed query parameters
    """
    
    async def dispatch(self, request: Request, call_next):
        """Process request and validate URL format"""
        
        raw_url = str(request.url)
        raw_query = request.url.query
        
        # Check for common URL format errors
        validation_errors = []
        
        # Error 1: Query string starts with '&' (indicates ?& pattern)
        if raw_query and raw_query.startswith('&'):
            validation_errors.append({
                "issue": "Query string starts with '&'",
                "found": f"?&{raw_query}",
                "should_be": f"?{raw_query[1:]}",
                "explanation": "URL query parameters should start with '?' not '?&'"
            })
        
        # Error 2: Multiple '?' in URL
        if raw_url.count('?') > 1:
            validation_errors.append({
                "issue": "Multiple '?' found in URL",
                "found": raw_url,
                "explanation": "URL should have only one '?' to start query parameters"
            })
        
        # Error 3: Empty parameter values (e.g., &param=&)
        if raw_query:
            params = raw_query.split('&')
            empty_params = [p.split('=')[0] for p in params if '=' in p and p.split('=')[1] == '']
            if empty_params:
                validation_errors.append({
                    "issue": "Empty parameter values",
                    "parameters": empty_params,
                    "explanation": f"Parameters {empty_params} have no values"
                })
        
        # If validation errors found, return helpful error response
        if validation_errors:
            logger.warning("="*80)
            logger.warning(f"⚠️ [URL VALIDATION] Malformed URL detected")
            logger.warning(f"Requested URL: {raw_url}")
            logger.warning(f"Path: {request.url.path}")
            logger.warning(f"Query: {raw_query}")
            logger.warning(f"Errors found: {len(validation_errors)}")
            for idx, error in enumerate(validation_errors, 1):
                logger.warning(f"  Error {idx}: {error['issue']}")
                if 'found' in error:
                    logger.warning(f"    Found: {error['found']}")
                if 'should_be' in error:
                    logger.warning(f"    Should be: {error['should_be']}")
            logger.warning("="*80)
            
            # Build corrected URL suggestion
            corrected_url = raw_url
            if raw_query and raw_query.startswith('&'):
                # Fix ?& pattern
                corrected_url = raw_url.replace(f"?&", "?", 1)
            
            return JSONResponse(
                status_code=400,
                content=ResponseWrapper.error(
                    message="Malformed URL: Invalid query string format",
                    error_code="INVALID_URL_FORMAT",
                    details={
                        "validation_errors": validation_errors,
                        "requested_url": raw_url,
                        "corrected_url_suggestion": corrected_url,
                        "help": {
                            "correct_format": f"{request.url.path}?param1=value1&param2=value2",
                            "your_format": raw_url,
                            "common_mistakes": [
                                "Don't use '?&' - use just '?'",
                                "Only one '?' is allowed in URL",
                                "Use '&' to separate multiple parameters"
                            ]
                        }
                    }
                )
            )
        
        # URL is valid, proceed with request
        response = await call_next(request)
        return response
