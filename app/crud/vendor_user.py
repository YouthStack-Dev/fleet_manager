from typing import List, Dict, Any, Optional, Union
from sqlalchemy.orm import Session
from sqlalchemy import or_
from app.models.vendor_user import VendorUser
from app.schemas.vendor_user import VendorUserCreate, VendorUserUpdate
from app.crud.base import CRUDBase
from common_utils.auth.utils import hash_password
from app.models.iam import Role, Policy  # lazy import

class CRUDVendorUser(CRUDBase[VendorUser, VendorUserCreate, VendorUserUpdate]):
    def get_by_email(self, db: Session, *, vendor_id: int, email: str) -> Optional[VendorUser]:
        """Get vendor user by email for a vendor"""
        return db.query(VendorUser).filter(
            VendorUser.vendor_id == vendor_id,
            VendorUser.email == email
        ).first()

    def get_by_phone(self, db: Session, *, vendor_id: int, phone: str) -> Optional[VendorUser]:
        """Get vendor user by phone for a vendor"""
        return db.query(VendorUser).filter(
            VendorUser.vendor_id == vendor_id,
            VendorUser.phone == phone
        ).first()

    def create_with_vendor(self, db: Session, *, obj_in: VendorUserCreate, vendor_id: int) -> VendorUser:
        """Create vendor user for a specific vendor"""
        db_obj = VendorUser(
            vendor_id=vendor_id,
            name=obj_in.name,
            email=obj_in.email,
            phone=obj_in.phone,
            password=hash_password(obj_in.password),
            role_id=obj_in.role_id,
            is_active=obj_in.is_active
        )
        db.add(db_obj)
        db.flush()
        return db_obj

    def update_with_password(
        self, db: Session, *, db_obj: VendorUser, obj_in: Union[VendorUserUpdate, Dict[str, Any]]
    ) -> VendorUser:
        """Update vendor user, hashing password if provided"""
        update_data = obj_in if isinstance(obj_in, dict) else obj_in.dict(exclude_unset=True)
        
        if "password" in update_data and update_data["password"]:
            update_data["password"] = hash_password(update_data["password"])

        return super().update(db, db_obj=db_obj, obj_in=update_data)

    def get_users_by_vendor(
        self, db: Session, *, vendor_id: int, skip: int = 0, limit: int = 100
    ) -> List[VendorUser]:
        """Get all vendor users for a vendor"""
        return db.query(VendorUser).filter(
            VendorUser.vendor_id == vendor_id
        ).offset(skip).limit(limit).all()

    def count_by_vendor(self, db: Session, *, vendor_id: int) -> int:
        """Count vendor users for a vendor"""
        return db.query(VendorUser).filter(
            VendorUser.vendor_id == vendor_id
        ).count()

    def search_users(
        self, db: Session, *, vendor_id: int, search_term: str, skip: int = 0, limit: int = 100
    ) -> List[VendorUser]:
        """Search vendor users by name, email or phone"""
        search_pattern = f"%{search_term}%"
        return db.query(VendorUser).filter(
            VendorUser.vendor_id == vendor_id,
            or_(
                VendorUser.name.ilike(search_pattern),
                VendorUser.email.ilike(search_pattern),
                VendorUser.phone.ilike(search_pattern)
            )
        ).offset(skip).limit(limit).all()

    def get_roles_and_permissions(
        self, db: Session, *, vendor_user_id: int, vendor_id: int
    ):
        vendor_user = db.query(VendorUser).filter(
            VendorUser.vendor_user_id == vendor_user_id,
            VendorUser.vendor_id == vendor_id,
            VendorUser.is_active == True
        ).first()

        if not vendor_user:
            return None, [], []

        # --- Expect exactly one role_id ---
        if not getattr(vendor_user, "role_id", None):
            return vendor_user, [], []

        role = db.query(Role).filter(
            Role.role_id == vendor_user.role_id,
            Role.is_active == True
        ).first()

        if not role:
            return vendor_user, [], []

        roles = [role.name]
        all_permissions = []

        # Fetch permissions via policies
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

        return vendor_user, roles, all_permissions



vendor_user_crud = CRUDVendorUser(VendorUser)
