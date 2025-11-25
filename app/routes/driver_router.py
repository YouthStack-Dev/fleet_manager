from datetime import date
from app.models.vendor import Vendor
from app.utils.validition import validate_future_dates
from common_utils.auth.utils import hash_password
from fastapi import APIRouter, Depends, UploadFile, Form, HTTPException, status , Query, Request
from sqlalchemy.orm import Session
from typing import Optional
import io
from app.crud.vendor import vendor_crud
import shutil
from sqlalchemy.exc import SQLAlchemyError
from app.database.session import get_db
from app.schemas.driver import DriverCreate, DriverPaginationResponse, DriverResponse, GovtIDTypeEnum
from app.crud.driver import driver_crud
from app.utils.response_utils import ResponseWrapper, handle_db_error, handle_http_error
from app.utils.file_utils import file_size_validator, save_file
from app.models.driver import Driver, VerificationStatusEnum ,GenderEnum 
from common_utils.auth.permission_checker import PermissionChecker
from app.core.logging_config import get_logger
from app.services.storage_service import storage_service
from app.firebase.driver_location import push_driver_location_to_firebase
from fastapi.encoders import jsonable_encoder
from app.utils.audit_helper import log_audit
logger = get_logger(__name__)
router = APIRouter(prefix="/drivers", tags=["drivers"])

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


@router.post("/create", response_model=dict, status_code=status.HTTP_201_CREATED)
async def create_driver(
    request: Request,
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
    driver_code = None ,
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
        # --- Vendor resolution (clean + correct) ---
        resolved_vendor_id = resolve_vendor_scope(
            user_data=user_data,
            provided_vendor_id=vendor_id,
            allow_create=True
        )

        vendor_obj = validate_vendor_and_tenant(db, resolved_vendor_id, user_data)
        vendor_id = resolved_vendor_id


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

        # --- Push driver location to Firebase ---
        try:
            # Get vendor with tenant relationship
            vendor = db.query(Vendor).filter(Vendor.vendor_id == vendor_id).first()
            if vendor and vendor.tenant_id:
                logger.info(f"Pushing driver {db_obj.driver_id} to Firebase")
                push_driver_location_to_firebase(
                    tenant_id=vendor.tenant_id,
                    vendor_id=vendor_id,
                    driver_id=db_obj.driver_id,
                    latitude=None,
                    longitude=None,
                    driver_code=driver_code
                )
        except Exception as firebase_error:
            logger.error(f"⚠️ Firebase push failed for driver {driver_code}: {str(firebase_error)}")
            # Continue - don't fail the entire operation if Firebase push fails

        # 🔍 Audit Log: Driver Creation
        try:
            log_audit(
                db=db,
                tenant_id=db_obj.vendor.tenant_id if db_obj.vendor else None,
                module="driver",
                action="CREATE",
                user_data=user_data,
                description=f"Created driver '{name}' with code '{driver_code}'",
                new_values={"name": name, "code": driver_code, "vendor_id": vendor_id, "driver_id": db_obj.driver_id},
                request=request
            )
        except Exception as audit_error:
            logger.error(f"Failed to create audit log for driver creation: {str(audit_error)}")

        logger.info(f"✅ Driver '{driver_code}' created successfully (ID={db_obj.driver_id})")
        return ResponseWrapper.success(
            data={"driver": DriverResponse.model_validate(db_obj, from_attributes=True)},
            message="Driver created successfully"
        )

    except HTTPException as e:
        db.rollback()
        logger.warning(
            f"Driver creation failed (HTTPException) for driver '{driver_code or code}': {e.detail}"
        )
        raise

    except SQLAlchemyError as e:
        db.rollback()
        logger.error(
            f"Database error creating driver '{driver_code or code}': {e}"
        )
        raise handle_db_error(e)

    except Exception as e:
        db.rollback()
        logger.error(
            f"Unexpected error creating driver '{driver_code or code}': {e}"
        )
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
    """
    Get specific driver details.

    Vendor resolution rules (unified):
      - admin          → must send vendor_id
      - vendor         → vendor_id from token only
      - employee       → must send vendor_id AND vendor must belong to employee tenant
      - driver         → forbidden
      - others         → forbidden
    """
    try:
        # 1️⃣ Resolve vendor scope with your centralized helpers
        resolved_vendor_id = resolve_vendor_scope(
            user_data=user_data,
            provided_vendor_id=vendor_id,
            allow_create=False
        )

        # 2️⃣ Validate vendor exists + employee tenant check
        vendor_obj = validate_vendor_and_tenant(
            db=db,
            vendor_id=resolved_vendor_id,
            user_data=user_data
        )
        if not vendor_obj.is_active:
            raise HTTPException(403, ResponseWrapper.error("Vendor inactive", "VENDOR_INACTIVE"))


        # Final vendor_id to use
        vendor_id = resolved_vendor_id

        logger.info(
            f"[GET DRIVER] Fetching driver_id={driver_id} for vendor_id={vendor_id} "
            f"by user={user_data.get('user_id')}"
        )

        # 3️⃣ Fetch driver within vendor scope
        driver = driver_crud.get_by_id_and_vendor(
            db=db,
            driver_id=driver_id,
            vendor_id=vendor_id
        )

        if not driver:
            logger.warning(f"[GET DRIVER] Driver {driver_id} not found for vendor {vendor_id}")
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=ResponseWrapper.error("Driver not found", "DRIVER_NOT_FOUND")
            )

        logger.info(f"[GET DRIVER] Driver fetched: driver_id={driver.driver_id}")
        return ResponseWrapper.success(
            data={"driver": DriverResponse.model_validate(driver, from_attributes=True)}
        )

    except HTTPException:
        raise
    except SQLAlchemyError as e:
        logger.error(f"[GET DRIVER] Database error: {e}")
        raise handle_db_error(e)
    except Exception as e:
        logger.error(f"[GET DRIVER] Unexpected error: {e}")
        raise handle_http_error(e)



# --------------------------
# GET all drivers for vendor with filters
# --------------------------
@router.get("/vendor", response_model=dict)
def get_drivers(
    vendor_id: Optional[int] = None,
    active_only: Optional[bool] = Query(None, description="Filter by active/inactive drivers"),
    license_number: Optional[str] = Query(None, description="Filter by license number"),
    search: Optional[str] = Query(None, description="Search by name, email, phone, badge, license"),
    db: Session = Depends(get_db),
    user_data=Depends(PermissionChecker(["driver.read"]))
):
    """
    Unified driver fetch endpoint.
    - Vendor users → only their vendor.
    - Employee users → only vendors under their tenant.
    - Admin/SuperAdmin → any vendor (must provide vendor_id if admin).
    """
    try:
        # --------------------------------------
        # 1️⃣ Resolve which vendor_id this user is allowed to query
        # --------------------------------------
        resolved_vendor_id = resolve_vendor_scope(
            user_data=user_data,
            provided_vendor_id=vendor_id,
            allow_create=False  # not create, but same validation applies
        )

        # --------------------------------------
        # 2️⃣ Validate vendor exists + employee tenant restriction
        # --------------------------------------
        vendor_obj = validate_vendor_and_tenant(
            db=db,
            vendor_id=resolved_vendor_id,
            user_data=user_data
        )

        logger.info(
            f"[GET DRIVERS] User={user_data.get('user_id')} "
            f"type={user_data.get('user_type')} "
            f"fetching drivers for vendor_id={resolved_vendor_id}"
        )

        # --------------------------------------
        # 3️⃣ Employee user special filtering (tenant-wide)
        # --------------------------------------
        if user_data.get("user_type") == "employee":
            token_tenant_id = user_data.get("tenant_id")

            query = (
                db.query(Driver)
                .join(Vendor)
                .filter(Vendor.tenant_id == token_tenant_id,
                        Vendor.vendor_id == resolved_vendor_id)
            )

            # apply filters
            if active_only is not None:
                query = query.filter(Driver.is_active == active_only)

            if license_number:
                query = query.filter(Driver.license_number == license_number)

            if search:
                search_like = f"%{search}%"
                query = query.filter(
                    Driver.name.ilike(search_like)
                    | Driver.email.ilike(search_like)
                    | Driver.phone.ilike(search_like)
                    | Driver.badge_number.ilike(search_like)
                    | Driver.license_number.ilike(search_like)
                )

            drivers = query.all()

            driver_list = [
                DriverResponse.model_validate(d, from_attributes=True)
                for d in drivers
            ]

            return ResponseWrapper.success(
                data=DriverPaginationResponse(
                    total=len(driver_list),
                    items=driver_list
                ).dict()
            )

        # --------------------------------------
        # 4️⃣ Default flow: vendor/admin/superadmin
        # --------------------------------------
        drivers = driver_crud.get_by_vendor(
            db=db,
            vendor_id=resolved_vendor_id,
            active_only=active_only,
            search=search
        )

        # Filter by license (manual)
        if license_number:
            drivers = [d for d in drivers if d.license_number == license_number]

        driver_list = [
            DriverResponse.model_validate(d, from_attributes=True)
            for d in drivers
        ]

        return ResponseWrapper.success(
            data=DriverPaginationResponse(total=len(driver_list), items=driver_list).dict()
        )

    except HTTPException:
        raise

    except SQLAlchemyError as e:
        logger.error(f"Database error fetching drivers: {e}")
        raise handle_db_error(e)

    except Exception as e:
        logger.error(f"Unexpected error fetching drivers: {e}")
        raise handle_http_error(e)

@router.put("/update", response_model=dict)
async def update_driver(
    driver_id: int,
    request: Request,
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

    # Files
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
    user_data=Depends(PermissionChecker(["driver.update"]))
):
    """
    Update driver details with unified vendor and tenant validation.
    """
    validate_future_dates(
        {
            "bg_expiry_date": bg_expiry_date,
            "police_expiry_date": police_expiry_date,
            "medical_expiry_date": medical_expiry_date,
            "training_expiry_date": training_expiry_date,
            "eye_expiry_date": eye_expiry_date,
            "badge_expiry_date": badge_expiry_date,
            "license_expiry_date": license_expiry_date,
        },
        context="driver"
    )

    try:
        # ------------------------------------------------------
        # 1️⃣ Resolve correct vendor_id for this user
        # ------------------------------------------------------
        resolved_vendor_id = resolve_vendor_scope(
            user_data=user_data,
            provided_vendor_id=vendor_id,
            allow_create=False
        )

        # ------------------------------------------------------
        # 2️⃣ Validate vendor exists + employee tenant check
        # ------------------------------------------------------
        vendor_obj = validate_vendor_and_tenant(
            db=db,
            vendor_id=resolved_vendor_id,
            user_data=user_data
        )

        logger.info(
            f"[UPDATE DRIVER] User={user_data.get('user_id')} updating driver_id={driver_id} "
            f"for vendor_id={resolved_vendor_id}"
        )

        # ------------------------------------------------------
        # 3️⃣ Fetch driver under validated vendor
        # ------------------------------------------------------
        db_obj = driver_crud.get_by_id_and_vendor(
            db=db,
            driver_id=driver_id,
            vendor_id=resolved_vendor_id
        )

        if not db_obj:
            raise HTTPException(
                404,
                ResponseWrapper.error("Driver not found", "DRIVER_NOT_FOUND")
            )

        # ------------------------------------------------------
        # 🔍 Capture old values before update
        # ------------------------------------------------------
        old_values = {}
        update_params = {
            "name": name, "code": code, "email": email, "phone": phone,
            "gender": gender, "date_of_birth": date_of_birth, "date_of_joining": date_of_joining,
            "permanent_address": permanent_address, "current_address": current_address,
            "license_number": license_number, "license_expiry_date": license_expiry_date,
            "badge_number": badge_number, "badge_expiry_date": badge_expiry_date,
            "alt_govt_id_number": alt_govt_id_number, "alt_govt_id_type": alt_govt_id_type,
            "induction_date": induction_date, "bg_expiry_date": bg_expiry_date,
            "police_expiry_date": police_expiry_date, "medical_expiry_date": medical_expiry_date,
            "training_expiry_date": training_expiry_date, "eye_expiry_date": eye_expiry_date,
            "bg_verify_status": bg_verify_status, "police_verify_status": police_verify_status,
            "medical_verify_status": medical_verify_status, "training_verify_status": training_verify_status,
            "eye_verify_status": eye_verify_status
        }
        
        for field, value in update_params.items():
            if value is not None and field != "password":
                old_val = getattr(db_obj, field, None)
                if old_val is not None:
                    old_values[field] = str(old_val) if not isinstance(old_val, (str, int, float, bool)) else old_val

        # ------------------------------------------------------
        # 4️⃣ Handle file uploads
        # ------------------------------------------------------
        allowed_docs = ["image/jpeg", "image/png", "application/pdf"]

        file_map = {
            "photo": "photo_url",
            "license_file": "license_url",
            "badge_file": "badge_url",
            "alt_govt_id_file": "alt_govt_id_url",
            "bgv_file": "bg_verify_url",
            "police_file": "police_verify_url",
            "medical_file": "medical_verify_url",
            "training_file": "training_verify_url",
            "eye_file": "eye_verify_url",
            "induction_file": "induction_url",
        }

        for upload_name, db_field in file_map.items():
            upload_file = locals()[upload_name]
            if upload_file and await file_size_validator(upload_file, allowed_docs, 10, required=False):
                # Remove old file
                old = getattr(db_obj, db_field)
                if old:
                    storage_service.delete_file(old)

                # Save new file
                new_url = storage_service.save_file(
                    upload_file, resolved_vendor_id, db_obj.code, upload_name.replace("_file", "")
                )
                setattr(db_obj, db_field, new_url)

        # ------------------------------------------------------
        # 5️⃣ Update normal fields
        # ------------------------------------------------------
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
            "bg_expiry_date": bg_expiry_date,
            "police_expiry_date": police_expiry_date,
            "medical_expiry_date": medical_expiry_date,
            "training_expiry_date": training_expiry_date,
            "eye_expiry_date": eye_expiry_date,
        }

        for field, value in update_fields.items():
            if value is not None:
                setattr(db_obj, field, value)

        # ------------------------------------------------------
        # 6️⃣ Update enum fields safely
        # ------------------------------------------------------
        for enum_field in [
            "bg_verify_status",
            "police_verify_status",
            "medical_verify_status",
            "training_verify_status",
            "eye_verify_status",
        ]:
            value = locals().get(enum_field)
            if value is not None:
                if isinstance(value, str):
                    value = VerificationStatusEnum(value)
                setattr(db_obj, enum_field, value)

        # ------------------------------------------------------
        # 7️⃣ Save changes
        # ------------------------------------------------------
        db.commit()
        db.refresh(db_obj)

        # ------------------------------------------------------
        # 🔍 Capture new values after update
        # ------------------------------------------------------
        new_values = {}
        for field in update_params.keys():
            if update_params[field] is not None and field != "password":
                new_val = getattr(db_obj, field, None)
                if new_val is not None:
                    new_values[field] = str(new_val) if not isinstance(new_val, (str, int, float, bool)) else new_val

        # ------------------------------------------------------
        # 🔍 Audit Log: Driver Update
        # ------------------------------------------------------
        try:
            changed_fields = [k for k, v in update_params.items() if v is not None]
            fields_str = ", ".join(changed_fields) if changed_fields else "details"
            
            log_audit(
                db=db,
                tenant_id=db_obj.vendor.tenant_id if db_obj.vendor else None,
                module="driver",
                action="UPDATE",
                user_data=user_data,
                description=f"Updated driver '{db_obj.name}' - changed fields: {fields_str}",
                new_values={"old": old_values, "new": new_values},
                request=request
            )
            logger.info(f"Audit log created for driver update")
        except Exception as audit_error:
            logger.error(f"Failed to create audit log for driver update: {str(audit_error)}", exc_info=True)

        logger.info(f"[UPDATE DRIVER] Driver updated successfully: {driver_id}")

        return ResponseWrapper.success(
            data={"driver": DriverResponse.model_validate(db_obj, from_attributes=True)},
            message="Driver updated successfully"
        )

    except HTTPException:
        db.rollback()
        raise

    except SQLAlchemyError as e:
        db.rollback()
        raise handle_db_error(e)

    except Exception as e:
        db.rollback()
        raise handle_http_error(e)

@router.patch("/{driver_id}/toggle-active", response_model=dict)
def toggle_driver_active(
    driver_id: int,
    request: Request,
    vendor_id: Optional[int] = None,
    db: Session = Depends(get_db),
    user_data=Depends(PermissionChecker(["driver.update"]))
):
    """
    Toggle the active status of a driver (activate/deactivate) with full vendor + tenant validation.
    """
    try:
        # ------------------------------------------------------
        # 1️⃣ Resolve vendor scope based on user role
        # ------------------------------------------------------
        resolved_vendor_id = resolve_vendor_scope(
            user_data=user_data,
            provided_vendor_id=vendor_id,
            allow_create=False
        )

        # ------------------------------------------------------
        # 2️⃣ Validate vendor exists and employee->tenant match
        # ------------------------------------------------------
        vendor_obj = validate_vendor_and_tenant(
            db=db,
            vendor_id=resolved_vendor_id,
            user_data=user_data
        )

        logger.info(
            f"[TOGGLE DRIVER ACTIVE] user={user_data.get('user_id')} "
            f"driver_id={driver_id} vendor_id={resolved_vendor_id}"
        )

        # ------------------------------------------------------
        # 3️⃣ Fetch driver under the validated vendor
        # ------------------------------------------------------
        driver = driver_crud.get_by_id_and_vendor(
            db=db,
            driver_id=driver_id,
            vendor_id=resolved_vendor_id
        )

        if not driver:
            raise HTTPException(
                404,
                ResponseWrapper.error("Driver not found", "DRIVER_NOT_FOUND")
            )

        # ------------------------------------------------------
        # 4️⃣ Toggle active flag
        # ------------------------------------------------------
        old_status = driver.is_active
        driver.is_active = not driver.is_active

        db.flush()
        db.commit()
        db.refresh(driver)

        status_str = "activated" if driver.is_active else "deactivated"

        # ------------------------------------------------------
        # 🔍 Audit Log: Status Toggle
        # ------------------------------------------------------
        try:
            status_text = 'active' if driver.is_active else 'inactive'
            log_audit(
                db=db,
                tenant_id=driver.vendor.tenant_id if driver.vendor else None,
                module="driver",
                action="UPDATE",
                user_data=user_data,
                description=f"Toggled driver '{driver.name}' status to {status_text}",
                new_values={"old_status": old_status, "new_status": driver.is_active},
                request=request
            )
        except Exception as audit_error:
            logger.error(f"Failed to create audit log for status toggle: {str(audit_error)}")

        logger.info(
            f"[TOGGLE DRIVER ACTIVE] Driver {driver_id} -> {status_str} "
            f"by user={user_data.get('user_id')}"
        )

        return ResponseWrapper.success(
            data={"driver_id": driver.driver_id, "is_active": driver.is_active},
            message=f"Driver successfully {status_str}"
        )

    except HTTPException:
        db.rollback()
        raise
    except SQLAlchemyError as e:
        db.rollback()
        raise handle_db_error(e)
    except Exception as e:
        db.rollback()
        raise handle_http_error(e)
