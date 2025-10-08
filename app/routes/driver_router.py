from fastapi import APIRouter, Depends, UploadFile, Form, HTTPException, status
from sqlalchemy.orm import Session
from typing import Optional
import io
import shutil
from sqlalchemy.exc import SQLAlchemyError
from app.database.session import get_db
from app.schemas.driver import DriverCreate, DriverResponse
from app.crud.driver import driver_crud
from app.utils.response_utils import ResponseWrapper, handle_db_error, handle_http_error
from app.utils.file_utils import file_size_validator, save_file
from app.models.driver import VerificationStatusEnum
from common_utils.auth.permission_checker import PermissionChecker
from app.core.logging_config import get_logger

logger = get_logger(__name__)
router = APIRouter(prefix="/drivers", tags=["drivers"])


@router.post("/vendor/{vendor_id}", response_model=dict, status_code=status.HTTP_201_CREATED)
async def create_driver(
    vendor_id: int,
    name: str = Form(...),
    code: str = Form(...),
    email: str = Form(...),
    phone: str = Form(...),
    gender: str = Form(...),
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

    # File uploads
    photo: Optional[UploadFile] = None,
    license_file: Optional[UploadFile] = None,
    badge_file: Optional[UploadFile] = None,
    alt_govt_id_file: Optional[UploadFile] = None,
    bgv_file: Optional[UploadFile] = None,

    db: Session = Depends(get_db),
    user_data=Depends(PermissionChecker(["driver.create"])),
):
    """
    Create a new driver for a vendor with file uploads and validation.
    Logs are concise and indicate success/failure clearly.
    """
    driver_code = code.strip()
    try:
        logger.info(f"Creating driver '{driver_code}' under vendor_id={vendor_id} by user={user_data.get('user_id')}")

        # Validate files
        allowed_docs = ["image/jpeg", "image/png", "application/pdf"]
        photo = await file_size_validator(photo, ["image/jpeg", "image/png"], 5, required=False)
        license_file = await file_size_validator(license_file, allowed_docs, 5, required=False)
        badge_file = await file_size_validator(badge_file, allowed_docs, 5, required=False)
        alt_govt_id_file = await file_size_validator(alt_govt_id_file, allowed_docs, 5, required=False)
        bgv_file = await file_size_validator(bgv_file, allowed_docs, 10, required=False)

        # Save files
        photo_url = save_file(photo, vendor_id, driver_code, "photo")
        license_url = save_file(license_file, vendor_id, driver_code, "license")
        badge_url = save_file(badge_file, vendor_id, driver_code, "badge")
        alt_govt_id_url = save_file(alt_govt_id_file, vendor_id, driver_code, "alt_govt_id")
        bgv_doc_url = save_file(bgv_file, vendor_id, driver_code, "bgv")

        logger.info(f"Files saved successfully for driver '{driver_code}'")

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
            photo_url=photo_url,
            license_number=license_number,
            license_expiry_date=license_expiry_date,
            license_url=license_url,
            badge_number=badge_number,
            badge_expiry_date=badge_expiry_date,
            badge_url=badge_url,
            alt_govt_id_number=alt_govt_id_number,
            alt_govt_id_type=alt_govt_id_type,
            alt_govt_id_url=alt_govt_id_url,
            induction_date=induction_date,
            induction_status=VerificationStatusEnum.PENDING,
            bg_verify_status=VerificationStatusEnum.PENDING,
            police_verify_status=VerificationStatusEnum.PENDING,
            medical_verify_status=VerificationStatusEnum.PENDING,
            training_verify_status=VerificationStatusEnum.PENDING,
            eye_verify_status=VerificationStatusEnum.PENDING,
            bgv_doc_url=bgv_doc_url
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







# from fastapi import APIRouter, Depends, HTTPException, Query, status
# from sqlalchemy.orm import Session
# from typing import Optional, List
# from app.database.session import get_db


# from app.models.driver import Driver
# from app.schemas.driver import DriverCreate, DriverUpdate, DriverResponse, DriverPaginationResponse
# from app.utils.pagination import paginate_query
# from common_utils.auth.permission_checker import PermissionChecker
# from common_utils.auth.utils import hash_password

# router = APIRouter(prefix="/drivers", tags=["drivers"])

# @router.post("/", response_model=DriverResponse, status_code=status.HTTP_201_CREATED)
# def create_driver(
#     driver: DriverCreate, 
#     db: Session = Depends(get_db),
#     user_data=Depends(PermissionChecker(["driver.create"], check_tenant=True))
# ):
#     db_driver = Driver(
#         **driver.dict(exclude={"password"}),
#         password=driver.password
#     )
#     db.add(db_driver)
#     db.commit()
#     db.refresh(db_driver)
#     return db_driver

# @router.get("/", response_model=DriverPaginationResponse)
# def read_drivers(
#     skip: int = 0,
#     limit: int = 100,
#     name: Optional[str] = None,
#     vendor_id: Optional[int] = None,
#     is_active: Optional[bool] = None,
#     db: Session = Depends(get_db),
#     user_data=Depends(PermissionChecker(["driver.read"], check_tenant=True))
# ):
#     query = db.query(Driver)
    
#     # Apply filters
#     if name:
#         query = query.filter(Driver.name.ilike(f"%{name}%"))
#     if vendor_id:
#         query = query.filter(Driver.vendor_id == vendor_id)
#     if is_active is not None:
#         query = query.filter(Driver.is_active == is_active)
    
#     total, items = paginate_query(query, skip, limit)
#     return {"total": total, "items": items}

# @router.get("/{driver_id}", response_model=DriverResponse)
# def read_driver(
#     driver_id: int, 
#     db: Session = Depends(get_db),
#     user_data=Depends(PermissionChecker(["driver.read"], check_tenant=True))
# ):
#     db_driver = db.query(Driver).filter(Driver.driver_id == driver_id).first()
#     if not db_driver:
#         raise HTTPException(
#             status_code=status.HTTP_404_NOT_FOUND,
#             detail=f"Driver with ID {driver_id} not found"
#         )
#     return db_driver

# @router.put("/{driver_id}", response_model=DriverResponse)
# def update_driver(
#     driver_id: int, 
#     driver_update: DriverUpdate, 
#     db: Session = Depends(get_db),
#     user_data=Depends(PermissionChecker(["driver.update"], check_tenant=True))
# ):
#     db_driver = db.query(Driver).filter(Driver.driver_id == driver_id).first()
#     if not db_driver:
#         raise HTTPException(
#             status_code=status.HTTP_404_NOT_FOUND,
#             detail=f"Driver with ID {driver_id} not found"
#         )
    
#     # Update only provided fields
#     update_data = driver_update.dict(exclude_unset=True)
    
#     # Hash password if it's being updated
#     if "password" in update_data:
#         update_data["password"] = hash_password(update_data["password"])
    
#     for key, value in update_data.items():
#         setattr(db_driver, key, value)
    
#     db.commit()
#     db.refresh(db_driver)
#     return db_driver

# @router.delete("/{driver_id}", status_code=status.HTTP_204_NO_CONTENT)
# def delete_driver(
#     driver_id: int, 
#     db: Session = Depends(get_db),
#     user_data=Depends(PermissionChecker(["driver.delete"], check_tenant=True))
# ):
#     db_driver = db.query(Driver).filter(Driver.driver_id == driver_id).first()
#     if not db_driver:
#         raise HTTPException(
#             status_code=status.HTTP_404_NOT_FOUND,
#             detail=f"Driver with ID {driver_id} not found"
#         )
    
#     db.delete(db_driver)
#     db.commit()
#     return None


# import traceback
# from fastapi import APIRouter, Depends, status, Form, UploadFile, File, HTTPException
# from pydantic import EmailStr
# from sqlalchemy.orm import Session
# from app.database.database import get_db
# from app.api.schemas.schemas import DriverCreate, DriverOut, DriverUpdate,StatusUpdate
# from app.database.models import Driver, User, Vendor
# from sqlalchemy.exc import IntegrityError, SQLAlchemyError
# from uuid import uuid4
# from typing import Annotated, Optional
# from datetime import date
# import os
# import shutil
# import logging
# from common_utils.auth.permission_checker import PermissionChecker
# # services/driver_service.py or similar
# from common_utils.auth.utils import hash_password
# from typing import Callable, Optional
# import io
# from sqlalchemy import or_
# from fastapi import Query
# from typing import List, Optional
# from sqlalchemy.orm import selectinload
# logger = logging.getLogger(__name__)
# router = APIRouter()
# from sqlalchemy.orm import joinedload

# @router.get("/tenants/drivers/", response_model=List[DriverOut])
# def get_all_drivers_by_tenant(
#     db: Session = Depends(get_db),
#     token_data: dict = Depends(PermissionChecker(["driver_management.read"])),
#     skip: int = Query(0, ge=0),
#     limit: int = Query(100, le=500)
# ) -> List[DriverOut]:
#     tenant_id = token_data.get("tenant_id")
#     logger.info(f"[DRIVER_FETCH] Start - tenant_id={tenant_id}, skip={skip}, limit={limit}")

#     try:
#         drivers = (
#             db.query(Driver)
#             .join(Driver.vendor)
#             .filter(Vendor.tenant_id == tenant_id)
#             .offset(skip)
#             .limit(limit)
#             .all()
#         )

#         logger.info(f"[DRIVER_FETCH] Success - tenant_id={tenant_id}, count={len(drivers)}")
#         return [DriverOut.model_validate(driver) for driver in drivers]

#     except SQLAlchemyError as db_err:
#         logger.exception(f"[DRIVER_FETCH] DB error - tenant_id={tenant_id}, error={db_err}")
#         raise HTTPException(status_code=500, detail="Database error while fetching drivers.")

#     except Exception as err:
#         logger.exception(f"[DRIVER_FETCH] Unexpected error - tenant_id={tenant_id}, error={err}")
#         raise HTTPException(status_code=500, detail="Unexpected server error.")

# async def file_size_validator(
#     file: UploadFile,
#     allowed_types: list[str],
#     max_size_mb: int = 5,
#     required: bool = True
# ) -> UploadFile:
#     if not file or not file.filename:
#         if required:
#             raise HTTPException(status_code=422, detail=f"'{file.filename}' file is required.")
#         return None

#     logger.info(f"Validating file: {file.filename}")

#     if file.content_type not in allowed_types:
#         logger.warning(f"{file.filename} has invalid type '{file.content_type}'. Allowed types: {allowed_types}")
#         raise HTTPException(
#             status_code=415,
#             detail=f"{file.filename} has invalid type '{file.content_type}'. Allowed types: {allowed_types}"
#         )

#     contents = await file.read()
#     size_mb = len(contents) / (1024 * 1024)
#     if size_mb > max_size_mb:
#         raise HTTPException(
#             status_code=413,
#             detail=f"{file.filename} is too large. Max allowed size is {max_size_mb}MB."
#         )

#     # Reset file pointer so it can be read again later
#     file.file = io.BytesIO(contents)
#     return file

# from pathlib import Path


# ROOT_DIR = Path(__file__).resolve().parent.parent.parent  # adjust if needed
# UPLOADS_DIR = ROOT_DIR / "uploaded_files"

# def save_file(
#     file: Optional[UploadFile],
#     vendor_id: int,
#     driver_code: str,
#     doc_type: str
# ) -> Optional[str]:
#     if file and file.filename:
#         # Get file extension from original filename
#         _, ext = os.path.splitext(file.filename)
#         ext = ext.lower().strip()

#         # Construct safe filename: {driver_code}_{doc_type}.{ext}
#         safe_filename = f"{driver_code.strip()}_{doc_type.strip()}{ext}"

#         folder_path = UPLOADS_DIR / "vendors" / str(vendor_id) / "drivers" / driver_code.strip() / doc_type
#         folder_path.mkdir(parents=True, exist_ok=True)

#         file_path = folder_path / safe_filename

#         with open(file_path, "wb") as f:
#             shutil.copyfileobj(file.file, f)

#         logger.info(f"{doc_type.upper()} document saved at: {file_path.resolve()}")
#         # return str(file_path.resolve())
#         relative_path = file_path.relative_to(ROOT_DIR)
#         logger.info(f"Relative path for {doc_type}: {relative_path}")
#         return str(relative_path).replace("\\", "/")  # ensure forward slashes


#     logger.debug(f"No file provided for {doc_type}")
#     return None

# @router.post("/{vendor_id}/drivers/", response_model=DriverOut, status_code=status.HTTP_201_CREATED)
# async def create_driver(
#     vendor_id: int,
#     # form_data: DriverCreate = Depends(),
#     driver_code: str = Form(...),
#     name: str = Form(...),
#     email: EmailStr = Form(...),
#     hashed_password: str = Form(...),
#     mobile_number: str = Form(...),

#     city: str = Form(...),
#     date_of_birth: date = Form(...),
#     gender: str = Form(...),

#     alternate_mobile_number: str = Form(...),
#     permanent_address: str = Form(...),
#     current_address: str = Form(...),

#     bgv_status: str = Form(...),
#     bgv_date: date = Form(...),

#     police_verification_status: str = Form(...),
#     police_verification_date: date = Form(...),

#     medical_verification_status: str = Form(...),
#     medical_verification_date: date = Form(...),

#     training_verification_status: str = Form(...),
#     training_verification_date: date = Form(...),

#     eye_test_verification_status: str = Form(...),
#     eye_test_verification_date: date = Form(...),

#     license_number: str = Form(...),
#     license_expiry_date: date = Form(...),

#     induction_date: date = Form(...),

#     badge_number: str = Form(...),
#     badge_expiry_date: date = Form(...),

#     alternate_govt_id: str = Form(...),
#     alternate_govt_id_doc_type: str = Form(...),

#     bgv_doc_file: UploadFile = File(...),
#     police_verification_doc_file: UploadFile = File(...),
#     medical_verification_doc_file: UploadFile = File(...),
#     training_verification_doc_file: UploadFile = File(...),
#     eye_test_verification_doc_file: UploadFile = File(...),
#     license_doc_file: UploadFile = File(...),
#     induction_doc_file: UploadFile = File(...),
#     badge_doc_file: UploadFile = File(...),
#     alternate_govt_id_doc_file: UploadFile = File(...),
#     photo_image: UploadFile = File(...),
#     db: Session = Depends(get_db),
#     token_data: dict = Depends(PermissionChecker(["driver_management.create"]))
# ):

#     try:

#         required_files = {
#             "bgv_doc_file": bgv_doc_file,
#             "police_verification_doc_file": police_verification_doc_file,
#             "medical_verification_doc_file": medical_verification_doc_file,
#             "training_verification_doc_file": training_verification_doc_file,
#             "eye_test_verification_doc_file": eye_test_verification_doc_file,
#             "license_doc_file": license_doc_file,
#             "induction_doc_file": induction_doc_file,
#             "badge_doc_file": badge_doc_file,
#             "alternate_govt_id_doc_file": alternate_govt_id_doc_file,
#             "photo_image": photo_image,
#         }

#         def validate_required_file(file: UploadFile, field_name: str):
#             if not file or not file.filename.strip():
#                 raise HTTPException(status_code=422, detail=f"{field_name} is required.")

#         # usage
#         for field_name, file in required_files.items():
#             validate_required_file(file, field_name)

#         logger.info(f"Creating driver for vendor_id={vendor_id} with email={email}")
#         logger.info(f"Received form data: bgv_doc_file: {bgv_doc_file.filename if bgv_doc_file else 'None'},police_verification_doc_file: {police_verification_doc_file.filename if police_verification_doc_file else 'None'},medical_verification_doc_file: {medical_verification_doc_file.filename if medical_verification_doc_file else 'None'}, training_verification_doc_file: {training_verification_doc_file.filename if training_verification_doc_file else 'None'}, eye_test_verification_doc_file: {eye_test_verification_doc_file.filename if eye_test_verification_doc_file else 'None'}, license_doc_file: {license_doc_file.filename if license_doc_file else 'None'}, induction_doc_file: {induction_doc_file.filename if induction_doc_file else 'None'}, badge_doc_file: {badge_doc_file.filename if badge_doc_file else 'None'}, alternate_govt_id_doc_file: {alternate_govt_id_doc_file.filename if alternate_govt_id_doc_file else 'None'}, photo_image: {photo_image.filename if photo_image else 'None'}")

#        # Validate file sizes if present
#         # For PDF documents
#         bgv_doc_file = await file_size_validator(bgv_doc_file, allowed_types=["application/pdf"])
#         police_verification_doc_file = await file_size_validator(police_verification_doc_file, allowed_types=["application/pdf"])
#         medical_verification_doc_file = await file_size_validator(medical_verification_doc_file, allowed_types=["application/pdf"])
#         training_verification_doc_file = await file_size_validator(training_verification_doc_file, allowed_types=["application/pdf"])
#         eye_test_verification_doc_file = await file_size_validator(eye_test_verification_doc_file, allowed_types=["application/pdf"])
#         license_doc_file = await file_size_validator(license_doc_file, allowed_types=["application/pdf"])
#         induction_doc_file = await file_size_validator(induction_doc_file, allowed_types=["application/pdf"])
#         badge_doc_file = await file_size_validator(badge_doc_file, allowed_types=["application/pdf"])
#         alternate_govt_id_doc_file = await file_size_validator(alternate_govt_id_doc_file, allowed_types=["application/pdf"])

#         # For photo image (jpeg/png)
#         photo_image = await file_size_validator(
#             photo_image,
#             allowed_types=["image/jpeg", "image/jpg", "image/png"]
#         )


#         # Log what files were uploaded
#         logger.info("Files uploaded:")
#         for label, file in {
#             "bgv": bgv_doc_file,
#             "police": police_verification_doc_file,
#             "medical": medical_verification_doc_file,
#             "training": training_verification_doc_file,
#             "eye": eye_test_verification_doc_file,
#             "license": license_doc_file,
#             "induction": induction_doc_file,
#             "badge": badge_doc_file,
#             "govt_id": alternate_govt_id_doc_file,
#             "photo": photo_image,
#         }.items():
#             if file:
#                 logger.info(f"{label}: {file.filename} ({len(await file.read()) / (1024 * 1024):.2f} MB)")
#                 file.file.seek(0)  # Reset after reading for logging



#         # Validation
#         if not name.strip():
#             raise HTTPException(status_code=422, detail="Name is required.")
#         if not driver_code.strip():
#             raise HTTPException(status_code=422, detail="Driver code is required.")
#         if not email.strip():
#             raise HTTPException(status_code=422, detail="Email is required.")
#         if '@' not in email:
#             raise HTTPException(status_code=422, detail="Invalid email format.")
#         if not mobile_number.strip():
#             raise HTTPException(status_code=422, detail="Mobile number is required.")
#         if len(mobile_number) > 15:
#             raise HTTPException(status_code=422, detail="Mobile number too long.")
#         if not hashed_password.strip():
#             raise HTTPException(status_code=422, detail="Password is required.")

#         # Vendor Check
#         vendor = db.query(Vendor).filter_by(vendor_id=vendor_id).first()
#         if not vendor:
#             raise HTTPException(status_code=404, detail="Vendor not found.")

#     # Check if vendor exists
#         vendor = db.query(Vendor).filter_by(vendor_id=vendor_id).first()
#         if not vendor:
#             raise HTTPException(status_code=404, detail="Vendor not found.")
        
#         # Uniqueness Checks in drivers table
#         if db.query(Driver).filter_by(email=email.strip()).first():
#             raise HTTPException(status_code=409, detail="Email already exists.")
        
#         if db.query(Driver).filter_by(mobile_number=mobile_number.strip()).first():
#             raise HTTPException(status_code=409, detail="Mobile number already exists.")
#         if db.query(Driver).filter_by(vendor_id=vendor_id, driver_code=driver_code.strip()).first():
#             raise HTTPException(status_code=409, detail=f"Driver code '{driver_code}' already exists for this vendor.")

#         bgv_doc_url = save_file(bgv_doc_file, vendor_id, driver_code, "bgv")
#         if bgv_doc_url:
#             logger.info(f"BGV document saved at: {bgv_doc_url}")
#         police_verification_doc_file_url = save_file(police_verification_doc_file, vendor_id, driver_code, "police_verification")
#         if police_verification_doc_file_url:
#             logger.info(f"Police verification document saved at: {police_verification_doc_file_url}")
#         medical_verification_doc_file_url = save_file(medical_verification_doc_file, vendor_id, driver_code, "medical_verification")
#         if medical_verification_doc_file_url:
#             logger.info(f"Medical verification document saved at: {medical_verification_doc_file_url}")
#         training_verification_doc_file_url = save_file(training_verification_doc_file, vendor_id, driver_code, "training_verification")
#         if training_verification_doc_file_url:
#             logger.info(f"Training verification document saved at: {training_verification_doc_file_url}")
#         eye_test_verification_doc_file_url = save_file(eye_test_verification_doc_file, vendor_id, driver_code, "eye_test_verification")
#         if eye_test_verification_doc_file_url:
#             logger.info(f"Eye test verification document saved at: {eye_test_verification_doc_file_url}")
#         license_doc_file_url = save_file(license_doc_file, vendor_id, driver_code, "license")
#         if license_doc_file_url:
#             logger.info(f"License document saved at: {license_doc_file_url}")
#         induction_doc_file_url = save_file(induction_doc_file, vendor_id, driver_code, "induction")
#         if induction_doc_file_url:
#             logger.info(f"Induction document saved at: {induction_doc_file_url}")
#         badge_doc_file_url = save_file(badge_doc_file, vendor_id, driver_code, "badge")
#         if badge_doc_file_url:
#             logger.info(f"Badge document saved at: {badge_doc_file_url}")
#         alternate_govt_id_doc_file_url = save_file(alternate_govt_id_doc_file, vendor_id, driver_code, "alternate_govt_id")
#         if alternate_govt_id_doc_file_url:
#             logger.info(f"Alternate government ID document saved at: {alternate_govt_id_doc_file_url}")
#         photo_image_url = save_file(photo_image, vendor_id, driver_code, "photo")
#         if photo_image_url:
#             logger.info(f"Photo image saved at: {photo_image_url}")

#         # Create Driver
#         new_driver = Driver(
#             name=name.strip(),
#             email=email.strip(),
#             driver_code=driver_code.strip(),
#             mobile_number=mobile_number.strip(),
#             hashed_password=hash_password(hashed_password.strip()),
#             vendor_id=vendor_id,
#             alternate_mobile_number=alternate_mobile_number,
#             city=city,
#             date_of_birth=date_of_birth,
#             gender=gender,
#             permanent_address=permanent_address,
#             current_address=current_address,
#             photo_url=photo_image_url,

#             # ✅ BGV
#             bgv_status=bgv_status,
#             bgv_date=bgv_date,
#             bgv_doc_url=bgv_doc_url,

#             # ✅ Police Verification
#             police_verification_status=police_verification_status,
#             police_verification_date=police_verification_date,
#             police_verification_doc_url=police_verification_doc_file_url,

#             # ✅ Medical Verification
#             medical_verification_status=medical_verification_status,
#             medical_verification_date=medical_verification_date,
#             medical_verification_doc_url=medical_verification_doc_file_url,

#             # ✅ Training Verification
#             training_verification_status=training_verification_status,
#             training_verification_date=training_verification_date,
#             training_verification_doc_url=training_verification_doc_file_url,

#             # ✅ Eye Test
#             eye_test_verification_status=eye_test_verification_status,
#             eye_test_verification_date=eye_test_verification_date,
#             eye_test_verification_doc_url=eye_test_verification_doc_file_url,

#             # ✅ License
#             license_number=license_number,
#             license_expiry_date=license_expiry_date,
#             license_doc_url=license_doc_file_url,


#             # ✅ Induction
#             induction_date=induction_date,
#             induction_doc_url=induction_doc_file_url,

#             # ✅ Badge
#             badge_number=badge_number,
#             badge_expiry_date=badge_expiry_date,
#             badge_doc_url=badge_doc_file_url,

#             # ✅ Alternate Govt ID
#             alternate_govt_id=alternate_govt_id,
#             alternate_govt_id_doc_type=alternate_govt_id_doc_type,
#             alternate_govt_id_doc_url=alternate_govt_id_doc_file_url,
#         )

#         db.add(new_driver)
#         db.commit()
#         db.refresh(new_driver)

#         # Response
#         return DriverOut.model_validate(new_driver, from_attributes=True)


#     except IntegrityError as e:
#         db.rollback()
#         logger.error(f"IntegrityError: {str(e.orig)}")
#         raise HTTPException(status_code=400, detail="Integrity error while creating driver.")
#     except SQLAlchemyError as e:
#         db.rollback()
#         logger.error(f"SQLAlchemyError: {str(e)}")
#         raise HTTPException(status_code=500, detail="Database error while creating driver.")
#     except HTTPException as e:
#         db.rollback()
#         logger.warning(f"HTTPException: {e.detail}")
#         raise e
#     except Exception as e:
#         db.rollback()
#         logger.exception("Unhandled error in driver creation: %s", str(e))
#         traceback.print_exc()
#         logger.error(f"Unexpected error: {str(e)}")
#         raise HTTPException(status_code=500, detail="Unexpected error while creating driver.")
    

# @router.put("/{vendor_id}/drivers/{driver_id}", response_model=DriverOut, status_code=status.HTTP_200_OK)
# async def update_driver(
#     # form_data: DriverUpdate = Depends(),  # reuse schema, all fields should be Optional
#     driver_id: int,
#     vendor_id: int,
#     name: Optional[str] = Form(None),
#     email: Optional[EmailStr] = Form(None),
#     hashed_password: Optional[str] = Form(None),
#     mobile_number: Optional[str] = Form(None),

#     city: Optional[str] = Form(None),
#     date_of_birth: Optional[date] = Form(None),
#     gender: Optional[str] = Form(None),

#     alternate_mobile_number: Optional[str] = Form(None),
#     permanent_address: Optional[str] = Form(None),
#     current_address: Optional[str] = Form(None),

#     bgv_status: Optional[str] = Form(None),
#     bgv_date: Optional[date] = Form(None),

#     police_verification_status: Optional[str] = Form(None),
#     police_verification_date: Optional[date] = Form(None),

#     medical_verification_status: Optional[str] = Form(None),
#     medical_verification_date: Optional[date] = Form(None),

#     training_verification_status: Optional[str] = Form(None),
#     training_verification_date: Optional[date] = Form(None),

#     eye_test_verification_status: Optional[str] = Form(None),
#     eye_test_verification_date: Optional[date] = Form(None),

#     license_number: Optional[str] = Form(None),
#     license_expiry_date: Optional[date] = Form(None),

#     induction_date: Optional[date] = Form(None),

#     badge_number: Optional[str] = Form(None),
#     badge_expiry_date: Optional[date] = Form(None),

#     alternate_govt_id: Optional[str] = Form(None),
#     alternate_govt_id_doc_type: Optional[str] = Form(None),

#     bgv_doc_file: Optional[UploadFile] = None,
#     police_verification_doc_file: Optional[UploadFile] = None,
#     medical_verification_doc_file: Optional[UploadFile] = None,
#     training_verification_doc_file: Optional[UploadFile] = None,
#     eye_test_verification_doc_file: Optional[UploadFile] = None,
#     license_doc_file: Optional[UploadFile] = None,
#     induction_doc_file: Optional[UploadFile] = None,
#     badge_doc_file: Optional[UploadFile] = None,
#     alternate_govt_id_doc_file: Optional[UploadFile] = None,
#     photo_image: Optional[UploadFile] = None,
#     db: Session = Depends(get_db),
#     token_data: dict = Depends(PermissionChecker(["driver_management.update"]))
# ):
#     try:
#         logger.info(f"[DRIVER_UPDATE] Attempting update: driver_id={driver_id}, vendor_id={vendor_id}")

#         # Ensure driver belongs to this vendor
#         driver = db.query(Driver).filter(
#             Driver.driver_id == driver_id,
#             Driver.vendor_id == vendor_id
#         ).first()

#         if not driver:
#             raise HTTPException(status_code=404, detail="Driver not found for this vendor")

#         # Uniqueness checks
#         if email and email != driver.email:
#             existing_email = db.query(Driver).filter(Driver.email == email).first()
#             if existing_email:
#                 raise HTTPException(status_code=409, detail="Email already exists.")

#         if mobile_number and mobile_number != driver.mobile_number:
#             existing_mobile = db.query(Driver).filter(Driver.mobile_number == mobile_number).first()
#             if existing_mobile:
#                 raise HTTPException(status_code=409, detail="Mobile number already exists.")

#         # Handle password
#         if hashed_password:
#             driver.hashed_password = hash_password(hashed_password)

#         # File handler
#         async def process_file(doc_file, doc_type, allowed_types):
#             if doc_file:
#                 validated = await file_size_validator(doc_file, allowed_types=allowed_types)
#                 doc_file.file.seek(0)  # ensure stream reset
#                 file_url = save_file(doc_file, vendor_id, driver.driver_code, doc_type)
#                 logger.info(f"{doc_type} document updated at: {file_url}")
#                 return file_url
#             return None

#         # Save files if provided
#         file_updates = {
#             "bgv_doc_url": await process_file(bgv_doc_file, "bgv", ["application/pdf"]),
#             "police_verification_doc_url": await process_file(police_verification_doc_file, "police_verification", ["application/pdf"]),
#             "medical_verification_doc_url": await process_file(medical_verification_doc_file, "medical_verification", ["application/pdf"]),
#             "training_verification_doc_url": await process_file(training_verification_doc_file, "training_verification", ["application/pdf"]),
#             "eye_test_verification_doc_url": await process_file(eye_test_verification_doc_file, "eye_test_verification", ["application/pdf"]),
#             "license_doc_url": await process_file(license_doc_file, "license", ["application/pdf"]),
#             "induction_doc_url": await process_file(induction_doc_file, "induction", ["application/pdf"]),
#             "badge_doc_url": await process_file(badge_doc_file, "badge", ["application/pdf"]),
#             "alternate_govt_id_doc_url": await process_file(alternate_govt_id_doc_file, "alternate_govt_id", ["application/pdf"]),
#             "photo_url": await process_file(photo_image, "photo", ["image/jpeg", "image/jpg", "image/png"]),
#         }

#         # Update normal fields
#         update_fields = {
#             "name": name,
#             "email": email,
#             "mobile_number": mobile_number,
#             "alternate_mobile_number": alternate_mobile_number,
#             "city": city,
#             "date_of_birth": date_of_birth,
#             "gender": gender,
#             "permanent_address": permanent_address,
#             "current_address": current_address,
#             "bgv_status": bgv_status,
#             "bgv_date": bgv_date,
#             "police_verification_status": police_verification_status,
#             "police_verification_date": police_verification_date,
#             "medical_verification_status": medical_verification_status,
#             "medical_verification_date": medical_verification_date,
#             "training_verification_status": training_verification_status,
#             "training_verification_date": training_verification_date,
#             "eye_test_verification_status": eye_test_verification_status,
#             "eye_test_verification_date": eye_test_verification_date,
#             "license_number": license_number,
#             "license_expiry_date": license_expiry_date,
#             "induction_date": induction_date,
#             "badge_number": badge_number,
#             "badge_expiry_date": badge_expiry_date,
#             "alternate_govt_id": alternate_govt_id,
#             "alternate_govt_id_doc_type": alternate_govt_id_doc_type,
#         }

#         for field, value in update_fields.items():
#             if value is not None:
#                 setattr(driver, field, value)

#         # Apply file URL updates
#         for field, value in file_updates.items():
#             if value:
#                 setattr(driver, field, value)

#         db.commit()
#         db.refresh(driver)
#         logger.info(f"Driver updated successfully: driver_id={driver.driver_id}, email={driver.email}")
#         return DriverOut.model_validate(driver, from_attributes=True)

#     except IntegrityError as e:
#         db.rollback()
#         logger.error(f"IntegrityError: {str(e.orig)}")
#         raise HTTPException(status_code=400, detail="Integrity error while updating driver.")
#     except HTTPException as e:
#         db.rollback()
#         raise e
#     except Exception as e:
#         db.rollback()
#         logger.exception("Unhandled exception in update_driver")
#         raise HTTPException(status_code=500, detail="Unexpected error during driver update.")

# @router.get("/{vendor_id}/drivers/", response_model=List[DriverOut])
# def get_drivers_by_vendor(
#     vendor_id: int,
#     skip: int = 0,
#     limit: int = 10,
#     bgv_status: Optional[str] = None,
#     search: Optional[str] = Query(None, description="Search by username or email"),
#     driver_id: Optional[int] = None,
#     driver_code: Optional[str] = None,
#     db: Session = Depends(get_db),
#     token_data: dict = Depends(PermissionChecker(["driver_management.create", "driver_management.read"]))
# ):
#     try:
#         logger.info(
#             f"Fetching drivers for vendor_id={vendor_id} with filters: skip={skip}, "
#             f"limit={limit}, bgv_status={bgv_status}, search={search}, "
#             f"driver_id={driver_id}, driver_code={driver_code}"
#         )

#         vendor = db.query(Vendor).filter_by(vendor_id=vendor_id).first()
#         if not vendor:
#             raise HTTPException(status_code=404, detail="Vendor not found.")

#         query = db.query(Driver).filter(Driver.vendor_id == vendor_id)

#         if driver_id:
#             query = query.filter(Driver.driver_id == driver_id)

#         if driver_code:
#             query = query.filter(Driver.driver_code == driver_code)

#         if bgv_status:
#             query = query.filter(Driver.bgv_status == bgv_status)

#         if search:
#             search_term = f"%{search.strip()}%"
#             query = query.filter(
#                 or_(
#                     Driver.driver_name.ilike(search_term),
#                     Driver.email.ilike(search_term)
#                 )
#             )

#         drivers = query.offset(skip).limit(limit).all()
        

#         if not drivers:
#             logger.warning("No drivers found for given filters.")
#             raise HTTPException(status_code=404, detail="No drivers found for the given filters.")

#         return drivers
#     except HTTPException as e:
#         raise e  # Allow FastAPI to handle it properly (don't override with 500)
#     except SQLAlchemyError as e:
#         logger.error(f"Database error: {str(e)}")
#         raise HTTPException(status_code=500, detail="Database error while fetching drivers.")
#     except Exception as e:
#         logger.exception("Unexpected error while fetching drivers.")
#         raise HTTPException(status_code=500, detail="Unexpected error while fetching drivers.")
 
# @router.patch("/{vendor_id}/drivers/{driver_id}/status", response_model=DriverOut)
# def toggle_driver_status(
#     vendor_id: int,
#     driver_id: int,
#     db: Session = Depends(get_db),
#     token_data: dict = Depends(PermissionChecker(["driver_management.update"]))
# ):
#     try:
#         driver = (
#             db.query(Driver)
#             .filter(Driver.driver_id == driver_id, Driver.vendor_id == vendor_id)
#             .first()
#         )

#         if not driver:
#             logger.warning(f"Driver ID {driver_id} not found for Vendor ID {vendor_id}")
#             raise HTTPException(status_code=404, detail="Driver not found for this vendor")

#         driver.is_active = not driver.is_active
#         db.commit()
#         db.refresh(driver)

#         status = "activated" if driver.is_active else "deactivated"
#         logger.info(f"Driver {driver_id} under vendor {vendor_id} successfully {status}")
#         return driver

#     except HTTPException as http_exc:
#         raise http_exc  # Don't override HTTPExceptions (like 404)

#     except Exception as e:
#         logger.exception(f"Error toggling status: {str(e)}")  # Use exception() to log full stack
#         raise HTTPException(status_code=500, detail="Internal Server Error")


# @router.put("/{vendor_id}/drivers/{driver_id}/status", response_model=DriverOut)
# def update_driver_status(
#     vendor_id: int,
#     driver_id: int,
#     status: StatusUpdate,
#     db: Session = Depends(get_db),
#     token_data: dict = Depends(PermissionChecker(["driver_management.update"]))
# ):
#     try:
#         driver = db.query(Driver).filter_by(driver_id=driver_id, vendor_id=vendor_id).first()
#         if not driver:
#             logger.warning(f"Driver ID {driver_id} not found for vendor ID {vendor_id}")
#             raise HTTPException(status_code=404, detail="Driver not found for this vendor")

#         if driver.is_active == status.is_active:
#             current_state = "active" if status.is_active else "inactive"
#             logger.info(f"Driver {driver_id} is already {current_state}")
#             raise HTTPException(status_code=400, detail=f"Driver is already {current_state}")

#         driver.is_active = status.is_active
#         db.commit()
#         db.refresh(driver)

#         new_state = "activated" if driver.is_active else "deactivated"
#         logger.info(f"Driver {driver_id} under vendor {vendor_id} successfully {new_state}")
#         return driver

#     except HTTPException as http_exc:
#         raise http_exc  # Allow FastAPI to handle proper HTTPException responses
    
#     except Exception as e:
#         db.rollback()
#         logger.exception(f"Unexpected error while toggling driver status: {str(e)}")
#         raise HTTPException(status_code=500, detail="Internal Server Error")