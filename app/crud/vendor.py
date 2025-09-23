from typing import List, Dict, Any, Optional, Union
from sqlalchemy.orm import Session
from sqlalchemy import or_
from app.models.vendor import Vendor
from app.schemas.vendor import VendorCreate, VendorUpdate
from app.crud.base import CRUDBase


class CRUDVendor(CRUDBase[Vendor, VendorCreate, VendorUpdate]):
    def get_by_id(self, db: Session, *, vendor_id: int) -> Optional[Vendor]:
        """Get vendor by unique ID"""
        return db.query(Vendor).filter(Vendor.vendor_id == vendor_id).first()

    def get_by_code(self, db: Session, *, tenant_id: str, vendor_code: str) -> Optional[Vendor]:
        """Get vendor by unique vendor_code within tenant"""
        return (
            db.query(Vendor)
            .filter(Vendor.tenant_id == tenant_id, Vendor.vendor_code == vendor_code)
            .first()
        )

    def get_by_name(self, db: Session, *, tenant_id: str, name: str) -> Optional[Vendor]:
        """Get vendor by name within a tenant"""
        return (
            db.query(Vendor)
            .filter(Vendor.tenant_id == tenant_id, Vendor.name == name)
            .first()
        )

    def create(self, db: Session, *, obj_in: VendorCreate) -> Vendor:
        """Create a vendor"""
        db_obj = Vendor(
            tenant_id=obj_in.tenant_id,
            name=obj_in.name,
            vendor_code=obj_in.vendor_code,
            email=obj_in.email,
            phone=obj_in.phone,
            is_active=obj_in.is_active if obj_in.is_active is not None else True,
        )
        db.add(db_obj)
        db.flush()
        return db_obj

    def update(
        self, db: Session, *, db_obj: Vendor, obj_in: Union[VendorUpdate, Dict[str, Any]]
    ) -> Vendor:
        """Update vendor"""
        update_data = obj_in if isinstance(obj_in, dict) else obj_in.dict(exclude_unset=True)
        return super().update(db, db_obj=db_obj, obj_in=update_data)

    def get_all(self, db: Session, *, tenant_id: str, skip: int = 0, limit: int = 100) -> List[Vendor]:
        """Get all vendors for a tenant"""
        return (
            db.query(Vendor)
            .filter(Vendor.tenant_id == tenant_id)
            .offset(skip)
            .limit(limit)
            .all()
        )

    def count(self, db: Session, *, tenant_id: str) -> int:
        """Count vendors in a tenant"""
        return db.query(Vendor).filter(Vendor.tenant_id == tenant_id).count()

    def search_vendors(
        self, db: Session, *, tenant_id: str, search_term: str, skip: int = 0, limit: int = 100
    ) -> List[Vendor]:
        """Search vendors by name, vendor_code, email, or phone within a tenant"""
        search_pattern = f"%{search_term}%"
        return (
            db.query(Vendor)
            .filter(
                Vendor.tenant_id == tenant_id,
                or_(
                    Vendor.name.ilike(search_pattern),
                    Vendor.vendor_code.ilike(search_pattern),
                    Vendor.email.ilike(search_pattern),
                    Vendor.phone.ilike(search_pattern),
                ),
            )
            .offset(skip)
            .limit(limit)
            .all()
        )

    def toggle_active(self, db: Session, *, vendor_id: int) -> Optional[Vendor]:
        """Toggle vendor active/inactive status"""
        vendor = db.query(Vendor).filter(Vendor.vendor_id == vendor_id).first()
        if vendor:
            vendor.is_active = not vendor.is_active
            db.add(vendor)
            db.flush()
        return vendor


vendor_crud = CRUDVendor(Vendor)
