import os
import secrets
import time
import logging
import sys
from app.crud.vendor_user import vendor_user_crud
from app.models.admin import Admin
from app.models.driver import Driver
from app.models.tenant import Tenant
from fastapi import APIRouter, Depends, HTTPException, Header, status, Body, Query

from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer, OAuth2PasswordRequestForm
from sqlalchemy.orm import Session, joinedload
from typing import Optional

from sqlalchemy.exc import SQLAlchemyError


from app.database.session import get_db
from app.models import Employee
from app.models.vendor import Vendor
from app.models.vendor_user import VendorUser
from app.schemas.auth import (
    AdminLoginRequest, AdminLoginResponse, LoginRequest, TokenResponse, RefreshTokenRequest, LoginResponse, PasswordResetRequest
)
from app.schemas.driver import DriverResponse
from app.schemas.tenant import TenantResponse
from app.schemas.vendor import VendorResponse
from app.schemas.vendor_user import VendorUserResponse
from common_utils.auth.utils import (
    create_access_token, create_refresh_token, 
    verify_token, hash_password, verify_password
)
from common_utils.auth.token_validation import Oauth2AsAccessor, validate_bearer_token
from app.schemas.employee import EmployeeResponse
from app.crud.employee import employee_crud
from app.crud.admin import admin_crud
from app.crud.driver import driver_crud
from app.core.logging_config import get_logger
from app.utils.response_utils import ResponseWrapper, handle_db_error, handle_http_error

from app.config import settings

# Create a security instance
security = HTTPBearer()

# Configuration - use centralized settings
SECRET_KEY = settings.SECRET_KEY
ALGORITHM = settings.ALGORITHM
TOKEN_EXPIRY_HOURS = settings.TOKEN_EXPIRY_HOURS
X_INTROSPECT_SECRET = settings.X_INTROSPECT_SECRET

import jwt
import hashlib

def hashkey(value: str) -> str:
    """
    Stable key-hashing utility used for in-memory cache keys.
    Returns a hex digest to avoid very long keys and match typical cache hashing behavior.
    """
    if value is None:
        return ""
    return hashlib.sha256(value.encode("utf-8")).hexdigest()

# Use centralized logging configuration
logger = get_logger(__name__)

# Test log to verify logging is working
print(f"AUTH ROUTER: Logger configured - {__name__}", flush=True)
logger.info("🔐 Auth router module loaded successfully")

router = APIRouter(
    prefix="/auth",
    tags=["Authentication"]
)

def employee_to_schema(employee: Employee) -> EmployeeResponse:
    """Convert Employee ORM model to EmployeeResponse Pydantic model"""
    logger.debug(f"Converting employee {employee.employee_id} to schema")
    employee_dict = {
        column.name: getattr(employee, column.name)
        for column in employee.__table__.columns
    }
    return EmployeeResponse(**employee_dict)

def refresh_permissions_from_db(db: Session, user_id: str, user_type: str, tenant_id: str = None, vendor_id: str = None) -> dict:
    """
    Fetch fresh roles and permissions from database when Redis cache expires.
    Called automatically when Redis TTL expires but JWT is still valid.
    
    Returns:
        dict with 'roles' and 'permissions' keys, or raises HTTPException if user not found
    """
    logger.info(f"🔄 Refreshing permissions from DB for {user_type} user_id={user_id}")
    
    try:
        if user_type == "employee":
            from app.models.iam import Role, Policy, Permission
            
            employee = (
                db.query(Employee)
                .options(
                    joinedload(Employee.role)
                    .joinedload(Role.policies)
                    .joinedload(Policy.permissions)
                )
                .filter(Employee.employee_id == int(user_id))
                .first()
            )
            
            if not employee or not employee.is_active:
                logger.warning(f"Employee {user_id} not found or inactive during permission refresh")
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail=ResponseWrapper.error("User not found or inactive", "USER_INACTIVE")
                )
            
            roles = []
            all_permissions = []
            
            # Employee has a single role (many-to-one relationship)
            role = employee.role if hasattr(employee, 'role') else None
            if role and role.is_active and (role.tenant_id == employee.tenant_id or role.is_system_role):
                roles.append(role.name)
                for policy in role.policies:
                        for permission in policy.permissions:
                            module = permission.module
                            action = permission.action
                            
                            existing = next((p for p in all_permissions if p["module"] == module), None)
                            if existing:
                                if action == "*":
                                    existing["action"] = ["create", "read", "update", "delete", "*"]
                                elif action not in existing["action"]:
                                    existing["action"].append(action)
                            else:
                                all_permissions.append({
                                    "module": module,
                                    "action": ["create", "read", "update", "delete", "*"] if action == "*" else [action]
                                })
            
            logger.info(f"✅ Refreshed employee {user_id}: {len(roles)} roles, {len(all_permissions)} permissions")
            return {"roles": roles, "permissions": all_permissions}
        
        elif user_type == "vendor":
            vendor_user = db.query(VendorUser).filter(
                VendorUser.vendor_user_id == int(user_id)
            ).first()
            
            if not vendor_user or not vendor_user.is_active:
                logger.warning(f"Vendor user {user_id} not found or inactive during permission refresh")
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail=ResponseWrapper.error("User not found or inactive", "USER_INACTIVE")
                )
            
            _, roles, all_permissions = vendor_user_crud.get_roles_and_permissions(
                db, vendor_user_id=vendor_user.vendor_user_id, vendor_id=vendor_user.vendor_id
            )
            
            logger.info(f"✅ Refreshed vendor user {user_id}: {len(roles)} roles, {len(all_permissions)} permissions")
            return {"roles": roles, "permissions": all_permissions}
        
        elif user_type == "admin":
            admin = db.query(Admin).filter(Admin.admin_id == int(user_id)).first()
            
            if not admin or not admin.is_active:
                logger.warning(f"Admin {user_id} not found or inactive during permission refresh")
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail=ResponseWrapper.error("User not found or inactive", "USER_INACTIVE")
                )
            
            _, roles, all_permissions = admin_crud.get_admin_roles_and_permissions(
                db, admin_id=admin.admin_id
            )
            
            logger.info(f"✅ Refreshed admin {user_id}: {len(roles)} roles, {len(all_permissions)} permissions")
            return {"roles": roles, "permissions": all_permissions}
        
        elif user_type == "driver":
            driver = db.query(Driver).filter(Driver.driver_id == int(user_id)).first()
            
            if not driver or not driver.is_active:
                logger.warning(f"Driver {user_id} not found or inactive during permission refresh")
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail=ResponseWrapper.error("User not found or inactive", "USER_INACTIVE")
                )
            
            _, roles, all_permissions = driver_crud.get_driver_roles_and_permissions(
                db, driver_id=driver.driver_id, tenant_id=driver.tenant_id
            )
            
            logger.info(f"✅ Refreshed driver {user_id}: {len(roles)} roles, {len(all_permissions)} permissions")
            return {"roles": roles, "permissions": all_permissions}
        
        else:
            logger.error(f"Unknown user_type during permission refresh: {user_type}")
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=ResponseWrapper.error(f"Invalid user type: {user_type}", "INVALID_USER_TYPE")
            )
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to refresh permissions from DB for {user_type} {user_id}: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=ResponseWrapper.error("Failed to refresh permissions", "DB_REFRESH_ERROR")
        )

def introspect_token_direct(token: str, db: Session = None) -> dict:
    """
    Optimized introspection function that validates JWT and returns claims.
    
    Smart caching strategy:
    1. JWT is decoded and validated first (fast, no external calls)
    2. If opaque_token exists, checks Redis cache for session validity
    3. If Redis cache expired but JWT still valid:
       - Fetches fresh permissions from DB
       - Re-caches in Redis with new TTL (15 min)
       - Returns updated permissions
    
    This ensures permissions stay fresh even when Redis cache expires,
    while maintaining performance through caching.
    """
    try:
        # Decode and validate JWT signature and expiration
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        logger.debug(f"Token decoded successfully for user: {payload.get('user_id')}, tenant: {payload.get('tenant_id')}")
        
        # Extract all data from JWT claims
        user_id = payload.get("user_id")
        tenant_id = payload.get("tenant_id")
        vendor_id = payload.get("vendor_id")
        user_type = payload.get("user_type", "employee")
        roles = payload.get("roles", [])
        permissions = payload.get("permissions", [])
        opaque_token = payload.get("opaque_token")
        
        # Basic validation
        if not user_id:
            logger.warning("Token introspection failed - Missing user_id in JWT")
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail=ResponseWrapper.error("Invalid token: missing user_id", "INVALID_TOKEN")
            )
        
        if user_type != "admin" and not tenant_id:
            logger.warning(f"Token introspection failed - Missing tenant_id for non-admin user: {user_id}")
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail=ResponseWrapper.error("Missing tenant_id for employee token", "MISSING_TENANT_ID")
            )
        
        # Check Redis cache and refresh permissions if expired
        permissions_refreshed = False
        if opaque_token:
            oauth_accessor = Oauth2AsAccessor()
            if oauth_accessor.use_redis:
                try:
                    # Check if opaque token exists in Redis
                    token_data = oauth_accessor.get_cached_oauth2_token(opaque_token, metadata=True)
                    
                    if not token_data:
                        # Redis cache expired but JWT is still valid
                        logger.info(f"🔄 Redis cache expired for user {user_id} ({user_type}), refreshing from DB")
                        
                        if db is None:
                            # If DB session not provided, we can't refresh
                            logger.warning(f"Cannot refresh permissions - no DB session provided for user {user_id}")
                        else:
                            # Fetch fresh permissions from database
                            fresh_data = refresh_permissions_from_db(db, user_id, user_type, tenant_id, vendor_id)
                            roles = fresh_data["roles"]
                            permissions = fresh_data["permissions"]
                            permissions_refreshed = True
                            
                            # Re-cache in Redis with new TTL (15 minutes = 900 seconds)
                            current_time = int(time.time())
                            cache_ttl = 900  # 15 minutes
                            
                            refreshed_payload = {
                                "user_id": str(user_id),
                                "roles": roles,
                                "permissions": permissions,
                                "user_type": user_type,
                                "iat": current_time,
                                "exp": current_time + cache_ttl,
                            }
                            
                            if tenant_id:
                                refreshed_payload["tenant_id"] = str(tenant_id)
                            if vendor_id:
                                refreshed_payload["vendor_id"] = str(vendor_id)
                            if opaque_token:
                                refreshed_payload["opaque_token"] = opaque_token
                            
                            # Store refreshed data in Redis
                            oauth_accessor.store_opaque_token(opaque_token, refreshed_payload, cache_ttl)
                            
                            # Also update session key TTL
                            session_key = f"{user_type}_session:{user_id}"
                            oauth_accessor.redis_manager.client.expire(session_key, cache_ttl)
                            
                            logger.info(f"✅ Permissions refreshed and re-cached for user {user_id} ({user_type})")
                    else:
                        # Cache hit - use cached permissions
                        logger.debug(f"📦 Serving permissions from Redis cache for user {user_id}")
                        # Update with cached data if present
                        if "roles" in token_data:
                            roles = token_data["roles"]
                        if "permissions" in token_data:
                            permissions = token_data["permissions"]
                    
                    # Check single-session enforcement
                    session_key = f"{user_type}_session:{user_id}"
                    active_token = oauth_accessor.redis_manager.client.get(session_key)
                    if active_token:
                        if isinstance(active_token, bytes):
                            active_token = active_token.decode()
                        if active_token != opaque_token:
                            logger.warning(f"Session invalidated for user {user_id} - different active token")
                            raise HTTPException(
                                status_code=status.HTTP_401_UNAUTHORIZED,
                                detail=ResponseWrapper.error(
                                    message="Session expired due to login on another device",
                                    error_code="SESSION_EXPIRED"
                                )
                            )
                except HTTPException:
                    raise
                except Exception as redis_err:
                    # Redis errors shouldn't block authentication if JWT is valid
                    logger.warning(f"Redis check failed during introspection for user {user_id}: {redis_err}")
        
        log_msg = f"Token introspection successful for user: {user_id}, user_type: {user_type}, roles: {roles}, permissions: {len(permissions)} modules"
        if permissions_refreshed:
            log_msg += " (refreshed from DB)"
        else:
            log_msg += " (from cache/JWT)"
        logger.info(log_msg)
        
        # Return the token payload
        token_payload = {
            "user_id": str(user_id),
            "roles": roles,
            "permissions": permissions,
            "user_type": user_type,
            "iat": payload.get("iat"),
            "exp": payload.get("exp"),
        }
        
        if opaque_token:
            token_payload["opaque_token"] = opaque_token
        
        if tenant_id:
            token_payload["tenant_id"] = str(tenant_id)
        
        if vendor_id:
            token_payload["vendor_id"] = str(vendor_id)
        
        return token_payload
        
    except jwt.ExpiredSignatureError:
        logger.warning("Token introspection failed - Token expired")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=ResponseWrapper.error("Token expired", "TOKEN_EXPIRED")
        )
    except jwt.InvalidTokenError as e:
        logger.warning(f"Token introspection failed - Invalid JWT: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=ResponseWrapper.error("Invalid token", "INVALID_TOKEN")
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Token introspection failed with unexpected error: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=ResponseWrapper.error("Unexpected error", "UNEXPECTED_ERROR"),
        )

@router.post("/employee/login")
async def employee_login(
    form_data: LoginRequest = Body(...),
    db: Session = Depends(get_db)
):
    """
    Authenticate an employee and return tokens + roles + permissions.
    Enforces single active session per employee: new login invalidates previous session.
    """
    logger.info(f"Employee login attempt for user: {form_data.username} in tenant: {form_data.tenant_id}")

    try:
        # Optimized single query with all necessary joins to prevent N+1 queries
        from app.models.iam import Role, Policy, Permission
        
        employee = (
            db.query(Employee)
            .options(
                joinedload(Employee.tenant),
                joinedload(Employee.team),
                joinedload(Employee.role)
                .joinedload(Role.policies)
                .joinedload(Policy.permissions)
            )
            .filter(
                Employee.email == form_data.username,
                Employee.tenant_id == form_data.tenant_id
            )
            .first()
        )

        if not employee:
            logger.warning(f"Employee login failed - not found: {form_data.username} in tenant {form_data.tenant_id}")
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail=ResponseWrapper.error(
                    message="Incorrect tenant, email, or password",
                    error_code=status.HTTP_401_UNAUTHORIZED,
                ),
            )

        tenant = employee.tenant
        logger.debug(f"Tenant validation successful - ID: {tenant.tenant_id}")
        tenant_details = {
            "tenant_id": tenant.tenant_id,
            "name": tenant.name,
            "address": tenant.address,
            "latitude": tenant.latitude,
            "longitude": tenant.longitude,
            "logo_url": tenant.logo_url if hasattr(tenant, "logo_url") else None,
        }

        # verify password
        if not verify_password(hash_password(form_data.password), employee.password):
            logger.warning(f"🔒 Login failed - Invalid password for employee: {employee.employee_id} ({form_data.username})")
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail=ResponseWrapper.error(
                    message="Incorrect password",
                    error_code=status.HTTP_401_UNAUTHORIZED,
                ),
            )

        # account active checks (using eager-loaded data)
        team_inactive = employee.team and not employee.team.is_active
        if not employee.is_active or not tenant.is_active or team_inactive:
            logger.warning(f"🚫 Login failed - Inactive account for employee: {employee.employee_id} ({form_data.username})")
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=ResponseWrapper.error(
                    message="User account is inactive",
                    error_code="ACCOUNT_INACTIVE",
                ),
            )

        # Extract roles & permissions from eager-loaded data (no additional queries)
        logger.debug(f"Processing roles and permissions for employee: {employee.employee_id} in tenant: {tenant.tenant_id}")
        roles = []
        all_permissions = []
        
        # Process role that is already loaded (single role relationship)
        role = employee.role
        
        if role:
            if role and role.is_active and (role.tenant_id == tenant.tenant_id or role.is_system_role):
                roles.append(role.name)
                
                # Get permissions from role policies (already eager-loaded)
                for policy in role.policies:
                    for permission in policy.permissions:
                        module, action = permission.module, permission.action
                        existing = next((p for p in all_permissions if p["module"] == module), None)
                        if existing:
                            if action == "*":
                                existing["action"] = ["create", "read", "update", "delete", "*"]
                            elif action not in existing["action"]:
                                existing["action"].append(action)
                        else:
                            actions = (
                                ["create", "read", "update", "delete", "*"]
                                if action == "*"
                                else [action]
                            )
                            all_permissions.append({"module": module, "action": actions})
        
        if not roles:
            logger.error(f"No active roles found for employee: {employee.employee_id}")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=ResponseWrapper.error(
                    message="Failed to fetch user roles",
                    error_code=status.HTTP_500_INTERNAL_SERVER_ERROR
                )
            )

        logger.info(f"🎯 Permissions collected for employee {employee.employee_id}: {len(all_permissions)} modules, roles: {roles}")

        # --- Prepare tokens ---
        current_time = int(time.time())
        expiry_time = current_time + (TOKEN_EXPIRY_HOURS * 3600)
        opaque_token = secrets.token_hex(16)

        token_payload = {
            "user_id": str(employee.employee_id),
            "tenant_id": str(employee.tenant_id),
            "opaque_token": opaque_token,
            "roles": roles,
            "permissions": all_permissions,
            "user_type": "employee",
            "iat": current_time,
            "exp": expiry_time,
        }

        # --- Single-session enforcement (new login invalidates old) ---
        oauth_accessor = Oauth2AsAccessor()
        ttl = expiry_time - current_time  # seconds

        employee_session_key = f"employee_session:{employee.employee_id}"
        metadata_prefix = "opaque_token_metadata:"
        basic_prefix = "opaque_token:"

        try:
            if oauth_accessor.use_redis:
                # Redis path
                try:
                    redis_client = oauth_accessor.redis_manager.client
                    old_token = redis_client.get(employee_session_key)
                    if old_token:
                        # ensure string
                        if isinstance(old_token, bytes):
                            old_token = old_token.decode()

                        # delete stored token metadata & basic keys so old token is invalid
                        redis_client.delete(f"{metadata_prefix}{old_token}")
                        redis_client.delete(f"{basic_prefix}{old_token}")
                        # also delete any other possible key forms
                        redis_client.delete(old_token)
                        logger.info(f"Invalidated previous session for employee {employee.employee_id} (old_token={old_token})")
                except Exception as redis_err:
                    # Redis may be flaky — log and continue; we still attempt to store new token
                    logger.warning(f"Redis error while cleaning old session for employee {employee.employee_id}: {redis_err}")

                # store new opaque token mapping + set employee_session pointer
                stored = oauth_accessor.store_opaque_token(opaque_token, token_payload, ttl)
                try:
                    redis_client.setex(employee_session_key, int(ttl), opaque_token)
                except Exception as ex:
                    logger.warning(f"Failed to set employee_session key in redis for {employee.employee_id}: {ex}")

                if not stored:
                    logger.error(f"Failed to store opaque token for employee {employee.employee_id}")
                    raise HTTPException(
                        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                        detail=ResponseWrapper.error("Failed to store authentication token", "TOKEN_STORE_FAILED"),
                    )

            else:
                # In-memory fallback path
                # 1) remove any old session mapping from cache
                try:
                    old_session_val = oauth_accessor.cache.get(f"employee_session:{employee.employee_id}")
                    if old_session_val:
                        # old_session_val could be stored as (opaque_token, expiry) or plain token
                        old_token = old_session_val[0] if isinstance(old_session_val, tuple) else old_session_val
                        # remove associated metadata entries (they are stored using hashkey in store_token_inmem_cache)
                        try:
                            meta_key = hashkey(f"{metadata_prefix}{old_token}")
                            basic_key = hashkey(f"{basic_prefix}{old_token}")
                            if meta_key in oauth_accessor.cache:
                                del oauth_accessor.cache[meta_key]
                            if basic_key in oauth_accessor.cache:
                                del oauth_accessor.cache[basic_key]
                            logger.info(f"Invalidated previous in-memory session for employee {employee.employee_id} (old_token={old_token})")
                        except Exception as ie:
                            logger.warning(f"Error cleaning in-memory old token for employee {employee.employee_id}: {ie}")
                except Exception as ex:
                    logger.warning(f"In-memory session cleanup failed for employee {employee.employee_id}: {ex}")

                # 2) store token in memory via existing accessor method (it will place metadata & basic entries)
                oauth_accessor.store_opaque_token(opaque_token, token_payload, ttl)
                # 3) store employee_session pointer in accessor.cache (simple key)
                try:
                    oauth_accessor.cache[f"employee_session:{employee.employee_id}"] = (opaque_token, current_time + ttl)
                except Exception as ex:
                    logger.warning(f"Failed to set in-memory employee_session pointer for {employee.employee_id}: {ex}")

        except HTTPException:
            # re-raise as-is
            raise
        except Exception as e:
            logger.error(f"Unexpected token storage error for employee {employee.employee_id}: {e}", exc_info=True)
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=ResponseWrapper.error("Failed to complete login (token storage error)", "TOKEN_STORE_ERROR", {"error": str(e)}),
            )

        # --- Build JWT tokens (access/refresh) ---
        access_token = create_access_token(
            user_id=str(employee.employee_id),
            tenant_id=str(employee.tenant_id),
            opaque_token=opaque_token,
            user_type="employee",
        )
        refresh_token = create_refresh_token(
            user_id=str(employee.employee_id),
            user_type="employee",
        )

        logger.info(f"🚀 Login successful for employee: {employee.employee_id} ({employee.email}) in tenant: {tenant.tenant_id}")

        response_data = {
            "access_token": access_token,
            "refresh_token": refresh_token,
            "token_type": "bearer",
            "user": {
                "employee": employee_to_schema(employee),
                "roles": roles,
                "permissions": all_permissions,
                "tenant": tenant_details
            }
        }

        return ResponseWrapper.success(data=response_data, message="Employee login successful")

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Employee login failed with unexpected error: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=ResponseWrapper.error(
                message="Login failed due to server error",
                error_code="SERVER_ERROR",
                details={"error": str(e)},
            ),
        )

@router.post("/vendor/login")
async def vendor_user_login(
    form_data: LoginRequest = Body(...),
    db: Session = Depends(get_db)
):
    """
    Authenticate a vendor user in a tenant and return access/refresh tokens
    """
    logger.info(f"Vendor login attempt for user: {form_data.username} in tenant: {form_data.tenant_id}")

    try:
        vendor_user = (
            db.query(VendorUser)
            .join(Vendor, Vendor.vendor_id == VendorUser.vendor_id)
            .filter(
                VendorUser.email == form_data.username,
                Vendor.tenant_id == form_data.tenant_id
            )
            .first()
        )

        if not vendor_user:
            logger.warning(
                f"Login failed - Vendor user not found or invalid tenant: "
                f"{form_data.username} in tenant_id {form_data.tenant_id}"
            )
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail=ResponseWrapper.error(
                    message="Incorrect tenant, email, or password",
                    error_code=status.HTTP_401_UNAUTHORIZED
                )
            )

        vendor = vendor_user.vendor
        tenant = vendor.tenant
        logger.debug(f"Tenant validation successful - ID: {tenant.tenant_id}")

        if not verify_password(hash_password(form_data.password), vendor_user.password):
            logger.warning(
                f"🔒 Login failed - Invalid password for vendor_user: "
                f"{vendor_user.vendor_user_id} ({form_data.username})"
            )
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail=ResponseWrapper.error(
                    message="Incorrect email or password",
                    error_code=status.HTTP_401_UNAUTHORIZED
                )
            )

        if not vendor_user.is_active or not vendor.is_active or not tenant.is_active:
            logger.warning(
                f"🚫 Login failed - Inactive account for vendor_user: "
                f"{vendor_user.vendor_user_id} ({form_data.username})"
            )
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=ResponseWrapper.error(
                    message="User account is inactive",
                    error_code="ACCOUNT_INACTIVE"
                )
            )

        logger.debug(
            f"Fetching roles and permissions for vendor_user: "
            f"{vendor_user.vendor_user_id} in tenant: {tenant.tenant_id}"
        )
        vendor_user_with_roles, roles, all_permissions = vendor_user_crud.get_roles_and_permissions(
            db, vendor_user_id=vendor_user.vendor_user_id, vendor_id=vendor.vendor_id
        )

        if not vendor_user_with_roles:
            logger.error(f"Failed to fetch vendor_user roles for user: {vendor_user.vendor_user_id}")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=ResponseWrapper.error(
                    message="Failed to fetch user roles",
                    error_code=status.HTTP_500_INTERNAL_SERVER_ERROR
                )
            )

        logger.info(
            f"🎯 Permissions collected for vendor_user {vendor_user.vendor_user_id}: "
            f"{len(all_permissions)} modules, roles: {roles}"
        )

        current_time = int(time.time())
        expiry_time = current_time + (TOKEN_EXPIRY_HOURS * 3600)
        opaque_token = secrets.token_hex(16)

        token_payload = {
            "user_id": str(vendor_user.vendor_user_id),
            "tenant_id": str(tenant.tenant_id),  # 👈 tenant_id instead of vendor_id
            "vendor_id": str(vendor.vendor_id),
            "opaque_token": opaque_token,
            "roles": roles,
            "permissions": all_permissions,
            "user_type": "vendor",
            "iat": current_time,
            "exp": expiry_time,
        }

        oauth_accessor = Oauth2AsAccessor()
        ttl = expiry_time - current_time
        if not oauth_accessor.store_opaque_token(opaque_token, token_payload, 1800):
            logger.error(
                f"💥 Failed to store opaque token in Redis for vendor_user: {vendor_user.vendor_user_id}"
            )
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=ResponseWrapper.error(
                    message="Failed to store authentication token",
                    error_code=status.HTTP_500_INTERNAL_SERVER_ERROR
                )
            )

        logger.debug(f"💾 Opaque token stored in Redis with TTL: {ttl} seconds")

        access_token = create_access_token(
            user_id=str(vendor_user.vendor_user_id),
            tenant_id=str(tenant.tenant_id),  # 👈 use tenant_id
            vendor_id=str(vendor.vendor_id),  # 👈 include vendor_id
            opaque_token=opaque_token,
            user_type="vendor"
        )
        refresh_token = create_refresh_token(
            user_id=str(vendor_user.vendor_user_id),
            user_type="vendor"
        )

        logger.info(
            f"🚀 Login successful for vendor_user: {vendor_user.vendor_user_id} "
            f"({vendor_user.email}) in tenant: {tenant.tenant_id}"
        )

        response_data = {
            "access_token": access_token,
            "refresh_token": refresh_token,
            "token_type": "bearer",
            "user": {"vendor_user": VendorUserResponse.model_validate(vendor_user),
                     "vendor": VendorResponse.model_validate(vendor),
                     "roles": roles,
                     "permissions": all_permissions
                     },
        }

        return ResponseWrapper.success(
            data=response_data,
            message="Vendor user login successful"
        )

    except HTTPException:
        raise
    except Exception as e:
        raise handle_db_error(e)
    except Exception as e:
        logger.error(f"Vendor user login failed with unexpected error: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=ResponseWrapper.error(
                message="Login failed due to server error",
                error_code="SERVER_ERROR",
                details={"error": str(e)}
            )
        )

@router.post("/admin/login")
async def admin_login(
    form_data: AdminLoginRequest = Body(...),
    db: Session = Depends(get_db)
):
    """Admin login endpoint with roles + permissions included"""
    logger.info(f"Admin login attempt for user: {form_data.username}")
    
    try:
        admin = db.query(Admin).filter(Admin.email == form_data.username).first()
        if not admin:
            logger.warning(f"Admin login failed - Admin not found: {form_data.username}")
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail=ResponseWrapper.error(
                    message="Incorrect email or password",
                    error_code=status.HTTP_401_UNAUTHORIZED
                )
            )
        
        if not verify_password(hash_password(form_data.password), admin.password):   
            logger.warning(f"Admin login failed - Invalid password for admin: {admin.admin_id} ({form_data.username})")
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail=ResponseWrapper.error(
                    message="Incorrect email or password", 
                    error_code=status.HTTP_401_UNAUTHORIZED
                )
            )

        if not admin.is_active:
            logger.warning(f"Admin login failed - Inactive account for admin: {admin.admin_id} ({form_data.username})")
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=ResponseWrapper.error(
                    message="Account is inactive",
                    error_code=status.HTTP_403_FORBIDDEN
                )
            )

        logger.debug(f"Fetching roles and permissions for admin: {admin.admin_id}")
        admin_with_roles, roles, all_permissions = admin_crud.get_admin_roles_and_permissions(
            db, admin_id=admin.admin_id
        )

        if not admin_with_roles:
            logger.error(f"Failed to fetch admin roles for admin: {admin.admin_id}")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=ResponseWrapper.error(
                    message="Failed to fetch admin roles",
                    error_code=status.HTTP_500_INTERNAL_SERVER_ERROR
                )
            )

        logger.info(
            f"🎯 Permissions collected for admin {admin.admin_id}: "
            f"{len(all_permissions)} permissions, roles: {roles}"
        )

        opaque_token = secrets.token_hex(16)
        logger.debug(f"Generated opaque token for admin: {admin.admin_id}")

        current_time = int(time.time())
        expiry_time = current_time + (TOKEN_EXPIRY_HOURS * 3600)
        token_payload = {
            "user_id": str(admin.admin_id),
            "user_type": "admin",
            "roles": roles,
            "permissions": all_permissions,
            "opaque_token": opaque_token,
            "iat": current_time,
            "exp": expiry_time,
        }

        oauth_accessor = Oauth2AsAccessor()
        ttl = expiry_time - current_time
        if not oauth_accessor.store_opaque_token(opaque_token, token_payload, ttl):
            logger.error(f"💥 Failed to store opaque token in Redis for admin: {admin.admin_id}")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=ResponseWrapper.error(
                    message="Failed to store authentication token",
                    error_code=status.HTTP_500_INTERNAL_SERVER_ERROR
                )
            )

        logger.debug(f"💾 Opaque token stored in Redis with TTL: {ttl} seconds")

        access_token = create_access_token(
            user_id=str(admin.admin_id),
            opaque_token=opaque_token,
            user_type="admin"
        )
        refresh_token = create_refresh_token(
            user_id=str(admin.admin_id),
            user_type="admin"
        )
        
        logger.info(f"🚀 Admin login successful for admin: {admin.admin_id} ({admin.email})")

        response_data = {
            "access_token": access_token,
            "refresh_token": refresh_token,
            "token_type": "bearer",
            "user": {
                "admin_id": admin.admin_id,
                "email": admin.email,
                "roles": roles,
                "permissions": all_permissions
            }
        }

        return ResponseWrapper.success(
            data=response_data,
            message="Admin login successful"
        )
        
    except HTTPException:
        raise
    except Exception as e:
        raise handle_db_error(e)
    except Exception as e:
        logger.error(f"Admin login failed with unexpected error: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=ResponseWrapper.error(
                message="Login failed due to server error",
                error_code="SERVER_ERROR",
                details={"error": str(e)}
            )
        )


@router.post("/driver/login")
async def driver_login(
    form_data: LoginRequest = Body(...),
    db: Session = Depends(get_db)
):
    """
    Authenticate a driver and return JWT + opaque token + roles + permissions.
    Enforces single active session per driver: new login invalidates previous session.
    """
    logger.info(f"Driver login attempt: {form_data.username}, tenant: {form_data.tenant_id}")

    try:
        # Fetch driver based on tenant + email
        driver = (
            db.query(Driver)
            .join(Vendor, Vendor.vendor_id == Driver.vendor_id)
            .join(Tenant, Tenant.tenant_id == Vendor.tenant_id)
            .filter(
                Driver.email == form_data.username,
                Tenant.tenant_id == form_data.tenant_id
            )
            .first()
        )

        if not driver:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail=ResponseWrapper.error(
                    message="Incorrect tenant, email, or password",
                    error_code=status.HTTP_401_UNAUTHORIZED
                )
            )

        vendor = driver.vendor
        tenant = vendor.tenant
        logger.debug(f"Tenant validation successful - ID: {tenant.tenant_id}")

        # Password verification
        if not verify_password(hash_password(form_data.password), driver.password):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail=ResponseWrapper.error("Incorrect password", "INVALID_PASSWORD")
            )

        # Active status check
        if not driver.is_active or not vendor.is_active or not tenant.is_active:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=ResponseWrapper.error("User account is inactive", "ACCOUNT_INACTIVE")
            )

        # Roles & permissions
        driver_with_roles, roles, all_permissions = driver_crud.get_driver_roles_and_permissions(
            db, driver_id=driver.driver_id, tenant_id=tenant.tenant_id
        )
        if not driver_with_roles:
            raise HTTPException(
                status_code=500,
                detail=ResponseWrapper.error("Failed to fetch roles", "ROLE_FETCH_ERROR")
            )

        # Prepare tokens
        current_time = int(time.time())
        expiry_time = current_time + (TOKEN_EXPIRY_HOURS * 3600)
        opaque_token = secrets.token_hex(16)

        token_payload = {
            "user_id": str(driver.driver_id),
            "tenant_id": str(tenant.tenant_id),
            "vendor_id": str(vendor.vendor_id),
            "opaque_token": opaque_token,
            "roles": roles,
            "permissions": all_permissions,
            "user_type": "driver",
            "iat": current_time,
            "exp": expiry_time,
        }

        # ================================
        # 🔥 SINGLE SESSION ENFORCEMENT
        # ================================
        oauth_accessor = Oauth2AsAccessor()
        ttl = expiry_time - current_time

        driver_session_key = f"driver_session:{driver.driver_id}"
        metadata_prefix = "opaque_token_metadata:"
        basic_prefix = "opaque_token:"

        try:
            if oauth_accessor.use_redis:
                redis_client = oauth_accessor.redis_manager.client

                # Delete old session token if exists
                try:
                    old_token = redis_client.get(driver_session_key)
                    if old_token:
                        if isinstance(old_token, bytes):
                            old_token = old_token.decode()
                        redis_client.delete(f"{metadata_prefix}{old_token}")
                        redis_client.delete(f"{basic_prefix}{old_token}")
                        redis_client.delete(old_token)
                        logger.info(f"Invalidated previous session for driver {driver.driver_id} (old_token={old_token})")
                except Exception as redis_err:
                    logger.warning(f"Redis cleanup failed for driver {driver.driver_id}: {redis_err}")

                # Store new token
                stored = oauth_accessor.store_opaque_token(opaque_token, token_payload, ttl)
                try:
                    redis_client.setex(driver_session_key, int(ttl), opaque_token)
                except Exception as ex:
                    logger.warning(f"Failed to store driver_session pointer for driver {driver.driver_id}: {ex}")

                if not stored:
                    raise HTTPException(
                        status_code=500,
                        detail=ResponseWrapper.error("Failed to store authentication token", "TOKEN_STORE_FAILED")
                    )

            else:
                # In-memory fallback
                try:
                    old_session_val = oauth_accessor.cache.get(driver_session_key)
                    if old_session_val:
                        old_token = old_session_val[0] if isinstance(old_session_val, tuple) else old_session_val
                        try:
                            meta_key = hashkey(f"{metadata_prefix}{old_token}")
                            basic_key = hashkey(f"{basic_prefix}{old_token}")
                            if meta_key in oauth_accessor.cache:
                                del oauth_accessor.cache[meta_key]
                            if basic_key in oauth_accessor.cache:
                                del oauth_accessor.cache[basic_key]
                            logger.info(f"Invalidated old in-memory session for driver {driver.driver_id}")
                        except Exception:
                            pass
                except Exception:
                    pass

                oauth_accessor.store_opaque_token(opaque_token, token_payload, ttl)

                try:
                    oauth_accessor.cache[driver_session_key] = (opaque_token, current_time + ttl)
                except Exception:
                    pass

        except Exception as e:
            logger.error(f"Single-session storage failed for driver {driver.driver_id}: {e}", exc_info=True)
            raise HTTPException(
                status_code=500,
                detail=ResponseWrapper.error("Login failed (session error)", "SESSION_ERROR", {"error": str(e)})
            )

        # Generate access/refresh tokens
        access_token = create_access_token(
            user_id=str(driver.driver_id),
            tenant_id=str(tenant.tenant_id),
            vendor_id=str(vendor.vendor_id),
            opaque_token=opaque_token,
            user_type="driver"
        )
        refresh_token = create_refresh_token(
            user_id=str(driver.driver_id),
            user_type="driver"
        )

        logger.info(f"🚀 Login successful for driver {driver.driver_id} ({driver.email}) in tenant {tenant.tenant_id}")

        return ResponseWrapper.success(
            data={
                "access_token": access_token,
                "refresh_token": refresh_token,
                "token_type": "bearer",
                "user": {
                    "driver": DriverResponse.model_validate(driver),
                    "tenant": TenantResponse.model_validate(tenant),
                    "roles": roles,
                    "permissions": all_permissions,
                },
            },
            message="Driver login successful",
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Driver login failed: {e}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail=ResponseWrapper.error(
                message="Login failed due to server error",
                error_code="SERVER_ERROR",
                details={"error": str(e)}
            )
        )

@router.post("/introspect")
async def introspect(x_introspect_secret: str = Header(...,alias="X_Introspect_Secret"), authorization: HTTPAuthorizationCredentials = Depends(security), db: Session = Depends(get_db)):
    """
    Validate and introspect a token, returning its associated data if valid.
    Now supports automatic permission refresh from DB when Redis cache expires.
    """
    logger.debug("Token introspection request received")
    
    if x_introspect_secret != X_INTROSPECT_SECRET:
        logger.warning(f"Introspection failed - Invalid introspect secret provided")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="You are not authorized"
        )
    
    return introspect_token_direct(authorization.credentials, db=db)

# @router.post("/refresh-token", response_model=TokenResponse)
# async def refresh_token(
#     refresh_req: RefreshTokenRequest,
#     db: Session = Depends(get_db)
# ):
#     """
#     Use refresh token to get a new access token
#     """
#     logger.info("Refresh token request received")
    
#     try:
#         payload = verify_token(refresh_req.refresh_token)
#         logger.debug(f"Refresh token verified for user: {payload.get('user_id')}")
        
#         if payload.get("token_type") != "refresh":
#             logger.warning("Refresh token validation failed - Invalid token type")
#             raise HTTPException(
#                 status_code=status.HTTP_401_UNAUTHORIZED,
#                 detail="Invalid refresh token"
#             )
        
#         user_id = payload.get("user_id")
#         if not user_id:
#             logger.warning("Refresh token validation failed - Missing user_id")
#             raise HTTPException(
#                 status_code=status.HTTP_401_UNAUTHORIZED,
#                 detail="Invalid refresh token"
#             )
        
#         employee = db.query(Employee).filter(Employee.employee_id == int(user_id)).first()
#         if not employee:
#             logger.warning(f"Refresh token failed - Employee not found: {user_id}")
#             raise HTTPException(
#                 status_code=status.HTTP_401_UNAUTHORIZED,
#                 detail="User not found or inactive"
#             )
        
#         if not employee.is_active:
#             logger.warning(f"Refresh token failed - Inactive employee: {user_id}")
#             raise HTTPException(
#                 status_code=status.HTTP_401_UNAUTHORIZED,
#                 detail="User not found or inactive"
#             )
            
#         logger.debug(f"Fetching updated permissions for refresh token - employee: {employee.employee_id}")
        
#         user_roles = user_role_crud.get_by_user_and_tenant(
#             db, user_id=employee.employee_id, tenant_id=employee.tenant_id
#         )
        
#         roles = []
#         all_permissions = []
        
#         for user_role in user_roles:
#             roles.append(user_role.role.name)
            
#             for policy in user_role.role.policies:
#                 for permission in policy.permissions:
#                     module = permission.module
#                     action = permission.action
                    
#                     existing_module = next(
#                         (p for p in all_permissions if p["module"] == module),
#                         None
#                     )
                    
#                     if existing_module:
#                         if action == "*":
#                             existing_module["action"] = ["create", "read", "update", "delete", "*"]
#                         elif action not in existing_module["action"]:
#                             existing_module["action"].append(action)
#                     else:
#                         if action == "*":
#                             actions = ["create", "read", "update", "delete", "*"]
#                         else:
#                             actions = [action]
                            
#                         all_permissions.append({
#                             "module": module,
#                             "action": actions
#                         })
        
#         new_access_token = create_access_token(
#             user_id=str(employee.employee_id),
#             tenant_id=str(employee.tenant_id),
#             roles=roles,
#             permissions=all_permissions
#         )
        
#         new_refresh_token = create_refresh_token(user_id=str(employee.employee_id))
        
#         logger.info(f"Refresh token successful for employee: {employee.employee_id} ({employee.email})")
        
#         return TokenResponse(
#             access_token=new_access_token,
#             refresh_token=new_refresh_token,
#             token_type="bearer"
#         )
#     except Exception as e:
#         logger.error(f"Refresh token failed with error: {str(e)}")
#         raise HTTPException(
#             status_code=status.HTTP_401_UNAUTHORIZED,
#             detail=f"Invalid refresh token: {str(e)}"
#         )

@router.post("/reset-password", status_code=status.HTTP_200_OK)
async def reset_password(
    reset_req: PasswordResetRequest,
    db: Session = Depends(get_db)
):
    """
    Reset employee password
    """
    logger.info(f"Password reset request for email: {reset_req.email}")
    
    employee = db.query(Employee).filter(Employee.email == reset_req.email).first()
    
    if not employee:
        logger.info(f"Password reset requested for non-existent email: {reset_req.email}")
        return {"message": "If your email is registered, you will receive a password reset link."}
    
    logger.info(f"Password reset email would be sent to employee: {employee.employee_id} ({reset_req.email})")
    
    return {"message": "If your email is registered, you will receive a password reset link."}

@router.get("/me", response_model=dict, status_code=status.HTTP_200_OK)
async def get_current_user_profile(
    db: Session = Depends(get_db),
    token_data: dict = Depends(validate_bearer_token())
):
    """
    Get the current authenticated user's profile (admin, employee, or vendor)
    with roles and permissions.
    """
    user_id = token_data.get("user_id")
    user_type = token_data.get("user_type")

    logger.debug(f"Profile request for user: {user_id} ({user_type})")

    if not user_id or not user_type:
        logger.warning("Profile request failed - Missing user_id or user_type in token")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=ResponseWrapper.error(
                message="Could not validate credentials",
                error_code=status.HTTP_401_UNAUTHORIZED,
            ),
        )

    try:
        if user_type == "employee":
            employee = employee_crud.get(db, id=int(user_id))
            if not employee:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail=ResponseWrapper.error(
                        message="Employee not found",
                        error_code=status.HTTP_404_NOT_FOUND,
                    ),
                )

            _, roles, permissions = employee_crud.get_employee_roles_and_permissions(
                db, employee_id=employee.employee_id, tenant_id=employee.tenant_id
            )

            response_data = {
                "user_type": "employee",
                "user": employee_to_schema(employee),
                "roles": roles,
                "permissions": permissions,
            }

        elif user_type == "vendor":
            vendor_user = db.query(VendorUser).filter(
                VendorUser.vendor_user_id == int(user_id)
            ).first()
            if not vendor_user:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail=ResponseWrapper.error(
                        message="Vendor user not found",
                        error_code=status.HTTP_404_NOT_FOUND,
                    ),
                )

            _, roles, permissions = vendor_user_crud.get_roles_and_permissions(
                db, vendor_user_id=vendor_user.vendor_user_id, vendor_id=vendor_user.vendor_id
            )

            response_data = {
                "user_type": "vendor",
                "user": VendorUserResponse.model_validate(vendor_user),
                "roles": roles,
                "permissions": permissions,
            }

        elif user_type == "admin":
            admin = db.query(Admin).filter(Admin.admin_id == int(user_id)).first()
            if not admin:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail=ResponseWrapper.error(
                        message="Admin not found",
                        error_code=status.HTTP_404_NOT_FOUND,
                    ),
                )

            _, roles, permissions = admin_crud.get_admin_roles_and_permissions(
                db, admin_id=admin.admin_id
            )

            response_data = {
                "user_type": "admin",
                "user": {
                    "admin_id": admin.admin_id,
                    "email": admin.email,
                },
                "roles": roles,
                "permissions": permissions,
            }

        elif user_type == "driver":
            driver = db.query(Driver).filter(Driver.driver_id == int(user_id)).first()
            if not driver:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail=ResponseWrapper.error(
                        message="Driver not found",
                        error_code=status.HTTP_404_NOT_FOUND,
                    ),
                )

            # Get driver roles and permissions
            from app.crud.driver import driver_crud
            _, roles, permissions = driver_crud.get_driver_roles_and_permissions(
                db, driver_id=driver.driver_id, tenant_id=driver.tenant_id
            )

            response_data = {
                "user_type": "driver",
                "user": {
                    "driver_id": driver.driver_id,
                    "name": driver.name,
                    "email": driver.email,
                    "phone": driver.phone,
                    "vendor_id": driver.vendor_id,
                    "tenant_id": driver.tenant_id,
                },
                "roles": roles,
                "permissions": permissions,
            }

        else:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=ResponseWrapper.error(
                    message=f"Unsupported user_type: {user_type}",
                    error_code="INVALID_USER_TYPE",
                ),
            )

        logger.info(f"✅ /me resolved for {user_type} {user_id}")

        return ResponseWrapper.success(
            data=response_data,
            message="Profile retrieved successfully"
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"💥 Failed to load /me profile: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=ResponseWrapper.error(
                message="Failed to fetch profile",
                error_code="SERVER_ERROR",
                details={"error": str(e)},
            ),
        )


@router.post("/driver/new/login")
async def driver_login_initial(
    license_number: str = Body(...),
    password: str = Body(...),
    db: Session = Depends(get_db)
):
    try:
        license_number = license_number.strip()
        password = password.strip()
        logger.info(f"Driver login attempt via DL={license_number}")

        # Fetch all driver entries with same DL
        drivers = (
            db.query(Driver)
            .join(Vendor, Vendor.vendor_id == Driver.vendor_id)
            .join(Tenant, Tenant.tenant_id == Vendor.tenant_id)
            .filter(Driver.license_number == license_number)
            .all()
        )

        if not drivers:
            raise HTTPException(
                status_code=401,
                detail=ResponseWrapper.error("Invalid DL or password", "INVALID_LOGIN")
            )

        # Validate password on FIRST matching record
        driver = drivers[0]
        if not verify_password(hash_password(password), driver.password):
            raise HTTPException(
                status_code=401,
                detail=ResponseWrapper.error("Invalid password", "INVALID_PASSWORD")
            )

        # Build accounts list
        accounts = []
        for d in drivers:
            v, t = d.vendor, d.vendor.tenant
            accounts.append({
                "driver_id": d.driver_id,
                "vendor_id": v.vendor_id,
                "vendor_name": v.name,
                "tenant_id": t.tenant_id,
                "tenant_name": t.name
            })

        # TEMP TOKEN MUST NOT contain driver_id
        temp_payload = {
            "license_number": driver.license_number,
            "type": "driver_temp_login",
            "iat": int(time.time()),
            "exp": int(time.time()) + 300,
        }
        temp_token = jwt.encode(temp_payload, SECRET_KEY, algorithm=ALGORITHM)

        # STORE TEMP TOKEN (ONE TIME USE)
        redis_client = Oauth2AsAccessor().redis_manager.client
        temp_key = f"temp_driver_login:{driver.license_number}"
        redis_client.setex(temp_key, 300, temp_token)


        return ResponseWrapper.success(
            message="Select vendor/tenant to continue",
            data={
                "temp_token": temp_token,
                "driver": {
                    "name": driver.name,
                    "license_number": driver.license_number,
                    "phone": driver.phone,
                    "email": driver.email,
                },
                "accounts": accounts
            }
        )

    except HTTPException:
        db.rollback()
        raise
    except SQLAlchemyError as e:
        db.rollback()
        raise handle_db_error(e)
    except Exception as e:
        db.rollback()
        raise handle_http_error(e)


@router.post("/driver/login/confirm")
async def driver_login_confirm(
    temp_token: str = Body(...),
    tenant_id: str = Body(...),
    vendor_id: int = Body(...),
    db: Session = Depends(get_db)
):
    try:
        # =====================================================
        # 1. Decode temp token
        # =====================================================
        try:
            temp_payload = jwt.decode(temp_token, SECRET_KEY, algorithms=[ALGORITHM])
            if temp_payload.get("type") != "driver_temp_login":
                raise ValueError("Invalid token type")
            license_number = temp_payload["license_number"]
        except Exception:
            raise HTTPException(
                status_code=401,
                detail=ResponseWrapper.error("Invalid or expired temporary token", "INVALID_TEMP_TOKEN")
            )

        # =====================================================
        # 2. Validate temp token from Redis (ONE-TIME USE)
        # =====================================================
        redis_client = Oauth2AsAccessor().redis_manager.client
        temp_key = f"temp_driver_login:{license_number}"
        saved_temp = redis_client.get(temp_key)

        if not saved_temp:
            raise HTTPException(
                status_code=401,
                detail=ResponseWrapper.error(
                    "Temporary token expired or already used",
                    "TEMP_TOKEN_INVALID"
                )
            )

        # ✔ Normalize type (bytes → str)
        if isinstance(saved_temp, bytes):
            saved_temp = saved_temp.decode()
        else:
            saved_temp = str(saved_temp)

        # Compare stored temp token with input token
        if saved_temp != temp_token:
            raise HTTPException(
                status_code=401,
                detail=ResponseWrapper.error(
                    "Temporary token mismatch",
                    "TEMP_TOKEN_INVALID"
                )
            )

        # ✔ DELETE TEMP TOKEN NOW — cannot reuse
        redis_client.delete(temp_key)


        # =====================================================
        # 3. Fetch EXACT driver row for selected vendor/tenant
        # =====================================================
        driver = (
            db.query(Driver)
            .join(Vendor, Vendor.vendor_id == Driver.vendor_id)
            .join(Tenant, Tenant.tenant_id == Vendor.tenant_id)
            .filter(
                Driver.license_number == license_number,
                Vendor.vendor_id == vendor_id,
                Tenant.tenant_id == tenant_id
            )
            .first()
        )

        if not driver:
            raise HTTPException(
                status_code=404,
                detail=ResponseWrapper.error("Invalid selection", "INVALID_ACCOUNT")
            )

        vendor = driver.vendor
        tenant = vendor.tenant

        # =====================================================
        # 4. Active checks
        # =====================================================
        if not driver.is_active or not vendor.is_active or not tenant.is_active:
            raise HTTPException(
                status_code=403,
                detail=ResponseWrapper.error("Account inactive", "ACCOUNT_INACTIVE")
            )

        # =====================================================
        # 5. Roles + permissions
        # =====================================================
        driver_with_roles, roles, all_permissions = driver_crud.get_driver_roles_and_permissions(
            db,
            driver_id=driver.driver_id,
            tenant_id=tenant.tenant_id
        )

        if not driver_with_roles:
            raise HTTPException(
                status_code=500,
                detail=ResponseWrapper.error("Failed to fetch roles", "ROLE_FETCH_ERROR")
            )

        # =====================================================
        # 6. Generate final JWT + Opaque token
        # =====================================================
        current_time = int(time.time())
        expiry_time = current_time + (TOKEN_EXPIRY_HOURS * 3600)
        opaque_token = secrets.token_hex(16)

        token_payload = {
            "user_id": str(driver.driver_id),
            "tenant_id": str(tenant.tenant_id),
            "vendor_id": str(vendor.vendor_id),
            "opaque_token": opaque_token,
            "roles": roles,
            "permissions": all_permissions,
            "user_type": "driver",
            "iat": current_time,
            "exp": expiry_time,
        }

        # =====================================================
        # 7. SINGLE SESSION ENFORCEMENT
        # =====================================================
        oauth_accessor = Oauth2AsAccessor()
        ttl = expiry_time - current_time

        session_key = f"driver_session:{driver.driver_id}"
        meta_prefix = "opaque_token_metadata:"
        basic_prefix = "opaque_token:"

        try:
            if oauth_accessor.use_redis:
                r = oauth_accessor.redis_manager.client

                # Delete previous active session
                old_token = r.get(session_key)
                if old_token:
                    old_token = old_token.decode() if isinstance(old_token, bytes) else old_token
                    r.delete(f"{meta_prefix}{old_token}")
                    r.delete(f"{basic_prefix}{old_token}")
                    r.delete(old_token)

                # Store new session token
                stored = oauth_accessor.store_opaque_token(opaque_token, token_payload, ttl)
                r.setex(session_key, ttl, opaque_token)

                if not stored:
                    raise HTTPException(
                        status_code=500,
                        detail=ResponseWrapper.error(
                            "Failed to store authentication token",
                            "TOKEN_STORE_FAILED"
                        )
                    )

        except Exception as e:
            raise HTTPException(
                status_code=500,
                detail=ResponseWrapper.error("Login failed (session error)", "SESSION_ERROR", {"error": str(e)})
            )

        # =====================================================
        # 8. Final Access/Refresh JWT generation
        # =====================================================
        access_token = create_access_token(
            user_id=str(driver.driver_id),
            tenant_id=str(tenant.tenant_id),
            vendor_id=str(vendor.vendor_id),
            opaque_token=opaque_token,
            user_type="driver"
        )

        refresh_token = create_refresh_token(
            user_id=str(driver.driver_id),
            user_type="driver"
        )

        # =====================================================
        # 9. Response
        # =====================================================
        return ResponseWrapper.success(
            message="Driver login successful",
            data={
                "access_token": access_token,
                "refresh_token": refresh_token,
                "token_type": "bearer",
                "user": {
                    "driver": DriverResponse.model_validate(driver),
                    "tenant": TenantResponse.model_validate(tenant),
                    "roles": roles,
                    "permissions": all_permissions,
                },
            }
        )

    except HTTPException:
        db.rollback()
        raise
    except SQLAlchemyError as e:
        db.rollback()
        raise handle_db_error(e)
    except Exception as e:
        db.rollback()
        raise handle_http_error(e)


@router.post("/driver/switch-company")
async def driver_switch_company(
    tenant_id: str = Body(...),
    vendor_id: int = Body(...),
    db: Session = Depends(get_db),
    token_data: dict = Depends(validate_bearer_token())
):
    """
    Allow an authenticated driver to switch to another company.
    Requires current valid access token + new company selection.
    Invalidates old token and generates new one for selected company.
    """
    try:
        # =====================================================
        # 1. Extract driver info from current token
        # =====================================================
        current_driver_id = int(token_data.get("user_id"))
        current_tenant_id = token_data.get("tenant_id")
        current_vendor_id = token_data.get("vendor_id")
        user_type = token_data.get("user_type")

        if user_type != "driver":
            raise HTTPException(
                status_code=403,
                detail=ResponseWrapper.error("Only drivers can switch companies", "INVALID_USER_TYPE")
            )

        logger.info(f"Driver {current_driver_id} switching from company {current_vendor_id} to {vendor_id}")

        # =====================================================
        # 2. Fetch current driver to get license number
        # =====================================================
        current_driver = db.query(Driver).filter(
            Driver.driver_id == current_driver_id
        ).first()

        if not current_driver:
            raise HTTPException(
                status_code=404,
                detail=ResponseWrapper.error("Driver not found", "DRIVER_NOT_FOUND")
            )

        license_number = current_driver.license_number

        # =====================================================
        # 3. Fetch target driver record for new company
        # =====================================================
        driver = (
            db.query(Driver)
            .join(Vendor, Vendor.vendor_id == Driver.vendor_id)
            .join(Tenant, Tenant.tenant_id == Vendor.tenant_id)
            .filter(
                Driver.license_number == license_number,
                Vendor.vendor_id == vendor_id,
                Tenant.tenant_id == tenant_id
            )
            .first()
        )

        if not driver:
            raise HTTPException(
                status_code=404,
                detail=ResponseWrapper.error("Invalid company selection", "INVALID_ACCOUNT")
            )

        vendor = driver.vendor
        tenant = vendor.tenant

        # =====================================================
        # 4. Active checks
        # =====================================================
        if not driver.is_active or not vendor.is_active or not tenant.is_active:
            raise HTTPException(
                status_code=403,
                detail=ResponseWrapper.error("Account inactive", "ACCOUNT_INACTIVE")
            )

        # =====================================================
        # 5. Roles + permissions for new company
        # =====================================================
        driver_with_roles, roles, all_permissions = driver_crud.get_driver_roles_and_permissions(
            db,
            driver_id=driver.driver_id,
            tenant_id=tenant.tenant_id
        )

        if not driver_with_roles:
            raise HTTPException(
                status_code=500,
                detail=ResponseWrapper.error("Failed to fetch roles", "ROLE_FETCH_ERROR")
            )

        # =====================================================
        # 6. Generate NEW token for new company
        # =====================================================
        current_time = int(time.time())
        expiry_time = current_time + (TOKEN_EXPIRY_HOURS * 3600)
        opaque_token = secrets.token_hex(16)

        token_payload = {
            "user_id": str(driver.driver_id),
            "tenant_id": str(tenant.tenant_id),
            "vendor_id": str(vendor.vendor_id),
            "opaque_token": opaque_token,
            "roles": roles,
            "permissions": all_permissions,
            "user_type": "driver",
            "iat": current_time,
            "exp": expiry_time,
        }

        # =====================================================
        # 7. SINGLE SESSION ENFORCEMENT - Delete old session
        # =====================================================
        oauth_accessor = Oauth2AsAccessor()
        ttl = expiry_time - current_time

        session_key = f"driver_session:{driver.driver_id}"
        meta_prefix = "opaque_token_metadata:"
        basic_prefix = "opaque_token:"

        try:
            if oauth_accessor.use_redis:
                r = oauth_accessor.redis_manager.client

                # Delete previous active session from OLD company
                old_token = r.get(session_key)
                if old_token:
                    old_token = old_token.decode() if isinstance(old_token, bytes) else old_token
                    r.delete(f"{meta_prefix}{old_token}")
                    r.delete(f"{basic_prefix}{old_token}")
                    r.delete(old_token)
                    logger.info(f"Invalidated previous session for driver {driver.driver_id}")

                # Store new session token for NEW company
                stored = oauth_accessor.store_opaque_token(opaque_token, token_payload, ttl)
                r.setex(session_key, ttl, opaque_token)

                if not stored:
                    raise HTTPException(
                        status_code=500,
                        detail=ResponseWrapper.error(
                            "Failed to store authentication token",
                            "TOKEN_STORE_FAILED"
                        )
                    )

        except Exception as e:
            raise HTTPException(
                status_code=500,
                detail=ResponseWrapper.error("Switch failed (session error)", "SESSION_ERROR", {"error": str(e)})
            )

        # =====================================================
        # 8. UPDATE last-used company to new selection
        # =====================================================
        try:
            last_company_key = f"driver_last_company:{license_number}"
            last_company_value = f"{vendor.vendor_id}:{tenant.tenant_id}"
            redis_client = oauth_accessor.redis_manager.client
            redis_client.setex(last_company_key, 30 * 24 * 3600, last_company_value)
            logger.info(f"Updated last company for driver {license_number}: {last_company_value}")
        except Exception as e:
            logger.warning(f"Failed to update last company for driver {license_number}: {e}")

        # =====================================================
        # 9. Generate NEW access/refresh tokens
        # =====================================================
        access_token = create_access_token(
            user_id=str(driver.driver_id),
            tenant_id=str(tenant.tenant_id),
            vendor_id=str(vendor.vendor_id),
            opaque_token=opaque_token,
            user_type="driver"
        )

        refresh_token = create_refresh_token(
            user_id=str(driver.driver_id),
            user_type="driver"
        )

        # =====================================================
        # 10. Response
        # =====================================================
        logger.info(f"🔄 Driver {driver.driver_id} switched to company {vendor.vendor_id} ({tenant.tenant_id})")
        
        return ResponseWrapper.success(
            message="Company switched successfully",
            data={
                "access_token": access_token,
                "refresh_token": refresh_token,
                "token_type": "bearer",
                "user": {
                    "driver": DriverResponse.model_validate(driver),
                    "tenant": TenantResponse.model_validate(tenant),
                    "roles": roles,
                    "permissions": all_permissions,
                },
            }
        )

    except HTTPException:
        db.rollback()
        raise
    except SQLAlchemyError as e:
        db.rollback()
        raise handle_db_error(e)
    except Exception as e:
        db.rollback()
        logger.error(f"Company switch failed: {e}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail=ResponseWrapper.error(
                message="Company switch failed due to server error",
                error_code="SERVER_ERROR",
                details={"error": str(e)}
            )
        )
