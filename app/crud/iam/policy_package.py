"""
CRUD helpers for PolicyPackage.
Permissions stored as JSON array directly in iam_policy_packages table.
"""
from typing import List, Optional
from sqlalchemy.orm import Session

from app.models.iam.policy import PolicyPackage
from app.models.iam.permission import Permission


class CRUDPolicyPackage:
    def create(self, db, *, tenant_id, name, description=None, permission_ids=None):
        obj = PolicyPackage(
            tenant_id=tenant_id,
            name=name,
            description=description,
            permission_ids=permission_ids or [],
        )
        db.add(obj)
        db.commit()
        db.refresh(obj)
        return obj

    def get(self, db, *, package_id):
        return db.query(PolicyPackage).filter(PolicyPackage.package_id == package_id).first()

    def get_by_tenant(self, db, *, tenant_id):
        return db.query(PolicyPackage).filter(PolicyPackage.tenant_id == tenant_id).first()

    def get_permissions(self, db, *, db_obj):
        if not db_obj.permission_ids:
            return []
        return db.query(Permission).filter(
            Permission.permission_id.in_(db_obj.permission_ids)
        ).all()

    def set_permissions(self, db, *, db_obj, permission_ids):
        from fastapi import HTTPException, status
        from app.utils.response_utils import ResponseWrapper
        if permission_ids:
            found = db.query(Permission.permission_id).filter(
                Permission.permission_id.in_(permission_ids)
            ).all()
            found_ids = {row.permission_id for row in found}
            missing = set(permission_ids) - found_ids
            if missing:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail=ResponseWrapper.error(
                        "Some permission IDs are invalid",
                        "INVALID_PERMISSION_IDS",
                        details={"invalid_ids": list(missing)},
                    ),
                )
        db_obj.permission_ids = permission_ids
        db.add(db_obj)
        db.commit()
        db.refresh(db_obj)
        return db_obj

    def update(self, db, *, db_obj, name=None, description=None):
        if name is not None:
            db_obj.name = name
        if description is not None:
            db_obj.description = description
        db.add(db_obj)
        db.commit()
        db.refresh(db_obj)
        return db_obj


policy_package_crud = CRUDPolicyPackage()
