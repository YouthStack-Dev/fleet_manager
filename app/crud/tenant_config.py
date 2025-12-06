from typing import Optional
from sqlalchemy.orm import Session
from app.models.tenant_config import TenantConfig
from app.schemas.tenant_config import TenantConfigCreate, TenantConfigUpdate
from app.crud.base import CRUDBase

class CRUDTenantConfig(CRUDBase[TenantConfig, TenantConfigCreate, TenantConfigUpdate]):

    def get_by_tenant(self, db: Session, *, tenant_id: str) -> Optional[TenantConfig]:
        """Get tenant config by tenant ID"""
        return db.query(TenantConfig).filter(TenantConfig.tenant_id == tenant_id).first()

    def ensure_config(self, db: Session, tenant_id: str) -> TenantConfig:
        """Ensure tenant config exists, create if not"""
        db_obj = self.get_by_tenant(db, tenant_id=tenant_id)
        if not db_obj:
            db_obj = TenantConfig(
                tenant_id=tenant_id,
                escort_required_for_women=True,  # Default value
                login_boarding_otp=True,         # Default OTP settings
                login_deboarding_otp=True,
                logout_boarding_otp=True,
                logout_deboarding_otp=True
            )
            db.add(db_obj)
            db.flush()
        return db_obj

    def create_with_tenant(self, db: Session, *, obj_in: TenantConfigCreate) -> TenantConfig:
        """Create tenant config for a tenant"""
        db_obj = TenantConfig(
            tenant_id=obj_in.tenant_id,
            escort_required_start_time=obj_in.escort_required_start_time,
            escort_required_end_time=obj_in.escort_required_end_time,
            escort_required_for_women=obj_in.escort_required_for_women,
            login_boarding_otp=obj_in.login_boarding_otp,
            login_deboarding_otp=obj_in.login_deboarding_otp,
            logout_boarding_otp=obj_in.logout_boarding_otp,
            logout_deboarding_otp=obj_in.logout_deboarding_otp
        )
        db.add(db_obj)
        db.commit()
        db.refresh(db_obj)
        return db_obj

    def update_by_tenant(self, db: Session, *, tenant_id: str, obj_in: TenantConfigUpdate) -> TenantConfig:
        """Update tenant config by tenant ID"""
        db_obj = self.ensure_config(db, tenant_id=tenant_id)
        update_data = obj_in.dict(exclude_unset=True)

        for field, value in update_data.items():
            setattr(db_obj, field, value)

        db.commit()
        db.refresh(db_obj)
        return db_obj

tenant_config_crud = CRUDTenantConfig(TenantConfig)