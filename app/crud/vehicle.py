from typing import Optional, List, Dict, Any, Union
from sqlalchemy.orm import Session
from sqlalchemy.exc import IntegrityError
from fastapi import HTTPException, status

from app.models.vehicle import Vehicle
from app.models.vehicle_type import VehicleType
from app.models.driver import Driver
from app.schemas.vehicle import VehicleCreate, VehicleUpdate
from app.utils.response_utils import ResponseWrapper, handle_db_error
from app.crud.base import CRUDBase
from app.core.logging_config import get_logger

logger = get_logger(__name__)

class CRUDVehicle(CRUDBase[Vehicle, VehicleCreate, VehicleUpdate]):

    def get_by_id_and_vendor(
        self, db: Session, *, vehicle_id: int, vendor_id: Optional[int] = None
    ) -> Optional[Vehicle]:
        """Fetch vehicle by ID (and vendor if provided)"""
        query = db.query(Vehicle).filter(Vehicle.vehicle_id == vehicle_id)
        if vendor_id is not None:
            query = query.filter(Vehicle.vendor_id == vendor_id)
        return query.first()

    def get_by_vendor(
        self,
        db: Session,
        *,
        vendor_id: int,
        active_only: Optional[bool] = None,
        search: Optional[str] = None
    ) -> List[Vehicle]:
        """List all vehicles for a vendor with optional filters"""
        query = db.query(Vehicle).filter(Vehicle.vendor_id == vendor_id)

        if active_only is not None:
            query = query.filter(Vehicle.is_active.is_(active_only))

        if search:
            search_str = f"%{search.strip()}%"
            query = query.filter(
                (Vehicle.rc_number.ilike(search_str)) |
                (Vehicle.insurance_number.ilike(search_str)) |
                (Vehicle.permit_number.ilike(search_str))
            )

        return query.order_by(Vehicle.created_at.desc()).all()

    def create_with_vendor(
        self, db: Session, *, vendor_id: int, obj_in: VehicleCreate
    ) -> Vehicle:
        """Create a vehicle under a vendor with relationship validation and logging."""
        logger.info(
            f"[VehicleCreate] Initiating vehicle creation | vendor_id={vendor_id}, vehicle_type_id={obj_in.vehicle_type_id}, driver_id={obj_in.driver_id}"
        )

        # ✅ Check if vehicle type exists
        vehicle_type = db.query(VehicleType).filter(
            VehicleType.vehicle_type_id == obj_in.vehicle_type_id,
            VehicleType.vendor_id == vendor_id
        ).first()
        if not vehicle_type:
            logger.warning(
                f"[VehicleCreate] Invalid vehicle_type_id={obj_in.vehicle_type_id} for vendor_id={vendor_id}"
            )
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=ResponseWrapper.error(
                    message="Invalid vehicle_type_id for this vendor",
                    error_code="INVALID_VEHICLE_TYPE",
                ),
            )
            # ✅ Normalize driver_id = 0 → None
        driver_id = obj_in.driver_id
        if driver_id in [0, "0", None, ""]:
            driver_id = None

        # ✅ Validate driver (if provided)
        if driver_id:
            driver_exists = db.query(Driver).filter(
                Driver.driver_id == driver_id,
                Driver.vendor_id == vendor_id
            ).first()
            if not driver_exists:
                logger.warning(f"[VehicleCreate] Invalid driver_id={driver_id} for vendor_id={vendor_id}")
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=ResponseWrapper.error("Driver not found for this vendor", "INVALID_DRIVER"),
                )

        # ✅ Check driver validity (if provided)
        if obj_in.driver_id:
            driver_exists = db.query(Driver).filter(
                Driver.driver_id == obj_in.driver_id,
                Driver.vendor_id == vendor_id
            ).first()
            if not driver_exists:
                logger.warning(
                    f"[VehicleCreate] Invalid driver_id={obj_in.driver_id} for vendor_id={vendor_id}"
                )
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=ResponseWrapper.error(
                        message="Driver not found for this vendor",
                        error_code="INVALID_DRIVER",
                    ),
                )

        # ✅ Create vehicle record
        db_obj = Vehicle(
            vendor_id=vendor_id,
            vehicle_type_id=obj_in.vehicle_type_id, 
            driver_id=driver_id,
            rc_number=obj_in.rc_number.strip(),
            rc_expiry_date=obj_in.rc_expiry_date,
            description=obj_in.description,
            puc_expiry_date=obj_in.puc_expiry_date,
            puc_url=obj_in.puc_url,
            fitness_expiry_date=obj_in.fitness_expiry_date,
            fitness_url=obj_in.fitness_url,
            tax_receipt_date=obj_in.tax_receipt_date,
            tax_receipt_url=obj_in.tax_receipt_url,
            insurance_expiry_date=obj_in.insurance_expiry_date,
            insurance_url=obj_in.insurance_url,
            permit_expiry_date=obj_in.permit_expiry_date,
            permit_url=obj_in.permit_url,
            is_active=obj_in.is_active if obj_in.is_active is not None else True,
        )

        db.add(db_obj)

        try:
            db.flush()
            logger.info(
                f"[VehicleCreate] Vehicle created successfully | vehicle_id={db_obj.vehicle_id}, vendor_id={vendor_id}"
            )
        except IntegrityError as e:
            logger.error(
                f"[VehicleCreate] IntegrityError for vendor_id={vendor_id}, rc_number={obj_in.rc_number}: {str(e)}"
            )
            raise handle_db_error(e)
        except Exception as e:
            logger.exception(
                f"[VehicleCreate] Unexpected error creating vehicle for vendor_id={vendor_id}: {str(e)}"
            )
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=ResponseWrapper.error(
                    message="Unexpected error occurred while creating vehicle",
                    error_code="VEHICLE_CREATE_FAILED",
                ),
            )

        return db_obj

    def update_with_vendor(
        self, db: Session, *, vehicle_id: int, obj_in: Union[VehicleUpdate, Dict[str, Any]]
    ) -> Vehicle:
        """Update vehicle and handle vendor-level uniqueness"""
        db_obj = db.query(Vehicle).filter(Vehicle.vehicle_id == vehicle_id).first()
        if not db_obj:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=ResponseWrapper.error(
                    message=f"Vehicle {vehicle_id} not found",
                    error_code="VEHICLE_NOT_FOUND",
                ),
            )

        update_data = obj_in if isinstance(obj_in, dict) else obj_in.dict(exclude_unset=True)

        # Prevent changing vendor_id or vehicle_type_id directly (use specific APIs)
        protected_fields = {"vendor_id"}
        for field in protected_fields:
            update_data.pop(field, None)

        for field, value in update_data.items():
            setattr(db_obj, field, value)

        try:
            db.flush()
        except IntegrityError:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=ResponseWrapper.error(
                    message="Duplicate vehicle document number for this vendor",
                    error_code="VEHICLE_DUPLICATE",
                ),
            )
        return db_obj

    def delete_with_vendor(self, db: Session, *, vehicle_id: int, vendor_id: int) -> bool:
        """Soft delete a vehicle by marking inactive"""
        db_obj = db.query(Vehicle).filter(
            Vehicle.vehicle_id == vehicle_id,
            Vehicle.vendor_id == vendor_id
        ).first()
        if not db_obj:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=ResponseWrapper.error(
                    message=f"Vehicle {vehicle_id} not found for this vendor",
                    error_code="VEHICLE_NOT_FOUND",
                ),
            )
        db_obj.is_active = False
        db.flush()
        return True


vehicle_crud = CRUDVehicle(Vehicle)
