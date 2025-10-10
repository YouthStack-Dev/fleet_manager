from datetime import date
from app.utils.file_utils import file_size_validator
from app.services.storage_service import storage_service
from fastapi import APIRouter, Depends, HTTPException, status, Query , UploadFile, Form
from fastapi.responses import FileResponse, StreamingResponse, Response
from sqlalchemy.orm import Session
from typing import Optional
import os
import mimetypes
import tempfile
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

def validate_future_dates(fields: dict, context: str = "vehicle"):
    today = date.today()
    for name, value in fields.items():
        if value and value <= today:
            field_label = name.replace("_", " ").title()
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                    detail=ResponseWrapper.error(
                        message="{field_label} must be a future date".format(field_label=field_label),
                        error_code="INVALID_DATE",
                    ),
            )


@router.post("/", response_model=dict, status_code=status.HTTP_201_CREATED)
async def create_vehicle(
    vehicle_type_id: int = Form(...),
    vendor_id: Optional[int] = Form(None),
    rc_number: str = Form(...),
    driver_id: Optional[int] = Form(None),
    rc_expiry_date: date = Form(...),
    description: Optional[str] = Form(None),
    puc_expiry_date: date = Form(...),
    fitness_expiry_date: date = Form(...),
    tax_receipt_date: date = Form(...),
    insurance_expiry_date: date = Form(...),
    permit_expiry_date: date = Form(...),

    # --- File uploads ---
    puc_file: UploadFile = Form(...),
    fitness_file: UploadFile = Form(...),
    tax_receipt_file: UploadFile = Form(...),
    insurance_file: UploadFile = Form(...),
    permit_file: UploadFile = Form(...),

    db: Session = Depends(get_db),
    user_data=Depends(PermissionChecker(["vehicle.create"], check_tenant=False)),
):
    """
    Create a new vehicle with optional file uploads.
    """
    today = date.today()

    # collect all date fields for validation
    expiry_fields = {
        "rc_expiry_date": rc_expiry_date,
        "puc_expiry_date": puc_expiry_date,
        "fitness_expiry_date": fitness_expiry_date,
        "tax_receipt_date": tax_receipt_date,
        "insurance_expiry_date": insurance_expiry_date,
        "permit_expiry_date": permit_expiry_date,
    }

    # validate each expiry date
    validate_future_dates(expiry_fields, context="vehicle")

    try:
        # --- Vendor & Admin logic remains the same ---
        user_type = user_data.get("user_type")
        if user_type == "vendor":
            vendor_id = user_data.get("vendor_id")
            logger.info(f"[VehicleCreate] Vendor ID={vendor_id} creating vehicle by user_id={user_data.get('user_id')}")
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
            logger.info(f"[VehicleCreate] Admin creating vehicle for vendor_id={vendor_id} by user_id={user_data.get('user_id')}")
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

        # --- Validate vendor, vehicle type, driver (same as before) ---
        # ...

        # --- Save files using new storage service ---
        allowed_types = ["image/jpeg", "image/png", "application/pdf"]
        
        puc_url = None
        if puc_file and await file_size_validator(puc_file, allowed_types, 5, required=False):
            puc_url = storage_service.save_file(puc_file, vendor_id, rc_number, "puc")
            
        fitness_url = None
        if fitness_file and await file_size_validator(fitness_file, allowed_types, 5, required=False):
            fitness_url = storage_service.save_file(fitness_file, vendor_id, rc_number, "fitness")
            
        tax_receipt_url = None
        if tax_receipt_file and await file_size_validator(tax_receipt_file, allowed_types, 5, required=False):
            tax_receipt_url = storage_service.save_file(tax_receipt_file, vendor_id, rc_number, "tax_receipt")
            
        insurance_url = None
        if insurance_file and await file_size_validator(insurance_file, allowed_types, 5, required=False):
            insurance_url = storage_service.save_file(insurance_file, vendor_id, rc_number, "insurance")
            
        permit_url = None
        if permit_file and await file_size_validator(permit_file, allowed_types, 5, required=False):
            permit_url = storage_service.save_file(permit_file, vendor_id, rc_number, "permit")

        # --- Build the VehicleCreate schema ---
        vehicle_in = VehicleCreate(
            vehicle_type_id=vehicle_type_id,
            vendor_id=vendor_id,
            rc_number=rc_number,
            driver_id=driver_id,
            rc_expiry_date=rc_expiry_date,
            description=description,
            puc_expiry_date=puc_expiry_date,
            fitness_expiry_date=fitness_expiry_date,
            tax_receipt_date=tax_receipt_date,
            insurance_expiry_date=insurance_expiry_date,
            permit_expiry_date=permit_expiry_date,
            
            # File URLs
            puc_url=puc_url,
            fitness_url=fitness_url,
            tax_receipt_url=tax_receipt_url,
            insurance_url=insurance_url,
            permit_url=permit_url
        )

        # --- Persist ---
        db_obj = vehicle_crud.create_with_vendor(db, vendor_id=vendor_id, obj_in=vehicle_in)
        db.commit()
        db.refresh(db_obj)

        logger.info(
            f"Vehicle '{vehicle_in.rc_number}' created for vendor {vendor_id} by user {user_data.get('user_id')}"
        )

        return ResponseWrapper.success(
            data={"vehicle": VehicleResponse.model_validate(db_obj, from_attributes=True)},
            message="Vehicle created successfully"
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



@router.put("/{vehicle_id}", response_model=dict, status_code=status.HTTP_200_OK)
async def update_vehicle(
    vehicle_id: int,
    vehicle_type_id: Optional[int] = Form(None),
    vendor_id: Optional[int] = Form(None),
    rc_number: Optional[str] = Form(None),
    driver_id: Optional[int] = Form(None),
    rc_expiry_date: Optional[date] = Form(None),
    description: Optional[str] = Form(None),
    puc_expiry_date: Optional[date] = Form(None),
    fitness_expiry_date: Optional[date] = Form(None),
    tax_receipt_date: Optional[date] = Form(None),
    insurance_expiry_date: Optional[date] = Form(None),
    permit_expiry_date: Optional[date] = Form(None),
    password: Optional[str] = Form(None),

    # --- File uploads ---
    puc_file: Optional[UploadFile] = None,
    fitness_file: Optional[UploadFile] = None,
    tax_receipt_file: Optional[UploadFile] = None,
    insurance_file: Optional[UploadFile] = None,
    permit_file: Optional[UploadFile] = None,

    db: Session = Depends(get_db),
    user_data=Depends(PermissionChecker(["vehicle.update"], check_tenant=True)),
):
    """
    Update an existing vehicle.

    Rules:
    - Vendor users → can update only their vendor's vehicles.
    - Admin users  → can update any vendor's vehicle (but must respect schema).
    - Validates:
        - Vehicle existence
        - Vehicle type belongs to vendor
        - Driver belongs to vendor (if provided)
    """
    expiry_fields = {
        "rc_expiry_date": rc_expiry_date,
        "puc_expiry_date": puc_expiry_date,
        "fitness_expiry_date": fitness_expiry_date,
        "tax_receipt_date": tax_receipt_date,
        "insurance_expiry_date": insurance_expiry_date,
        "permit_expiry_date": permit_expiry_date,
    }
    validate_future_dates(expiry_fields, context="update_vehicle")
    try:
        user_id = user_data.get("user_id")
        user_type = user_data.get("user_type")
        token_vendor_id = user_data.get("vendor_id")

        logger.info(
            f"[VehicleUpdate] user_id={user_id}, vehicle_id={vehicle_id}, user_type={user_type}"
        )

        # --- Fetch vehicle ---
        db_vehicle = db.query(Vehicle).filter(Vehicle.vehicle_id == vehicle_id).first()
        if not db_vehicle:
            logger.warning(f"[VehicleUpdate] Vehicle ID={vehicle_id} not found")
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=ResponseWrapper.error("Vehicle not found", "VEHICLE_NOT_FOUND"),
            )

        # --- Vendor access check ---
        if user_type == "vendor":
            if int(db_vehicle.vendor_id) != int(token_vendor_id):
                logger.warning(
                    f"[VehicleUpdate] Unauthorized update attempt | "
                    f"user_vendor={token_vendor_id}, vehicle_vendor={db_vehicle.vendor_id}"
                )
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail=ResponseWrapper.error("You don't have permission to update this vehicle", "FORBIDDEN"),
                )
            vendor_id = int(token_vendor_id)
        elif user_type in {"admin", "superadmin"}:
            vendor_id = db_vehicle.vendor_id
        else:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=ResponseWrapper.error("You don't have permission to update vehicles", "FORBIDDEN"),
            )

        # --- Validate vehicle_type if updated ---
        if vehicle_type_id:
            valid_vehicle_type = vehicle_type_crud.get_by_vendor_and_id(
                db, vendor_id=vendor_id, vehicle_type_id=vehicle_type_id
            )
            if not valid_vehicle_type:
                logger.warning(
                    f"[VehicleUpdate] Invalid vehicle_type_id={vehicle_type_id} "
                    f"for vendor_id={vendor_id}"
                )
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=ResponseWrapper.error("Invalid vehicle_type_id for this vendor", "INVALID_VEHICLE_TYPE"),
                )

        # --- Validate driver if provided ---
        if driver_id not in [None, 0, "0", ""]:
            # Check driver exists for this vendor
            valid_driver = driver_crud.get_by_id_and_vendor(db, driver_id=driver_id, vendor_id=vendor_id)
            if not valid_driver:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=ResponseWrapper.error("Driver not found for this vendor", "INVALID_DRIVER"),
                )

            # Check driver is not assigned to another active vehicle
            assigned_vehicle = db.query(Vehicle).filter(
                Vehicle.driver_id == driver_id,
                Vehicle.vehicle_id != vehicle_id,  # exclude current vehicle
                Vehicle.is_active == True
            ).first()
            if assigned_vehicle:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=ResponseWrapper.error(
                        f"Driver is inactive or already assigned to active vehicle {assigned_vehicle.rc_number}",
                        "DRIVER_ALREADY_ASSIGNED"
                    ),
                )


        # --- Save files using new storage service ---
        allowed_types = ["image/jpeg", "image/png", "application/pdf"]
        
        if puc_file and await file_size_validator(puc_file, allowed_types, 5, required=False):
            # Delete old file if exists
            if db_vehicle.puc_url:
                storage_service.delete_file(db_vehicle.puc_url)
            db_vehicle.puc_url = storage_service.save_file(puc_file, vendor_id, db_vehicle.rc_number, "puc")
            
        if fitness_file and await file_size_validator(fitness_file, allowed_types, 5, required=False):
            if db_vehicle.fitness_url:
                storage_service.delete_file(db_vehicle.fitness_url)
            db_vehicle.fitness_url = storage_service.save_file(fitness_file, vendor_id, db_vehicle.rc_number, "fitness")
            
        if tax_receipt_file and await file_size_validator(tax_receipt_file, allowed_types, 5, required=False):
            if db_vehicle.tax_receipt_url:
                storage_service.delete_file(db_vehicle.tax_receipt_url)
            db_vehicle.tax_receipt_url = storage_service.save_file(tax_receipt_file, vendor_id, db_vehicle.rc_number, "tax_receipt")
            
        if insurance_file and await file_size_validator(insurance_file, allowed_types, 5, required=False):
            if db_vehicle.insurance_url:
                storage_service.delete_file(db_vehicle.insurance_url)
            db_vehicle.insurance_url = storage_service.save_file(insurance_file, vendor_id, db_vehicle.rc_number, "insurance")
            
        if permit_file and await file_size_validator(permit_file, allowed_types, 5, required=False):
            if db_vehicle.permit_url:
                storage_service.delete_file(db_vehicle.permit_url)
            db_vehicle.permit_url = storage_service.save_file(permit_file, vendor_id, db_vehicle.rc_number, "permit")

        # --- Update other fields ---
        update_fields = {
            "vehicle_type_id": vehicle_type_id,
            "rc_number": rc_number,
            "driver_id": driver_id,
            "rc_expiry_date": rc_expiry_date,
            "description": description,
            "puc_expiry_date": puc_expiry_date,
            "fitness_expiry_date": fitness_expiry_date,
            "tax_receipt_date": tax_receipt_date,
            "insurance_expiry_date": insurance_expiry_date,
            "permit_expiry_date": permit_expiry_date,
            "password": password,
        }
        for key, value in update_fields.items():
            if value is not None:
                setattr(db_vehicle, key, value)

        db.commit()
        db.refresh(db_vehicle)

        logger.info(f"Vehicle '{db_vehicle.rc_number}' updated by user {user_id}")

        return ResponseWrapper.success(
            data={"vehicle": VehicleResponse.model_validate(db_vehicle, from_attributes=True)},
            message="Vehicle updated successfully"
        )

    except SQLAlchemyError as e:
        db.rollback()
        logger.exception(f"DB error while updating vehicle: {e}")
        raise handle_db_error(e)
    except HTTPException as e:
        db.rollback()
        logger.warning(f"HTTP error while updating vehicle: {e.detail}")
        raise handle_http_error(e)
    except Exception as e:
        db.rollback()
        logger.exception(f"Unexpected error updating vehicle: {e}")
        raise handle_http_error(e)

@router.patch("/{vehicle_id}/status", status_code=status.HTTP_200_OK, response_model=dict)
def update_vehicle_status(
    vehicle_id: int,
    is_active: bool,
    db: Session = Depends(get_db),
    user_data=Depends(PermissionChecker(["vehicle.update"], check_tenant=True)),
):
    """
    Activate or deactivate a vehicle.

    Rules:
    - Vendor users → can update only their own vehicles.
    - Admin/Superadmin → can update any vehicle.
    """
    try:
        user_id = user_data.get("user_id")
        user_type = user_data.get("user_type")
        token_vendor_id = int(user_data.get("vendor_id", 0))

        logger.info(f"[VehicleStatusUpdate] user_id={user_id}, vehicle_id={vehicle_id}, user_type={user_type}, set_active={is_active}")

        # --- Fetch vehicle ---
        db_vehicle = db.query(Vehicle).filter(Vehicle.vehicle_id == vehicle_id).first()
        if not db_vehicle:
            logger.warning(f"[VehicleStatusUpdate] Vehicle ID={vehicle_id} not found")
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=ResponseWrapper.error("Vehicle not found", "VEHICLE_NOT_FOUND"),
            )

        # --- Permission check ---
        if user_type == "vendor" and int(db_vehicle.vendor_id) != token_vendor_id:
            logger.warning(f"[VehicleStatusUpdate] Unauthorized status change attempt | user_vendor={token_vendor_id}, vehicle_vendor={db_vehicle.vendor_id}")
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=ResponseWrapper.error(
                    "You don't have permission to update this vehicle", "FORBIDDEN"
                ),
            )
        elif user_type not in {"vendor", "admin", "superadmin"}:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=ResponseWrapper.error(
                    "You don't have permission to update vehicles", "FORBIDDEN"
                ),
            )

        # --- Update status ---
        db_vehicle.is_active = is_active
        db.commit()
        db.refresh(db_vehicle)

        status_str = "activated" if is_active else "deactivated"
        logger.info(f"[VehicleStatusUpdate] Vehicle ID={vehicle_id} {status_str} by user_id={user_id}")

        return ResponseWrapper.success(
            data={"vehicle": VehicleResponse.model_validate(db_vehicle, from_attributes=True)},
            message=f"Vehicle {status_str} successfully",
        )

    except SQLAlchemyError as e:
        db.rollback()
        logger.exception(f"[VehicleStatusUpdate] DB error for vehicle_id={vehicle_id}: {e}")
        raise handle_db_error(e)

    except HTTPException as e:
        db.rollback()
        logger.warning(f"[VehicleStatusUpdate] HTTP error: {e.detail}")
        raise

    except Exception as e:
        db.rollback()
        logger.exception(f"[VehicleStatusUpdate] Unexpected error for vehicle_id={vehicle_id}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=ResponseWrapper.error("Unexpected error updating vehicle status", "VEHICLE_STATUS_UPDATE_FAILED"),
        )

@router.get("/storage/info", status_code=status.HTTP_200_OK, response_model=dict)
def get_storage_info(
    user_data=Depends(PermissionChecker(["vehicle.read"], check_tenant=False)),
):
    """
    Get current storage configuration info (for debugging/monitoring).
    Only accessible by admin users.
    """
    try:
        user_type = user_data.get("user_type")
        
        # Only allow admin users to see storage info
        if user_type not in {"admin", "superadmin"}:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=ResponseWrapper.error("Insufficient permissions", "FORBIDDEN"),
            )
        
        storage_info = storage_service.get_storage_info()
        
        return ResponseWrapper.success(
            data=storage_info,
            message="Storage configuration retrieved successfully"
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.exception(f"Error getting storage info: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=ResponseWrapper.error("Failed to get storage info", "STORAGE_INFO_FAILED"),
        )

@router.get("/files/{file_path:path}", 
           status_code=status.HTTP_200_OK,
           response_class=FileResponse)
def get_file(
    file_path: str,
    download: Optional[bool] = Query(False, description="Force download instead of inline display"),
    db: Session = Depends(get_db),
    user_data=Depends(PermissionChecker(["vehicle.read"], check_tenant=True)),
):
    """
    Serve a file from storage given its file path.
    
    Rules:
    - Vendor users can only access files from their own vehicles
    - Admin users can access any file
    - File must exist in storage
    - Use ?download=true to force download instead of inline display
    """
    try:
        user_type = user_data.get("user_type")
        token_vendor_id = user_data.get("vendor_id")
        user_id = user_data.get("user_id")
        
        print("Inside get file route")
        logger.info(f"[FileAccess] user_id={user_id}, file_path={file_path}, user_type={user_type}, download={download}")
        
        # Check if file exists in storage
        if not storage_service.file_exists(file_path):
            logger.warning(f"[FileAccess] File not found: {file_path}")
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=ResponseWrapper.error("File not found", "FILE_NOT_FOUND"),
            )
        
        # For vendor users, validate they can access this file by checking if it belongs to their vehicles
        if user_type == "vendor":
            # Extract vendor_id from file path (format: vendor_{vendor_id}/vehicle_{rc_number}/...)
            try:
                path_parts = file_path.split("/")
                if len(path_parts) >= 1 and path_parts[0].startswith("vendor_"):
                    file_vendor_id = int(path_parts[0].replace("vendor_", ""))
                    
                    if file_vendor_id != token_vendor_id:
                        logger.warning(
                            f"[FileAccess] Unauthorized file access attempt | "
                            f"user_vendor={token_vendor_id}, file_vendor={file_vendor_id}"
                        )
                        raise HTTPException(
                            status_code=status.HTTP_403_FORBIDDEN,
                            detail=ResponseWrapper.error("You don't have permission to access this file", "FORBIDDEN"),
                        )
                else:
                    # If path doesn't follow expected format, deny access for vendor users
                    logger.warning(f"[FileAccess] Invalid file path format for vendor user: {file_path}")
                    raise HTTPException(
                        status_code=status.HTTP_403_FORBIDDEN,
                        detail=ResponseWrapper.error("Invalid file path", "FORBIDDEN"),
                    )
            except (ValueError, IndexError) as e:
                logger.warning(f"[FileAccess] Error parsing vendor from file path {file_path}: {e}")
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail=ResponseWrapper.error("Invalid file path format", "FORBIDDEN"),
                )
        
        # Get full file URL
        file_url = storage_service.get_file_url(file_path)
        
        # Determine content type
        content_type, _ = mimetypes.guess_type(file_path)
        if not content_type:
            content_type = "application/octet-stream"
        
        # For local filesystem, serve the file directly
        if file_url.startswith("file://"):
            local_path = file_url.replace("file://", "")
            
            if not os.path.exists(local_path):
                logger.warning(f"[FileAccess] Local file not found: {local_path}")
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail=ResponseWrapper.error("File not found on disk", "FILE_NOT_FOUND"),
                )
            
            logger.info(f"[FileAccess] Serving local file: {local_path} to user_id={user_id}")
            print(f"[FileAccess] Serving local file: {local_path} to user_id={user_id}")
            
            return FileResponse(
                path=local_path,
                media_type=content_type
            )
        else:
            # For cloud storage, download to temp file and serve via FileResponse
            try:
                file_content = storage_service.get_file_content(file_path)
                
                # Create temporary file
                file_extension = os.path.splitext(file_path)[1]
                temp_file = tempfile.NamedTemporaryFile(delete=False, suffix=file_extension)
                temp_file.write(file_content)
                temp_file.close()
                
                logger.info(f"[FileAccess] Serving cloud file via temp: {file_url} to user_id={user_id} ({len(file_content)} bytes)")
                
                # Return FileResponse with temp file
                return FileResponse(
                    path=temp_file.name,
                    media_type=content_type
                )
                
            except Exception as e:
                logger.error(f"[FileAccess] Error reading file {file_url}: {e}")
                raise HTTPException(
                    status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                    detail=ResponseWrapper.error("Error reading file from storage", "FILE_READ_ERROR"),
                )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.exception(f"[FileAccess] Unexpected error accessing file {file_path}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=ResponseWrapper.error("Unexpected error accessing file", "FILE_ACCESS_FAILED"),
        )
