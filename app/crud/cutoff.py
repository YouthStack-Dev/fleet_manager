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
                booking_cutoff=timedelta(0),
                cancel_cutoff=timedelta(0)
            )
            db.add(db_obj)
            db.flush()
        return db_obj

    def create_with_tenant(self, db: Session, *, obj_in: CutoffCreate) -> Cutoff:
        db_obj = Cutoff(
            tenant_id=obj_in.tenant_id,
            booking_cutoff=self._parse_time(obj_in.booking_cutoff),
            cancel_cutoff=self._parse_time(obj_in.cancel_cutoff)
        )
        db.add(db_obj)
        db.flush()
        return db_obj

    def update_by_tenant(self, db: Session, *, tenant_id: str, obj_in: CutoffUpdate) -> Cutoff:
        db_obj = self.ensure_cutoff(db, tenant_id=tenant_id)
        update_data = obj_in.dict(exclude_unset=True)
        if "booking_cutoff" in update_data:
            update_data["booking_cutoff"] = self._parse_time(update_data["booking_cutoff"])
        if "cancel_cutoff" in update_data:
            update_data["cancel_cutoff"] = self._parse_time(update_data["cancel_cutoff"])
        for field, value in update_data.items():
            setattr(db_obj, field, value)
        db.add(db_obj)
        db.flush()
        return db_obj

cutoff_crud = CRUDCutoff(Cutoff)
