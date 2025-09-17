from typing import List, Dict, Any, Optional, Union
from sqlalchemy.orm import Session
from sqlalchemy import or_, and_
from app.models import Employee
from app.schemas.employee import EmployeeCreate, EmployeeUpdate
from app.crud.base import CRUDBase
from common_utils.auth.utils import hash_password

class CRUDEmployee(CRUDBase[Employee, EmployeeCreate, EmployeeUpdate]):
    def get_by_email(self, db: Session, *, email: str) -> Optional[Employee]:
        """Get employee by email"""
        return db.query(Employee).filter(Employee.email == email).first()
    
    def get_by_employee_code(self, db: Session, *, employee_code: str, tenant_id: int) -> Optional[Employee]:
        """Get employee by employee code within a specific tenant"""
        return db.query(Employee).filter(
            Employee.employee_code == employee_code,
            Employee.tenant_id == tenant_id
        ).first()
    
    def create_with_tenant(self, db: Session, *, obj_in: EmployeeCreate, tenant_id: int) -> Employee:
        """Create employee for a specific tenant"""
        db_obj = Employee(
            tenant_id=tenant_id,
            name=obj_in.name,
            employee_code=obj_in.employee_code,
            email=obj_in.email,
            password=hash_password(obj_in.password),
            team_id=obj_in.team_id,
            phone=obj_in.phone,
            alternate_phone=obj_in.alternate_phone,
            special_needs=obj_in.special_needs,
            special_needs_start_date=obj_in.special_needs_start_date,
            special_needs_end_date=obj_in.special_needs_end_date,
            address=obj_in.address,
            latitude=obj_in.latitude,
            longitude=obj_in.longitude,
            gender=obj_in.gender,
            is_active=obj_in.is_active
        )
        db.add(db_obj)
        db.commit()
        db.refresh(db_obj)
        return db_obj
    
    def update_with_password(
        self, db: Session, *, db_obj: Employee, obj_in: Union[EmployeeUpdate, Dict[str, Any]]
    ) -> Employee:
        """Update employee, hashing the password if it's provided"""
        update_data = obj_in if isinstance(obj_in, dict) else obj_in.dict(exclude_unset=True)
        
        if "password" in update_data and update_data["password"]:
            update_data["password"] = hash_password(update_data["password"])
        
        return super().update(db, db_obj=db_obj, obj_in=update_data)
    
    def get_employees_by_tenant(
        self, db: Session, *, tenant_id: int, skip: int = 0, limit: int = 100
    ) -> List[Employee]:
        """Get all employees for a specific tenant"""
        return db.query(Employee).filter(
            Employee.tenant_id == tenant_id
        ).offset(skip).limit(limit).all()
    
    def count_by_tenant(self, db: Session, *, tenant_id: int) -> int:
        """Count employees in a specific tenant"""
        return db.query(Employee).filter(Employee.tenant_id == tenant_id).count()
    
    def search_employees(
        self, db: Session, *, tenant_id: int, search_term: str, skip: int = 0, limit: int = 100
    ) -> List[Employee]:
        """Search employees by name, email or employee code"""
        search_pattern = f"%{search_term}%"
        return db.query(Employee).filter(
            Employee.tenant_id == tenant_id,
            or_(
                Employee.name.ilike(search_pattern),
                Employee.email.ilike(search_pattern),
                Employee.employee_code.ilike(search_pattern)
            )
        ).offset(skip).limit(limit).all()

employee_crud = CRUDEmployee(Employee)
