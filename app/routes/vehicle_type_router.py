from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from sqlalchemy.exc import SQLAlchemyError
from typing import Optional
from app.crud.vendor import vendor_crud
from app.database.session import get_db
from app.schemas.vehicle_type import VehicleTypeCreate, VehicleTypeUpdate, VehicleTypeResponse
from app.crud.vehicle_type import vehicle_type_crud
from app.utils.response_utils import ResponseWrapper, handle_db_error, handle_http_error
from common_utils.auth.permission_checker import PermissionChecker
from app.core.logging_config import get_logger

logger = get_logger(__name__)
router = APIRouter(prefix="/vehicle-types", tags=["vehicle types"])


@router.post("/", response_model=dict, status_code=status.HTTP_201_CREATED)
def create_vehicle_type(
    vehicle_in: VehicleTypeCreate,
    db: Session = Depends(get_db),
    user_data=Depends(PermissionChecker(["vehicle-type.create"], check_tenant=False)),
):
    """
    Create a new vehicle type.

    Rules:
    - vendor -> vendor_id taken from token (payload.vendor_id ignored/overwritten)
    - admin  -> vendor_id must be provided in payload
    - others -> forbidden
    """
    try:
        user_type = user_data.get("user_type")

        # --- Vendor role ---
        if user_type == "vendor":
            token_vendor_id = user_data.get("vendor_id")
            if not token_vendor_id:
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail=ResponseWrapper.error(
                        message="Vendor ID missing in token",
                        error_code="VENDOR_ID_REQUIRED",
                    ),
                )
            vendor_id = token_vendor_id  # override whatever payload has

        # --- Admin role ---
        elif user_type in {"admin"}:
            vendor_id = getattr(vehicle_in, "vendor_id", None)
            if not vendor_id:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=ResponseWrapper.error(
                        message="vendor_id is required in payload for admin/superadmin users",
                        error_code="VENDOR_ID_REQUIRED",
                    ),
                )

        # --- Others blocked ---
        else:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=ResponseWrapper.error(
                    message="You don't have permission to create vehicle types",
                    error_code="FORBIDDEN",
                ),
            )


        # --- Ensure vendor exists ---
        vendor = vendor_crud.get_by_id(db, vendor_id=vendor_id)
        if not vendor:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=ResponseWrapper.error(
                    message=f"Vendor {vendor_id} not found",
                    error_code="VENDOR_NOT_FOUND",
                ),
            )

        # --- Prevent duplicate (handled by UniqueConstraint but better explicit) ---
        existing = db.query(vehicle_type_crud.model).filter_by(
            vendor_id=vendor_id,
            name=vehicle_in.name
        ).first()
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
    name: Optional[str] = None,  # <-- filter by name
    active_only: Optional[bool] = True,
    db: Session = Depends(get_db),
    user_data=Depends(PermissionChecker(["vehicle-type.read"], check_tenant=False)),
):
    """
    Get all vehicle types under a vendor.

    Rules:
    - vendor -> vendor_id taken from token
    - admin  -> vendor_id required in query
    - others -> forbidden
    """
    try:
        user_type = user_data.get("user_type")

        if user_type == "vendor":
            vendor_id = user_data.get("vendor_id")
            if not vendor_id:
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail=ResponseWrapper.error(
                        message="Vendor ID missing in token",
                        error_code="VENDOR_ID_REQUIRED",
                    ),
                )

        elif user_type == "admin":
            if not vendor_id:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=ResponseWrapper.error(
                        message="vendor_id is required in query for admin users",
                        error_code="VENDOR_ID_REQUIRED",
                    ),
                )

        else:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=ResponseWrapper.error(
                    message="You don't have permission to read vehicle types",
                    error_code="FORBIDDEN",
                ),
            )

        vendor = vendor_crud.get_by_id(db, vendor_id=vendor_id)
        if not vendor:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=ResponseWrapper.error(
                    message=f"Vendor {vendor_id} not found",
                    error_code="VENDOR_NOT_FOUND",
                ),
            )

        logger.info(f"Fetching all vehicle types for vendor_id={vendor_id}, active_only={active_only}, name={name}")
        items = vehicle_type_crud.get_by_vendor(
            db, vendor_id=vendor_id, active_only=active_only, name=name
        )

        return ResponseWrapper.success(
            data={"items": [VehicleTypeResponse.model_validate(obj, from_attributes=True) for obj in items]},
            message=f"Vehicle types fetched for vendor {vendor_id}",
        )

    except SQLAlchemyError as e:
        logger.exception(f"DB error while fetching all vehicle types for vendor {vendor_id}: {e}")
        raise handle_db_error(e)
    except HTTPException:
        raise
    except Exception as e:
        logger.exception(f"Unexpected error fetching all vehicle types for vendor {vendor_id}: {e}")
        raise handle_http_error(e)



@router.get("/{vehicle_type_id}", response_model=dict, status_code=status.HTTP_200_OK)
def get_vehicle_type(
    vehicle_type_id: int,
    db: Session = Depends(get_db),
    user_data=Depends(PermissionChecker(["vehicle-type.read"], check_tenant=False)),
):
    """
    Get a particular vehicle type by ID.

    Rules:
    - vendor -> vendor_id taken from token
    - admin  -> vendor_id required in query
    - others -> forbidden
    """
    try:
        user_type = user_data.get("user_type")

        if user_type == "vendor":
            vendor_id = user_data.get("vendor_id")
            if not vendor_id:
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail=ResponseWrapper.error(
                        message="Vendor ID missing in token",
                        error_code="VENDOR_ID_REQUIRED",
                    ),
                )
        elif user_type == "admin":
            vendor_id = None

        else:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=ResponseWrapper.error(
                    message="You don't have permission to read vehicle types",
                    error_code="FORBIDDEN",
                ),
            )

        db_obj = vehicle_type_crud.get_by_vendor_and_id(
            db, vendor_id=vendor_id, vehicle_type_id=vehicle_type_id
        )


        if not db_obj:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=ResponseWrapper.error(
                    message=f"Vehicle type {vehicle_type_id} not found for vendor {vendor_id}",
                    error_code="VEHICLE_TYPE_NOT_FOUND",
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



@router.put("/{vehicle_type_id}", response_model=dict, status_code=status.HTTP_200_OK)
def update_vehicle_type(
    vehicle_type_id: int,
    update_in: VehicleTypeUpdate,
    db: Session = Depends(get_db),
    user_data=Depends(PermissionChecker(["vehicle-type.update"], check_tenant=False)),
):
    """Update an existing vehicle type"""
    try:
        logger.info(f"Updating vehicle type {vehicle_type_id} with data={update_in.dict(exclude_unset=True)}")
        db_obj = vehicle_type_crud.update_with_vendor(db, vehicle_type_id=vehicle_type_id, obj_in=update_in)
        db.commit()
        db.refresh(db_obj)

        return ResponseWrapper.success(
            data={"vehicle_type": VehicleTypeResponse.model_validate(db_obj, from_attributes=True)},
            message=f"Vehicle type {vehicle_type_id} updated successfully",
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


@router.delete("/{vehicle_type_id}", response_model=dict, status_code=status.HTTP_200_OK)
def delete_vehicle_type(
    vehicle_type_id: int,
    db: Session = Depends(get_db),
    user_data=Depends(PermissionChecker(["vehicle-type.delete"], check_tenant=False)),
):
    """Soft delete or deactivate a vehicle type"""
    try:
        logger.info(f"Deleting (soft) vehicle type {vehicle_type_id}")
        db_obj = db.query(vehicle_type_crud.model).filter_by(vehicle_type_id=vehicle_type_id).first()
        if not db_obj:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=ResponseWrapper.error(
                    message=f"Vehicle type {vehicle_type_id} not found",
                    error_code="VEHICLE_TYPE_NOT_FOUND",
                ),
            )

        db_obj.is_active = False
        db.commit()
        db.refresh(db_obj)

        return ResponseWrapper.success(
            data={"vehicle_type": VehicleTypeResponse.model_validate(db_obj, from_attributes=True)},
            message=f"Vehicle type {vehicle_type_id} deactivated successfully",
        )

    except SQLAlchemyError as e:
        db.rollback()
        logger.exception(f"DB error while deleting vehicle type {vehicle_type_id}: {e}")
        raise handle_db_error(e)
    except HTTPException:
        db.rollback()
        raise
    except Exception as e:
        db.rollback()
        logger.exception(f"Unexpected error deleting vehicle type {vehicle_type_id}: {e}")
        raise handle_http_error(e)
