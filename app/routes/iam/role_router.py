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

@router.post("/", response_model=RoleResponse, status_code=status.HTTP_201_CREATED)
async def create_role(
    role: RoleCreate,
    db: Session = Depends(get_db),
    user_data=Depends(PermissionChecker(["iam.create"], check_tenant=True))
):
    """Create a new role with associated policies"""
    # If tenant-specific role, validate tenant access
    if role.tenant_id and not role.is_system_role:
        if int(role.tenant_id) != int(user_data.get("tenant_id", 0)) and "admin.create" not in user_data.get("permissions", []):
            raise HTTPException(status_code=403, detail="Not authorized to create roles for this tenant")
    
    # Verify all policy IDs exist
    if role.policy_ids:
        existing_policies = db.query(Policy).filter(
            Policy.policy_id.in_(role.policy_ids)
        ).all()
        if len(existing_policies) != len(role.policy_ids):
            raise HTTPException(status_code=400, detail="One or more policy IDs are invalid")
    
    return role_crud.create_with_policies(db=db, obj_in=role)

@router.get("/", response_model=RolePaginationResponse)
async def get_roles(
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=100),
    name: Optional[str] = None,
    tenant_id: Optional[int] = None,
    is_system_role: Optional[bool] = None,
    db: Session = Depends(get_db),
    user_data=Depends(PermissionChecker(["iam.read"], check_tenant=True))
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
    user_data=Depends(PermissionChecker(["iam.read"], check_tenant=True))
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
    user_data=Depends(PermissionChecker(["iam.update"], check_tenant=True))
):
    """Update a role and its policies"""
    role = role_crud.get(db, id=role_id)
    if not role:
        raise HTTPException(status_code=404, detail="Role not found")
    
    # Check tenant access for non-system roles
    if role.tenant_id and not role.is_system_role:
        has_admin_perm = any("admin.update" in p for p in user_data.get("permissions", []))
        if int(role.tenant_id) != int(user_data.get("tenant_id", 0)) and not has_admin_perm:
            raise HTTPException(status_code=403, detail="Not authorized to update this role")
    
    # Verify policy IDs if provided
    if role_update.policy_ids is not None:
        if role_update.policy_ids:
            existing_policies = db.query(Policy).filter(
                Policy.policy_id.in_(role_update.policy_ids)
            ).all()
            if len(existing_policies) != len(role_update.policy_ids):
                raise HTTPException(status_code=400, detail="One or more policy IDs are invalid")
    
    return role_crud.update_with_policies(db, db_obj=role, obj_in=role_update)

@router.delete("/{role_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_role(
    role_id: int,
    db: Session = Depends(get_db),
    user_data=Depends(PermissionChecker(["iam.delete"], check_tenant=True))
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
