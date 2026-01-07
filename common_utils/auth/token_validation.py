import os
import base64
import logging
import time
import httpx
import json
from cachetools import TTLCache
from cachetools.keys import hashkey
from fastapi import Request, HTTPException, status, Depends
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from typing import Dict, Optional, List, Set
import jwt
from jwt.exceptions import PyJWTError
from functools import lru_cache

from app.database.session import SessionLocal, get_db
from app.models.iam import Permission, Policy, Role
from sqlalchemy.orm import Session, joinedload
from app.config import settings
from app.utils.response_utils import ResponseWrapper

# Configuration - use centralized settings
SECRET_KEY = settings.SECRET_KEY
ALGORITHM = settings.ALGORITHM

logger = logging.getLogger("uvicorn")

# Simple in-memory cache for permissions
permission_cache = {}
permission_cache_ttl = 60*60*24  # 5 minutes

# Create a security instance
security = HTTPBearer()

# Environment Variables - use centralized settings
OAUTH2_ENV = settings.ENV
X_INTROSPECT_SECRET = settings.X_INTROSPECT_SECRET
OAUTH2_URL = settings.OAUTH2_URL

print(f"Running in {OAUTH2_ENV} mode")
print(f"OAUTH2_URL = {OAUTH2_URL}")

# Redis connection settings - use centralized settings
REDIS_HOST = settings.REDIS_HOST
REDIS_PORT = settings.REDIS_PORT
REDIS_DB = settings.REDIS_DB
REDIS_PASSWORD = settings.REDIS_PASSWORD or "redispassword"
USE_REDIS = settings.USE_REDIS


class OAuthApiAccessorError(Exception):
    def __init__(self, message, error_code):
        super().__init__(message)
        self.error_code = error_code


class RedisTokenManager:
    """Redis implementation for token storage"""
    _instance = None
    
    def __new__(cls):
        if not cls._instance:
            cls._instance = super(RedisTokenManager, cls).__new__(cls)
            cls._instance.__initialized = False
        return cls._instance
    
    def __init__(self):
        if self.__initialized:
            return
        
        try:
            import redis
            self.client = redis.Redis(
                host=REDIS_HOST, 
                port=REDIS_PORT,
                db=REDIS_DB,
                password=REDIS_PASSWORD if REDIS_PASSWORD else None,
                decode_responses=True
            )
            # Test connection
            self.client.ping()
            self.available = True
            logging.info("Connected to Redis successfully")
        except ImportError:
            logging.error("Redis package not installed. Please install it with 'pip install redis'")
            self.available = False
        except Exception as e:
            logging.error(f"Failed to connect to Redis: {str(e)}")
            self.available = False
        
        self.__initialized = True
    
    def is_available(self):
        """Check if Redis is available"""
        return self.available
    
    def store_token(self, token, data, ttl=None):
        """Store a token with its associated data in Redis"""
        if not self.available:
            return False
        
        try:
            metadata_prefix = "opaque_token_metadata:"
            basic_prefix = "opaque_token:"
            
            metadata_key = f"{metadata_prefix}{token}"
            basic_key = f"{basic_prefix}{token}"
            
            # Set active flag
            if isinstance(data, dict):
                data["active"] = True
            
            # Store full payload
            self.client.setex(metadata_key, int(ttl or 3600), json.dumps(data))
            
            # Store basic info for quick lookups
            basic_data = {
                "exp": data.get("exp", int(time.time()) + (ttl or 3600)),
                "user_id": data.get("user_id", ""),
                "tenant_id": data.get("tenant_id", ""),
                "active": True
            }
            
            self.client.setex(basic_key, int(ttl or 3600), json.dumps(basic_data))
            
            logging.info(
                "Token stored in Redis with dual mappings: %s, TTL: %s seconds",
                token,
                ttl or 3600,
            )
            return True
        except Exception as e:
            logging.error(f"Error storing token in Redis: {str(e)}")
            return False
    
    def get_token_metadata(self, token):
        """
        Retrieve token data from Redis
        
        Args:
            token: The token to retrieve
            metadata_only: If True, only retrieve from the metadata store
        """
        if not self.available:
            return None
        
        try:
            metadata_prefix = "opaque_token_metadata:"
            
            metadata_key = f"{metadata_prefix}{token}"
            
            # First try to get full metadata
            data = self.client.get(metadata_key)
            
            if data:
                parsed_data = json.loads(data)
                if isinstance(parsed_data, dict):
                    parsed_data["source"] = "redis-cache-metadata"
                return parsed_data
                                
            return None
        except Exception as e:
            logging.error(f"Error retrieving token from Redis: {str(e)}")
            return None
    
    def get_token_basic_info(self, token):
        """Get only the basic token info (exp, user_id, tenant_id, active)"""
        if not self.available:
            return None
        
        try:
            basic_prefix = "opaque_token:"
            basic_key = f"{basic_prefix}{token}"
            
            data = self.client.get(basic_key)
            if data:
                parsed_data = json.loads(data)
                if isinstance(parsed_data, dict):
                    parsed_data["source"] = "redis-cache-basic"
                return parsed_data
            return None
        except Exception as e:
            logging.error(f"Error retrieving basic token info from Redis: {str(e)}")
            return None
    
    def revoke_token(self, token):
        """Mark a token as revoked/inactive in Redis"""
        if not self.available:
            return False
        
        try:
            prefix = "token:"
            key = f"{prefix}{token}"
            data = self.client.get(key)
            
            if data:
                parsed_data = json.loads(data)
                if isinstance(parsed_data, dict):
                    parsed_data["active"] = False
                    ttl = self.client.ttl(key)
                    if ttl > 0:
                        self.client.setex(key, ttl, json.dumps(parsed_data))
                        return True
            return False
        except Exception as e:
            logging.error(f"Error revoking token in Redis: {str(e)}")
            return False
    
    def list_tokens(self, pattern="*", limit=100):
        """List tokens in Redis matching a pattern (caution: can be expensive with large DBs)"""
        if not self.available:
            return []
        
        try:
            results = []
            prefix = "token:"
            full_pattern = f"{prefix}{pattern}"
            
            cursor = '0'
            count = 0
            
            while cursor != 0 and count < limit:
                cursor, keys = self.client.scan(cursor=cursor, match=full_pattern, count=10)
                count += len(keys)
                
                for key in keys:
                    token = key.replace(prefix, "")
                    data = self.client.get(key)
                    ttl = self.client.ttl(key)
                    
                    if data:
                        results.append({
                            "token": token,
                            "expires_in": ttl,
                            "data": json.loads(data)
                        })
            
            return results
        except Exception as e:
            logging.error(f"Error listing tokens from Redis: {str(e)}")
            return []


class Oauth2AsAccessor:
    _instance = None

    def __new__(cls, *args, **kwargs):
        if not cls._instance:
            cls._instance = super(Oauth2AsAccessor, cls).__new__(cls)
            cls._instance.__initialized = False
        return cls._instance

    def __init__(self):
        if self.__initialized:
            return
        
        # Initialize memory cache for backward compatibility
        self.cache = TTLCache(maxsize=1000, ttl=3600)
        
        # Initialize Redis token manager
        self.redis_manager = RedisTokenManager()
        self.use_redis = USE_REDIS and self.redis_manager.is_available()
        
        if self.use_redis:
            logging.info("Using Redis for token storage")
        else:
            logging.info("Using in-memory cache for token storage")
            
        self.__initialized = True

    @classmethod
    def set_verbosity(cls, verbosity):
        logging.basicConfig(level=verbosity)
        logging.info("Logging verbosity set to: %s", verbosity)

    def validate_env_variables(self):
        if (
            not OAUTH2_ENV
            or not OAUTH2_URL
        ):
            raise OAuthApiAccessorError(
                "Required environment variables are not set.", 5003
            )

    @staticmethod
    def get_validation_url():
        oauth_token_url = OAUTH2_URL
        if not oauth_token_url:
            raise OAuthApiAccessorError(f"OAuth token url is not set for {OAUTH2_ENV}", 5002)
        
        # Ensure URL has a protocol (http:// or https://)
        if not oauth_token_url.startswith(('http://', 'https://')):
            oauth_token_url = f"https://{oauth_token_url}"
            logging.warning(f"Protocol missing from OAUTH2_URL. Using: {oauth_token_url}")
        
        return oauth_token_url

    @staticmethod
    def get_headers(token: str):
        
        return {
            "X_Introspect_Secret": X_INTROSPECT_SECRET,
            "Authorization": f'Bearer {token}',
            "accept": "application/json",
        }

    @staticmethod
    def handle_response(response):

        if response.status_code == 200:
            return response.json()
        else:
            raise HTTPException(
                status_code=response.status_code,
                detail=response.json()['detail']
            )

    def store_token_inmem_cache(self, opaque_token,data,ttl=None):
        # Fallback to in-memory cache or if Redis failed
        metadata_prefix = "opaque_token_metadata:"
        basic_prefix = "opaque_token:"
        
        metadata_key = hashkey(f"{metadata_prefix}{opaque_token}")
        basic_key = hashkey(f"{basic_prefix}{opaque_token}")
        expiry_time = data.get("exp", int(time.time()) + (ttl or 3600))
        basic_data = {
                "exp": expiry_time,
                "user_id": data.get("user_id", ""),
                "tenant_id": data.get("tenant_id", ""),
                "opaque_token": data.get("opaque_token", ""),
                "active": True
            }
        
        # Store token with active flag
        if isinstance(data, dict):
            data["active"] = True
        
        
        self.cache[metadata_key] = (data, expiry_time)
        self.cache[basic_key] = (basic_data, expiry_time)

        logging.info(
            "Opaque token cached in memory: %s, TTL: %s seconds",
            opaque_token,
            ttl,
        )

        return True

    def store_opaque_token(self, opaque_token, data, ttl=None):
        """
        Store an opaque token mapping to its corresponding data
        
        Args:
            opaque_token: The opaque token string
            data: The data to associate with the token (typically JWT payload)
            ttl: Time to live in seconds, if None uses data["exp"] - current time
        """
        if ttl is None and isinstance(data, dict) and "exp" in data:
            ttl = data["exp"] - int(time.time())
        
        ttl = ttl or 3600  # Default 1 hour
        
        # First try Redis if available
        if self.use_redis:
            result = self.redis_manager.store_token(opaque_token, data, ttl)
            if result:
                return True
        
        # Store token in in-memory cache
        self.store_token_inmem_cache(opaque_token,data,ttl)
        return True

    def get_cached_oauth2_token(self, opaque_token, metadata = True):
        # First try Redis if available
        if self.use_redis:
            # Try to get the full metadata first
            if metadata:
                redis_data = self.redis_manager.get_token_metadata(opaque_token)
                if redis_data:
                    logging.info("Token metadata found in Redis: %s %s", opaque_token, redis_data)
                    return redis_data

            else:
                redis_data = self.redis_manager.get_token_basic_info(opaque_token)
                if redis_data:
                    logging.info("Token basic info found in Redis: %s %s", opaque_token, redis_data)
                    return redis_data

            logging.info("Token data not found in redis")
            return False         
        
        # Fallback to in-memory cache
        metadata_prefix = "opaque_token_metadata:"
        basic_prefix = "opaque_token:"

        if metadata:
            cache_key = hashkey(f"{metadata_prefix}{opaque_token}")
        else:
            cache_key = hashkey(f"{basic_prefix}{opaque_token}")

        cached_item = self.cache.get(cache_key)

        if cached_item:
            response_data, expiry = cached_item
            if time.time() <= expiry:
                logging.info("Returning cached response for token: %s", opaque_token)
                response_data["source"] = "sm-cache"
                return response_data
            else:
                del self.cache[cache_key]
        return None

    def validate_oauth2_token(self, oauth_token, opaque_token=None, use_cache=True, db: Session = None):

        # ------------------------
        # Extract payload
        # ------------------------
        try:
            payload = jwt.decode(oauth_token, SECRET_KEY, algorithms=[ALGORITHM])
            user_id = str(payload.get("user_id"))
            user_type = payload.get("user_type")
        except Exception:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail=ResponseWrapper.error(
                    message="Invalid token payload",
                    error_code="INVALID_TOKEN_PAYLOAD",
                ),
            )

        # Determine session key (employee/driver)
        if user_type == "employee":
            session_key = f"employee_session:{user_id}"
        elif user_type == "driver":
            session_key = f"driver_session:{user_id}"
        else:
            session_key = None

        # ----------------------------------------------
        # 1) CHECK ACTIVE SESSION BEFORE CACHE VALIDATION
        # ----------------------------------------------
        if session_key and opaque_token:
            active_token = self.redis_manager.client.get(session_key)
            if active_token and active_token != opaque_token:
                logging.warning(
                    f"❌ Session mismatch: active={active_token} provided={opaque_token}"
                )
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail=ResponseWrapper.error(
                        message="Session expired due to login on another device",
                        error_code="SESSION_EXPIRED",
                    ),
                )

        # ------------------------
        # 2) Try cache
        # ------------------------
        if use_cache:
            cached_response = self.get_cached_oauth2_token(opaque_token)
            if cached_response:

                if session_key:
                    active_token = self.redis_manager.client.get(session_key)
                    if active_token and active_token != opaque_token:
                        logging.warning("❌ Cached token rejected (other device logged in)")
                        raise HTTPException(
                            status_code=status.HTTP_401_UNAUTHORIZED,
                            detail=ResponseWrapper.error(
                                message="Session expired due to login on another device",
                                error_code="SESSION_EXPIRED",
                            ),
                        )

                logging.info("Cache hit")
                return cached_response

        # -------------------------------------------------
        # 3) Cache miss → direct introspection
        # -------------------------------------------------
        logging.info("Cache miss - calling introspection directly")

        try:
            from app.routes.auth_router import introspect_token_direct

            response_data = introspect_token_direct(oauth_token, db=db)

            # Store if valid
            if response_data:
                expiry_time = response_data.get("exp", int(time.time()) + 3600)
                current_time = int(time.time())
                ttl = max(1, expiry_time - current_time)

                if use_cache:
                    if self.use_redis:
                        self.redis_manager.store_token(opaque_token, response_data, ttl)
                    else:
                        self.store_token_inmem_cache(opaque_token, response_data, ttl)

            # enforce single session again
            if session_key:
                active_token = self.redis_manager.client.get(session_key)
                if active_token and active_token != opaque_token:
                    raise HTTPException(
                        status_code=status.HTTP_401_UNAUTHORIZED,
                        detail=ResponseWrapper.error(
                            message="Session expired due to login on another device",
                            error_code="SESSION_EXPIRED",
                        ),
                    )

            response_data["source"] = "introspect-direct"
            return response_data

        except HTTPException:
            raise
        except ImportError:
            return self._validate_oauth2_token_http(oauth_token, opaque_token, use_cache)
        except Exception as ex:
            logging.error(f"Error validating OAuth token: {ex}", exc_info=True)
            raise HTTPException(
                status_code=500,
                detail="Authentication process failed"
            )

    def _validate_oauth2_token_http(self, oauth_token, opaque_token=None, use_cache=True):
        """Fallback method for external HTTP validation when direct call is not available"""
        try:
            logging.debug("OAUTH2_ENV: %s", OAUTH2_ENV)
            self.validate_env_variables()
            url = self.get_validation_url()
            headers = self.get_headers(oauth_token)
            
            # Add debug logging for the request
            logging.info(f"Making HTTP request to: {url}")
            logging.debug(f"Request headers: {headers}")
            
            import requests
            # Set timeout to avoid hanging requests
            response = requests.post(url, headers=headers, timeout=30.0)
            
            logging.debug(f"Response status: {response.status_code}")
            logging.debug(f"Response headers: {response.headers}")
            
            response_data = self.handle_response(response)
            
            # Only cache if response is 200 and if it contains 'exp'
            if response.status_code == 200:
                # Calculate the expiry time based on the 'exp' field
                expiry_time = response_data.get("exp", int(time.time()) + 3600)
                current_time = int(time.time())

                if expiry_time > current_time:
                    ttl = expiry_time - current_time
                    if use_cache:
                        # Store in Redis if available
                        if self.use_redis:
                            self.redis_manager.store_token(oauth_token, response_data, ttl)
                        else:
                            self.store_token_inmem_cache(oauth_token, response_data, ttl)
                        
                        logging.info(
                            "Response cached for token: %s, TTL: %s seconds",
                            oauth_token,
                            ttl,
                        )

            # Indicate the source is a network call
            response_data["source"] = "introspect-http"
            
            return response_data
        
        except requests.exceptions.ReadTimeout:
            logging.error("Request to OAuth2 server timed out. Server might be down or unreachable.")
            raise HTTPException(
                status_code=503,
                detail=ResponseWrapper.error(
                    message="Authentication server is not responding. Please try again later.",
                    error_code="AUTH_SERVER_UNAVAILABLE",
                ),
            )
            
        except requests.exceptions.ConnectionError as ex:
            logging.error(f"Connection error to OAuth2 server: {str(ex)}")
            raise HTTPException(
                status_code=503,
                detail=ResponseWrapper.error(
                    message="Authentication server is not responding. Please try again later.",
                    error_code="AUTH_SERVER_UNAVAILABLE",
                ),
            )
            
        except Exception as ex:
            logging.error(
                "Error occurred in HTTP validation: %s", str(ex),
                exc_info=True
            )
            raise HTTPException(
                        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                        detail=ResponseWrapper.error(
                            message="Authentication process failed. Please try again or contact support.",
                            error_code="AUTH_PROCESS_FAILED",
                        ),
                    )

    def revoke_token(self, token):
        """Mark a token as inactive/revoked"""
        success = False
        
        # Try Redis first if available
        if self.use_redis:
            success = self.redis_manager.revoke_token(token) or success
        
        # Also try in-memory cache
        cache_key = hashkey(token)
        cached_item = self.cache.get(cache_key)
        if cached_item:
            data, expiry = cached_item
            if isinstance(data, dict):
                data["active"] = False
                self.cache[cache_key] = (data, expiry)
                success = True
        
        return success

    def list_cached_items(self):
        results = []
        
        # First get items from Redis if available
        if self.use_redis:
            redis_results = self.redis_manager.list_tokens()
            results.extend(redis_results)
        
        # Then get in-memory items
        logging.info("Listing cached items:")
        for key, (response_data, expiry_time) in self.cache.items():
            expiry_seconds = expiry_time - time.time()
            results.append({
                "token_hash": str(key),
                "expires_in": expiry_seconds,
                "data": response_data,
                "source": "memory-cache"
            })
        
        return results


def access_token_validator(token, opaque_token, verbosity, use_cache: bool = True, db: Session = None):
    Oauth2AsAccessor.set_verbosity(verbosity)
    accessor = Oauth2AsAccessor()
    return accessor.validate_oauth2_token(token, opaque_token, use_cache=use_cache, db=db)


def validate_bearer_token(use_cache: bool = True):
    async def get_token_data(credentials: HTTPAuthorizationCredentials = Depends(security), db: Session = Depends(get_db)) -> Dict:
        token = credentials.credentials
        
        try:
            # Verify token and extract payload
            payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
            
            logger.debug(f"Token payload: {payload}")
            validation_result = access_token_validator(token, payload.get("opaque_token"), 40, use_cache, db=db)

            logger.debug(f"Validation result from cache: {validation_result}")

            # Get user permissions from validation result
            user_id = validation_result.get("user_id") or payload.get("user_id")
            tenant_id = validation_result.get("tenant_id") or payload.get("tenant_id")
            vendor_id = validation_result.get("vendor_id") or payload.get("vendor_id")
            
            logger.debug(f"User ID: {user_id}, Tenant ID: {tenant_id}")
            
            if not user_id:
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail=ResponseWrapper.error(
                        message="Invalid authentication token",
                        error_code="INVALID_TOKEN",
                    ),
                )

            # Return the token data with permissions from validation result
            return {
                "user_id": user_id,
                "tenant_id": tenant_id,
                "vendor_id": vendor_id,
                "roles": validation_result.get("roles", []),
                "permissions": validation_result.get("permissions", []),
                "user_type": validation_result.get("user_type"),
            }
        
        except HTTPException:
            # 🔥 IMPORTANT: DO NOT WRAP — bubble up original session-expired or invalid-password errors.
            raise
        except PyJWTError as e:
            logger.error(f"JWT validation error: {str(e)}")
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail=ResponseWrapper.error(
                    message="Invalid authentication token",
                    error_code="INVALID_TOKEN",
                ),
            )
        except Exception as e:
            logger.error(f"Unexpected error in token validation: {str(e)}")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=ResponseWrapper.error(
                    message="Internal server error during token validation",
                    error_code="INTERNAL_SERVER_ERROR",
                ),
            )
            
    return get_token_data