"""
Policy Package Router
=====================
The PolicyPackage is the **super-admin-managed permission boundary** for a tenant.
Permissions are stored directly on the package — completely separate from iam_policies,
which are for tenant-managed role policies.

Endpoints (only 2 — creation happens automatically during tenant creation)
──────────
  GET  /iam/policy-packages/                         → get the package for a tenant
  PUT  /iam/policy-packages/{id}/permissions          → replace the full permission set (super-admin only)

Access rules
────────────
  GET: admin (query ?tenant_id=), employee/vendor (own tenant from token)
  PUT: admin only
"""

from __future__ import annotations

from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.core.logging_config import get_logger
from app.crud.iam.policy_package import policy_package_crud
from app.database.session import get_db
from app.utils.response_utils import ResponseWrapper
from common_utils.auth.permission_checker import PermissionChecker

logger = get_logger(__name__)

router = APIRouter(prefix="/policy-packages", tags=["IAM Policy Packages"])


# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────

def _serialize(pkg, db: Session = None) -> dict:
    """Serialize a PolicyPackage. Pass db to expand permission_ids into full objects."""
    perm_ids = pkg.permission_ids or []
    permissions_detail = []
    if db and perm_ids:
        from app.models.iam.permission import Permission
        perms = db.query(Permission).filter(Permission.permission_id.in_(perm_ids)).all()
        permissions_detail = [
            {"permission_id": p.permission_id, "module": p.module, "action": p.action, "description": p.description}
            for p in perms
        ]
    return {
        "package_id": pkg.package_id,
        "tenant_id": pkg.tenant_id,
        "name": pkg.name,
        "description": pkg.description,
        "created_at": pkg.created_at,
        "updated_at": pkg.updated_at,
        "permission_count": len(perm_ids),
        "permission_ids": perm_ids,
        "permissions": permissions_detail,
    }


def _get_package_or_404(db: Session, package_id: int):
    pkg = policy_package_crud.get(db=db, package_id=package_id)
    if not pkg:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=ResponseWrapper.error(
                f"Policy package {package_id} not found", "PACKAGE_NOT_FOUND"
            ),
        )
    return pkg


# ─────────────────────────────────────────────────────────────────────────────
# GET /iam/policy-packages/  — Get tenant's package
# ─────────────────────────────────────────────────────────────────────────────

@router.get("/", status_code=status.HTTP_200_OK)
async def get_policy_package(
    tenant_id: Optional[str] = Query(None, description="Tenant ID (admin only — ignored for employee/vendor)"),
    db: Session = Depends(get_db),
    user_data=Depends(PermissionChecker(["policy-package.read"], check_tenant=True)),
):
    """
    Get the policy package (permission boundary) for a tenant.

    - **Admin**: pass `?tenant_id=` to query any tenant's package.
    - **Employee / Vendor**: always returns their own tenant's package (query param ignored).
    """
    user_type = user_data.get("user_type")

    if user_type in ("employee", "vendor"):
        effective_tenant_id = user_data.get("tenant_id")
        if not effective_tenant_id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=ResponseWrapper.error("Tenant ID missing in token", "TENANT_ID_MISSING"),
            )
    elif user_type == "admin":
        if not tenant_id:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=ResponseWrapper.error(
                    "Admin must supply ?tenant_id= query parameter", "TENANT_ID_REQUIRED"
                ),
            )
        effective_tenant_id = tenant_id
    else:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=ResponseWrapper.error("Unauthorized user type", "UNAUTHORIZED_USER_TYPE"),
        )

    pkg = policy_package_crud.get_by_tenant(db=db, tenant_id=effective_tenant_id)
    if not pkg:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=ResponseWrapper.error(
                f"No policy package found for tenant '{effective_tenant_id}'",
                "PACKAGE_NOT_FOUND",
            ),
        )

    return ResponseWrapper.success(data=_serialize(pkg, db), message="Policy package fetched successfully")


# ─────────────────────────────────────────────────────────────────────────────
# PUT /iam/policy-packages/{package_id}/permissions  — Replace permission set
# ─────────────────────────────────────────────────────────────────────────────

class PackagePermissionsBody(BaseModel):
    permission_ids: List[int]

    model_config = {
        "json_schema_extra": {
            "example": {"permission_ids": [1, 2, 3, 4]}
        }
    }


@router.put("/{package_id}/permissions", status_code=status.HTTP_200_OK)
async def update_package_permissions(
    package_id: int,
    payload: PackagePermissionsBody,
    db: Session = Depends(get_db),
    user_data=Depends(PermissionChecker(["policy-package.update"], check_tenant=True)),
):
    """
    **Replace** the full permission set on a tenant's policy package. Super-admin only.

    This is a **full replace** — whatever you send becomes the complete set.
    Any permission not in the list is removed.

    All `permission_ids` must exist in `iam_permissions`.
    """
    if user_data.get("user_type") != "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=ResponseWrapper.error(
                "Only super-admin can update the company permission boundary.",
                "FORBIDDEN",
            ),
        )

    pkg = _get_package_or_404(db, package_id)

    old_count = len(pkg.permission_ids or [])
    pkg = policy_package_crud.set_permissions(
        db=db, db_obj=pkg, permission_ids=payload.permission_ids
    )
    new_count = len(payload.permission_ids)

    logger.info(f"PolicyPackage {package_id} permissions updated: {old_count} → {new_count}")
    return ResponseWrapper.success(
        data=_serialize(pkg, db),
        message=f"Permission set updated: {new_count} permissions now active.",
    )
