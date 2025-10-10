from typing import Optional, List, Dict, Any, Union
from sqlalchemy.orm import Session
from sqlalchemy.exc import IntegrityError
from fastapi import HTTPException, status
from sqlalchemy.exc import SQLAlchemyError
from app.models.driver import Driver, VerificationStatusEnum, GenderEnum
from app.schemas.driver import DriverCreate, DriverUpdate
from app.models.vendor import Vendor
from app.utils.response_utils import ResponseWrapper, handle_db_error, handle_http_error
from app.crud.base import CRUDBase


class CRUDDriver(CRUDBase[Driver, DriverCreate, DriverUpdate]):

    def get_by_id_and_vendor(
        self, db: Session, *, driver_id: int, vendor_id: Optional[int] = None
    ) -> Optional[Driver]:
        """Fetch driver by ID (and vendor if provided)."""
        query = db.query(Driver).filter(Driver.driver_id == driver_id)
        if vendor_id is not None:
            query = query.filter(Driver.vendor_id == vendor_id)
        return query.first()

    def get_by_vendor(
        self,
        db: Session,
        *,
        vendor_id: int,
        active_only: Optional[bool] = None,
        search: Optional[str] = None,
        verify_status: Optional[str] = None
    ) -> List[Driver]:
        """List all drivers for a vendor with optional filters."""
        query = db.query(Driver).filter(Driver.vendor_id == vendor_id)

        if active_only is not None:
            query = query.filter(Driver.is_active.is_(active_only))

        if verify_status:
            query = query.filter(Driver.bg_verify_status == verify_status)

        if search:
            search_str = f"%{search.strip()}%"
            query = query.filter(
                (Driver.name.ilike(search_str))
                | (Driver.email.ilike(search_str))
                | (Driver.phone.ilike(search_str))
                | (Driver.badge_number.ilike(search_str))
                | (Driver.license_number.ilike(search_str))
            )

        return query.order_by(Driver.created_at.desc()).all()

    def create_with_vendor(
        self, db: Session, *, vendor_id: int, obj_in: DriverCreate
    ) -> Driver:
        """Create a driver under a vendor with proper relationship and uniqueness checks."""
        
        # ✅ Validate vendor
        vendor_exists = db.query(Vendor).filter(Vendor.vendor_id == vendor_id).first()
        if not vendor_exists:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=ResponseWrapper.error(
                    message="Vendor not found",
                    error_code="INVALID_VENDOR",
                ),
            )

        # ✅ Create driver object
        db_obj = Driver(
            vendor_id=vendor_id,
            name=obj_in.name.strip(),
            code=obj_in.code.strip(),
            email=obj_in.email.strip(),
            phone=obj_in.phone.strip(),
            gender=obj_in.gender,
            password=obj_in.password,
            date_of_birth=obj_in.date_of_birth,
            date_of_joining=obj_in.date_of_joining,
            permanent_address=obj_in.permanent_address,
            current_address=obj_in.current_address,

            # FILE URLS
            photo_url=obj_in.photo_url,
            license_url=obj_in.license_url,
            badge_url=obj_in.badge_url,
            alt_govt_id_url=obj_in.alt_govt_id_url,
            bg_verify_url=obj_in.bg_verify_url,
            police_verify_url=obj_in.police_verify_url,
            medical_verify_url=obj_in.medical_verify_url,
            training_verify_url=obj_in.training_verify_url,
            eye_verify_url=obj_in.eye_verify_url,
            induction_url=obj_in.induction_url,

            # Verification statuses
            bg_verify_status=obj_in.bg_verify_status,
            police_verify_status=obj_in.police_verify_status,
            medical_verify_status=obj_in.medical_verify_status,
            training_verify_status=obj_in.training_verify_status,
            eye_verify_status=obj_in.eye_verify_status,

            # Verification expiries ✅ 
            bg_expiry_date=obj_in.bg_expiry_date,
            police_expiry_date=obj_in.police_expiry_date,
            medical_expiry_date=obj_in.medical_expiry_date,
            training_expiry_date=obj_in.training_expiry_date,
            eye_expiry_date=obj_in.eye_expiry_date,

            # License info
            license_number=obj_in.license_number,
            license_expiry_date=obj_in.license_expiry_date,

            # Badge info
            badge_number=obj_in.badge_number,
            badge_expiry_date=obj_in.badge_expiry_date,

            # Alternate govt ID
            alt_govt_id_number=obj_in.alt_govt_id_number,
            alt_govt_id_type=obj_in.alt_govt_id_type,

            # Induction
            induction_date=obj_in.induction_date,

            # System flags
            is_active=True,
        )

        # ✅ Save
        db.add(db_obj)
        try:
            db.flush()
        except SQLAlchemyError as e:
            raise handle_db_error(e)
        except HTTPException as e:
            raise handle_http_error(e)
        
        return db_obj

    def update_with_vendor(
        self, db: Session, *, driver_id: int, obj_in: Union[DriverUpdate, Dict[str, Any]]
    ) -> Driver:
        """Update a driver’s details safely."""
        db_obj = db.query(Driver).filter(Driver.driver_id == driver_id).first()
        if not db_obj:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=ResponseWrapper.error(
                    message=f"Driver {driver_id} not found",
                    error_code="DRIVER_NOT_FOUND",
                ),
            )

        update_data = obj_in if isinstance(obj_in, dict) else obj_in.dict(exclude_unset=True)

        # Prevent vendor_id modification
        protected_fields = {"vendor_id"}
        for field in protected_fields:
            update_data.pop(field, None)

        for field, value in update_data.items():
            setattr(db_obj, field, value)

        try:
            db.flush()
        except SQLAlchemyError as e:
            raise handle_db_error(e)
        return db_obj

    def delete_with_vendor(self, db: Session, *, driver_id: int, vendor_id: int) -> bool:
        """Soft delete driver by marking inactive."""
        db_obj = db.query(Driver).filter(
            Driver.driver_id == driver_id,
            Driver.vendor_id == vendor_id
        ).first()
        if not db_obj:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=ResponseWrapper.error(
                    message=f"Driver {driver_id} not found for this vendor",
                    error_code="DRIVER_NOT_FOUND",
                ),
            )
        db_obj.is_active = False
        db.flush()
        return True


driver_crud = CRUDDriver(Driver)
