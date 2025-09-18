import os
import secrets
import time
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
from common_utils.auth.token_validation import Oauth2AsAccessor, validate_bearer_token  # Add this import
from app.crud.iam import user_role_crud
from app.schemas.employee import EmployeeResponse
from app.crud.employee import employee_crud
TOKEN_EXPIRY_HOURS = int(os.getenv("TOKEN_EXPIRY_HOURS", "1"))
X_INTROSPECT_SECRET = os.getenv("X_Introspect_Secret","Testing_").strip()

# Create a security instance
security = HTTPBearer()

# Configuration
SECRET_KEY = "your-secret-key"  # Should be stored in environment variables
ALGORITHM = "HS256"
import jwt
router = APIRouter(
    prefix="/auth",
    tags=["Authentication"]
)

def employee_to_schema(employee: Employee) -> EmployeeResponse:
    """Convert Employee ORM model to EmployeeResponse Pydantic model"""
    # Convert ORM object to dict first
    employee_dict = {
        column.name: getattr(employee, column.name)
        for column in employee.__table__.columns
    }
    return EmployeeResponse(**employee_dict)

# @router.post("/login", response_model=LoginResponse)
# async def login(
#     form_data: EmployeeLoginRequest = Body(...),
#     db: Session = Depends(get_db)
# ):
#     """
#     Authenticate employee and return access token
#     """
#     # Find the employee by email
#     employee = db.query(Employee).filter(Employee.email == form_data.username).first()
    
#     # Verify employee exists and password is correct
#     if not employee or not (form_data.password == employee.password):
#         raise HTTPException(
#             status_code=status.HTTP_401_UNAUTHORIZED,
#             detail="Incorrect email or password",
#             headers={"WWW-Authenticate": "Bearer"},
#         )
    
#     # Check if employee is active
#     if not employee.is_active:
#         raise HTTPException(
#             status_code=status.HTTP_403_FORBIDDEN,
#             detail="Account is inactive"
#         )
    
#     # Get user roles and their permissions
#     user_roles = user_role_crud.get_by_user_and_tenant(
#         db, user_id=employee.employee_id, tenant_id=employee.tenant_id
#     )
    
#     # Extract role names and permissions
#     roles = []
#     all_permissions = []
    
#     for user_role in user_roles:
#         roles.append(user_role.role.name)
        
#         # Get permissions for this role
#         for policy in user_role.role.policies:
#             for permission in policy.permissions:
#                 # Format each permission
#                 module = permission.module
#                 action = permission.action
                
#                 # Check if this module is already in the list
#                 existing_module = next(
#                     (p for p in all_permissions if p["module"] == module),
#                     None
#                 )
                
#                 if existing_module:
#                     # Module exists, just add the action
#                     if action == "*":
#                         # Add all actions
#                         existing_module["action"] = ["create", "read", "update", "delete", "*"]
#                     elif action not in existing_module["action"]:
#                         existing_module["action"].append(action)
#                 else:
#                     # Add new module with action
#                     if action == "*":
#                         actions = ["create", "read", "update", "delete", "*"]
#                     else:
#                         actions = [action]
                        
#                     all_permissions.append({
#                         "module": module,
#                         "action": actions
#                     })
    
#     # Create token payload with metadata
#     current_time = int(time.time())
#     expiry_time = current_time + (TOKEN_EXPIRY_HOURS * 3600)
    
#     # Generate an opaque token to return to the client
#     opaque_token = secrets.token_hex(16)
    
#     # Full metadata payload
#     token_payload = {
#         "user_id": str(employee.employee_id),
#         "tenant_id": str(employee.tenant_id),
#         "opaque_token": opaque_token,
#         "roles": roles,
#         "permissions": all_permissions,
#         "iat": current_time,
#         "exp": expiry_time,
#     }

#     # Store the mapping between opaque token and JWT payload in Redis
#     oauth_accessor = Oauth2AsAccessor()
#     ttl = expiry_time - current_time

#     if not oauth_accessor.store_opaque_token(opaque_token, token_payload, ttl):
#             raise HTTPException(
#                 status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
#                 detail="Failed to store authentication token"
#             )
#     # Create access and refresh tokens
#     access_token = create_access_token(
#         user_id=str(employee.employee_id),
#         tenant_id=str(employee.tenant_id),
#         permissions=all_permissions,
#         opaque_token=opaque_token
#     )
    
#     refresh_token = create_refresh_token(user_id=str(employee.employee_id))
    
#     # Convert to response model - use the new helper function
#     employee_data = employee_to_schema(employee)
    
#     return LoginResponse(
#         access_token=access_token,
#         refresh_token=refresh_token,
#         token_type="bearer",
#         user=employee_data
#     )

@router.post("/login", response_model=LoginResponse)
async def login(
    form_data: EmployeeLoginRequest = Body(...),
    db: Session = Depends(get_db)
):
    """
    Authenticate employee in a tenant and return access/refresh tokens
    """
    # Step 1: Validate tenant
    tenant = db.query(Tenant).filter(Tenant.tenant_code == form_data.tenant_code).first()
    if not tenant:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Invalid tenant code"
        )

    # Step 2: Find employee in this tenant
    employee = (
        db.query(Employee)
        .filter(
            Employee.email == form_data.username,
            Employee.tenant_id == tenant.tenant_id
        )
        .first()
    )
    if not employee or not verify_password(form_data.password, employee.password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect email or password",
            headers={"WWW-Authenticate": "Bearer"},
        )

    # Step 3: Check active flag
    if not employee.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Account is inactive"
        )

    # Step 4: Collect roles + permissions (scoped to tenant)
    user_roles = user_role_crud.get_by_user_and_tenant(
        db, user_id=employee.employee_id, tenant_id=tenant.tenant_id
    )

    roles, all_permissions = [], []
    for ur in user_roles:
        roles.append(ur.role.name)
        for policy in ur.role.policies:
            for perm in policy.permissions:
                module, action = perm.module, perm.action
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

    # Step 5: Generate tokens
    current_time = int(time.time())
    expiry_time = current_time + (TOKEN_EXPIRY_HOURS * 3600)
    opaque_token = secrets.token_hex(16)

    token_payload = {
        "user_id": str(employee.employee_id),
        "tenant_id": str(tenant.tenant_id),
        "opaque_token": opaque_token,
        # "roles": roles,
        # "permissions": all_permissions,
        "iat": current_time,
        "exp": expiry_time,
    }

    # Store opaque token → JWT mapping in Redis
    oauth_accessor = Oauth2AsAccessor()
    ttl = expiry_time - current_time
    if not oauth_accessor.store_opaque_token(opaque_token, token_payload, ttl):
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to store authentication token"
        )

    access_token = create_access_token(
        user_id=str(employee.employee_id),
        tenant_id=str(tenant.tenant_id),
        # permissions=all_permissions,
        opaque_token=opaque_token,
    )
    refresh_token = create_refresh_token(
        user_id=str(employee.employee_id)
    )

    return LoginResponse(
        access_token=access_token,
        refresh_token=refresh_token,
        token_type="bearer",
        user=employee_to_schema(employee)
    )

@router.post("/admin/login", response_model=AdminLoginResponse)
async def login(
    form_data: AdminLoginRequest = Body(...),
    db: Session = Depends(get_db)
):
    admin = db.query(Admin).filter(Admin.email == form_data.username).first()
    if not admin or not verify_password(form_data.password, admin.password):
        raise HTTPException(status_code=401, detail="Incorrect email or password")

    if not admin.is_active:
        raise HTTPException(status_code=403, detail="Account is inactive")

    opaque_token = secrets.token_hex(16)

    access_token = create_access_token(
        user_id=str(admin.admin_id),
        opaque_token=opaque_token,
        token_context="admin"
    )
    refresh_token = create_refresh_token(user_id=str(admin.admin_id), token_context="admin")

    return AdminLoginResponse(
        access_token=access_token,
        refresh_token=refresh_token,
        token_type="bearer"
    )

@router.post("/introspect")
async def introspect(x_introspect_secret: str = Header(...,alias="X_Introspect_Secret"), authorization: HTTPAuthorizationCredentials = Depends(security), db: Session = Depends(get_db)):
    """
    Validate and introspect a token, returning its associated data if valid.
    
    The token should be provided in the Authorization header as 'Bearer <token>'.
    """
    
    if x_introspect_secret != X_INTROSPECT_SECRET:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="You are not authorized"
        )
    
    payload = jwt.decode(authorization.credentials, SECRET_KEY, algorithms=[ALGORITHM])
    
    print(payload)
    # Get user roles and their permissions
    user_roles = user_role_crud.get_by_user_and_tenant(
        db, user_id=payload["user_id"], tenant_id=payload["tenant_id"]
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
    
    # Create token payload with metadata
    current_time = int(time.time())
    expiry_time = current_time + (TOKEN_EXPIRY_HOURS * 3600)
    
    # Generate an opaque token to return to the client
    opaque_token = secrets.token_hex(16)
    
    # Full metadata payload
    token_payload = {
        "user_id": str(payload["user_id"]),
        "tenant_id": str(payload["tenant_id"]),
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
    try:
        # Verify the refresh token
        payload = verify_token(refresh_req.refresh_token)
        
        # Check if it's actually a refresh token
        if payload.get("token_type") != "refresh":
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid refresh token"
            )
        
        user_id = payload.get("user_id")
        if not user_id:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid refresh token"
            )
        
        # Find the employee
        employee = db.query(Employee).filter(Employee.employee_id == int(user_id)).first()
        if not employee or not employee.is_active:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="User not found or inactive"
            )
            
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
        
        return TokenResponse(
            access_token=new_access_token,
            refresh_token=new_refresh_token,
            token_type="bearer"
        )
    except Exception as e:
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
    # Find employee by email
    employee = db.query(Employee).filter(Employee.email == reset_req.email).first()
    
    if not employee:
        # Always return success to prevent email enumeration
        return {"message": "If your email is registered, you will receive a password reset link."}
    
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
    
    if not user_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Could not validate credentials",
        )
    
    employee = employee_crud.get(db, id=int(user_id))
    
    if not employee:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found",
        )
        
    # Use the helper function here too
    return employee_to_schema(employee)


