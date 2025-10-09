from fastapi import APIRouter, Depends, UploadFile, Form, HTTPException, status
from sqlalchemy.orm import Session
from typing import Optional
import io
import shutil
from sqlalchemy.exc import SQLAlchemyError
from app.database.session import get_db
from app.schemas.driver import DriverCreate, DriverPaginationResponse, DriverResponse
from app.crud.driver import driver_crud
from app.utils.response_utils import ResponseWrapper, handle_db_error, handle_http_error
from app.utils.file_utils import file_size_validator, save_file
from app.models.driver import VerificationStatusEnum
from common_utils.auth.permission_checker import PermissionChecker
from app.core.logging_config import get_logger
from fastapi import Query

logger = get_logger(__name__)
router = APIRouter(prefix="/drivers", tags=["drivers"])


@router.post("/vendor/{vendor_id}", response_model=dict, status_code=status.HTTP_201_CREATED)
async def create_driver(
    vendor_id: int,
    name: str = Form(...),
    code: str = Form(...),
    email: str = Form(...),
    phone: str = Form(...),
    gender: Optional[str] = Form(None),
    password: str = Form(...),
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

    # File uploads (10 total)
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
    bg_verify_status: Optional[VerificationStatusEnum] = VerificationStatusEnum.PENDING,
    police_verify_status: Optional[VerificationStatusEnum] = VerificationStatusEnum.PENDING,
    medical_verify_status: Optional[VerificationStatusEnum] = VerificationStatusEnum.PENDING,
    training_verify_status: Optional[VerificationStatusEnum] = VerificationStatusEnum.PENDING,
    eye_verify_status: Optional[VerificationStatusEnum] = VerificationStatusEnum.PENDING,
    db: Session = Depends(get_db),
    user_data=Depends(PermissionChecker(["driver.create"])),
):
    driver_code = code.strip()
    try:
        logger.info(f"[CREATE DRIVER] Received files: "
            f"photo={photo.filename if photo else None}, "
            f"license_file={license_file.filename if license_file else None}, "
            f"badge_file={badge_file.filename if badge_file else None}, "
            f"alt_govt_id_file={alt_govt_id_file.filename if alt_govt_id_file else None}, "
            f"bgv_file={bgv_file.filename if bgv_file else None}, "
            f"police_file={police_file.filename if police_file else None}, "
            f"medical_file={medical_file.filename if medical_file else None}, "
            f"training_file={training_file.filename if training_file else None}, "
            f"eye_file={eye_file.filename if eye_file else None}, "
            f"induction_file={induction_file.filename if induction_file else None})")
        logger.info(f"Creating driver '{driver_code}' under vendor_id={vendor_id} by user={user_data.get('user_id')}")

        allowed_docs = ["image/jpeg", "image/png", "application/pdf"]
        # Validate files
        photo = await file_size_validator(photo, ["image/jpeg", "image/png"], 5, required=False)
        license_file = await file_size_validator(license_file, allowed_docs, 5, required=False)
        badge_file = await file_size_validator(badge_file, allowed_docs, 5, required=False)
        alt_govt_id_file = await file_size_validator(alt_govt_id_file, allowed_docs, 5, required=False)
        bgv_file = await file_size_validator(bgv_file, allowed_docs, 10, required=False)
        police_file = await file_size_validator(police_file, allowed_docs, 5, required=False)
        medical_file = await file_size_validator(medical_file, allowed_docs, 5, required=False)
        training_file = await file_size_validator(training_file, allowed_docs, 5, required=False)
        eye_file = await file_size_validator(eye_file, allowed_docs, 5, required=False)
        induction_file = await file_size_validator(induction_file, allowed_docs, 5, required=False)

        # Save files
        photo_url = save_file(photo, vendor_id, driver_code, "photo")
        license_url = save_file(license_file, vendor_id, driver_code, "license")
        badge_url = save_file(badge_file, vendor_id, driver_code, "badge")
        alt_govt_id_url = save_file(alt_govt_id_file, vendor_id, driver_code, "alt_govt_id")
        bg_verify_url = save_file(bgv_file, vendor_id, driver_code, "bgv")
        police_verify_url = save_file(police_file, vendor_id, driver_code, "police")
        medical_verify_url = save_file(medical_file, vendor_id, driver_code, "medical")
        training_verify_url = save_file(training_file, vendor_id, driver_code, "training")
        eye_verify_url = save_file(eye_file, vendor_id, driver_code, "eye")
        induction_url = save_file(induction_file, vendor_id, driver_code, "induction")

        logger.info(f"Files saved successfully for driver '{driver_code}'")
        logger.info(f"photo_url: {photo_url}, license_url: {license_url}, badge_url: {badge_url}, alt_govt_id_url: {alt_govt_id_url}, bg_verify_url: {bg_verify_url}, police_verify_url: {police_verify_url}, medical_verify_url: {medical_verify_url}, training_verify_url: {training_verify_url}, eye_verify_url: {eye_verify_url}, induction_url: {induction_url}")

        # Prepare driver payload
        driver_in = DriverCreate(
            vendor_id=vendor_id,
            name=name,
            code=driver_code,
            email=email,
            phone=phone,
            gender=gender,
            password=password,
            date_of_birth=date_of_birth,
            date_of_joining=date_of_joining,
            permanent_address=permanent_address,
            current_address=current_address,
            
            # FILE URLS
            photo_url=photo_url,
            license_url=license_url,
            badge_url=badge_url,
            alt_govt_id_url=alt_govt_id_url,
            bg_verify_url=bg_verify_url,
            police_verify_url=police_verify_url,
            medical_verify_url=medical_verify_url,
            training_verify_url=training_verify_url,
            eye_verify_url=eye_verify_url,
            induction_url=induction_url,
            
            # Verification statuses
            bg_verify_status=bg_verify_status,
            police_verify_status=police_verify_status,
            medical_verify_status=medical_verify_status,
            training_verify_status=training_verify_status,
            eye_verify_status=eye_verify_status,

            # License info
            license_number=license_number,
            license_expiry_date=license_expiry_date,

            # Badge info
            badge_number=badge_number,
            badge_expiry_date=badge_expiry_date,

            # Alternate govt ID
            alt_govt_id_number=alt_govt_id_number,
            alt_govt_id_type=alt_govt_id_type,

            # Induction
            induction_date=induction_date,
        )


        # Persist to DB
        db_obj = driver_crud.create_with_vendor(db, vendor_id=vendor_id, obj_in=driver_in)
        db.commit()
        db.refresh(db_obj)

        logger.info(f"Driver '{driver_code}' created successfully with ID={db_obj.driver_id}")
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
@router.get("/vendor/{vendor_id}/{driver_id}", response_model=dict)
def get_driver(
    vendor_id: int,
    driver_id: int,
    db: Session = Depends(get_db),
    user_data=Depends(PermissionChecker(["driver.read"]))
):
    try:
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

    except Exception as e:
        logger.error(f"[GET DRIVER] Unexpected error: {e}")
        raise handle_db_error(e)


# --------------------------
# GET all drivers for vendor with filters
# --------------------------
@router.get("/vendor/{vendor_id}", response_model=dict)
def get_drivers(
    vendor_id: int,
    active_only: Optional[bool] = Query(None, description="Filter by active/inactive drivers"),
    license_number: Optional[str] = Query(None, description="Filter by license number"),
    search: Optional[str] = Query(None, description="Search by name, email, phone, badge, license"),
    db: Session = Depends(get_db),
    user_data=Depends(PermissionChecker(["driver.read"]))
):
    try:
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

    except Exception as e:
        logger.error(f"[GET DRIVERS] Unexpected error: {e}")
        raise handle_db_error(e)
    
@router.put("/vendor/{vendor_id}/{driver_id}", response_model=dict)
async def update_driver(
    vendor_id: int,
    driver_id: int,
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
    bg_verify_status: Optional[VerificationStatusEnum] = None,
    police_verify_status: Optional[VerificationStatusEnum] = None,
    medical_verify_status: Optional[VerificationStatusEnum] = None,
    training_verify_status: Optional[VerificationStatusEnum] = None,
    eye_verify_status: Optional[VerificationStatusEnum] = None,
    # File uploads (optional)
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
    Update driver details including optional files and verification statuses.
    """
    try:
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

        # Validate and save files if provided
        file_mapping = {
            "photo": (photo, 5),
            "license_file": (license_file, 5),
            "badge_file": (badge_file, 5),
            "alt_govt_id_file": (alt_govt_id_file, 5),
            "bgv_file": (bgv_file, 10),
            "police_file": (police_file, 5),
            "medical_file": (medical_file, 5),
            "training_file": (training_file, 5),
            "eye_file": (eye_file, 5),
            "induction_file": (induction_file, 5),
        }

        file_urls = {}
        for key, (file_obj, size_mb) in file_mapping.items():
            validated_file = await file_size_validator(file_obj, allowed_docs, size_mb, required=False)
            if validated_file:
                file_urls[key] = save_file(validated_file, vendor_id, db_obj.code, key)

        # Prepare update payload
        update_data = {
            "name": name,
            "code": code,
            "email": email,
            "phone": phone,
            "gender": gender,
            "password": password,
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
            "bg_verify_status": bg_verify_status,
            "police_verify_status": police_verify_status,
            "medical_verify_status": medical_verify_status,
            "training_verify_status": training_verify_status,
            "eye_verify_status": eye_verify_status,
            # File URLs
            "photo_url": file_urls.get("photo"),
            "license_url": file_urls.get("license_file"),
            "badge_url": file_urls.get("badge_file"),
            "alt_govt_id_url": file_urls.get("alt_govt_id_file"),
            "bg_verify_url": file_urls.get("bgv_file"),
            "police_verify_url": file_urls.get("police_file"),
            "medical_verify_url": file_urls.get("medical_file"),
            "training_verify_url": file_urls.get("training_file"),
            "eye_verify_url": file_urls.get("eye_file"),
            "induction_url": file_urls.get("induction_file"),
        }

        # Remove None values
        update_data = {k: v for k, v in update_data.items() if v is not None}

        # Update driver
        updated_driver = driver_crud.update_with_vendor(db, driver_id=driver_id, obj_in=update_data)
        db.commit()
        db.refresh(updated_driver)

        logger.info(f"[UPDATE DRIVER] Driver {driver_id} updated successfully")
        return ResponseWrapper.success(
            data={"driver": DriverResponse.model_validate(updated_driver, from_attributes=True)},
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
@router.patch("/vendor/{vendor_id}/{driver_id}/toggle-active", response_model=dict)
def toggle_driver_active(
    vendor_id: int,
    driver_id: int,
    db: Session = Depends(get_db),
    user_data=Depends(PermissionChecker(["driver.update"]))
):
    """
    Toggle the active status of a driver (soft activate/deactivate).
    """
    try:
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
