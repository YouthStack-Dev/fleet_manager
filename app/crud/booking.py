from typing import Optional, List, Union, Dict, Any
from sqlalchemy.orm import Session
from sqlalchemy.exc import SQLAlchemyError
from app.models.booking import Booking
from app.schemas.booking import BookingCreate, BookingUpdate
from app.crud.base import CRUDBase


class CRUDBooking(CRUDBase[Booking, BookingCreate, BookingUpdate]):
    def get_by_id(self, db: Session, *, booking_id: int) -> Optional[Booking]:
        return db.query(Booking).filter(Booking.booking_id == booking_id).first()

    def get_by_employee(self, db: Session, *, employee_id: int, skip: int = 0, limit: int = 100) -> List[Booking]:
        return db.query(Booking).filter(Booking.employee_id == employee_id).offset(skip).limit(limit).all()

    def get_by_tenant(self, db: Session, *, tenant_id: str, skip: int = 0, limit: int = 100) -> List[Booking]:
        return db.query(Booking).filter(Booking.tenant_id == tenant_id).offset(skip).limit(limit).all()

    def create(self, db: Session, *, obj_in: BookingCreate) -> Booking:
        db_obj = Booking(**obj_in.model_dump())
        db.add(db_obj)
        db.commit()
        db.refresh(db_obj)
        return db_obj

    def update_booking(
        self,
        db: Session,
        *,
        db_obj: Booking,
        obj_in: Union[BookingUpdate, Dict[str, Any]]
    ) -> Booking:
        update_data = obj_in if isinstance(obj_in, dict) else obj_in.model_dump(exclude_unset=True)

        for field, value in update_data.items():
            setattr(db_obj, field, value)

        db.add(db_obj)
        db.commit()
        db.refresh(db_obj)
        return db_obj

    def delete(self, db: Session, *, db_obj: Booking) -> None:
        db.delete(db_obj)
        db.commit()


booking_crud = CRUDBooking(Booking)
