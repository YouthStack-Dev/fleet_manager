from typing import List, Dict, Any, Optional, Union
from sqlalchemy.orm import Session
from sqlalchemy import and_
from app.models.shift import Shift
from app.schemas.shift import ShiftCreate, ShiftUpdate
from app.crud.base import CRUDBase


class CRUDShift(CRUDBase[Shift, ShiftCreate, ShiftUpdate]):
    def get_by_id(self, db: Session, *, shift_id: int) -> Optional[Shift]:
        """Get shift by ID"""
        return db.query(Shift).filter(Shift.shift_id == shift_id).first()

    def get_by_code(self, db: Session, *, tenant_id: str, shift_code: str) -> Optional[Shift]:
        """Get shift by code scoped to tenant"""
        return (
            db.query(Shift)
            .filter(and_(Shift.tenant_id == tenant_id, Shift.shift_code == shift_code))
            .first()
        )

    def create(self, db: Session, *, obj_in: ShiftCreate) -> Shift:
        """Create a new shift"""
        db_obj = Shift(**obj_in.dict())
        db.add(db_obj)
        db.flush()
        return db_obj
    
    def create_with_tenant(self, db: Session, *, obj_in: ShiftCreate, tenant_id: str) -> Shift:
        """Create a shift tied to a tenant"""
        data = obj_in.dict(exclude_unset=True)
        data["tenant_id"] = tenant_id
        db_obj = Shift(**data)
        db.add(db_obj)
        db.flush()
        return db_obj
    
    def update(
        self, db: Session, *, db_obj: Shift, obj_in: Union[ShiftUpdate, Dict[str, Any]]
    ) -> Shift:
        """Update shift"""
        update_data = obj_in if isinstance(obj_in, dict) else obj_in.dict(exclude_unset=True)
        return super().update(db, db_obj=db_obj, obj_in=update_data)

    def get_all(
        self, db: Session, *, tenant_id: str, skip: int = 0, limit: int = 100,
        filters: Optional[Dict[str, Any]] = None
    ) -> List[Shift]:
        """Get all shifts with optional filters"""
        query = db.query(Shift).filter(Shift.tenant_id == tenant_id)

        if filters:
            if filters.get("shift_code"):
                query = query.filter(Shift.shift_code.ilike(f"%{filters['shift_code']}%"))
            if filters.get("log_type"):
                query = query.filter(Shift.log_type == filters["log_type"])
            if filters.get("pickup_type"):
                query = query.filter(Shift.pickup_type == filters["pickup_type"])
            if filters.get("gender"):
                query = query.filter(Shift.gender == filters["gender"])
            if filters.get("is_active") is not None:
                query = query.filter(Shift.is_active == filters["is_active"])

        return query.offset(skip).limit(limit).all()

    def count(self, db: Session, *, tenant_id: str) -> int:
        """Count shifts per tenant"""
        return db.query(Shift).filter(Shift.tenant_id == tenant_id).count()


shift_crud = CRUDShift(Shift)
