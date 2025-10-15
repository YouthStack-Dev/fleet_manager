from datetime import date
from app.utils.validition import validate_future_dates
from common_utils.auth.utils import hash_password
from fastapi import APIRouter, Depends, UploadFile, Form, HTTPException, status , Query
from sqlalchemy.orm import Session
from typing import Optional
import io
import shutil
from sqlalchemy.exc import SQLAlchemyError
from app.database.session import get_db
from app.schemas.driver import DriverCreate, DriverPaginationResponse, DriverResponse, GovtIDTypeEnum
from app.crud.driver import driver_crud
from app.utils.response_utils import ResponseWrapper, handle_db_error, handle_http_error
from app.utils.file_utils import file_size_validator, save_file
from app.models.driver import VerificationStatusEnum ,GenderEnum 
from common_utils.auth.permission_checker import PermissionChecker
from app.core.logging_config import get_logger
from app.services.storage_service import storage_service
from fastapi.encoders import jsonable_encoder
logger = get_logger(__name__)
router = APIRouter(prefix="/drivers", tags=["drivers"])

@router.post("/create", response_model=dict, status_code=status.HTTP_201_CREATED)
async def create_driver(
    vendor_id: Optional[int] = Form(None),
    name: str = Form(...),
    code: str = Form(...),
    email: str = Form(...),
    phone: str = Form(...),
    gender: Optional[GenderEnum] = Form(...),
    password: str = Form(...),
    date_of_birth: Optional[date] = Form(None),
    date_of_joining: Optional[date] = Form(None),
    permanent_address: str = Form(...),
    current_address: str = Form(...),

    # License info
    license_number: str = Form(...),
    license_expiry_date: date = Form(...),

    # Badge info
    badge_number: str = Form(...),
    badge_expiry_date: date = Form(...),

    # Government ID
    alt_govt_id_number: str = Form(...),
    alt_govt_id_type: str = Form(...),  # could use Enum if you have GovtIDTypeEnum

    # Induction info
    induction_date: date = Form(...),

    # Verification expiries
    bg_expiry_date: date = Form(...),
    police_expiry_date: date= Form(...),
    medical_expiry_date:date = Form(...),
    training_expiry_date:date = Form(...),
    eye_expiry_date: date = Form(...),

    # File uploads
    photo: Optional[UploadFile] = Form(None),
    license_file: UploadFile = Form(...),
    badge_file: UploadFile = Form(...),
    alt_govt_id_file: UploadFile = Form(...),
    bgv_file:UploadFile = Form(...),
    police_file: UploadFile = Form(...),
    medical_file: UploadFile = Form(...),
    training_file: UploadFile = Form(...),
    eye_file: UploadFile = Form(...),
    induction_file: UploadFile = Form(...),

    # Verification statuses (with default)
    bg_verify_status: VerificationStatusEnum = Form(default=VerificationStatusEnum.PENDING),
    police_verify_status: VerificationStatusEnum = Form(default=VerificationStatusEnum.PENDING),
    medical_verify_status: VerificationStatusEnum = Form(default=VerificationStatusEnum.PENDING),
    training_verify_status: VerificationStatusEnum = Form(default=VerificationStatusEnum.PENDING),
    eye_verify_status: VerificationStatusEnum = Form(default=VerificationStatusEnum.PENDING),

    db: Session = Depends(get_db),
    user_data=Depends(PermissionChecker(["driver.create"])),
):
    """
    Create a new driver under a vendor.
    Vendor users → can only create drivers for their own vendor.
    Admin users → can create for any vendor.
    """
    expiry_fields = {
        "bg_expiry_date": bg_expiry_date,
        "police_expiry_date": police_expiry_date,
        "medical_expiry_date": medical_expiry_date,
        "training_expiry_date": training_expiry_date,
        "eye_expiry_date": eye_expiry_date,
        "badge_expiry_date": badge_expiry_date,
        "license_expiry_date": license_expiry_date,

    }
    validate_future_dates(expiry_fields, context="driver")
    try:
        user_type = user_data.get("user_type")
        token_vendor_id = user_data.get("vendor_id")

        if user_type == "vendor":
            vendor_id = token_vendor_id
        elif user_type == "admin":
            vendor_id = vendor_id
            if not vendor_id:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=ResponseWrapper.error("Vendor ID is required", "BAD_REQUEST"),
                )
        elif user_type not in {"admin", "superadmin"}:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=ResponseWrapper.error("You don't have permission to create drivers", "FORBIDDEN")
            )

        driver_code = code.strip()
        logger.info(f"[DriverCreate] Creating driver '{driver_code}' for vendor={vendor_id}")

        allowed_docs = ["image/jpeg", "image/png", "application/pdf"]

        # --- File validation ---
        for file in [
            ("photo", photo),
            ("license_file", license_file),
            ("badge_file", badge_file),
            ("alt_govt_id_file", alt_govt_id_file),
            ("bgv_file", bgv_file),
            ("police_file", police_file),
            ("medical_file", medical_file),
            ("training_file", training_file),
            ("eye_file", eye_file),
            ("induction_file", induction_file),
        ]:
            if file[1]:
                await file_size_validator(file[1], allowed_docs, 10, required=False)

        # --- Save files ---
        save = lambda f, name: storage_service.save_file(f, vendor_id, driver_code, name) if f else None
        photo_url = save(photo, "photo")
        license_url = save(license_file, "license")
        badge_url = save(badge_file, "badge")
        alt_govt_id_url = save(alt_govt_id_file, "alt_govt_id")
        bg_verify_url = save(bgv_file, "bgv")
        police_verify_url = save(police_file, "police")
        medical_verify_url = save(medical_file, "medical")
        training_verify_url = save(training_file, "training")
        eye_verify_url = save(eye_file, "eye")
        induction_url = save(induction_file, "induction")

        # --- Hash password ---
        hashed_password = hash_password(password)
        logger.info(f"Hashed password: {hashed_password}")
        # --- Build payload ---
        driver_in = DriverCreate(
            vendor_id=vendor_id,
            name=name,
            code=driver_code,
            email=email,
            phone=phone,
            gender=gender,
            password=hashed_password,
            date_of_birth=date_of_birth,
            date_of_joining=date_of_joining,
            permanent_address=permanent_address,
            current_address=current_address,

            # Verification
            bg_verify_status=bg_verify_status,
            bg_expiry_date=bg_expiry_date,
            bg_verify_url=bg_verify_url,
            police_verify_status=police_verify_status,
            police_expiry_date=police_expiry_date,
            police_verify_url=police_verify_url,
            medical_verify_status=medical_verify_status,
            medical_expiry_date=medical_expiry_date,
            medical_verify_url=medical_verify_url,
            training_verify_status=training_verify_status,
            training_expiry_date=training_expiry_date,
            training_verify_url=training_verify_url,
            eye_verify_status=eye_verify_status,
            eye_expiry_date=eye_expiry_date,
            eye_verify_url=eye_verify_url,

            # License & badge
            license_number=license_number,
            license_expiry_date=license_expiry_date,
            license_url=license_url,
            badge_number=badge_number,
            badge_expiry_date=badge_expiry_date,
            badge_url=badge_url,

            # Govt ID
            alt_govt_id_number=alt_govt_id_number,
            alt_govt_id_type=alt_govt_id_type,
            alt_govt_id_url=alt_govt_id_url,

            # Induction
            induction_date=induction_date,
            induction_url=induction_url,

            photo_url=photo_url,
        )

        # --- Persist ---
        logger.info(f"Driver creation obj_in: {jsonable_encoder(driver_in)}")
        db_obj = driver_crud.create_with_vendor(db, vendor_id=vendor_id, obj_in=driver_in)
        db.commit()
        db.refresh(db_obj)

        logger.info(f"✅ Driver '{driver_code}' created successfully (ID={db_obj.driver_id})")
        return ResponseWrapper.success(
            data={"driver": DriverResponse.model_validate(db_obj, from_attributes=True)},
            message="Driver created successfully"
        )

    except HTTPException as e:
        db.rollback()
        logger.warning(f"Driver creation failed (HTTPException) for driver '{driver_code}': {e.detail}")
        raise
    except SQLAlchemyError as e:
        db.rollback()
        logger.error(f"Database error creating driver '{driver_code}': {e}")
        raise handle_db_error(e)
    except Exception as e:
        db.rollback()
        logger.error(f"Unexpected error creating driver '{driver_code}': {e}")
        raise handle_http_error(e)


# --------------------------
# GET single driver
# --------------------------
@router.get("/get", response_model=dict)
def get_driver(
    driver_id: int,
    vendor_id: Optional[int] = None,
    db: Session = Depends(get_db),
    user_data=Depends(PermissionChecker(["driver.read"]))
):
    try:
        user_type = user_data.get("user_type")
        token_vendor_id = user_data.get("vendor_id")

        if user_type == "vendor":
            vendor_id = token_vendor_id
        elif user_type == "driver":
            vendor_id = vendor_id
            if not vendor_id:
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail=ResponseWrapper.error("vendor_id is required", "bad request")
                )

        elif user_type not in {"admin", "superadmin"}:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=ResponseWrapper.error("You don't have permission to create drivers", "FORBIDDEN")
            )
        logger.info(f"[GET DRIVER] Fetching driver_id={driver_id} for vendor_id={vendor_id} by user={user_data.get('user_id')}")
        driver = driver_crud.get_by_id_and_vendor(db, driver_id=driver_id, vendor_id=vendor_id)
        if not driver:
            logger.warning(f"[GET DRIVER] Driver {driver_id} not found for vendor {vendor_id}")
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=ResponseWrapper.error(
                    message="Driver not found",
                    error_code="DRIVER_NOT_FOUND"
                )
            )
        logger.info(f"[GET DRIVER] Driver fetched successfully: driver_id={driver.driver_id}")
        return ResponseWrapper.success(data={"driver": DriverResponse.model_validate(driver, from_attributes=True)})

    except HTTPException as e:
        logger.warning(f"Driver creation failed (HTTPException) for driver '{driver_id}': {e.detail}")
        raise
    except SQLAlchemyError as e:
        logger.error(f"Database error creating driver '{driver_id}': {e}")
        raise handle_db_error(e)
    except Exception as e:
        db.rollback()
        logger.error(f"Unexpected error creating driver '{driver_id}': {e}")
        raise handle_http_error(e)
    


# --------------------------
# GET all drivers for vendor with filters
# --------------------------
@router.get("/vendor", response_model=dict)
def get_drivers(
    vendor_id: int,
    active_only: Optional[bool] = Query(None, description="Filter by active/inactive drivers"),
    license_number: Optional[str] = Query(None, description="Filter by license number"),
    search: Optional[str] = Query(None, description="Search by name, email, phone, badge, license"),
    db: Session = Depends(get_db),
    user_data=Depends(PermissionChecker(["driver.read"]))
):
    try:
        user_type = user_data.get("user_type")
        token_vendor_id = user_data.get("vendor_id")

        if user_type == "vendor":
            vendor_id = token_vendor_id
        elif user_type not in {"admin", "superadmin"}:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=ResponseWrapper.error("You don't have permission to create drivers", "FORBIDDEN")
            )
        logger.info(f"[GET DRIVERS] Fetching drivers for vendor_id={vendor_id} by user={user_data.get('user_id')}, "
                    f"filters: active_only={active_only}, license_number={license_number}, search={search}")

        drivers = driver_crud.get_by_vendor(
            db,
            vendor_id=vendor_id,
            active_only=active_only,
            search=search
        )

        # Additional filter by license number if provided
        if license_number:
            drivers = [d for d in drivers if d.license_number == license_number]

        logger.info(f"[GET DRIVERS] Found {len(drivers)} drivers for vendor_id={vendor_id}")
        driver_list = [DriverResponse.model_validate(d, from_attributes=True) for d in drivers]

        return ResponseWrapper.success(
            data=DriverPaginationResponse(total=len(driver_list), items=driver_list).dict()
        )

    except HTTPException as e:
        logger.warning(f"Driver creation failed (HTTPException) for driver : {e.detail}")
        raise
    except SQLAlchemyError as e:
        logger.error(f"Database error creating driver : {e}")
        raise handle_db_error(e)
    except Exception as e:
        logger.error(f"Unexpected error creating driver : {e}")
        raise handle_http_error(e)
    
@router.put("/update", response_model=dict)
async def update_driver(
    driver_id: int,
    vendor_id: Optional[int] = Form(None),
    name: Optional[str] = Form(None),
    code: Optional[str] = Form(None),
    email: Optional[str] = Form(None),
    phone: Optional[str] = Form(None),
    gender: Optional[str] = Form(None),
    password: Optional[str] = Form(None),
    date_of_birth: Optional[str] = Form(None),
    date_of_joining: Optional[str] = Form(None),
    permanent_address: Optional[str] = Form(None),
    current_address: Optional[str] = Form(None),
    license_number: Optional[str] = Form(None),
    license_expiry_date: Optional[str] = Form(None),
    badge_number: Optional[str] = Form(None),
    badge_expiry_date: Optional[str] = Form(None),
    alt_govt_id_number: Optional[str] = Form(None),
    alt_govt_id_type: Optional[str] = Form(None),
    induction_date: Optional[str] = Form(None),
    bg_expiry_date: Optional[date] = Form(None),
    police_expiry_date: Optional[date] = Form(None),
    medical_expiry_date: Optional[date] = Form(None),
    training_expiry_date: Optional[date] = Form(None),
    eye_expiry_date: Optional[date] = Form(None),

    bg_verify_status: Optional[VerificationStatusEnum] = Form(None),
    police_verify_status: Optional[VerificationStatusEnum] = Form(None),
    medical_verify_status: Optional[VerificationStatusEnum] = Form(None),
    training_verify_status: Optional[VerificationStatusEnum] = Form(None),
    eye_verify_status: Optional[VerificationStatusEnum] = Form(None),
    # File uploads
    photo: Optional[UploadFile] = None,
    license_file: Optional[UploadFile] = None,
    badge_file: Optional[UploadFile] = None,
    alt_govt_id_file: Optional[UploadFile] = None,
    bgv_file: Optional[UploadFile] = None,
    police_file: Optional[UploadFile] = None,
    medical_file: Optional[UploadFile] = None,
    training_file: Optional[UploadFile] = None,
    eye_file: Optional[UploadFile] = None,
    induction_file: Optional[UploadFile] = None,
    db: Session = Depends(get_db),
    user_data=Depends(PermissionChecker(["driver.update"])),
):
    """
    Update driver details, including optional files and verification statuses.
    Handles old file deletion automatically.
    """
    expiry_fields = {
        "bg_expiry_date": bg_expiry_date,
        "police_expiry_date": police_expiry_date,
        "medical_expiry_date": medical_expiry_date,
        "training_expiry_date": training_expiry_date,
        "eye_expiry_date": eye_expiry_date,
        "badge_expiry_date": badge_expiry_date,
        "license_expiry_date": license_expiry_date,
    }

    validate_future_dates(expiry_fields, context="driver")
    try:
        user_type = user_data.get("user_type")
        token_vendor_id = user_data.get("vendor_id")

        if user_type == "vendor":
            vendor_id = token_vendor_id
        elif user_type == "admin":
            vendor_id = vendor_id
            if not vendor_id:
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail=ResponseWrapper.error("vendor_id is required", "bad request")
                )
        elif user_type not in {"admin", "superadmin"}:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=ResponseWrapper.error("You don't have permission to create drivers", "FORBIDDEN")
            )
        logger.info(f"[UPDATE DRIVER] Updating driver_id={driver_id} for vendor_id={vendor_id} by user={user_data.get('user_id')}")

        # Fetch existing driver
        db_obj = driver_crud.get_by_id_and_vendor(db, driver_id=driver_id, vendor_id=vendor_id)
        if not db_obj:
            logger.warning(f"[UPDATE DRIVER] Driver {driver_id} not found for vendor {vendor_id}")
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=ResponseWrapper.error(
                    message="Driver not found",
                    error_code="DRIVER_NOT_FOUND"
                )
            )

        allowed_docs = ["image/jpeg", "image/png", "application/pdf"]
        file_fields = {
            "photo": photo,
            "license_file": license_file,
            "badge_file": badge_file,
            "alt_govt_id_file": alt_govt_id_file,
            "bgv_file": bgv_file,
            "police_file": police_file,
            "medical_file": medical_file,
            "training_file": training_file,
            "eye_file": eye_file,
            "induction_file": induction_file,
        }

        # Save files if provided and delete old ones
        for key, file_obj in file_fields.items():
            if file_obj and await file_size_validator(file_obj, allowed_docs, 10, required=False):
                db_field = key.replace("_file", "_url")
                old_url = getattr(db_obj, db_field)
                if old_url:
                    storage_service.delete_file(old_url)
                new_url = storage_service.save_file(file_obj, vendor_id, db_obj.code, key.replace("_file", ""))
                setattr(db_obj, db_field, new_url)

        # --- Update other fields ---
        update_fields = {
            "name": name,
            "code": code,
            "email": email,
            "phone": phone,
            "gender": gender,
            "password": hash_password(password) if password else None,
            "date_of_birth": date_of_birth,
            "date_of_joining": date_of_joining,
            "permanent_address": permanent_address,
            "current_address": current_address,
            "license_number": license_number,
            "license_expiry_date": license_expiry_date,
            "badge_number": badge_number,
            "badge_expiry_date": badge_expiry_date,
            "alt_govt_id_number": alt_govt_id_number,
            "alt_govt_id_type": alt_govt_id_type,
            "induction_date": induction_date,
        }

        # Update normal fields
        for key, value in update_fields.items():
            if value is not None:
                setattr(db_obj, key, value)

        # --- Handle verification status enums separately ---
        enum_fields = [
            "bg_verify_status",
            "police_verify_status",
            "medical_verify_status",
            "training_verify_status",
            "eye_verify_status",
        ]
        for key in enum_fields:
            value = locals().get(key)
            if value is not None:
                if isinstance(value, str):
                    try:
                        value = VerificationStatusEnum(value)
                    except ValueError:
                        raise HTTPException(
                            status_code=status.HTTP_400_BAD_REQUEST,
                            detail=ResponseWrapper.error(f"Invalid value for {key}", "INVALID_ENUM")
                        )
                setattr(db_obj, key, value)

        db.commit()
        db.refresh(db_obj)
        logger.info(f"[UPDATE DRIVER] Driver {driver_id} updated successfully")

        return ResponseWrapper.success(
            data={"driver": DriverResponse.model_validate(db_obj, from_attributes=True)},
            message="Driver updated successfully"
        )

    except HTTPException as e:
        db.rollback()
        logger.warning(f"[UPDATE DRIVER] HTTPException: {e.detail}")
        raise
    except SQLAlchemyError as e:
        db.rollback()
        logger.error(f"[UPDATE DRIVER] Database error: {e}")
        raise handle_db_error(e)
    except Exception as e:
        db.rollback()
        logger.error(f"[UPDATE DRIVER] Unexpected error: {e}")
        raise handle_http_error(e)

@router.patch("/{driver_id}/toggle-active", response_model=dict)
def toggle_driver_active(
    driver_id: int,
    vendor_id: Optional[int] = None,
    db: Session = Depends(get_db),
    user_data=Depends(PermissionChecker(["driver.update"]))
):
    """
    Toggle the active status of a driver (soft activate/deactivate).
    """
    try:
        user_type = user_data.get("user_type")
        token_vendor_id = user_data.get("vendor_id")

        if user_type == "vendor":
            vendor_id = token_vendor_id

        elif user_type not in {"admin", "superadmin"}:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=ResponseWrapper.error("You don't have permission to create drivers", "FORBIDDEN")
            )
        logger.info(f"[TOGGLE DRIVER ACTIVE] User {user_data.get('user_id')} toggling active status for driver_id={driver_id} vendor_id={vendor_id}")

        driver = driver_crud.get_by_id_and_vendor(db, driver_id=driver_id, vendor_id=vendor_id)
        if not driver:
            logger.warning(f"[TOGGLE DRIVER ACTIVE] Driver {driver_id} not found for vendor {vendor_id}")
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=ResponseWrapper.error(
                    message="Driver not found",
                    error_code="DRIVER_NOT_FOUND"
                )
            )

        # Toggle the is_active flag
        driver.is_active = not driver.is_active
        db.flush()
        db.commit()
        db.refresh(driver)

        status_str = "activated" if driver.is_active else "deactivated"
        logger.info(f"[TOGGLE DRIVER ACTIVE] Driver {driver_id} has been {status_str}")

        return ResponseWrapper.success(
            data={"driver_id": driver.driver_id, "is_active": driver.is_active},
            message=f"Driver successfully {status_str}"
        )

    except SQLAlchemyError as e:
        db.rollback()
        logger.error(f"[TOGGLE DRIVER ACTIVE] Database error: {e}")
        raise handle_db_error(e)
    except Exception as e:
        db.rollback()
        logger.error(f"[TOGGLE DRIVER ACTIVE] Unexpected error: {e}")
        raise handle_http_error(e)
