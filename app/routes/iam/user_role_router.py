from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.orm import Session
from typing import List, Optional
from app.database.session import get_db
from app.models.iam import UserRole, Role
from app.schemas.iam import (
    UserRoleCreate, UserRoleUpdate, UserRoleResponse, UserRolePaginationResponse,
    UserRoleAssignment
)
from app.crud.iam import user_role_crud, role_crud
from common_utils.auth.permission_checker import PermissionChecker

router = APIRouter(
    prefix="/user-roles",
    tags=["IAM User Roles"]
)

@router.post("/assign", status_code=status.HTTP_201_CREATED)
async def assign_roles_to_user(
    assignment: UserRoleAssignment,
    db: Session = Depends(get_db),
    user_data=Depends(PermissionChecker(["role.create"], check_tenant=True))
):
    """Assign multiple roles to a user"""
    # Check tenant access
    tenant_id = assignment.tenant_id or user_data.get("tenant_id")
    if tenant_id != user_data.get("tenant_id") and not any("admin.create" in p for p in user_data.get("permissions", [])):
        raise HTTPException(status_code=403, detail="Not authorized to assign roles for this tenant")
    
    # Verify all role IDs exist and are accessible
    roles = db.query(Role).filter(Role.role_id.in_(assignment.role_ids)).all()
    if len(roles) != len(assignment.role_ids):
        raise HTTPException(status_code=400, detail="One or more role IDs are invalid")
    
    # Check tenant-specific roles
    for role in roles:
        if role.tenant_id and not role.is_system_role and role.tenant_id != tenant_id:
            raise HTTPException(status_code=400, detail=f"Role {role.name} belongs to a different tenant")
    
    # First, clear existing roles if needed
    db.query(UserRole).filter(
        UserRole.user_id == assignment.user_id,
        UserRole.tenant_id == tenant_id
    ).delete()
    
    # Then assign new roles
    for role_id in assignment.role_ids:
        user_role = UserRole(
            user_id=assignment.user_id,
            role_id=role_id,
            tenant_id=tenant_id,
            is_active=True
        )
        db.add(user_role)
    
    db.commit()
    return {"message": "Roles assigned successfully"}

@router.get("/", response_model=UserRolePaginationResponse)
async def get_user_roles(
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=100),
    user_id: Optional[int] = None,
    tenant_id: Optional[int] = None,
    db: Session = Depends(get_db),
    user_data=Depends(PermissionChecker(["role.read"], check_tenant=True))
):
    """Get a list of user role assignments with optional filters"""
    filters = {}
    if user_id:
        filters["user_id"] = user_id
    
    # Handle tenant filtering based on user permissions
    has_admin_perm = any("admin.read" in p for p in user_data.get("permissions", []))
    
    if tenant_id:
        # Only allow if it's the user's tenant or they have admin permission
        if int(tenant_id) != int(user_data.get("tenant_id", 0)) and not has_admin_perm:
            raise HTTPException(status_code=403, detail="Not authorized to view roles for this tenant")
        filters["tenant_id"] = tenant_id
    elif not has_admin_perm:
        # Regular users can only see their tenant's user roles
        filters["tenant_id"] = user_data.get("tenant_id")
        
    user_roles = user_role_crud.get_multi(db, skip=skip, limit=limit, filters=filters)
    total = user_role_crud.count(db, filters=filters)
    
    return {"total": total, "items": user_roles}

@router.get("/user/{user_id}", response_model=List[UserRoleResponse])
async def get_roles_for_user(
    user_id: int,
    tenant_id: Optional[int] = None,
    db: Session = Depends(get_db),
    user_data=Depends(PermissionChecker(["role.read"], check_tenant=True))
):
    """Get all roles assigned to a specific user"""
    filters = {"user_id": user_id}
    
    # Handle tenant filtering
    current_tenant_id = user_data.get("tenant_id")
    has_admin_perm = any("admin.read" in p for p in user_data.get("permissions", []))
    
    if tenant_id:
        if int(tenant_id) != int(current_tenant_id) and not has_admin_perm:
            raise HTTPException(status_code=403, detail="Not authorized to view roles for this tenant")
        filters["tenant_id"] = tenant_id
    elif not has_admin_perm:
        filters["tenant_id"] = current_tenant_id
    
    user_roles = user_role_crud.get_multi_by_filter(db, filters=filters)
    return user_roles

@router.delete("/{user_role_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_user_role(
    user_role_id: int,
    db: Session = Depends(get_db),
    user_data=Depends(PermissionChecker(["role.delete"], check_tenant=True))
):
    """Delete a user role assignment"""
    user_role = user_role_crud.get(db, id=user_role_id)
    if not user_role:
        raise HTTPException(status_code=404, detail="User role assignment not found")
    
    # Check tenant access
    has_admin_perm = any("admin.delete" in p for p in user_data.get("permissions", []))
    if user_role.tenant_id and user_role.tenant_id != user_data.get("tenant_id") and not has_admin_perm:
        raise HTTPException(status_code=403, detail="Not authorized to delete this role assignment")
    
    user_role_crud.remove(db, id=user_role_id)
    return None
