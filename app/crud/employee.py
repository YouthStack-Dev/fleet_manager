from typing import List, Dict, Any, Optional, Union
from sqlalchemy.orm import Session, joinedload, subqueryload
from sqlalchemy import or_, and_
from app.models import Employee
from app.models.iam.role import Role
from app.models.team import Team
from app.schemas.employee import EmployeeCreate, EmployeeUpdate
from app.crud.base import CRUDBase
from common_utils.auth.utils import hash_password
from app.crud.weekoff import weekoff_crud
from app.utils.cache_manager import (
    get_cached_permissions,
    cache_permissions,
)

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
    
    def create_with_tenant(self, db: Session, *, obj_in: EmployeeCreate, role_id: Optional[int] = None, tenant_id: str) -> Employee:
        """Create employee for a specific tenant"""
        role_id = role_id or self.get_system_role_id(db, role_name="Employee")
        if role_id is None:
            raise ValueError("System role 'Employee' not found in DB")
        db_obj = Employee(
            tenant_id=tenant_id,
            name=obj_in.name,
            role_id=role_id,
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
        db.flush()
        weekoff_crud.ensure_weekoff_config(
            db,
            employee_id=db_obj.employee_id,
        )
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
        """
        Get employee with their effective roles and permissions.

        Permission resolution rules
        ───────────────────────────
        1. Load the tenant's PolicyPackage → build a set of allowed permission_ids.
        2. Tenant role   → only permissions present in the tenant's package are granted.
        3. System role   → only permissions that are in BOTH the system policy AND the
                           tenant's package (intersection) are granted.
        4. No package    → fall back to legacy behaviour (all role permissions granted)
                           so existing tenants without a package are not broken.

        Result is cached in Redis for 5 minutes (PERMISSIONS_TTL).
        """
        from app.models.iam import Role, Policy
        from app.models.iam.policy import PolicyPackage

        # ── 1. Check cache (returns None on miss or when Redis is unavailable) ──
        cached = get_cached_permissions(employee_id, tenant_id)
        if cached is not None:
            return None, cached["roles"], cached["permissions"]

        # ── 2. Fetch employee + role + policies + permissions in 3 queries ──
        # joinedload(Employee.role)    → single JOIN (employee has exactly one FK role)
        # subqueryload(Role.policies)  → 1 subquery for all policies of that role
        # subqueryload(Policy.permissions) → 1 subquery for all permissions of those policies
        employee = (
            db.query(Employee)
            .options(
                joinedload(Employee.role)
                .subqueryload(Role.policies)
                .subqueryload(Policy.permissions)
            )
            .filter(
                Employee.employee_id == employee_id,
                Employee.tenant_id == tenant_id,
                Employee.is_active == True
            )
            .first()
        )

        if not employee:
            return None, [], []

        # ── Build the allowed permission_id set from the tenant's PackagePolicy ──
        package = db.query(PolicyPackage).filter_by(tenant_id=tenant_id).first()
        allowed_permission_ids: set | None = None   # None = no package → no filtering
        if package:
            allowed_permission_ids = set(package.permission_ids or [])

        # ── Collect roles ──────────────────────────────────────────────────────
        if hasattr(employee, 'roles') and employee.roles:
            try:
                role_list = list(employee.roles)
            except TypeError:
                role_list = [employee.roles]
        elif hasattr(employee, 'role') and employee.role:
            role_list = [employee.role]
        else:
            role_list = []

        roles: list[str] = []
        # module → {"module": str, "action": list[str]}  — O(1) lookup by module name
        permissions_by_module: dict[str, dict] = {}

        for role in role_list:
            if not role or not role.is_active:
                continue
            if role.tenant_id != tenant_id and not role.is_system_role:
                continue   # ignore roles from other tenants

            roles.append(role.name)

            for policy in (role.policies or []):
                for permission in (policy.permissions or []):
                    # ── Package intersection filter ────────────────────────
                    if allowed_permission_ids is not None:
                        if permission.permission_id not in allowed_permission_ids:
                            # Permission not in tenant package → skip
                            continue

                    module, action = permission.module, permission.action
                    entry = permissions_by_module.get(module)
                    if entry:
                        if action == "*":
                            entry["action"] = ["create", "read", "update", "delete", "*"]
                        elif action not in entry["action"]:
                            entry["action"].append(action)
                    else:
                        actions = (
                            ["create", "read", "update", "delete", "*"]
                            if action == "*"
                            else [action]
                        )
                        permissions_by_module[module] = {"module": module, "action": actions}

        all_permissions = list(permissions_by_module.values())

        # ── 3. Populate cache ────────────────────────────────────────────────
        cache_permissions(employee_id, tenant_id, {"roles": roles, "permissions": all_permissions})

        return employee, roles, all_permissions

    def is_employee_team_inactive(self, db: Session, employee_id: int) -> bool:
        """
        Single-query version: join Employee → Team and check if team is inactive.
        """
        inactive_team_exists = (
            db.query(Team)
            .join(Employee, Employee.team_id == Team.team_id)
            .filter(Employee.employee_id == employee_id, Team.is_active == False)
            .first()
        )
        return inactive_team_exists is not None
    def get_system_role_id(self, db: Session, *, role_name: str) -> Optional[int]:
        """
        Fetch the role_id of a system role by its name.
        Returns None if role not found.
        """
        role = db.query(Role).filter(
            Role.name == role_name,
            Role.is_system_role == True
        ).first()
        return role.role_id if role else None

employee_crud = CRUDEmployee(Employee)
