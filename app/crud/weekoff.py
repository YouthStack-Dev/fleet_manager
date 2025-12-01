from fastapi import HTTPException, status
from typing import Optional, List, Dict, Any, Union
from app.utils.response_utils import ResponseWrapper
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

    def ensure_weekoff_config(self, db: Session, employee_id: int) -> WeekoffConfig:
        """Ensure employee always has a weekoff config (default Sunday=True)."""

        employee = db.query(Employee).filter(Employee.employee_id == employee_id).first()
        if not employee:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=ResponseWrapper.error(
                    message=f"Employee with ID {employee_id} does not exist",
                    error_code="EMPLOYEE_NOT_FOUND",
                )
            )
        db_obj = self.get_by_employee(db, employee_id=employee_id)
        if not db_obj:
            db_obj = WeekoffConfig(
                employee_id=employee_id,
                sunday=True,
                monday=False,
                tuesday=False,
                wednesday=False,
                thursday=False,
                friday=False,
                saturday=False,
            )
            db.add(db_obj)
            db.flush()
        return db_obj

    def update_by_employee(
        self, db: Session, *, employee_id: int, obj_in: Union[WeekoffConfigUpdate, Dict[str, Any]]
    ) -> WeekoffConfig:
        db_obj = self.ensure_weekoff_config(db, employee_id=employee_id)
        update_data = obj_in if isinstance(obj_in, dict) else obj_in.model_dump(exclude_unset=True)
        for field, value in update_data.items():
            setattr(db_obj, field, value)
        db.flush()
        return db_obj

    def update_by_team(
        self, db: Session, *, team_id: int, obj_in: Union[WeekoffConfigUpdate, Dict[str, Any]]
    ) -> List[WeekoffConfig]:
        employees = db.query(Employee).filter(Employee.team_id == team_id).all()
        if not employees:
            return []

        update_data = obj_in if isinstance(obj_in, dict) else obj_in.model_dump(exclude_unset=True)
        results = []
        for emp in employees:
            db_obj = self.ensure_weekoff_config(db, employee_id=emp.employee_id)
            for field, value in update_data.items():
                setattr(db_obj, field, value)
            results.append(db_obj)
        db.flush()
        return results

    def update_by_tenant(
        self, db: Session, *, tenant_id: str, obj_in: Union[WeekoffConfigUpdate, Dict[str, Any]]
    ) -> List[WeekoffConfig]:
        employees = db.query(Employee).filter(Employee.tenant_id == tenant_id).all()
        if not employees:
            return []

        update_data = obj_in if isinstance(obj_in, dict) else obj_in.model_dump(exclude_unset=True)
        results = []
        for emp in employees:
            db_obj = self.ensure_weekoff_config(db, employee_id=emp.employee_id)
            for field, value in update_data.items():
                setattr(db_obj, field, value)
            results.append(db_obj)
        db.flush()
        return results

    def get_by_team(self, db: Session, *, team_id: int) -> List[WeekoffConfig]:
        return (
            db.query(WeekoffConfig)
            .join(Employee, Employee.employee_id == WeekoffConfig.employee_id)
            .filter(Employee.team_id == team_id)
            .all()
        )

    def get_by_tenant(self, db: Session, *, tenant_id: str) -> List[WeekoffConfig]:
        return (
            db.query(WeekoffConfig)
            .join(Employee, Employee.employee_id == WeekoffConfig.employee_id)
            .filter(Employee.tenant_id == tenant_id)
            .all()
        )
    def update_by_team(self, db: Session, team_id: int, obj_in: WeekoffConfigUpdate) -> List[WeekoffConfig]:
        """
        Bulk update weekoff configs for all employees in a team.
        Ensures missing configs are auto-created.
        """
        employees = db.query(Employee).filter(Employee.team_id == team_id).all()
        if not employees:
            return []

        updated_configs = []

        for emp in employees:
            # ensure config exists
            config = (
                db.query(WeekoffConfig)
                .filter(WeekoffConfig.employee_id == emp.employee_id)
                .first()
            )
            if not config:
                config = WeekoffConfig(employee_id=emp.employee_id)
                db.add(config)
                db.flush()

            # apply updates
            for field, value in obj_in.model_dump(exclude_unset=True).items():
                setattr(config, field, value)

            updated_configs.append(config)

        return updated_configs

weekoff_crud = CRUDWeekoff(WeekoffConfig)
