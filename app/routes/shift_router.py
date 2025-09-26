from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.orm import Session
from sqlalchemy.exc import SQLAlchemyError
from typing import Optional

from app.database.session import get_db
from app.models.shift import Shift
from app.schemas.shift import ShiftCreate, ShiftUpdate, ShiftResponse, ShiftPaginationResponse
from app.crud.shift import shift_crud
from app.crud.tenant import tenant_crud
from app.utils.pagination import paginate_query
from app.utils.response_utils import ResponseWrapper, handle_db_error, handle_http_error
from common_utils.auth.permission_checker import PermissionChecker
from app.core.logging_config import get_logger

logger = get_logger(__name__)
router = APIRouter(prefix="/shifts", tags=["shifts"])


@router.post("/", response_model=dict, status_code=status.HTTP_201_CREATED)
def create_shift(
    shift_in: ShiftCreate,
    db: Session = Depends(get_db),
    user_data=Depends(PermissionChecker(["shift.create"], check_tenant=True)),
):
    """
    Create a new shift for a tenant.

    Rules:
    - vendor/driver -> forbidden
    - employee -> tenant_id taken from token
    - admin/superadmin -> tenant_id must be provided in payload (shift_in.tenant_id)
    """
    try:
        user_type = user_data.get("user_type")
        token_tenant_id = user_data.get("tenant_id")

        # ---- Basic role guards ----
        if user_type in {"vendor", "driver"}:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=ResponseWrapper.error(
                    message="You don't have permission to create shifts",
                    error_code="FORBIDDEN",
                ),
            )

        # ---- Determine tenant_id to use ----
        if user_type == "employee":
            tenant_id = token_tenant_id
            if not tenant_id:
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail=ResponseWrapper.error(
                        message="Tenant ID missing in token for employee",
                        error_code="TENANT_ID_REQUIRED",
                    ),
                )
        elif user_type in {"admin", "superadmin"}:
            tenant_id = getattr(shift_in, "tenant_id", None)
            if not tenant_id:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=ResponseWrapper.error(
                        message="tenant_id is required in payload for admin users",
                        error_code="TENANT_ID_REQUIRED",
                    ),
                )
        else:
            # conservative default
            tenant_id = token_tenant_id
            if not tenant_id:
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail=ResponseWrapper.error(
                        message="Tenant context not available",
                        error_code="TENANT_ID_REQUIRED",
                    ),
                )

        # ---- Validate tenant exists ----
        tenant = tenant_crud.get_by_id(db=db, tenant_id=tenant_id)
        if not tenant:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=ResponseWrapper.error(
                    message=f"Tenant {tenant_id} not found",
                    error_code="TENANT_NOT_FOUND",
                ),
            )

        # ---- Prevent duplicate shift_code inside tenant ----
        shift_code = getattr(shift_in, "shift_code", None)
        if shift_code:
            existing = shift_crud.get_by_code(db, tenant_id=tenant_id, shift_code=shift_code)
            if existing:
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail=ResponseWrapper.error(
                        message=f"Shift with code '{shift_code}' already exists for tenant {tenant_id}",
                        error_code="SHIFT_CODE_CONFLICT",
                    ),
                )

        # ---- Create shift (CRUD should not commit) ----
        new_shift = shift_crud.create_with_tenant(db=db, obj_in=shift_in, tenant_id=tenant_id)

        # commit/refresh
        db.commit()
        db.refresh(new_shift)

        logger.info(f"Shift created for tenant {tenant_id}: {new_shift.shift_code} by user {user_data.get('user_id')}")

        return ResponseWrapper.success(
            data=ShiftResponse.model_validate(new_shift, from_attributes=True),
            message="Shift created successfully"
        )

    except SQLAlchemyError as e:
        raise handle_db_error(e)
    except HTTPException:
        raise
    except Exception as e:
        logger.exception(f"Unexpected error while creating shift: {e}")
        raise handle_http_error(e)


@router.get("/", response_model=dict, status_code=status.HTTP_200_OK)
def read_shifts(
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=500),
    is_active: Optional[bool] = Query(None),
    tenant_id: Optional[str] = Query(None, description="Tenant ID (required for admin/superadmin)"),
    db: Session = Depends(get_db),
    user_data=Depends(PermissionChecker(["shift.read"], check_tenant=True)),
):
    """
    Fetch shifts with optional filters for the tenant.

    Rules:
    - vendor/driver -> forbidden
    - employee -> tenant_id taken from token
    - admin/superadmin -> tenant_id must be provided as query param
    """
    try:
        user_type = user_data.get("user_type")
        token_tenant_id = user_data.get("tenant_id")

        # ---- Basic role guards ----
        if user_type in {"vendor", "driver"}:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=ResponseWrapper.error(
                    message="You don't have permission to read shifts",
                    error_code="FORBIDDEN",
                ),
            )

        # ---- Determine tenant_id to use ----
        if user_type == "employee":
            resolved_tenant_id = token_tenant_id
            if not resolved_tenant_id:
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail=ResponseWrapper.error(
                        message="Tenant ID missing in token for employee",
                        error_code="TENANT_ID_REQUIRED",
                    ),
                )
        elif user_type in {"admin", "superadmin"}:
            resolved_tenant_id = tenant_id
            if not resolved_tenant_id:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=ResponseWrapper.error(
                        message="tenant_id query param is required for admin users",
                        error_code="TENANT_ID_REQUIRED",
                    ),
                )
        else:
            # conservative fallback
            resolved_tenant_id = token_tenant_id
            if not resolved_tenant_id:
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail=ResponseWrapper.error(
                        message="Tenant context not available",
                        error_code="TENANT_ID_REQUIRED",
                    ),
                )

        # ---- Validate tenant exists ----
        tenant = tenant_crud.get_by_id(db=db, tenant_id=resolved_tenant_id)
        if not tenant:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=ResponseWrapper.error(
                    message=f"Tenant {resolved_tenant_id} not found",
                    error_code="TENANT_NOT_FOUND",
                ),
            )

        # ---- Build query ----
        query = db.query(Shift).filter(Shift.tenant_id == resolved_tenant_id)

        if is_active is not None:
            query = query.filter(Shift.is_active == is_active)

        total, items = paginate_query(query, skip, limit)
        shifts = [ShiftResponse.model_validate(s, from_attributes=True) for s in items]

        logger.info(
            f"Fetched {len(shifts)} shifts for tenant {resolved_tenant_id} "
            f"by user {user_data.get('user_id')} ({user_type})"
        )

        return ResponseWrapper.success(
            data=ShiftPaginationResponse(total=total, items=shifts),
            message="Shifts fetched successfully"
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.exception(f"Unexpected error while reading shifts: {e}")
        raise handle_http_error(e)

@router.get("/{shift_id}", response_model=dict, status_code=status.HTTP_200_OK)
def read_shift(
    shift_id: int,
    db: Session = Depends(get_db),
    user_data=Depends(PermissionChecker(["shift.read"], check_tenant=True)),
):
    """
    Fetch a shift by ID.

    Rules:
    - vendor/driver -> forbidden
    - employee -> tenant_id taken from token; must match shift's tenant
    - admin/superadmin -> no tenant_id needed; can fetch any shift by ID
    """
    try:
        user_type = user_data.get("user_type")
        token_tenant_id = user_data.get("tenant_id")

        # ---- Role guards ----
        if user_type in {"vendor", "driver"}:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=ResponseWrapper.error(
                    message="You don't have permission to read shifts",
                    error_code="FORBIDDEN",
                ),
            )

        # ---- Fetch shift by ID (tenant scope applied later if needed) ----
        db_shift = db.query(Shift).filter(Shift.shift_id == shift_id).first()
        if not db_shift:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=ResponseWrapper.error(
                    message=f"Shift {shift_id} not found",
                    error_code="NOT_FOUND",
                ),
            )

        # ---- Employee must match their tenant ----
        if user_type == "employee":
            if not token_tenant_id or db_shift.tenant_id != token_tenant_id:
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail=ResponseWrapper.error(
                        message="You don't have access to this shift",
                        error_code="TENANT_MISMATCH",
                    ),
                )

        # ---- Admin/Superadmin -> allowed, no tenant check ----
        # (we already fetched by ID, so they get the record regardless of tenant)

        logger.info(
            f"Shift {shift_id} fetched by user {user_data.get('user_id')} ({user_type}), "
            f"tenant {db_shift.tenant_id}"
        )

        return ResponseWrapper.success(
            data=ShiftResponse.model_validate(db_shift, from_attributes=True),
            message="Shift fetched successfully"
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.exception(f"Unexpected error while reading shift {shift_id}: {e}")
        raise handle_http_error(e)


@router.put("/{shift_id}", response_model=dict, status_code=status.HTTP_200_OK)
def update_shift(
    shift_id: int,
    shift_update: ShiftUpdate,
    db: Session = Depends(get_db),
    user_data=Depends(PermissionChecker(["shift.update"], check_tenant=True)),
):
    """
    Update a shift by ID.

    Rules:
    - vendor/driver -> forbidden
    - employee -> tenant_id taken from token; must match shift's tenant
    - admin/superadmin -> no tenant_id needed; can update any shift by ID
    """
    try:
        user_type = user_data.get("user_type")
        token_tenant_id = user_data.get("tenant_id")

        # ---- Role guards ----
        if user_type in {"vendor", "driver"}:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=ResponseWrapper.error(
                    message="You don't have permission to update shifts",
                    error_code="FORBIDDEN",
                ),
            )

        # ---- Fetch shift ----
        db_shift = db.query(Shift).filter(Shift.shift_id == shift_id).first()
        if not db_shift:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=ResponseWrapper.error(
                    message=f"Shift {shift_id} not found",
                    error_code="NOT_FOUND",
                ),
            )

        # ---- Employee must match their tenant ----
        if user_type == "employee":
            if not token_tenant_id or db_shift.tenant_id != token_tenant_id:
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail=ResponseWrapper.error(
                        message="You don't have access to update this shift",
                        error_code="TENANT_MISMATCH",
                    ),
                )

        # ---- Admin/Superadmin -> allowed ----
        # No tenant check needed, they can update any shift

        # ---- Perform update ----
        db_shift = shift_crud.update(db, db_obj=db_shift, obj_in=shift_update)

        db.commit()
        db.refresh(db_shift)

        logger.info(
            f"Shift {shift_id} updated by user {user_data.get('user_id')} ({user_type}), "
            f"tenant {db_shift.tenant_id}"
        )

        return ResponseWrapper.success(
            data=ShiftResponse.model_validate(db_shift, from_attributes=True),
            message="Shift updated successfully"
        )
    except SQLAlchemyError as e:
        raise handle_db_error(e)
    except HTTPException:
        raise
    except Exception as e:
        logger.exception(f"Unexpected error while updating shift {shift_id}: {e}")
        raise handle_http_error(e)


@router.patch("/{shift_id}/toggle-status", status_code=status.HTTP_200_OK)
def toggle_shift_status(
    shift_id: int,
    db: Session = Depends(get_db),
    user_data=Depends(PermissionChecker(["shift.update"], check_tenant=True)),
):
    """
    Toggle a shift's active/inactive status.

    Rules:
    - vendor/driver -> forbidden
    - employee -> can only toggle shifts within their tenant
    - admin/superadmin -> can toggle any shift
    """
    try:
        user_type = user_data.get("user_type")
        token_tenant_id = user_data.get("tenant_id")

        # ---- Role guards ----
        if user_type in {"vendor", "driver"}:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=ResponseWrapper.error(
                    message="You don't have permission to toggle shifts",
                    error_code="FORBIDDEN",
                ),
            )

        # ---- Fetch shift by ID ----
        db_shift = db.query(Shift).filter(Shift.shift_id == shift_id).first()
        if not db_shift:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=ResponseWrapper.error(
                    message=f"Shift {shift_id} not found",
                    error_code="NOT_FOUND",
                ),
            )

        # ---- Employee tenant check ----
        if user_type == "employee" and db_shift.tenant_id != token_tenant_id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=ResponseWrapper.error(
                    message="You don't have access to toggle this shift",
                    error_code="TENANT_MISMATCH",
                ),
            )

        # ---- Toggle status ----
        db_shift.is_active = not db_shift.is_active
        db.commit()
        db.refresh(db_shift)

        logger.info(
            f"Shift {shift_id} toggled to {'active' if db_shift.is_active else 'inactive'} "
            f"by user {user_data.get('user_id')} ({user_type}), tenant {db_shift.tenant_id}"
        )

        return ResponseWrapper.success(
            data=ShiftResponse.model_validate(db_shift, from_attributes=True),
            message=f"Shift {shift_id} is now {'active' if db_shift.is_active else 'inactive'}"
        )

    except HTTPException:
        raise
    except SQLAlchemyError as e:
        raise handle_db_error(e)
    except Exception as e:
        logger.exception(f"Unexpected error while toggling shift {shift_id}: {e}")
        raise handle_http_error(e)


# @router.delete("/{shift_id}", status_code=status.HTTP_204_NO_CONTENT)
# def delete_shift(
#     shift_id: int,
#     db: Session = Depends(get_db),
#     user_data=Depends(PermissionChecker(["shift.delete"]))
# ):
#     """
#     Delete a shift (hard delete).
#     """
#     try:
#         tenant_id = user_data.get("tenant_id")
#         success = shift_crud.remove_with_tenant(db, tenant_id=tenant_id, shift_id=shift_id)
#         if not success:
#             raise HTTPException(
#                 status_code=status.HTTP_404_NOT_FOUND,
#                 detail=ResponseWrapper.error(f"Shift {shift_id} not found", "NOT_FOUND")
#             )

#         logger.info(f"Shift {shift_id} deleted for tenant {tenant_id}")
#         return None
#     except Exception as e:
#         raise handle_http_error(e)
