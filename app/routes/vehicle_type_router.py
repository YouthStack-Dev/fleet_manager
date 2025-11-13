from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from sqlalchemy.exc import SQLAlchemyError
from typing import Optional

from app.crud.vendor import vendor_crud
from app.database.session import get_db
from app.schemas.vehicle_type import (
    VehicleTypeCreate,
    VehicleTypeUpdate,
    VehicleTypeResponse,
)
from app.crud.vehicle_type import vehicle_type_crud
from app.utils.response_utils import ResponseWrapper, handle_db_error, handle_http_error
from common_utils.auth.permission_checker import PermissionChecker
from app.core.logging_config import get_logger

logger = get_logger(__name__)
router = APIRouter(prefix="/vehicle-types", tags=["vehicle types"])


# ---------------------------
# Vendor scope resolver
# ---------------------------
def resolve_vendor_scope(user_data: dict, provided_vendor_id: Optional[int], allow_create: bool) -> int:
    """
    Resolve and return the vendor_id the current user is allowed to operate on.

    Rules:
      - admin: GLOBAL — provided_vendor_id **must** be given (payload/query).
      - vendor: vendor_id from token (provided_vendor_id ignored/overwritten).
      - employee: tenant-level admin — provided_vendor_id **must** be given and will be validated
                  that vendor.tenant_id == user_data['tenant_id'].
      - others: forbidden
    """
    user_type = user_data.get("user_type")
    token_vendor_id = user_data.get("vendor_id")
    token_tenant_id = user_data.get("tenant_id")

    # Admin (global)
    if user_type == "admin":
        if not provided_vendor_id:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=ResponseWrapper.error("vendor_id is required for admin users", "VENDOR_ID_REQUIRED"),
            )
        return provided_vendor_id

    # Vendor (scoped)
    if user_type == "vendor":
        if not token_vendor_id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=ResponseWrapper.error("Vendor ID missing in vendor token", "VENDOR_ID_REQUIRED"),
            )
        # vendor cannot act on other vendors
        return token_vendor_id

    # Employee (tenant-level admin)
    if user_type == "employee":
        if allow_create is False:
            # allow_create flag is used only to permit create; employees are allowed to create per your spec,
            # so create calls will pass allow_create=True. We keep this check to be explicit.
            pass
        if not provided_vendor_id:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=ResponseWrapper.error("vendor_id is required for employee operations", "VENDOR_ID_REQUIRED"),
            )
        # vendor_id will be validated later against tenant
        return provided_vendor_id

    # Others
    raise HTTPException(
        status_code=status.HTTP_403_FORBIDDEN,
        detail=ResponseWrapper.error("You don't have permission to perform this action", "FORBIDDEN"),
    )


# ---------------------------
# Helper: validate vendor exists + employee tenant check
# ---------------------------
def validate_vendor_and_tenant(db: Session, vendor_id: int, user_data: dict):
    """
    Ensures vendor exists. If user is employee, ensure vendor.tenant_id == user_data['tenant_id'].
    """
    vendor = vendor_crud.get_by_id(db, vendor_id=vendor_id)
    if not vendor:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=ResponseWrapper.error(f"Vendor {vendor_id} not found", "VENDOR_NOT_FOUND"),
        )

    if user_data.get("user_type") == "employee":
        token_tenant_id = user_data.get("tenant_id")
        # tenant_id must be present on employee token
        if not token_tenant_id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=ResponseWrapper.error("Tenant ID missing in employee token", "TENANT_ID_REQUIRED"),
            )
        if getattr(vendor, "tenant_id", None) != token_tenant_id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=ResponseWrapper.error("Vendor does not belong to your tenant", "TENANT_FORBIDDEN"),
            )

    return vendor


# ---------------------------
# CREATE
# ---------------------------
@router.post("/", response_model=dict, status_code=status.HTTP_201_CREATED)
def create_vehicle_type(
    vehicle_in: VehicleTypeCreate,
    db: Session = Depends(get_db),
    user_data=Depends(PermissionChecker(["vehicle-type.create"], check_tenant=False)),
):
    """
    Create a new vehicle type.

    - admin: provide vendor_id in payload
    - vendor: vendor_id taken from token (payload.vendor_id ignored)
    - employee: provide vendor_id in payload (must belong to employee's tenant)
    """
    try:
        # determine vendor_id source:
        vendor_id_candidate = getattr(vehicle_in, "vendor_id", None)
        vendor_id = resolve_vendor_scope(user_data=user_data, provided_vendor_id=vendor_id_candidate, allow_create=True)

        # validate vendor and tenant relation (for employees)
        validate_vendor_and_tenant(db, vendor_id, user_data)

        # prevent duplicate
        existing = (
            db.query(vehicle_type_crud.model)
            .filter_by(vendor_id=vendor_id, name=vehicle_in.name)
            .first()
        )
        if existing:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=ResponseWrapper.error(
                    message=f"Vehicle type '{vehicle_in.name}' already exists for vendor {vendor_id}",
                    error_code="VEHICLE_TYPE_CONFLICT",
                ),
            )

        # --- Create ---
        db_obj = vehicle_type_crud.create_with_vendor(db, vendor_id=vendor_id, obj_in=vehicle_in)
        db.commit()
        db.refresh(db_obj)

        logger.info(
            f"Vehicle type '{vehicle_in.name}' created for vendor {vendor_id} by user {user_data.get('user_id')}"
        )

        return ResponseWrapper.success(
            data={"vehicle_type": VehicleTypeResponse.model_validate(db_obj, from_attributes=True)},
            message="Vehicle type created successfully",
        )

    except SQLAlchemyError as e:
        db.rollback()
        logger.exception(f"DB error while creating vehicle type: {e}")
        raise handle_db_error(e)
    except HTTPException:
        db.rollback()
        raise
    except Exception as e:
        db.rollback()
        logger.exception(f"Unexpected error creating vehicle type: {e}")
        raise handle_http_error(e)


@router.get("/", response_model=dict, status_code=status.HTTP_200_OK)
def get_all_vehicle_types(
    vendor_id: Optional[int] = None,
    name: Optional[str] = None,
    active_only: Optional[bool] = None,
    db: Session = Depends(get_db),
    user_data=Depends(PermissionChecker(["vehicle-type.read"], check_tenant=False)),
):
    """
    Fetch vehicle types:

    - admin: vendor_id required in query
    - vendor: vendor_id taken from token
    - employee: vendor_id required in query and must belong to same tenant
    """
    try:
        vendor_id_resolved = resolve_vendor_scope(user_data=user_data, provided_vendor_id=vendor_id, allow_create=True)

        # validate vendor existence & tenant for employee
        validate_vendor_and_tenant(db, vendor_id_resolved, user_data)

        logger.info(f"Fetching vehicle types for vendor_id={vendor_id_resolved}, active_only={active_only}, name={name}")
        items = vehicle_type_crud.get_by_vendor(db, vendor_id=vendor_id_resolved, active_only=active_only, name=name)

        return ResponseWrapper.success(
            data={"items": [VehicleTypeResponse.model_validate(obj, from_attributes=True) for obj in items]},
            message=f"Vehicle types fetched for vendor {vendor_id_resolved}",
        )

    except SQLAlchemyError as e:
        logger.exception(f"DB error while fetching vehicle types: {e}")
        raise handle_db_error(e)
    except HTTPException:
        raise
    except Exception as e:
        logger.exception(f"Unexpected error fetching vehicle types: {e}")
        raise handle_http_error(e)


# ---------------------------
# GET BY ID
# ---------------------------
@router.get("/{vehicle_type_id}", response_model=dict, status_code=status.HTTP_200_OK)
def get_vehicle_type(
    vehicle_type_id: int,
    vendor_id: Optional[int] = None,
    db: Session = Depends(get_db),
    user_data=Depends(PermissionChecker(["vehicle-type.read"], check_tenant=False)),
):
    """
    Get single vehicle type by ID.

    vendor_id must be provided by admin/employee as query param.
    vendor token overrides for vendor users.
    """
    try:
        vendor_id_resolved = resolve_vendor_scope(user_data=user_data, provided_vendor_id=vendor_id, allow_create=True)

        # validate vendor + tenant
        validate_vendor_and_tenant(db, vendor_id_resolved, user_data)

        db_obj = vehicle_type_crud.get_by_vendor_and_id(db, vendor_id=vendor_id_resolved, vehicle_type_id=vehicle_type_id)
        if not db_obj:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=ResponseWrapper.error(
                    f"Vehicle type {vehicle_type_id} not found for vendor {vendor_id_resolved}",
                    "VEHICLE_TYPE_NOT_FOUND",
                ),
            )

        return ResponseWrapper.success(
            data={"vehicle_type": VehicleTypeResponse.model_validate(db_obj, from_attributes=True)},
            message=f"Vehicle type {vehicle_type_id} fetched successfully",
        )

    except SQLAlchemyError as e:
        logger.exception(f"DB error while fetching vehicle type {vehicle_type_id}: {e}")
        raise handle_db_error(e)
    except HTTPException:
        raise
    except Exception as e:
        logger.exception(f"Unexpected error fetching vehicle type {vehicle_type_id}: {e}")
        raise handle_http_error(e)


# ---------------------------
# UPDATE
# ---------------------------
@router.put("/{vehicle_type_id}", response_model=dict, status_code=status.HTTP_200_OK)
def update_vehicle_type(
    vehicle_type_id: int,
    update_in: VehicleTypeUpdate,
    vendor_id: Optional[int] = None,
    db: Session = Depends(get_db),
    user_data=Depends(PermissionChecker(["vehicle-type.update"], check_tenant=False)),
):
    """
    Update vehicle type.

    - admin: vendor_id query required
    - vendor: vendor_id from token
    - employee: vendor_id query required and must be within employee's tenant
    """
    try:
        vendor_id_resolved = resolve_vendor_scope(user_data=user_data, provided_vendor_id=vendor_id, allow_create=True)

        # validate vendor + tenant
        validate_vendor_and_tenant(db, vendor_id_resolved, user_data)

        db_obj = vehicle_type_crud.get_by_vendor_and_id(db, vendor_id=vendor_id_resolved, vehicle_type_id=vehicle_type_id)
        if not db_obj:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=ResponseWrapper.error("Vehicle type not found", "VEHICLE_TYPE_NOT_FOUND"),
            )

        # duplicate name check
        if update_in.name and update_in.name != db_obj.name:
            duplicate = vehicle_type_crud.get_by_vendor_and_name(db, vendor_id=db_obj.vendor_id, name=update_in.name)
            if duplicate:
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail=ResponseWrapper.error(
                        f"Vehicle type '{update_in.name}' already exists for vendor {db_obj.vendor_id}",
                        "VEHICLE_TYPE_CONFLICT",
                    ),
                )

        update_data = update_in.model_dump(exclude_unset=True)
        for field, value in update_data.items():
            setattr(db_obj, field, value)

        db.commit()
        db.refresh(db_obj)

        logger.info(f"Vehicle type {vehicle_type_id} updated by user {user_data.get('user_id')} with data={update_data}")

        return ResponseWrapper.success(
            data={"vehicle_type": VehicleTypeResponse.model_validate(db_obj, from_attributes=True)},
            message="Vehicle type updated successfully",
        )

    except SQLAlchemyError as e:
        db.rollback()
        logger.exception(f"DB error while updating vehicle type {vehicle_type_id}: {e}")
        raise handle_db_error(e)
    except HTTPException:
        db.rollback()
        raise
    except Exception as e:
        db.rollback()
        logger.exception(f"Unexpected error updating vehicle type {vehicle_type_id}: {e}")
        raise handle_http_error(e)


# ---------------------------
# TOGGLE STATUS
# ---------------------------
@router.patch("/{vehicle_type_id}/toggle-status", response_model=dict, status_code=status.HTTP_200_OK)
def toggle_vehicle_type_status(
    vehicle_type_id: int,
    vendor_id: Optional[int] = None,
    db: Session = Depends(get_db),
    user_data=Depends(PermissionChecker(["vehicle-type.update"], check_tenant=False)),
):
    """
    Toggle active status.

    - admin: vendor_id required in query
    - vendor: vendor_id from token
    - employee: vendor_id required in query and must belong to employee's tenant
    """
    try:
        vendor_id_resolved = resolve_vendor_scope(user_data=user_data, provided_vendor_id=vendor_id, allow_create=True)

        # validate vendor + tenant
        validate_vendor_and_tenant(db, vendor_id_resolved, user_data)

        db_obj = vehicle_type_crud.get_by_vendor_and_id(db, vendor_id=vendor_id_resolved, vehicle_type_id=vehicle_type_id)
        if not db_obj:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=ResponseWrapper.error("Vehicle type not found", "VEHICLE_TYPE_NOT_FOUND"),
            )

        db_obj.is_active = not db_obj.is_active
        db.commit()
        db.refresh(db_obj)

        status_text = "activated" if db_obj.is_active else "deactivated"
        logger.info(f"Vehicle type {vehicle_type_id} {status_text} by user {user_data.get('user_id')}")

        return ResponseWrapper.success(
            data={"vehicle_type": VehicleTypeResponse.model_validate(db_obj, from_attributes=True)},
            message=f"Vehicle type {vehicle_type_id} {status_text} successfully",
        )

    except SQLAlchemyError as e:
        db.rollback()
        logger.exception(f"DB error while toggling status of vehicle type {vehicle_type_id}: {e}")
        raise handle_db_error(e)
    except HTTPException:
        db.rollback()
        raise
    except Exception as e:
        db.rollback()
        logger.exception(f"Unexpected error toggling status of vehicle type {vehicle_type_id}: {e}")
        raise handle_http_error(e)
