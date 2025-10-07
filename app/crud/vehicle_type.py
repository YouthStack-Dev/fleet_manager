from typing import Optional, List, Dict, Any, Union
from sqlalchemy.orm import Session
from sqlalchemy.exc import IntegrityError
from fastapi import HTTPException, status

from app.models.vehicle_type import VehicleType
from app.schemas.vehicle_type import VehicleTypeCreate, VehicleTypeUpdate
from app.utils.response_utils import ResponseWrapper
from app.crud.base import CRUDBase


class CRUDVehicleType(CRUDBase[VehicleType, VehicleTypeCreate, VehicleTypeUpdate]):

    def get_by_vendor_and_name(
        self, db: Session, *, vendor_id: int, name: str
    ) -> Optional[VehicleType]:
        """Fetch vehicle type by vendor + name"""
        return (
            db.query(VehicleType)
            .filter(
                VehicleType.vendor_id == vendor_id,
                VehicleType.name.ilike(name.strip()),
            )
            .first()
        )

    def get_by_vendor_and_id(
        self, db: Session, *, vendor_id: Optional[int], vehicle_type_id: int
    ) -> Optional[VehicleType]:
        """Fetch vehicle type by vendor + id"""
        query = db.query(VehicleType).filter(VehicleType.vehicle_type_id == vehicle_type_id)
        if vendor_id is not None:  # vendor user
            query = query.filter(VehicleType.vendor_id == vendor_id)
        return query.first()



    def create_with_vendor(
        self, db: Session, *, vendor_id: int, obj_in: VehicleTypeCreate
    ) -> VehicleType:
        """Create a vehicle type under a specific vendor"""
        db_obj = VehicleType(
            vendor_id=vendor_id,
            name=obj_in.name.strip(),
            description=obj_in.description,
            seats=obj_in.seats,
            is_active=obj_in.is_active if obj_in.is_active is not None else True,
        )
        db.add(db_obj)
        try:
            db.flush()
        except IntegrityError:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=ResponseWrapper.error(
                    message=f"Vehicle type '{obj_in.name}' already exists for this vendor",
                    error_code="VEHICLE_TYPE_DUPLICATE",
                ),
            )
        return db_obj

    def update_with_vendor(
        self, db: Session, *, vehicle_type_id: int, obj_in: Union[VehicleTypeUpdate, Dict[str, Any]]
    ) -> VehicleType:
        """Update a vehicle type and handle unique constraint"""
        db_obj = db.query(VehicleType).filter(VehicleType.vehicle_type_id == vehicle_type_id).first()
        if not db_obj:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=ResponseWrapper.error(
                    message=f"Vehicle type {vehicle_type_id} not found",
                    error_code="VEHICLE_TYPE_NOT_FOUND",
                ),
            )

        update_data = obj_in if isinstance(obj_in, dict) else obj_in.dict(exclude_unset=True)

        for field, value in update_data.items():
            setattr(db_obj, field, value)

        try:
            db.flush()
        except IntegrityError:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=ResponseWrapper.error(
                    message=f"Vehicle type with name '{db_obj.name}' already exists for this vendor",
                    error_code="VEHICLE_TYPE_DUPLICATE",
                ),
            )

        return db_obj

    def get_by_vendor(
        self,
        db: Session,
        *,
        vendor_id: int,
        active_only: Optional[bool] = None,
        name: Optional[str] = None  # <-- filter by name
    ) -> List[VehicleType]:
        """Get all vehicle types for a vendor, optionally filter by name and active status"""
        query = db.query(VehicleType).filter(VehicleType.vendor_id == vendor_id)

        if active_only is not None:
            query = query.filter(VehicleType.is_active.is_(active_only))

        if name:
            query = query.filter(VehicleType.name.ilike(f"%{name.strip()}%"))

        return query.all()


vehicle_type_crud = CRUDVehicleType(VehicleType)
