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
    
    def get_by_employee_code(self, db: Session, *, employee_code: str, tenant_id: str) -> Optional[Employee]:
        """Get employee by employee code within a specific tenant"""
        return db.query(Employee).filter(
            Employee.employee_code == employee_code,
            Employee.tenant_id == tenant_id
        ).first()
    
    def create_with_tenant(self, db: Session, *, obj_in: EmployeeCreate, tenant_id: str) -> Employee:
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
        self, db: Session, *, tenant_id: str, skip: int = 0, limit: int = 100
    ) -> List[Employee]:
        """Get all employees for a specific tenant"""
        return db.query(Employee).filter(
            Employee.tenant_id == tenant_id
        ).offset(skip).limit(limit).all()
    
    def count_by_tenant(self, db: Session, *, tenant_id: str) -> int:
        """Count employees in a specific tenant"""
        return db.query(Employee).filter(Employee.tenant_id == tenant_id).count()
    
    def search_employees(
        self, db: Session, *, tenant_id: str, search_term: str, skip: int = 0, limit: int = 100
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
    
    def get_employee_roles_and_permissions(self, db: Session, *, employee_id: int, tenant_id: str):
        """Get employee with their roles and permissions for a specific tenant"""
        from app.models.iam import Role, Policy  # Import here to avoid circular imports
        
        employee = db.query(Employee).filter(
            Employee.employee_id == employee_id,
            Employee.tenant_id == tenant_id,
            Employee.is_active == True
        ).first()
        
        if not employee:
            return None, [], []
        
        # Get roles - handle both single role and multiple roles cases
        roles = []
        all_permissions = []
        
        # Check if employee has a single role or multiple roles
        if hasattr(employee, 'roles') and employee.roles:
            # Multiple roles case - if roles is a collection
            try:
                role_list = list(employee.roles) if employee.roles else []
            except TypeError:
                # Single role case - if roles is a single Role object
                role_list = [employee.roles] if employee.roles else []
        elif hasattr(employee, 'role') and employee.role:
            # Single role relationship
            role_list = [employee.role]
        else:
            role_list = []
        
        for role in role_list:
            if role and role.is_active and (role.tenant_id == tenant_id or role.is_system_role):
                roles.append(role.name)
                
                # Get permissions from role policies
                for policy in role.policies:
                    for permission in policy.permissions:
                        module, action = permission.module, permission.action
                        existing = next((p for p in all_permissions if p["module"] == module), None)
                        if existing:
                            if action == "*":
                                existing["action"] = ["create", "read", "update", "delete", "*"]
                            elif action not in existing["action"]:
                                existing["action"].append(action)
                        else:
                            actions = (
                                ["create", "read", "update", "delete", "*"]
                                if action == "*"
                                else [action]
                            )
                            all_permissions.append({"module": module, "action": actions})
        
        return employee, roles, all_permissions

employee_crud = CRUDEmployee(Employee)
