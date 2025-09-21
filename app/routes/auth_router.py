import os
import secrets
import time
import logging
import sys
from app.crud.vendor_user import vendor_user_crud
from app.models.admin import Admin
from app.models.tenant import Tenant
from fastapi import APIRouter, Depends, HTTPException, Header, status, Body, Query

from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer, OAuth2PasswordRequestForm
from sqlalchemy.orm import Session
from typing import Optional

from app.database.session import get_db
from app.models import Employee
from app.models.vendor import Vendor
from app.models.vendor_user import VendorUser
from app.schemas.auth import (
    AdminLoginRequest, AdminLoginResponse, LoginRequest, TokenResponse, RefreshTokenRequest, LoginResponse, PasswordResetRequest
)
from app.schemas.vendor_user import VendorUserResponse
from common_utils.auth.utils import (
    create_access_token, create_refresh_token, 
    verify_token, hash_password, verify_password
)
from common_utils.auth.token_validation import Oauth2AsAccessor, validate_bearer_token
from app.schemas.employee import EmployeeResponse
from app.crud.employee import employee_crud
from app.crud.admin import admin_crud
from app.core.logging_config import get_logger
from app.utils.response_utils import ResponseWrapper, handle_db_error

from app.config import settings

# Create a security instance
security = HTTPBearer()

# Configuration - use centralized settings
SECRET_KEY = settings.SECRET_KEY
ALGORITHM = settings.ALGORITHM
TOKEN_EXPIRY_HOURS = settings.TOKEN_EXPIRY_HOURS
X_INTROSPECT_SECRET = settings.X_INTROSPECT_SECRET

import jwt

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

def introspect_token_direct(token: str) -> dict:
    """
    Direct introspection function that can be called internally without HTTP overhead.
    This function performs the same logic as the HTTP introspection endpoint.
    """
    db = next(get_db())  # Get actual database session
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        logger.debug(f"Token decoded successfully for user: {payload.get('user_id')}, tenant: {payload.get('tenant_id')}")
    except jwt.InvalidTokenError as e:
        logger.warning(f"Token introspection failed - Invalid JWT: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token"
        )
    finally:
        db.close()  # Ensure session is closed
    
    db = next(get_db())  # Get new session for database operations
    try:
        user_id = payload.get("user_id")
        tenant_id = payload.get("tenant_id")
        user_type = payload.get("user_type")  # Get token context from JWT
        
        logger.debug(f"Fetching roles and permissions for introspection - user: {user_id}, tenant: {tenant_id}, context: {user_type}")
        
        if user_type == "admin":
            admin = db.query(Admin).filter(Admin.admin_id == int(user_id)).first()
            if not admin:
                logger.warning(f"Introspection failed - Admin not found: {user_id}")
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail="User not found"
                )
            
            if not admin.is_active:
                logger.warning(f"Introspection failed - Inactive admin: {user_id}")
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail="User account is inactive"
                )
            
            admin_with_roles, roles, all_permissions = admin_crud.get_admin_roles_and_permissions(
                db, admin_id=admin.admin_id
            )
            
            if not admin_with_roles:
                logger.error(f"Failed to fetch admin roles for admin: {admin.admin_id}")
                raise HTTPException(
                    status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                    detail="Failed to fetch user roles"
                )
        else:
            if not tenant_id:
                logger.warning(f"Introspection failed - Missing tenant_id for employee context: {user_id}")
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail="Invalid token - missing tenant information"
                )
            
            employee = db.query(Employee).filter(
                Employee.employee_id == int(user_id),
                Employee.tenant_id == tenant_id
            ).first()
            
            if not employee:
                logger.warning(f"Introspection failed - Employee not found: {user_id} in tenant: {tenant_id}")
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail="User not found"
                )
            
            if not employee.is_active:
                logger.warning(f"Introspection failed - Inactive employee: {user_id}")
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail="User account is inactive"
                )
            
            employee_with_roles, roles, all_permissions = employee_crud.get_employee_roles_and_permissions(
                db, employee_id=employee.employee_id, tenant_id=tenant_id
            )
            
            if not employee_with_roles:
                logger.error(f"Failed to fetch employee roles for employee: {employee.employee_id}")
                raise HTTPException(
                    status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                    detail="Failed to fetch user roles"
                )
        
        logger.info(f"Token introspection successful for user: {user_id}, context: {user_type}, roles: {roles}, permissions: {len(all_permissions)} modules")
        
        current_time = int(time.time())
        expiry_time = current_time + (TOKEN_EXPIRY_HOURS * 3600)
        
        opaque_token = secrets.token_hex(16)
        
        token_payload = {
            "user_id": str(user_id),
            "opaque_token": opaque_token,
            "roles": roles,
            "permissions": all_permissions,
            "iat": current_time,
            "exp": expiry_time,
        }
        
        if user_type != "admin" and tenant_id:
            token_payload["tenant_id"] = str(tenant_id)
        
        if user_type:
            token_payload["user_type"] = user_type

        return token_payload
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Token introspection failed with unexpected error: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Token introspection failed due to server error"
        )
    finally:
        db.close()  # Ensure session is closed

@router.post("/employee/login")
async def employee_login(
    form_data: LoginRequest = Body(...),
    db: Session = Depends(get_db)
):
    """
    Authenticate employee in a tenant and return access/refresh tokens
    """
    logger.info(f"Login attempt for user: {form_data.username} in tenant: {form_data.tenant_id}")
    
    try:
        employee = (
            db.query(Employee)
            .join(Tenant, Tenant.tenant_id == Employee.tenant_id)
            .filter(
                Employee.email == form_data.username,
                Employee.tenant_id == form_data.tenant_id
            )
            .first()
        )

        if not employee:
            logger.warning(
                f"Login failed - Employee not found or invalid tenant: "
                f"{form_data.username} in tenant_id {form_data.tenant_id}"
            )
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail=ResponseWrapper.error(
                    message="Incorrect tenant, email, or password",
                    error_code=status.HTTP_401_UNAUTHORIZED
                )
            )

        tenant = employee.tenant
        logger.debug(f"Tenant validation successful - ID: {tenant.tenant_id}")

        if not verify_password(form_data.password, employee.password):
            logger.warning(f"🔒 Login failed - Invalid password for employee: {employee.employee_id} ({form_data.username})")
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail=ResponseWrapper.error(
                    message="Incorrect email or password",
                    error_code=status.HTTP_401_UNAUTHORIZED
                )
            )

        if not employee.is_active or not tenant.is_active:
            logger.warning(f"🚫 Login failed - Inactive account for employee: {employee.employee_id} ({form_data.username})")
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=ResponseWrapper.error(
                    message="User account is inactive",
                    error_code="ACCOUNT_INACTIVE"
                )
            )

        logger.debug(f"Fetching roles and permissions for employee: {employee.employee_id} in tenant: {tenant.tenant_id}")
        employee_with_roles, roles, all_permissions = employee_crud.get_employee_roles_and_permissions(
            db, employee_id=employee.employee_id, tenant_id=tenant.tenant_id
        )
        
        if not employee_with_roles:
            logger.error(f"Failed to fetch employee roles for employee: {employee.employee_id}")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=ResponseWrapper.error(
                    message="Failed to fetch user roles",
                    error_code=status.HTTP_500_INTERNAL_SERVER_ERROR
                )
            )

        logger.info(f"🎯 Permissions collected for employee {employee.employee_id}: {len(all_permissions)} modules, roles: {roles}")

        current_time = int(time.time())
        expiry_time = current_time + (TOKEN_EXPIRY_HOURS * 3600)
        opaque_token = secrets.token_hex(16)

        token_payload = {
            "user_id": str(employee.employee_id),
            "tenant_id": str(tenant.tenant_id),
            "opaque_token": opaque_token,
            "roles": roles,
            "permissions": all_permissions,
            "user_type": "employee",  # Add token context
            "iat": current_time,
            "exp": expiry_time,
        }

        oauth_accessor = Oauth2AsAccessor()
        ttl = expiry_time - current_time
        if not oauth_accessor.store_opaque_token(opaque_token, token_payload, 1800):
            logger.error(f"💥 Failed to store opaque token in Redis for employee: {employee.employee_id}")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=ResponseWrapper.error(
                    message="Failed to store authentication token",
                    error_code=status.HTTP_500_INTERNAL_SERVER_ERROR
                )
            )
        
        logger.debug(f"💾 Opaque token stored in Redis with TTL: {ttl} seconds")

        access_token = create_access_token(
            user_id=str(employee.employee_id),
            tenant_id=str(tenant.tenant_id),
            opaque_token=opaque_token,
            user_type="employee" 
        )
        refresh_token = create_refresh_token(
            user_id=str(employee.employee_id),
            user_type="employee"
        )

        logger.info(f"🚀 Login successful for employee: {employee.employee_id} ({employee.email}) in tenant: {tenant.tenant_id}")

        response_data = {
            "access_token": access_token,
            "refresh_token": refresh_token,
            "token_type": "bearer",
            "user": employee_to_schema(employee)
        }

        return ResponseWrapper.success(
            data=response_data,
            message="Employee login successful"
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Employee login failed with unexpected error: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=ResponseWrapper.error(
                message="Login failed due to server error",
                error_code="SERVER_ERROR",
                details={"error": str(e)}
            )
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

        if not verify_password(form_data.password, vendor_user.password):
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
            "opaque_token": opaque_token,
            "roles": roles,
            "permissions": all_permissions,
            "user_type": "vendor_user",
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
            opaque_token=opaque_token,
            user_type="vendor_user"
        )
        refresh_token = create_refresh_token(
            user_id=str(vendor_user.vendor_user_id),
            user_type="vendor_user"
        )

        logger.info(
            f"🚀 Login successful for vendor_user: {vendor_user.vendor_user_id} "
            f"({vendor_user.email}) in tenant: {tenant.tenant_id}"
        )

        response_data = {
            "access_token": access_token,
            "refresh_token": refresh_token,
            "token_type": "bearer",
            "user": VendorUserResponse.model_validate(vendor_user)
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
        
        if not verify_password(form_data.password, admin.password):
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
            "user_type": "admin",  # Add token context
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

@router.post("/introspect")
async def introspect(x_introspect_secret: str = Header(...,alias="X_Introspect_Secret"), authorization: HTTPAuthorizationCredentials = Depends(security), db: Session = Depends(get_db)):
    """
    Validate and introspect a token, returning its associated data if valid.
    """
    logger.debug("Token introspection request received")
    
    if x_introspect_secret != X_INTROSPECT_SECRET:
        logger.warning(f"Introspection failed - Invalid introspect secret provided")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="You are not authorized"
        )
    
    return introspect_token_direct(authorization.credentials)

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

@router.get("/me", response_model=EmployeeResponse)
async def get_current_user_profile(
    db: Session = Depends(get_db),
    token_data: dict = Depends(validate_bearer_token())
):
    """
    Get the current authenticated user's profile
    """
    user_id = token_data.get("user_id")
    logger.debug(f"Profile request for user: {user_id}")
    
    if not user_id:
        logger.warning("Profile request failed - Missing user_id in token")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Could not validate credentials",
        )
    
    employee = employee_crud.get(db, id=int(user_id))
    
    if not employee:
        logger.warning(f"Profile request failed - Employee not found: {user_id}")
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found",
        )
    
    logger.debug(f"Profile retrieved successfully for employee: {employee.employee_id}")
    
    return employee_to_schema(employee)


