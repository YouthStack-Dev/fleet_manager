from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.orm import Session
from typing import List
from app.database.session import get_db
from app.models.iam import Permission
from app.schemas.iam import (
    PermissionCreate, PermissionUpdate, PermissionResponse, PermissionPaginationResponse
)
from app.crud.iam import permission_crud
from common_utils.auth.permission_checker import PermissionChecker

router = APIRouter(
    prefix="/permissions",
    tags=["IAM Permissions"]
)

@router.post("/", response_model=PermissionResponse, status_code=status.HTTP_201_CREATED)
async def create_permission(
    permission: PermissionCreate,
    db: Session = Depends(get_db),
    _=Depends(PermissionChecker(["permissions.create"], check_tenant=False))
):
    """Create a new permission"""
    try:
        return permission_crud.create(db=db, obj_in=permission)
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Could not create permission: {str(e)}")

@router.get("/", response_model=PermissionPaginationResponse)
async def get_permissions(
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=100),
    module: str = None,
    action: str = None,
    db: Session = Depends(get_db),
    _=Depends(PermissionChecker(["permissions.read"], check_tenant=False))
):
    """Get a list of permissions with optional filters"""
    filters = {}
    if module:
        filters["module"] = module
    if action:
        filters["action"] = action
        
    permissions = permission_crud.get_multi(db, skip=skip, limit=limit, filters=filters)
    total = permission_crud.count(db, filters=filters)
    
    return {"total": total, "items": permissions}

@router.get("/{permission_id}", response_model=PermissionResponse)
async def get_permission(
    permission_id: int,
    db: Session = Depends(get_db),
    _=Depends(PermissionChecker(["permissions.read"], check_tenant=False))
):
    """Get a specific permission by ID"""
    permission = permission_crud.get(db, id=permission_id)
    if not permission:
        raise HTTPException(status_code=404, detail="Permission not found")
    return permission

@router.put("/{permission_id}", response_model=PermissionResponse)
async def update_permission(
    permission_id: int,
    permission_update: PermissionUpdate,
    db: Session = Depends(get_db),
    _=Depends(PermissionChecker(["iam.update"], check_tenant=False))
):
    """Update a permission"""
    permission = permission_crud.get(db, id=permission_id)
    if not permission:
        raise HTTPException(status_code=404, detail="Permission not found")
    
    return permission_crud.update(db, db_obj=permission, obj_in=permission_update)

@router.delete("/{permission_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_permission(
    permission_id: int,
    db: Session = Depends(get_db),
    _=Depends(PermissionChecker(["permissions.delete"], check_tenant=False))
):
    """Delete a permission"""
    permission = permission_crud.get(db, id=permission_id)
    if not permission:
        raise HTTPException(status_code=404, detail="Permission not found")
    
    permission_crud.remove(db, id=permission_id)
    return None
