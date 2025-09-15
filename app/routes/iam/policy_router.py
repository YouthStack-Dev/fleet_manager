from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.orm import Session
from typing import List
from app.database.session import get_db
from app.models.iam import Policy, Permission
from app.schemas.iam import (
    PolicyCreate, PolicyUpdate, PolicyResponse, PolicyPaginationResponse
)
from app.crud.iam import policy_crud, permission_crud
from common_utils.auth.permission_checker import PermissionChecker

router = APIRouter(
    prefix="/policies",
    tags=["IAM Policies"]
)

@router.post("/", response_model=PolicyResponse, status_code=status.HTTP_201_CREATED)
async def create_policy(
    policy: PolicyCreate,
    db: Session = Depends(get_db),
    _=Depends(PermissionChecker(["iam.create"], check_tenant=False))
):
    """Create a new policy with associated permissions"""
    # Verify all permission IDs exist
    if policy.permission_ids:
        existing_permissions = db.query(Permission).filter(
            Permission.permission_id.in_(policy.permission_ids)
        ).all()
        if len(existing_permissions) != len(policy.permission_ids):
            raise HTTPException(status_code=400, detail="One or more permission IDs are invalid")
    
    return policy_crud.create_with_permissions(db=db, obj_in=policy)

@router.get("/", response_model=PolicyPaginationResponse)
async def get_policies(
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=100),
    name: str = None,
    db: Session = Depends(get_db),
    _=Depends(PermissionChecker(["iam.read"], check_tenant=False))
):
    """Get a list of policies with optional filters"""
    filters = {}
    if name:
        filters["name"] = name
        
    policies = policy_crud.get_multi(db, skip=skip, limit=limit, filters=filters)
    total = policy_crud.count(db, filters=filters)
    
    return {"total": total, "items": policies}

@router.get("/{policy_id}", response_model=PolicyResponse)
async def get_policy(
    policy_id: int,
    db: Session = Depends(get_db),
    _=Depends(PermissionChecker(["iam.read"], check_tenant=False))
):
    """Get a specific policy by ID"""
    policy = policy_crud.get(db, id=policy_id)
    if not policy:
        raise HTTPException(status_code=404, detail="Policy not found")
    return policy

@router.put("/{policy_id}", response_model=PolicyResponse)
async def update_policy(
    policy_id: int,
    policy_update: PolicyUpdate,
    db: Session = Depends(get_db),
    _=Depends(PermissionChecker(["iam.update"], check_tenant=False))
):
    """Update a policy and its permissions"""
    policy = policy_crud.get(db, id=policy_id)
    if not policy:
        raise HTTPException(status_code=404, detail="Policy not found")
    
    # Verify permission IDs if provided
    if policy_update.permission_ids is not None:
        if policy_update.permission_ids:
            existing_permissions = db.query(Permission).filter(
                Permission.permission_id.in_(policy_update.permission_ids)
            ).all()
            if len(existing_permissions) != len(policy_update.permission_ids):
                raise HTTPException(status_code=400, detail="One or more permission IDs are invalid")
    
    return policy_crud.update_with_permissions(db, db_obj=policy, obj_in=policy_update)

@router.delete("/{policy_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_policy(
    policy_id: int,
    db: Session = Depends(get_db),
    _=Depends(PermissionChecker(["iam.delete"], check_tenant=False))
):
    """Delete a policy"""
    policy = policy_crud.get(db, id=policy_id)
    if not policy:
        raise HTTPException(status_code=404, detail="Policy not found")
    
    policy_crud.remove(db, id=policy_id)
    return None
