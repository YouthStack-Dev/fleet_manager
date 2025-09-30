from typing import Optional, List, Dict, Any, Union
from sqlalchemy.orm import Session, joinedload
from sqlalchemy.exc import IntegrityError

from app.models.weekoff_config import WeekoffConfig
from app.models import Employee
from app.schemas.weekoff_config import WeekoffConfigCreate, WeekoffConfigUpdate
from app.crud.base import CRUDBase


class CRUDWeekoff(CRUDBase[WeekoffConfig, WeekoffConfigCreate, WeekoffConfigUpdate]):
    def get_by_employee(self, db: Session, *, employee_id: int) -> Optional[WeekoffConfig]:
        """Fetch weekoff config for a specific employee"""
        return (
            db.query(WeekoffConfig)
            .options(joinedload(WeekoffConfig.employee))
            .filter(WeekoffConfig.employee_id == employee_id)
            .first()
        )

    def create_or_update(
        self,
        db: Session,
        *,
        employee_id: int,
        obj_in: Union[WeekoffConfigCreate, Dict[str, Any]]
    ) -> WeekoffConfig:
        """
        Create or update weekoff config for an employee.
        Enforces one config per employee.
        """
        update_data = obj_in if isinstance(obj_in, dict) else obj_in.dict(exclude_unset=True)

        db_obj = self.get_by_employee(db, employee_id=employee_id)
        if db_obj:
            # update existing
            for field, value in update_data.items():
                setattr(db_obj, field, value)
        else:
            # create new
            db_obj = WeekoffConfig(employee_id=employee_id, **update_data)
            db.add(db_obj)

        try:
            db.flush()
        except IntegrityError as e:
            db.rollback()
            raise ValueError(f"Weekoff config failed for employee {employee_id}: {e.orig}")
        return db_obj

    def get_by_tenant(
        self, db: Session, *, tenant_id: str, skip: int = 0, limit: int = 100
    ) -> List[WeekoffConfig]:
        """Fetch all weekoff configs belonging to a tenant (via employees)"""
        return (
            db.query(WeekoffConfig)
            .join(Employee, Employee.employee_id == WeekoffConfig.employee_id)
            .filter(Employee.tenant_id == tenant_id)
            .offset(skip)
            .limit(limit)
            .all()
        )

    def delete_by_employee(self, db: Session, *, employee_id: int) -> bool:
        """Delete weekoff config for an employee"""
        db_obj = self.get_by_employee(db, employee_id=employee_id)
        if not db_obj:
            return False
        db.delete(db_obj)
        db.flush()
        return True


weekoff_crud = CRUDWeekoff(WeekoffConfig)
