from typing import List, Dict, Any, Optional, Union
from sqlalchemy.orm import Session
from sqlalchemy import or_
from app.models import Admin
from app.schemas.admin import AdminCreate, AdminUpdate
from app.crud.base import CRUDBase
from common_utils.auth.utils import hash_password


class CRUDAdmin(CRUDBase[Admin, AdminCreate, AdminUpdate]):
    def get_by_email(self, db: Session, *, email: str) -> Optional[Admin]:
        """Get admin by email (global scope)"""
        return db.query(Admin).filter(Admin.email == email).first()
    
    def get_by_phone(self, db: Session, *, phone: str) -> Optional[Admin]:
        """Get admin by phone (global scope)"""
        return db.query(Admin).filter(Admin.phone == phone).first()

    def create(self, db: Session, *, obj_in: AdminCreate) -> Admin:
        """Create admin user (system level, no tenant)"""
        db_obj = Admin(
            name=obj_in.name,
            email=obj_in.email,
            phone=obj_in.phone,
            password=hash_password(obj_in.password),
            is_active=obj_in.is_active,
        )
        db.add(db_obj)
        db.commit()
        db.refresh(db_obj)
        return db_obj

    def update_with_password(
        self, db: Session, *, db_obj: Admin, obj_in: Union[AdminUpdate, Dict[str, Any]]
    ) -> Admin:
        """Update admin, hashing password if provided"""
        update_data = obj_in if isinstance(obj_in, dict) else obj_in.dict(exclude_unset=True)

        if "password" in update_data and update_data["password"]:
            update_data["password"] = hash_password(update_data["password"])

        return super().update(db, db_obj=db_obj, obj_in=update_data)

    def get_all(self, db: Session, *, skip: int = 0, limit: int = 100) -> List[Admin]:
        """Get all admins (system level)"""
        return db.query(Admin).offset(skip).limit(limit).all()

    def count(self, db: Session) -> int:
        """Count all admins"""
        return db.query(Admin).count()

    def search_admins(
        self, db: Session, *, search_term: str, skip: int = 0, limit: int = 100
    ) -> List[Admin]:
        """Search admins by name, email, or phone"""
        search_pattern = f"%{search_term}%"
        return db.query(Admin).filter(
            or_(
                Admin.name.ilike(search_pattern),
                Admin.email.ilike(search_pattern),
                Admin.phone.ilike(search_pattern),
            )
        ).offset(skip).limit(limit).all()

    def get_admin_roles_and_permissions(self, db: Session, *, admin_id: int):
        """Get admin with their roles and permissions (global, no tenant restriction)"""
        from app.models.iam import Role, Policy  # avoid circular imports

        admin = db.query(Admin).filter(
            Admin.admin_id == admin_id,
            Admin.is_active == True
        ).first()

        if not admin:
            return None, [], []

        roles = []
        all_permissions = []

        # multiple roles or single role
        if hasattr(admin, "roles") and admin.roles:
            try:
                role_list = list(admin.roles) if admin.roles else []
            except TypeError:
                role_list = [admin.roles] if admin.roles else []
        elif hasattr(admin, "role") and admin.role:
            role_list = [admin.role]
        else:
            role_list = []

        for role in role_list:
            if role and role.is_active:  # no tenant restriction here
                roles.append(role.name)

                # get permissions from role policies
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

        return admin, roles, all_permissions


admin_crud = CRUDAdmin(Admin)
