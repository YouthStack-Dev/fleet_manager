from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.orm import Session
from typing import Optional
from app.database.session import get_db
from app.models.iam import Permission
from app.schemas.iam import (
    PermissionCreate, PermissionUpdate, PermissionResponse, PermissionPaginationResponse
)
from app.crud.iam import permission_crud
from common_utils.auth.permission_checker import PermissionChecker
from app.utils.response_utils import ResponseWrapper
from app.core.logging_config import get_logger

logger = get_logger(__name__)

router = APIRouter(
    prefix="/permissions",
    tags=["IAM Permissions"]
)


@router.post("/", response_model=dict, status_code=status.HTTP_201_CREATED)
async def create_permission(
    permission: PermissionCreate,
    db: Session = Depends(get_db),
    _=Depends(PermissionChecker(["permissions.create"], check_tenant=False))
):
    """Create a new permission"""
    try:
        new_permission = permission_crud.create(db=db, obj_in=permission)
        logger.info(f"Permission created: {new_permission.permission_id}")

        return ResponseWrapper.success(
            data=PermissionResponse.model_validate(new_permission, from_attributes=True),
            message="Permission created successfully"
        )
    except Exception as e:
        logger.exception(f"Error creating permission: {e}")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=ResponseWrapper.error(
                message="Could not create permission",
                error_code=status.HTTP_400_BAD_REQUEST,
                details={"error": str(e)},
            ),
        )


@router.get("/", response_model=dict, status_code=status.HTTP_200_OK)
async def get_permissions(
    skip: int = Query(0, ge=0, description="Number of records to skip"),
    limit: int = Query(100, ge=1, le=100, description="Max number of records to fetch"),
    module: Optional[str] = Query(None, description="Filter by module"),
    action: Optional[str] = Query(None, description="Filter by action"),
    db: Session = Depends(get_db),
    _=Depends(PermissionChecker(["permissions.read"], check_tenant=False))
):
    """Get a list of permissions with optional filters"""
    try:
        filters = {}
        if module:
            filters["module"] = module
        if action:
            filters["action"] = action

        permissions = permission_crud.get_multi(db, skip=skip, limit=limit, filters=filters)
        total = permission_crud.count(db, filters=filters)

        items = [PermissionResponse.model_validate(p, from_attributes=True) for p in permissions]

        logger.info(f"Fetched {len(items)} permissions (total={total}, skip={skip}, limit={limit})")

        return ResponseWrapper.success(
            data=PermissionPaginationResponse(total=total, items=items),
            message="Permissions fetched successfully"
        )
    except Exception as e:
        logger.exception(f"Error fetching permissions: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=ResponseWrapper.error(
                message="Unexpected error while fetching permissions",
                error_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                details={"error": str(e)},
            ),
        )


@router.get("/{permission_id}", response_model=dict, status_code=status.HTTP_200_OK)
async def get_permission(
    permission_id: int,
    db: Session = Depends(get_db),
    _=Depends(PermissionChecker(["permissions.read"], check_tenant=False))
):
    """Get a specific permission by ID"""
    try:
        permission = permission_crud.get(db, id=permission_id)
        if not permission:
            logger.warning(f"Permission not found: {permission_id}")
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=ResponseWrapper.error(
                    message="Permission not found",
                    error_code=status.HTTP_404_NOT_FOUND,
                ),
            )

        return ResponseWrapper.success(
            data=PermissionResponse.model_validate(permission, from_attributes=True),
            message="Permission fetched successfully"
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.exception(f"Error fetching permission {permission_id}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=ResponseWrapper.error(
                message=f"Unexpected error while fetching permission {permission_id}",
                error_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                details={"error": str(e)},
            ),
        )


@router.put("/{permission_id}", response_model=dict, status_code=status.HTTP_200_OK)
async def update_permission(
    permission_id: int,
    permission_update: PermissionUpdate,
    db: Session = Depends(get_db),
    _=Depends(PermissionChecker(["permissions.update"], check_tenant=False))
):
    """Update a permission"""
    try:
        permission = permission_crud.get(db, id=permission_id)
        if not permission:
            logger.warning(f"Permission update failed - not found: {permission_id}")
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=ResponseWrapper.error(
                    message="Permission not found",
                    error_code=status.HTTP_404_NOT_FOUND,
                ),
            )

        updated_permission = permission_crud.update(db, db_obj=permission, obj_in=permission_update)

        logger.info(f"Permission updated: {permission_id}")

        return ResponseWrapper.success(
            data=PermissionResponse.model_validate(updated_permission, from_attributes=True),
            message=f"Permission {permission_id} updated successfully"
        )
    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        logger.exception(f"Error updating permission {permission_id}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=ResponseWrapper.error(
                message=f"Unexpected error while updating permission {permission_id}",
                error_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                details={"error": str(e)},
            ),
        )


@router.delete("/{permission_id}", status_code=status.HTTP_200_OK, response_model=dict)
async def delete_permission(
    permission_id: int,
    db: Session = Depends(get_db),
    _=Depends(PermissionChecker(["permissions.delete"], check_tenant=False))
):
    """Delete a permission"""
    try:
        permission = permission_crud.get(db, id=permission_id)
        if not permission:
            logger.warning(f"Permission delete failed - not found: {permission_id}")
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=ResponseWrapper.error(
                    message="Permission not found",
                    error_code=status.HTTP_404_NOT_FOUND,
                ),
            )

        permission_crud.remove(db, id=permission_id)

        logger.info(f"Permission deleted: {permission_id}")

        return ResponseWrapper.success(
            data=None,
            message=f"Permission {permission_id} deleted successfully"
        )
    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        logger.exception(f"Error deleting permission {permission_id}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=ResponseWrapper.error(
                message=f"Unexpected error while deleting permission {permission_id}",
                error_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                details={"error": str(e)},
            ),
        )
