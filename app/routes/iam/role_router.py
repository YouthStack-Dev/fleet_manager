from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.orm import Session
from typing import List, Optional
from app.database.session import get_db
from app.models.iam import Role, Policy
from app.schemas.iam import (
    RoleCreate, RoleUpdate, RoleResponse, RolePaginationResponse
)
from app.crud.iam import role_crud, policy_crud
from common_utils.auth.permission_checker import PermissionChecker

router = APIRouter(
    prefix="/roles",
    tags=["IAM Roles"]
)

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
            status_code=403, 
            detail=f"Access denied: Cannot assign policies with permissions you don't have: {', '.join(sorted(missing_permissions))}"
        )
    
    print(f"DEBUG - Permission validation passed")

@router.post("/", response_model=RoleResponse, status_code=status.HTTP_201_CREATED)
async def create_role(
    role: RoleCreate,
    db: Session = Depends(get_db),
    user_data=Depends(PermissionChecker(["role.create"], check_tenant=True))
):
    """Create a new role with associated policies"""
    print(f"DEBUG - Creating role with policy_ids: {role.policy_ids}")
    print(f"DEBUG - User data: {user_data}")
    
    user_permissions = extract_user_permissions(user_data)
    
    # If tenant-specific role, validate tenant access
    if role.tenant_id and not role.is_system_role:
        if int(role.tenant_id) != int(user_data.get("tenant_id", 0)) and "admin.create" not in user_permissions:
            raise HTTPException(status_code=403, detail="Not authorized to create roles for this tenant")
    
    # CRITICAL: Validate policy permissions BEFORE creating role
    if role.policy_ids:
        existing_policies = db.query(Policy).filter(
            Policy.policy_id.in_(role.policy_ids)
        ).all()
        if len(existing_policies) != len(role.policy_ids):
            raise HTTPException(status_code=400, detail="One or more policy IDs are invalid")
        
        # This should block if user doesn't have the required permissions
        validate_policy_permissions(existing_policies, user_permissions, "create")
    
    return role_crud.create_with_policies(db=db, obj_in=role)

@router.get("/", response_model=RolePaginationResponse)
async def get_roles(
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=100),
    name: Optional[str] = None,
    tenant_id: Optional[int] = None,
    is_system_role: Optional[bool] = None,
    db: Session = Depends(get_db),
    user_data=Depends(PermissionChecker(["role.read"], check_tenant=True))
):
    """Get a list of roles with optional filters"""
    filters = {}
    if name:
        filters["name"] = name
    if is_system_role is not None:
        filters["is_system_role"] = is_system_role
    
    # Handle tenant filtering based on user permissions
    has_admin_perm = any("admin.read" in p for p in user_data.get("permissions", []))
    
    if tenant_id:
        # Only allow if it's the user's tenant or they have admin permission
        if int(tenant_id) != int(user_data.get("tenant_id", 0)) and not has_admin_perm:
            raise HTTPException(status_code=403, detail="Not authorized to view roles for this tenant")
        filters["tenant_id"] = tenant_id
    elif not has_admin_perm:
        # Regular users can only see their tenant's roles and system roles
        filters["tenant_id"] = [None, user_data.get("tenant_id")]
        
    roles = role_crud.get_multi(db, skip=skip, limit=limit, filters=filters)
    total = role_crud.count(db, filters=filters)
    
    return {"total": total, "items": roles}

@router.get("/{role_id}", response_model=RoleResponse)
async def get_role(
    role_id: int,
    db: Session = Depends(get_db),
    user_data=Depends(PermissionChecker(["role.read"], check_tenant=True))
):
    """Get a specific role by ID"""
    role = role_crud.get(db, id=role_id)
    if not role:
        raise HTTPException(status_code=404, detail="Role not found")
    
    # Check tenant access for non-system roles
    if role.tenant_id and not role.is_system_role:
        has_admin_perm = any("admin.read" in p for p in user_data.get("permissions", []))
        if int(role.tenant_id) != int(user_data.get("tenant_id", 0)) and not has_admin_perm:
            raise HTTPException(status_code=403, detail="Not authorized to access this role")
    
    return role

@router.put("/{role_id}", response_model=RoleResponse)
async def update_role(
    role_id: int,
    role_update: RoleUpdate,
    db: Session = Depends(get_db),
    user_data=Depends(PermissionChecker(["role.update"], check_tenant=True))
):
    """Update a role and its policies"""
    role = role_crud.get(db, id=role_id)
    if not role:
        raise HTTPException(status_code=404, detail="Role not found")
    
    user_permissions = extract_user_permissions(user_data)
    
    # Check tenant access for non-system roles
    if role.tenant_id and not role.is_system_role:
        if int(role.tenant_id) != int(user_data.get("tenant_id", 0)) and "admin.update" not in user_permissions:
            raise HTTPException(status_code=403, detail="Not authorized to update this role")
    
    # CRITICAL: Validate policy permissions if policies are being updated
    if role_update.policy_ids is not None:
        if role_update.policy_ids:
            existing_policies = db.query(Policy).filter(
                Policy.policy_id.in_(role_update.policy_ids)
            ).all()
            if len(existing_policies) != len(role_update.policy_ids):
                raise HTTPException(status_code=400, detail="One or more policy IDs are invalid")
            
            # This should block if user doesn't have the required permissions
            validate_policy_permissions(existing_policies, user_permissions, "update")
    
    return role_crud.update_with_policies(db, db_obj=role, obj_in=role_update)

@router.delete("/{role_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_role(
    role_id: int,
    db: Session = Depends(get_db),
    user_data=Depends(PermissionChecker(["role.delete"], check_tenant=True))
):
    """Delete a role"""
    role = role_crud.get(db, id=role_id)
    if not role:
        raise HTTPException(status_code=404, detail="Role not found")
    
    # Check tenant access for non-system roles
    if role.tenant_id and not role.is_system_role:
        has_admin_perm = any("admin.delete" in p for p in user_data.get("permissions", []))
        if int(role.tenant_id) != int(user_data.get("tenant_id", 0)) and not has_admin_perm:
            raise HTTPException(status_code=403, detail="Not authorized to delete this role")
    
    role_crud.remove(db, id=role_id)
    return None
