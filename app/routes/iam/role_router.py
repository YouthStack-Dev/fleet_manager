from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.orm import Session
from sqlalchemy.exc import IntegrityError
from typing import List, Optional
from app.database.session import get_db
from app.models.iam import Role, Policy
from app.schemas.iam import (
    RoleCreate, RoleUpdate, RoleResponse, RolePaginationResponse
)
from app.crud.iam import role_crud, policy_crud
from common_utils.auth.permission_checker import PermissionChecker
from app.utils.response_utils import ResponseWrapper

router = APIRouter(
    prefix="/roles",
    tags=["IAM Roles"]
)

def resolve_tenant_id(user_data: dict, tenant_id_from_request: Optional[str] = None) -> str:
    """
    Resolve tenant_id based on user type.
    
    Args:
        user_data: User data from token
        tenant_id_from_request: tenant_id from request body/payload (for admin users)
    
    Returns:
        Resolved tenant_id
        
    Raises:
        HTTPException: If tenant_id cannot be resolved
    """
    user_type = user_data.get("user_type")
    
    if user_type in ["employee", "vendor"]:
        resolved_tenant_id = user_data.get("tenant_id")
        if not resolved_tenant_id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=ResponseWrapper.error(
                    message="Tenant ID missing in token",
                    error_code="TENANT_ID_REQUIRED"
                )
            )
        # Employee/vendor can only create for their own tenant
        if tenant_id_from_request and str(tenant_id_from_request) != str(resolved_tenant_id):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=ResponseWrapper.error(
                    message="You can only create roles for your own tenant",
                    error_code="UNAUTHORIZED_TENANT_ACCESS"
                )
            )
    elif user_type == "admin":
        if tenant_id_from_request:
            resolved_tenant_id = tenant_id_from_request
        else:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=ResponseWrapper.error(
                    message="Tenant ID is required in request for admin",
                    error_code="TENANT_ID_REQUIRED"
                )
            )
    else:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=ResponseWrapper.error(
                message="Unauthorized user type for this operation",
                error_code="UNAUTHORIZED_USER_TYPE"
            )
        )
    
    return resolved_tenant_id

def extract_user_permissions(user_data) -> set:
    """Extract permission names from user_data"""
    user_permissions_data = user_data.get("permissions", [])
    user_permissions = set()
    
    print(f"DEBUG - Raw permissions data: {user_permissions_data}")
    
    if user_permissions_data:
        for perm in user_permissions_data:
            if isinstance(perm, dict):
                # Handle the actual structure: {'module': 'role', 'action': ['create', 'read']}
                module = perm.get("module", "")
                actions = perm.get("action", [])
                
                if module and actions:
                    for action in actions:
                        permission_name = f"{module}.{action}"
                        user_permissions.add(permission_name)
                        print(f"DEBUG - Added permission: {permission_name}")
                
                # Also handle other possible structures
                perm_name = perm.get("name") or perm.get("permission_name")
                if perm_name:
                    user_permissions.add(str(perm_name))
                    print(f"DEBUG - Added permission (name): {perm_name}")
            elif isinstance(perm, str):
                user_permissions.add(perm)
                print(f"DEBUG - Added permission (string): {perm}")
            else:
                if hasattr(perm, 'name'):
                    user_permissions.add(str(perm.name))
                    print(f"DEBUG - Added permission (attr name): {perm.name}")
                elif hasattr(perm, 'permission_name'):
                    user_permissions.add(str(perm.permission_name))
                    print(f"DEBUG - Added permission (attr permission_name): {perm.permission_name}")
    
    print(f"DEBUG - Final extracted user permissions: {sorted(user_permissions)}")
    return user_permissions

def validate_policy_permissions(existing_policies, user_permissions: set, operation: str):
    """Validate that user has all permissions in the policies they're trying to assign"""
    # Extract all permissions from the policies being assigned
    policy_permissions = set()
    
    print(f"DEBUG - Number of policies to check: {len(existing_policies)}")
    
    for i, policy in enumerate(existing_policies):
        print(f"DEBUG - Policy {i+1}: ID={policy.policy_id}, Name={getattr(policy, 'name', 'N/A')}")
        print(f"DEBUG - Policy permissions attribute: {policy.permissions}")
        print(f"DEBUG - Policy permissions type: {type(policy.permissions)}")
        
        if policy.permissions:
            print(f"DEBUG - Policy has {len(policy.permissions)} permissions")
            for j, perm in enumerate(policy.permissions):
                print(f"DEBUG - Permission {j+1}: {perm}, type: {type(perm)}")
                
                perm_name = None
                
                # Handle Permission objects with module and action attributes
                if hasattr(perm, 'module') and hasattr(perm, 'action'):
                    module = getattr(perm, 'module', '')
                    action = getattr(perm, 'action', '')
                    if module and action:
                        perm_name = f"{module}.{action}"
                        print(f"DEBUG - Constructed permission from module.action: {perm_name}")
                # Fallback to other possible attributes
                elif hasattr(perm, 'name'):
                    perm_name = perm.name
                    print(f"DEBUG - Found perm.name: {perm_name}")
                elif hasattr(perm, 'permission_name'):
                    perm_name = perm.permission_name
                    print(f"DEBUG - Found perm.permission_name: {perm_name}")
                elif isinstance(perm, str):
                    perm_name = perm
                    print(f"DEBUG - Permission is string: {perm_name}")
                else:
                    print(f"DEBUG - Could not extract permission name from: {perm}")
                
                if perm_name:
                    policy_permissions.add(str(perm_name))
                    print(f"DEBUG - Added policy permission: {perm_name}")
        else:
            print(f"DEBUG - Policy has no permissions or permissions is falsy")
    
    # Debug logging
    print(f"DEBUG - Operation: {operation}")
    print(f"DEBUG - User permissions: {sorted(user_permissions)}")
    print(f"DEBUG - Policy permissions being assigned: {sorted(policy_permissions)}")
    
    # Check for admin override
    admin_permission = f"admin.{operation}"
    if admin_permission in user_permissions:
        print(f"DEBUG - Admin permission {admin_permission} found, allowing operation")
        return
    
    # Check for missing permissions
    missing_permissions = policy_permissions - user_permissions
    if missing_permissions:
        print(f"DEBUG - Missing permissions: {sorted(missing_permissions)}")
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=ResponseWrapper.error(
                message="Access denied: Cannot assign policies with permissions you don't have",
                error_code="INSUFFICIENT_PERMISSIONS",
                details={
                    "missing_permissions": sorted(missing_permissions),
                    "required_permissions": sorted(policy_permissions),
                    "user_permissions": sorted(user_permissions)
                }
            )
        )
    
    print(f"DEBUG - Permission validation passed")

@router.post("/", status_code=status.HTTP_201_CREATED)
async def create_role(
    role: RoleCreate,
    db: Session = Depends(get_db),
    user_data=Depends(PermissionChecker(["role.create"], check_tenant=True))
):
    """Create a new role with associated policies"""
    print(f"DEBUG - Creating role with policy_ids: {role.policy_ids}")
    print(f"DEBUG - User data: {user_data}")
    
    user_permissions = extract_user_permissions(user_data)
    
    # Validate and resolve tenant_id based on user type
    if role.tenant_id and not role.is_system_role:
        resolved_tenant_id = resolve_tenant_id(user_data, role.tenant_id)
        # Ensure the role uses the validated tenant_id
        role.tenant_id = resolved_tenant_id
    
    # CRITICAL: Validate policy permissions BEFORE creating role
    if role.policy_ids:
        existing_policies = db.query(Policy).filter(
            Policy.policy_id.in_(role.policy_ids)
        ).all()
        if len(existing_policies) != len(role.policy_ids):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=ResponseWrapper.error(
                    message="One or more policy IDs are invalid",
                    error_code="INVALID_POLICY_IDS",
                    details={"requested_policy_ids": role.policy_ids}
                )
            )
        
        # This should block if user doesn't have the required permissions
        validate_policy_permissions(existing_policies, user_permissions, "create")
    
    try:
        created_role = role_crud.create_with_policies(db=db, obj_in=role)
        return ResponseWrapper.success(
            data=created_role,
            message="Role created successfully"
        )
    except IntegrityError as e:
        db.rollback()
        error_msg = str(e.orig)
        if "uq_role_tenant_name" in error_msg or "duplicate key" in error_msg.lower():
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=ResponseWrapper.error(
                    message=f"Role with name '{role.name}' already exists for this tenant",
                    error_code="DUPLICATE_ROLE_NAME",
                    details={"role_name": role.name, "tenant_id": role.tenant_id}
                )
            )
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=ResponseWrapper.error(
                message="Failed to create role due to database constraint violation",
                error_code="DATABASE_CONSTRAINT_VIOLATION"
            )
        )

@router.get("/")
async def get_roles(
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=100),
    name: Optional[str] = None,
    tenant_id: Optional[str] = None,
    is_system_role: Optional[bool] = None,
    db: Session = Depends(get_db),
    user_data=Depends(PermissionChecker(["role.read"], check_tenant=True))
):
    """
    Get a list of roles with optional filters.
    
    Rules:
    - Admin: Must provide tenant_id as query parameter
    - Employee/Vendor: tenant_id taken from token
    - All users get system roles (is_system_role=true) + their tenant-specific roles
    """
    filters = {}
    if name:
        filters["name"] = name
    if is_system_role is not None:
        filters["is_system_role"] = is_system_role
    
    user_type = user_data.get("user_type")
    
    # Admin must provide tenant_id
    if user_type == "admin":
        if not tenant_id:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=ResponseWrapper.error(
                    message="Tenant ID is required as query parameter for admin",
                    error_code="TENANT_ID_REQUIRED"
                )
            )
        # Admin can view any tenant's roles
        resolved_tenant_id = tenant_id
    elif user_type in ["employee", "vendor"]:
        # Employee/vendor use their token tenant_id
        resolved_tenant_id = user_data.get("tenant_id")
        if not resolved_tenant_id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=ResponseWrapper.error(
                    message="Tenant ID missing in token",
                    error_code="TENANT_ID_REQUIRED"
                )
            )
        # Employee/vendor cannot request other tenants
        if tenant_id and str(tenant_id) != str(resolved_tenant_id):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=ResponseWrapper.error(
                    message="You can only view roles for your own tenant",
                    error_code="UNAUTHORIZED_TENANT_ACCESS"
                )
            )
    else:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=ResponseWrapper.error(
                message="Unauthorized user type for this operation",
                error_code="UNAUTHORIZED_USER_TYPE"
            )
        )
    
    # Include system roles (tenant_id=null) + tenant-specific roles
    # Query system roles separately to ensure they're included
    from sqlalchemy import or_
    
    base_query = db.query(Role).filter(
        or_(
            Role.is_system_role == True,  # System roles (tenant_id should be null)
            Role.tenant_id == resolved_tenant_id  # Tenant-specific roles
        )
    )
    
    # Apply other filters
    if name:
        base_query = base_query.filter(Role.name.ilike(f"%{name}%"))
    if is_system_role is not None:
        base_query = base_query.filter(Role.is_system_role == is_system_role)
    
    # Get total count
    total = base_query.count()
    
    # Apply pagination
    roles = base_query.offset(skip).limit(limit).all()
    
    return ResponseWrapper.success(
        data={"total": total, "items": roles},
        message="Roles retrieved successfully"
    )

@router.get("/{role_id}")
async def get_role(
    role_id: int,
    db: Session = Depends(get_db),
    user_data=Depends(PermissionChecker(["role.read"], check_tenant=True))
):
    """Get a specific role by ID"""
    role = role_crud.get(db, id=role_id)
    if not role:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=ResponseWrapper.error(
                message="Role not found",
                error_code="ROLE_NOT_FOUND",
                details={"role_id": role_id}
            )
        )
    
    # Check tenant access for non-system roles
    if role.tenant_id and not role.is_system_role:
        has_admin_perm = any("admin.read" in p for p in user_data.get("permissions", []))
        if str(role.tenant_id) != str(user_data.get("tenant_id", "")) and not has_admin_perm:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=ResponseWrapper.error(
                    message="Not authorized to access this role",
                    error_code="UNAUTHORIZED_ROLE_ACCESS"
                )
            )
    
    return ResponseWrapper.success(
        data=role,
        message="Role retrieved successfully"
    )

@router.put("/{role_id}")
async def update_role(
    role_id: int,
    role_update: RoleUpdate,
    db: Session = Depends(get_db),
    user_data=Depends(PermissionChecker(["role.update"], check_tenant=True))
):
    """Update a role and its policies"""
    role = role_crud.get(db, id=role_id)
    if not role:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=ResponseWrapper.error(
                message="Role not found",
                error_code="ROLE_NOT_FOUND",
                details={"role_id": role_id}
            )
        )
    
    user_permissions = extract_user_permissions(user_data)
    user_type = user_data.get("user_type")
    
    # System roles can only be updated by admin users
    if role.is_system_role and user_type != "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=ResponseWrapper.error(
                message="Only admin users can update system roles",
                error_code="UNAUTHORIZED_SYSTEM_ROLE_UPDATE"
            )
        )
    
    # Check tenant access for non-system roles
    if role.tenant_id and not role.is_system_role:
        if str(role.tenant_id) != str(user_data.get("tenant_id", "")) and "admin.update" not in user_permissions:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=ResponseWrapper.error(
                    message="Not authorized to update this role",
                    error_code="UNAUTHORIZED_ROLE_UPDATE"
                )
            )
    
    # CRITICAL: Validate policy permissions if policies are being updated
    if role_update.policy_ids is not None:
        if role_update.policy_ids:
            existing_policies = db.query(Policy).filter(
                Policy.policy_id.in_(role_update.policy_ids)
            ).all()
            if len(existing_policies) != len(role_update.policy_ids):
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=ResponseWrapper.error(
                        message="One or more policy IDs are invalid",
                        error_code="INVALID_POLICY_IDS",
                        details={"requested_policy_ids": role_update.policy_ids}
                    )
                )
            
            # This should block if user doesn't have the required permissions
            validate_policy_permissions(existing_policies, user_permissions, "update")
    
    try:
        updated_role = role_crud.update_with_policies(db, db_obj=role, obj_in=role_update)
        return ResponseWrapper.success(
            data=updated_role,
            message="Role updated successfully"
        )
    except IntegrityError as e:
        db.rollback()
        error_msg = str(e.orig)
        if "uq_role_tenant_name" in error_msg or "duplicate key" in error_msg.lower():
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=ResponseWrapper.error(
                    message=f"Role with name '{role_update.name}' already exists for this tenant",
                    error_code="DUPLICATE_ROLE_NAME",
                    details={"role_name": role_update.name, "role_id": role_id}
                )
            )
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=ResponseWrapper.error(
                message="Failed to update role due to database constraint violation",
                error_code="DATABASE_CONSTRAINT_VIOLATION"
            )
        )

@router.delete("/{role_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_role(
    role_id: int,
    db: Session = Depends(get_db),
    user_data=Depends(PermissionChecker(["role.delete"], check_tenant=True))
):
    """Delete a role"""
    role = role_crud.get(db, id=role_id)
    if not role:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=ResponseWrapper.error(
                message="Role not found",
                error_code="ROLE_NOT_FOUND",
                details={"role_id": role_id}
            )
        )
    
    # Check tenant access for non-system roles
    if role.tenant_id and not role.is_system_role:
        has_admin_perm = any("admin.delete" in p for p in user_data.get("permissions", []))
        if str(role.tenant_id) != str(user_data.get("tenant_id", "")) and not has_admin_perm:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=ResponseWrapper.error(
                    message="Not authorized to delete this role",
                    error_code="UNAUTHORIZED_ROLE_DELETE"
                )
            )
    
    role_crud.remove(db, id=role_id)
    return ResponseWrapper.success(
        data=None,
        message="Role deleted successfully"
    )
