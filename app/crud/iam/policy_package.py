"""
CRUD helpers for PolicyPackage — the per-tenant container that groups policies.
"""
from typing import List, Optional
from sqlalchemy.orm import Session

from app.models.iam.policy import Policy, PolicyPackage


class CRUDPolicyPackage:
    # ─── Create ─────────────────────────────────────────────────────────────
    def create(self, db: Session, *, tenant_id: str, name: str, description: Optional[str] = None) -> PolicyPackage:
        obj = PolicyPackage(tenant_id=tenant_id, name=name, description=description)
        db.add(obj)
        db.commit()
        db.refresh(obj)
        return obj

    # ─── Read one ────────────────────────────────────────────────────────────
    def get(self, db: Session, *, package_id: int) -> Optional[PolicyPackage]:
        return db.query(PolicyPackage).filter(PolicyPackage.package_id == package_id).first()

    def get_by_tenant(self, db: Session, *, tenant_id: str) -> Optional[PolicyPackage]:
        """Each tenant has at most one package."""
        return db.query(PolicyPackage).filter(PolicyPackage.tenant_id == tenant_id).first()

    # ─── List ────────────────────────────────────────────────────────────────
    def list(
        self,
        db: Session,
        *,
        tenant_id: Optional[str] = None,
        skip: int = 0,
        limit: int = 100,
    ) -> List[PolicyPackage]:
        q = db.query(PolicyPackage)
        if tenant_id:
            q = q.filter(PolicyPackage.tenant_id == tenant_id)
        return q.offset(skip).limit(limit).all()

    def count(self, db: Session, *, tenant_id: Optional[str] = None) -> int:
        q = db.query(PolicyPackage)
        if tenant_id:
            q = q.filter(PolicyPackage.tenant_id == tenant_id)
        return q.count()

    # ─── Update ──────────────────────────────────────────────────────────────
    def update(
        self,
        db: Session,
        *,
        db_obj: PolicyPackage,
        name: Optional[str] = None,
        description: Optional[str] = None,
        default_policy_id: Optional[int] = None,
    ) -> PolicyPackage:
        if name is not None:
            db_obj.name = name
        if description is not None:
            db_obj.description = description
        if default_policy_id is not None:
            # Validate: the policy must exist AND belong to this package
            policy = db.query(Policy).filter(
                Policy.policy_id == default_policy_id,
                Policy.package_id == db_obj.package_id,
            ).first()
            if not policy:
                from fastapi import HTTPException, status
                from app.utils.response_utils import ResponseWrapper
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=ResponseWrapper.error(
                        f"Policy {default_policy_id} does not exist or does not belong to this package",
                        "INVALID_DEFAULT_POLICY_ID",
                    ),
                )
            db_obj.default_policy_id = default_policy_id
        db.add(db_obj)
        db.commit()
        db.refresh(db_obj)
        return db_obj

    def set_permissions_on_default_policy(
        self,
        db: Session,
        *,
        db_obj: PolicyPackage,
        permission_ids: List[int],
    ) -> PolicyPackage:
        """
        Full replace of the permission set on the package's default policy.
        Raises 400 if no default_policy_id is set.
        Raises 404 if any permission_id is invalid.
        """
        from fastapi import HTTPException, status
        from app.utils.response_utils import ResponseWrapper
        from app.models.iam.permission import Permission

        if not db_obj.default_policy_id:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=ResponseWrapper.error(
                    "Package has no default policy set. Set default_policy_id first.",
                    "NO_DEFAULT_POLICY",
                ),
            )

        default_policy = db.query(Policy).filter(
            Policy.policy_id == db_obj.default_policy_id
        ).first()
        if not default_policy:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=ResponseWrapper.error("Default policy not found", "DEFAULT_POLICY_NOT_FOUND"),
            )

        permissions = db.query(Permission).filter(
            Permission.permission_id.in_(permission_ids)
        ).all()
        found_ids = {p.permission_id for p in permissions}
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

        # Full replace — clear existing, assign new set
        default_policy.permissions = permissions
        db.add(default_policy)
        db.commit()
        db.refresh(db_obj)
        return db_obj

    # ─── Delete ──────────────────────────────────────────────────────────────
    def delete(self, db: Session, *, db_obj: PolicyPackage) -> None:
        db.delete(db_obj)
        db.commit()


policy_package_crud = CRUDPolicyPackage()
