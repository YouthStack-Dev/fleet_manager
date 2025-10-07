from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.orm import Session
from typing import Optional
from app.database.session import get_db
from app.crud.vehicle import  vehicle_crud
from app.crud.vendor import vendor_crud
from app.crud.vehicle_type import vehicle_type_crud
from app.crud.driver import driver_crud
from sqlalchemy.exc import SQLAlchemyError
from app.models.vehicle import Vehicle
from app.schemas.vehicle import VehicleCreate, VehicleUpdate, VehicleResponse, VehiclePaginationResponse
from app.utils.pagination import paginate_query
from app.utils.response_utils import ResponseWrapper, handle_db_error, handle_http_error
from common_utils.auth.permission_checker import PermissionChecker
from app.core.logging_config import get_logger

logger = get_logger(__name__)
router = APIRouter(prefix="/vehicles", tags=["vehicles"])


@router.post("/", response_model=dict, status_code=status.HTTP_201_CREATED)
def create_vehicle(
    vehicle_in: VehicleCreate,
    db: Session = Depends(get_db),
    user_data=Depends(PermissionChecker(["vehicle.create"], check_tenant=False)),
):
    """
    Create a new vehicle.

    Rules:
    - Vendor users -> vendor_id taken from token (payload.vendor_id ignored)
    - Admin users  -> vendor_id must be provided in payload
    - Others       -> forbidden
    """
    try:
        user_type = user_data.get("user_type")

        # --- Vendor role ---
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
                    message="You don't have permission to create vehicles",
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

        # --- Validate vehicle type belongs to vendor ---
        vehicle_type = vehicle_type_crud.get_by_vendor_and_id(
            db, vendor_id=vendor_id, vehicle_type_id=vehicle_in.vehicle_type_id
        )
        if not vehicle_type:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=ResponseWrapper.error(
                    message="Invalid vehicle_type_id for this vendor",
                    error_code="INVALID_VEHICLE_TYPE",
                ),
            )

        # --- Validate driver (if provided) ---
        if vehicle_in.driver_id:
            driver = driver_crud.get_by_id_and_vendor(
                db, driver_id=vehicle_in.driver_id, vendor_id=vendor_id
            )
            if not driver:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=ResponseWrapper.error(
                        message="Driver not found for this vendor",
                        error_code="INVALID_DRIVER",
                    ),
                )

        # --- Create ---
        db_obj = vehicle_crud.create_with_vendor(db, vendor_id=vendor_id, obj_in=vehicle_in)
        db.commit()
        db.refresh(db_obj)

        logger.info(
            f"Vehicle '{vehicle_in.rc_number}' created for vendor {vendor_id} by user {user_data.get('user_id')}"
        )

        return ResponseWrapper.success(
            data={"vehicle": VehicleResponse.model_validate(db_obj, from_attributes=True)},
            message="Vehicle created successfully",
        )

    except SQLAlchemyError as e:
        db.rollback()
        logger.exception(f"DB error while creating vehicle: {e}")
        raise handle_db_error(e)
    except HTTPException:
        db.rollback()
        raise
    except Exception as e:
        db.rollback()
        logger.exception(f"Unexpected error creating vehicle: {e}")
        raise handle_http_error(e)

@router.get("/{vehicle_id}", status_code=status.HTTP_200_OK)
def read_vehicle(
    vehicle_id: int,
    db: Session = Depends(get_db),
    user_data=Depends(PermissionChecker(["vehicle.read"], check_tenant=True)),
):
    """
    Get details of a specific vehicle by ID.
    Enforces tenant isolation for vendor users.
    """
    try:
        user_type = user_data.get("user_type")
        token_vendor_id = user_data.get("vendor_id")

        query = db.query(Vehicle).filter(Vehicle.vehicle_id == vehicle_id)

        # --- Restrict vendor user to own vendor_id
        if user_type == "vendor":
            query = query.filter(Vehicle.vendor_id == token_vendor_id)

        db_vehicle = query.first()
        if not db_vehicle:
            logger.warning(f"[VehicleRead] Vehicle ID {vehicle_id} not found or unauthorized access")
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=ResponseWrapper.error(f"Vehicle {vehicle_id} not found", "VEHICLE_NOT_FOUND"),
            )

        logger.info(f"[VehicleRead] Vehicle ID={vehicle_id} fetched by user_id={user_data.get('user_id')}")
        return ResponseWrapper.success(
            data=VehicleResponse.model_validate(db_vehicle, from_attributes=True),
            message="Vehicle details fetched successfully",
        )

    except SQLAlchemyError as e:
        logger.exception(f"[VehicleRead] DB error for vehicle_id={vehicle_id}: {e}")
        raise handle_db_error(e)
    except HTTPException as e:
        logger.exception(f"[VehicleRead] HTTP error for vehicle_id={vehicle_id}: {e}")
        raise handle_http_error(e)
    except Exception as e:
        logger.exception(f"[VehicleRead] Unexpected error for vehicle_id={vehicle_id}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=ResponseWrapper.error("Unexpected error fetching vehicle details", "VEHICLE_READ_FAILED"),
        )

@router.get("/", status_code=status.HTTP_200_OK, response_model=dict)
def read_vehicles(
    skip: int = 0,
    limit: int = 100,
    rc_number: Optional[str] = None,
    vendor_id: Optional[int] = None,
    vehicle_type_id: Optional[int] = None,
    driver_id: Optional[int] = None,
    is_active: Optional[bool] = None,
    db: Session = Depends(get_db),
    user_data=Depends(PermissionChecker(["vehicle.read"], check_tenant=True)),
):
    try:
        user_type = user_data.get("user_type")
        token_vendor_id = user_data.get("vendor_id")

        if user_type == "vendor":
            vendor_id = token_vendor_id
        elif user_type in ["employee", "driver"]:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=ResponseWrapper.error(
                    message="You don't have permission to create vehicles",
                    error_code="FORBIDDEN",
                ),
            )

        query = db.query(Vehicle)
        if vendor_id:
            query = query.filter(Vehicle.vendor_id == vendor_id)
        if rc_number:
            query = query.filter(Vehicle.rc_number.ilike(f"%{rc_number}%"))
        if vehicle_type_id:
            query = query.filter(Vehicle.vehicle_type_id == vehicle_type_id)
        if driver_id:
            query = query.filter(Vehicle.driver_id == driver_id)
        if is_active is not None:
            query = query.filter(Vehicle.is_active == is_active)

        total, items = paginate_query(query, skip, limit)

        # 🔥 Convert ORM → Pydantic
        vehicle_list = [VehicleResponse.model_validate(vehicle) for vehicle in items]

        logger.info(
            f"[VehicleList] vendor_id={vendor_id} user_id={user_data.get('user_id')} "
            f"filters={{rc_number:{rc_number}, driver_id:{driver_id}, active:{is_active}}} "
            f"returned={len(vehicle_list)}"
        )

        return ResponseWrapper.success(
            data={"total": total, "items": vehicle_list},
            message="Vehicle list fetched successfully",
        )

    except SQLAlchemyError as e:
        logger.exception(f"[VehicleList] DB error: {e}")
        raise handle_db_error(e)
    except HTTPException:
        logger.exception(f"[VehicleList] HTTP error: {e}")
        raise handle_http_error(e)
    except Exception as e:
        logger.exception(f"[VehicleList] Unexpected error: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=ResponseWrapper.error("Unexpected error fetching vehicles", "VEHICLE_FETCH_FAILED"),
        )



@router.put("/{vehicle_id}", response_model=VehicleResponse)
def update_vehicle(
    vehicle_id: int, 
    vehicle_update: VehicleUpdate, 
    db: Session = Depends(get_db),
    user_data=Depends(PermissionChecker(["vehicle.update"], check_tenant=True))
):
    db_vehicle = db.query(Vehicle).filter(Vehicle.vehicle_id == vehicle_id).first()
    if not db_vehicle:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Vehicle with ID {vehicle_id} not found"
        )
    
    update_data = vehicle_update.dict(exclude_unset=True)
    for key, value in update_data.items():
        setattr(db_vehicle, key, value)
    
    db.commit()
    db.refresh(db_vehicle)
    return db_vehicle

@router.delete("/{vehicle_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_vehicle(
    vehicle_id: int, 
    db: Session = Depends(get_db),
    user_data=Depends(PermissionChecker(["vehicle.delete"], check_tenant=True))
):
    db_vehicle = db.query(Vehicle).filter(Vehicle.vehicle_id == vehicle_id).first()
    if not db_vehicle:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Vehicle with ID {vehicle_id} not found"
        )
    
    db.delete(db_vehicle)
    db.commit()
    return None
