from typing import Optional
from sqlalchemy.orm import Session
from datetime import timedelta
from app.models.cutoff import Cutoff
from app.schemas.cutoff import CutoffCreate, CutoffUpdate
from app.crud.base import CRUDBase

class CRUDCutoff(CRUDBase[Cutoff, CutoffCreate, CutoffUpdate]):

    def _parse_time(self, time_str: str) -> timedelta:
        h, m = map(int, time_str.split(":"))
        return timedelta(hours=h, minutes=m)

    def get_by_tenant(self, db: Session, *, tenant_id: str) -> Optional[Cutoff]:
        return db.query(Cutoff).filter(Cutoff.tenant_id == tenant_id).first()

    def ensure_cutoff(self, db: Session, tenant_id: str) -> Cutoff:
        db_obj = self.get_by_tenant(db, tenant_id=tenant_id)
        if not db_obj:
            db_obj = Cutoff(
                tenant_id=tenant_id,
                booking_login_cutoff=timedelta(0),
                cancel_login_cutoff=timedelta(0),
                booking_logout_cutoff=timedelta(0),
                cancel_logout_cutoff=timedelta(0),
                medical_emergency_booking_cutoff=timedelta(0),
                medical_emergency_cancel_cutoff=timedelta(0),
                adhoc_booking_cutoff=timedelta(0),
                allow_adhoc_booking=False,
                allow_medical_emergency_booking=False,
                allow_medical_emergency_cancel=False
            )
            db.add(db_obj)
            db.flush()
        return db_obj

    def create_with_tenant(self, db: Session, *, obj_in: CutoffCreate) -> Cutoff:
        db_obj = Cutoff(
            tenant_id=obj_in.tenant_id,
            booking_login_cutoff=self._parse_time(obj_in.booking_login_cutoff),
            cancel_login_cutoff=self._parse_time(obj_in.cancel_login_cutoff),
            booking_logout_cutoff=self._parse_time(obj_in.booking_logout_cutoff),
            cancel_logout_cutoff=self._parse_time(obj_in.cancel_logout_cutoff),
            medical_emergency_booking_cutoff=self._parse_time(obj_in.medical_emergency_booking_cutoff),
            medical_emergency_cancel_cutoff=self._parse_time(obj_in.medical_emergency_cancel_cutoff),
            adhoc_booking_cutoff=self._parse_time(obj_in.adhoc_booking_cutoff),
            allow_adhoc_booking=obj_in.allow_adhoc_booking,
            allow_medical_emergency_booking=obj_in.allow_medical_emergency_booking,
            allow_medical_emergency_cancel=obj_in.allow_medical_emergency_cancel
        )
        db.add(db_obj)
        db.flush()
        return db_obj

    def update_by_tenant(self, db: Session, *, tenant_id: str, obj_in: CutoffUpdate) -> Cutoff:
        db_obj = self.ensure_cutoff(db, tenant_id=tenant_id)
        update_data = obj_in.dict(exclude_unset=True)

        # Never allow tenant_id to be updated
        update_data.pop("tenant_id", None)

        # Parse interval fields from HH:MM format to timedelta
        interval_fields = [
            "booking_login_cutoff", "cancel_login_cutoff", "booking_logout_cutoff", "cancel_logout_cutoff",
            "medical_emergency_booking_cutoff", "medical_emergency_cancel_cutoff", "adhoc_booking_cutoff"
        ]
        for field in interval_fields:
            if field in update_data:
                update_data[field] = self._parse_time(update_data[field])

        for field, value in update_data.items():
            setattr(db_obj, field, value)

        db.add(db_obj)
        db.flush()
        return db_obj

cutoff_crud = CRUDCutoff(Cutoff)
