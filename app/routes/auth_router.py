import os
import secrets
import time
import logging
import sys
from app.models.admin import Admin
from app.models.tenant import Tenant
from fastapi import APIRouter, Depends, HTTPException, Header, status, Body, Query

from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer, OAuth2PasswordRequestForm
from sqlalchemy.orm import Session
from typing import Optional

from app.database.session import get_db
from app.models import Employee
from app.schemas.auth import (
    AdminLoginRequest, AdminLoginResponse, TokenResponse, RefreshTokenRequest, LoginResponse, 
    EmployeeLoginRequest, PasswordResetRequest
)
from common_utils.auth.utils import (
    create_access_token, create_refresh_token, 
    verify_token, hash_password, verify_password
)
from common_utils.auth.token_validation import Oauth2AsAccessor, validate_bearer_token
from app.crud.iam import user_role_crud
from app.schemas.employee import EmployeeResponse
from app.crud.employee import employee_crud
from app.crud.admin import admin_crud
from app.core.logging_config import get_logger
from app.utils.response_utils import ResponseWrapper

TOKEN_EXPIRY_HOURS = int(os.getenv("TOKEN_EXPIRY_HOURS", "1"))
X_INTROSPECT_SECRET = os.getenv("X_Introspect_Secret","Testing_").strip()

# Create a security instance
security = HTTPBearer()

# Configuration
SECRET_KEY = "your-secret-key"  # Should be stored in environment variables
ALGORITHM = "HS256"
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
@router.post("/employee/login")
async def login(
    form_data: EmployeeLoginRequest = Body(...),
    db: Session = Depends(get_db)
):
    """
    Authenticate employee in a tenant and return access/refresh tokens
    """
    logger.info(f"Login attempt for user: {form_data.username} in tenant: {form_data.tenant_id}")
    
    try:
        # Step 1: Fetch employee with tenant validation
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

        # Step 2: Verify password
        if not verify_password(form_data.password, employee.password):
            logger.warning(f"🔒 Login failed - Invalid password for employee: {employee.employee_id} ({form_data.username})")
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail=ResponseWrapper.error(
                    message="Incorrect email or password",
                    error_code=status.HTTP_401_UNAUTHORIZED
                )
            )

        # Step 3: Check active flag
        if not employee.is_active:
            logger.warning(f"🚫 Login failed - Inactive account for employee: {employee.employee_id} ({form_data.username})")
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=ResponseWrapper.error(
                    message="Account is inactive",
                    error_code=status.HTTP_403_FORBIDDEN
                )
            )

        # Step 4: Collect roles + permissions (scoped to tenant)
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

        # Step 5: Generate tokens
        current_time = int(time.time())
        expiry_time = current_time + (TOKEN_EXPIRY_HOURS * 3600)
        opaque_token = secrets.token_hex(16)

        token_payload = {
            "user_id": str(employee.employee_id),
            "tenant_id": str(tenant.tenant_id),
            "opaque_token": opaque_token,
            "roles": roles,
            "permissions": all_permissions,
            "iat": current_time,
            "exp": expiry_time,
        }

        oauth_accessor = Oauth2AsAccessor()
        ttl = expiry_time - current_time
        if not oauth_accessor.store_opaque_token(opaque_token, token_payload, ttl):
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
            token_context="tenant",
            user_id=str(employee.employee_id),
            tenant_id=str(tenant.tenant_id),
            opaque_token=opaque_token,
        )
        refresh_token = create_refresh_token(
            user_id=str(employee.employee_id),
            token_context="tenant"
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

@router.post("/admin/login")
async def admin_login(
    form_data: AdminLoginRequest = Body(...),
    db: Session = Depends(get_db)
):
    """Admin login endpoint with roles + permissions included"""
    logger.info(f"Admin login attempt for user: {form_data.username}")
    
    try:
        # Step 1: Validate admin existence
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
        
        # Step 2: Validate password
        if not verify_password(form_data.password, admin.password):
            logger.warning(f"Admin login failed - Invalid password for admin: {admin.admin_id} ({form_data.username})")
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail=ResponseWrapper.error(
                    message="Incorrect email or password", 
                    error_code=status.HTTP_401_UNAUTHORIZED
                )
            )

        # Step 3: Check active flag
        if not admin.is_active:
            logger.warning(f"Admin login failed - Inactive account for admin: {admin.admin_id} ({form_data.username})")
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=ResponseWrapper.error(
                    message="Account is inactive",
                    error_code=status.HTTP_403_FORBIDDEN
                )
            )

        # Step 4: Fetch roles + permissions for admin
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

        # Step 5: Generate opaque token
        opaque_token = secrets.token_hex(16)
        logger.debug(f"Generated opaque token for admin: {admin.admin_id}")

        # Step 6: Prepare token payload + expiry
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

        # Step 7: Store opaque token in Redis
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

        # Step 8: Generate JWT tokens
        access_token = create_access_token(
            user_id=str(admin.admin_id),
            opaque_token=opaque_token,
            token_context="admin"
        )
        refresh_token = create_refresh_token(
            user_id=str(admin.admin_id),
            token_context="admin"
        )
        
        logger.info(f"🚀 Admin login successful for admin: {admin.admin_id} ({admin.email})")

        # Step 9: Response wrapper
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
    
    try:
        payload = jwt.decode(authorization.credentials, SECRET_KEY, algorithms=[ALGORITHM])
        logger.debug(f"Token decoded successfully for user: {payload.get('user_id')}, tenant: {payload.get('tenant_id')}")
    except jwt.InvalidTokenError as e:
        logger.warning(f"Token introspection failed - Invalid JWT: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token"
        )
    
    user_id = payload.get("user_id")
    tenant_id = payload.get("tenant_id")
    
    logger.debug(f"Fetching roles and permissions for introspection - user: {user_id}, tenant: {tenant_id}")
    
    # Get user roles and their permissions
    user_roles = user_role_crud.get_by_user_and_tenant(
        db, user_id=user_id, tenant_id=tenant_id
    )
    
    # Extract role names and permissions
    roles = []
    all_permissions = []
    
    for user_role in user_roles:
        roles.append(user_role.role.name)
        
        # Get permissions for this role
        for policy in user_role.role.policies:
            for permission in policy.permissions:
                # Format each permission
                module = permission.module
                action = permission.action
                
                # Check if this module is already in the list
                existing_module = next(
                    (p for p in all_permissions if p["module"] == module),
                    None
                )
                
                if existing_module:
                    # Module exists, just add the action
                    if action == "*":
                        # Add all actions
                        existing_module["action"] = ["create", "read", "update", "delete", "*"]
                    elif action not in existing_module["action"]:
                        existing_module["action"].append(action)
                else:
                    # Add new module with action
                    if action == "*":
                        actions = ["create", "read", "update", "delete", "*"]
                    else:
                        actions = [action]
                        
                    all_permissions.append({
                        "module": module,
                        "action": actions
                    })
    
    logger.info(f"Token introspection successful for user: {user_id}, roles: {roles}, permissions: {len(all_permissions)} modules")
    
    # Create token payload with metadata
    current_time = int(time.time())
    expiry_time = current_time + (TOKEN_EXPIRY_HOURS * 3600)
    
    # Generate an opaque token to return to the client
    opaque_token = secrets.token_hex(16)
    
    # Full metadata payload
    token_payload = {
        "user_id": str(user_id),
        "tenant_id": str(tenant_id),
        "opaque_token": opaque_token,
        "roles": roles,
        "permissions": all_permissions,
        "iat": current_time,
        "exp": expiry_time,
    }

    return token_payload

@router.post("/refresh-token", response_model=TokenResponse)
async def refresh_token(
    refresh_req: RefreshTokenRequest,
    db: Session = Depends(get_db)
):
    """
    Use refresh token to get a new access token
    """
    logger.info("Refresh token request received")
    
    try:
        # Verify the refresh token
        payload = verify_token(refresh_req.refresh_token)
        logger.debug(f"Refresh token verified for user: {payload.get('user_id')}")
        
        # Check if it's actually a refresh token
        if payload.get("token_type") != "refresh":
            logger.warning("Refresh token validation failed - Invalid token type")
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid refresh token"
            )
        
        user_id = payload.get("user_id")
        if not user_id:
            logger.warning("Refresh token validation failed - Missing user_id")
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid refresh token"
            )
        
        # Find the employee
        employee = db.query(Employee).filter(Employee.employee_id == int(user_id)).first()
        if not employee:
            logger.warning(f"Refresh token failed - Employee not found: {user_id}")
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="User not found or inactive"
            )
        
        if not employee.is_active:
            logger.warning(f"Refresh token failed - Inactive employee: {user_id}")
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="User not found or inactive"
            )
            
        logger.debug(f"Fetching updated permissions for refresh token - employee: {employee.employee_id}")
        
        # Get user roles and permissions (similar to login)
        user_roles = user_role_crud.get_by_user_and_tenant(
            db, user_id=employee.employee_id, tenant_id=employee.tenant_id
        )
        
        roles = []
        all_permissions = []
        
        for user_role in user_roles:
            roles.append(user_role.role.name)
            
            # Get permissions for this role
            for policy in user_role.role.policies:
                for permission in policy.permissions:
                    # Format each permission as before
                    module = permission.module
                    action = permission.action
                    
                    existing_module = next(
                        (p for p in all_permissions if p["module"] == module),
                        None
                    )
                    
                    if existing_module:
                        if action == "*":
                            existing_module["action"] = ["create", "read", "update", "delete", "*"]
                        elif action not in existing_module["action"]:
                            existing_module["action"].append(action)
                    else:
                        if action == "*":
                            actions = ["create", "read", "update", "delete", "*"]
                        else:
                            actions = [action]
                            
                        all_permissions.append({
                            "module": module,
                            "action": actions
                        })
        
        # Create new access token
        new_access_token = create_access_token(
            user_id=str(employee.employee_id),
            tenant_id=str(employee.tenant_id),
            roles=roles,
            permissions=all_permissions
        )
        
        # Create new refresh token (optional, some systems reuse the old one)
        new_refresh_token = create_refresh_token(user_id=str(employee.employee_id))
        
        logger.info(f"Refresh token successful for employee: {employee.employee_id} ({employee.email})")
        
        return TokenResponse(
            access_token=new_access_token,
            refresh_token=new_refresh_token,
            token_type="bearer"
        )
    except Exception as e:
        logger.error(f"Refresh token failed with error: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=f"Invalid refresh token: {str(e)}"
        )

@router.post("/reset-password", status_code=status.HTTP_200_OK)
async def reset_password(
    reset_req: PasswordResetRequest,
    db: Session = Depends(get_db)
):
    """
    Reset employee password
    """
    logger.info(f"Password reset request for email: {reset_req.email}")
    
    # Find employee by email
    employee = db.query(Employee).filter(Employee.email == reset_req.email).first()
    
    if not employee:
        logger.info(f"Password reset requested for non-existent email: {reset_req.email}")
        # Always return success to prevent email enumeration
        return {"message": "If your email is registered, you will receive a password reset link."}
    
    logger.info(f"Password reset email would be sent to employee: {employee.employee_id} ({reset_req.email})")
    
    # In a real system, you would:
    # 1. Generate a reset token
    # 2. Store it with an expiration time
    # 3. Send an email with a link containing the token
    
    # For this example, we'll just return a success message
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
    
    # Use the helper function here too
    return employee_to_schema(employee)


