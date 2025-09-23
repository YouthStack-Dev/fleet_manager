from app.core.logging_config import get_logger
from typing import List, Dict, Any, Optional, Union
from sqlalchemy.orm import Session
from sqlalchemy import or_
from app.models import Tenant
from app.schemas.tenant import TenantCreate, TenantUpdate
from app.crud.base import CRUDBase

logger = get_logger(__name__)

class CRUDTenant(CRUDBase[Tenant, TenantCreate, TenantUpdate]):
    def get_by_id(self, db: Session, *, tenant_id: str) -> Optional[Tenant]:
        """Get tenant by unique ID"""
        logger.debug(f"Fetching tenant by ID: {tenant_id}")
        result = db.query(Tenant).filter(Tenant.tenant_id == tenant_id).first()
        logger.debug(f"get_by_id({tenant_id}) returned: {vars(result) if result else None}")
        return result

    def get_by_name(self, db: Session, *, name: str) -> Optional[Tenant]:
        """Get tenant by unique name"""
        result = db.query(Tenant).filter(Tenant.name == name).first()
        logger.debug(f"get_by_name({name}) returned: {result}")
        return result

    def create(self, db: Session, *, obj_in: TenantCreate) -> Tenant:
        """Create a tenant"""
        db_obj = Tenant(
            tenant_id=obj_in.tenant_id,
            name=obj_in.name,
            is_active=obj_in.is_active,
        )
        db.add(db_obj)
        db.flush()
        return db_obj

    def update(
        self, db: Session, *, db_obj: Tenant, obj_in: Union[TenantUpdate, Dict[str, Any]]
    ) -> Tenant:
        """Update tenant"""
        update_data = obj_in if isinstance(obj_in, dict) else obj_in.dict(exclude_unset=True)
        return super().update(db, db_obj=db_obj, obj_in=update_data)

    def get_all(self, db: Session, *, skip: int = 0, limit: int = 100) -> List[Tenant]:
        """Get all tenants"""
        return db.query(Tenant).offset(skip).limit(limit).all()

    def count(self, db: Session) -> int:
        """Count tenants"""
        return db.query(Tenant).count()

    def search_tenants(
        self, db: Session, *, search_term: str, skip: int = 0, limit: int = 100
    ) -> List[Tenant]:
        """Search tenants by name or tenant_id"""
        search_pattern = f"%{search_term}%"
        return db.query(Tenant).filter(
            or_(
                Tenant.name.ilike(search_pattern),
                Tenant.tenant_id.ilike(search_pattern)
            )
        ).offset(skip).limit(limit).all()

    def get_tenant_roles_and_permissions(self, db: Session, *, tenant_id: str):
        """Get tenant with their roles and permissions"""
        from app.models.iam import Role, Policy  # avoid circular imports

        tenant = db.query(Tenant).filter(
            Tenant.tenant_id == tenant_id,
            Tenant.is_active == True
        ).first()

        if not tenant:
            return None, [], []

        roles = []
        all_permissions = []

        # If tenant has roles (e.g., Admin, SubAdmin etc.)
        role_list = getattr(tenant, "roles", [])

        for role in role_list:
            if role and role.is_active:
                roles.append(role.name)

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

        return tenant, roles, all_permissions


tenant_crud = CRUDTenant(Tenant)
