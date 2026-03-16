"""
Policy Package Router
=====================
Manages the per-tenant PolicyPackage — the direct container of tenant-scoped policies.

Endpoints
─────────
  POST   /iam/policy-packages/                               → create a package for a tenant
  GET    /iam/policy-packages/                               → list packages
  GET    /iam/policy-packages/{package_id}                   → get one package with its policies
  PUT    /iam/policy-packages/{package_id}                   → update name / description / default_policy_id
  PATCH  /iam/policy-packages/{package_id}/permissions       → replace the full permission set on the default policy
  DELETE /iam/policy-packages/{package_id}                   → delete package (cascades to policies)

Access rules
────────────
  - admin: can create / manage packages for any tenant (must supply tenant_id in body)
  - employee/vendor: can only view and manage their own tenant's package
"""

from __future__ import annotations

from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.core.logging_config import get_logger
from app.crud.iam.policy_package import policy_package_crud
from app.database.session import get_db
from app.models.iam.policy import PolicyPackage
from app.models.tenant import Tenant
from app.schemas.iam.policy import PolicyPackageCreate, PolicyPackageResponse
from app.utils.response_utils import ResponseWrapper
from common_utils.auth.permission_checker import PermissionChecker

logger = get_logger(__name__)

router = APIRouter(prefix="/policy-packages", tags=["IAM Policy Packages"])


# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────

def _resolve_tenant_id(user_data: dict, tenant_id_from_body: Optional[str]) -> str:
    """
    Resolve the effective tenant_id:
    - admin  → must provide tenant_id in body
    - employee/vendor → always own tenant from token (body value ignored)
    """
    user_type = user_data.get("user_type")
    if user_type in ("employee", "vendor"):
        t = user_data.get("tenant_id")
        if not t:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=ResponseWrapper.error("Tenant ID missing in token", "TENANT_ID_MISSING"),
            )
        return t
    if user_type == "admin":
        if not tenant_id_from_body:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=ResponseWrapper.error(
                    "Admin must supply tenant_id in request body", "TENANT_ID_REQUIRED"
                ),
            )
        return tenant_id_from_body
    raise HTTPException(
        status_code=status.HTTP_403_FORBIDDEN,
        detail=ResponseWrapper.error("Unauthorized user type", "UNAUTHORIZED_USER_TYPE"),
    )


def _get_package_or_404(db: Session, package_id: int) -> PolicyPackage:
    pkg = policy_package_crud.get(db=db, package_id=package_id)
    if not pkg:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=ResponseWrapper.error(
                f"Policy package {package_id} not found", "PACKAGE_NOT_FOUND"
            ),
        )
    return pkg


def _assert_tenant_access(user_data: dict, package: PolicyPackage) -> None:
    """Non-admin users can only touch their own tenant's package."""
    if user_data.get("user_type") == "admin":
        return
    if str(user_data.get("tenant_id", "")) != str(package.tenant_id):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=ResponseWrapper.error(
                "You can only access your own tenant's policy package",
                "TENANT_FORBIDDEN",
            ),
        )


def _serialize(pkg: PolicyPackage) -> dict:
    """Minimal serialisation — include policy count and policy IDs for quick overview."""
    policies = getattr(pkg, "policies", []) or []
    return {
        "package_id": pkg.package_id,
        "tenant_id": pkg.tenant_id,
        "name": pkg.name,
        "description": pkg.description,
        "created_at": pkg.created_at,
        "updated_at": pkg.updated_at,
        "policy_count": len(policies),
        "policies": [
            {
                "policy_id": p.policy_id,
                "name": p.name,
                "is_active": p.is_active,
                "is_system_policy": p.is_system_policy,
                "permission_count": len(p.permissions) if p.permissions else 0,
                "permissions": [
                    {"permission_id": perm.permission_id, "module": perm.module, "action": perm.action}
                    for perm in (p.permissions or [])
                ],
            }
            for p in policies
        ],
    }


# ─────────────────────────────────────────────────────────────────────────────
# POST /iam/policy-packages/  — Create
# ─────────────────────────────────────────────────────────────────────────────

@router.post("/", status_code=status.HTTP_201_CREATED)
async def create_policy_package(
    payload: PolicyPackageCreate,
    db: Session = Depends(get_db),
    user_data=Depends(PermissionChecker(["policy-package.create"], check_tenant=True)),
):
    """
    Create a policy package for a tenant.

    - **Admin**: supply `tenant_id` in body — can create for any tenant.
    - **Employee / Vendor**: `tenant_id` is taken from the JWT; body value is ignored.

    Each tenant can have **at most one** policy package.
    """
    tenant_id = _resolve_tenant_id(user_data, payload.tenant_id)

    # Validate tenant exists
    tenant = db.query(Tenant).filter(Tenant.tenant_id == tenant_id).first()
    if not tenant:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=ResponseWrapper.error(
                f"Tenant '{tenant_id}' not found",
                "TENANT_NOT_FOUND",
            ),
        )

    # One package per tenant
    existing = policy_package_crud.get_by_tenant(db=db, tenant_id=tenant_id)
    if existing:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=ResponseWrapper.error(
                f"Tenant {tenant_id} already has a policy package (ID={existing.package_id}). "
                "Update it instead.",
                "PACKAGE_ALREADY_EXISTS",
                details={"existing_package_id": existing.package_id},
            ),
        )

    pkg = policy_package_crud.create(
        db=db,
        tenant_id=tenant_id,
        name=payload.name,
        description=payload.description,
    )
    logger.info(f"PolicyPackage created: id={pkg.package_id}, tenant={tenant_id}")
    return ResponseWrapper.success(data=_serialize(pkg), message="Policy package created successfully")


# ─────────────────────────────────────────────────────────────────────────────
# GET /iam/policy-packages/  — List
# ─────────────────────────────────────────────────────────────────────────────

@router.get("/", status_code=status.HTTP_200_OK)
async def list_policy_packages(
    tenant_id: Optional[str] = Query(None, description="Filter by tenant_id (admin only)"),
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=500),
    db: Session = Depends(get_db),
    user_data=Depends(PermissionChecker(["policy-package.read"], check_tenant=True)),
):
    """
    List policy packages.

    - **Admin**: can list all packages or filter by `tenant_id`.
    - **Employee / Vendor**: always scoped to their own tenant — query param ignored.
    """
    user_type = user_data.get("user_type")
    if user_type in ("employee", "vendor"):
        tenant_id = user_data.get("tenant_id")

    packages = policy_package_crud.list(db=db, tenant_id=tenant_id, skip=skip, limit=limit)
    total = policy_package_crud.count(db=db, tenant_id=tenant_id)

    return ResponseWrapper.success(
        data={"total": total, "items": [_serialize(p) for p in packages]},
        message="Policy packages fetched successfully",
    )


# ─────────────────────────────────────────────────────────────────────────────
# GET /iam/policy-packages/{package_id}  — Get one
# ─────────────────────────────────────────────────────────────────────────────

@router.get("/{package_id}", status_code=status.HTTP_200_OK)
async def get_policy_package(
    package_id: int,
    db: Session = Depends(get_db),
    user_data=Depends(PermissionChecker(["policy-package.read"], check_tenant=True)),
):
    """
    Retrieve a single policy package including all its policies and permissions.
    """
    pkg = _get_package_or_404(db, package_id)
    _assert_tenant_access(user_data, pkg)
    return ResponseWrapper.success(data=_serialize(pkg), message="Policy package fetched successfully")


# ─────────────────────────────────────────────────────────────────────────────
# PUT /iam/policy-packages/{package_id}  — Update
# ─────────────────────────────────────────────────────────────────────────────

class _PackageUpdate:
    """Inline simple update body — avoids importing a separate schema file."""
    pass

from pydantic import BaseModel

class PolicyPackageUpdateBody(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    # Swap which policy is the main/default one.
    # Must be the policy_id of a policy that already belongs to this package.
    default_policy_id: Optional[int] = None


@router.put("/{package_id}", status_code=status.HTTP_200_OK)
async def update_policy_package(
    package_id: int,
    payload: PolicyPackageUpdateBody,
    db: Session = Depends(get_db),
    user_data=Depends(PermissionChecker(["policy-package.update"], check_tenant=True)),
):
    """
    Update a policy package.

    - `name` — rename the package.
    - `description` — change the description.
    - `default_policy_id` — change which policy in this package is the default/main one.
      The policy must already belong to this package.
    """
    pkg = _get_package_or_404(db, package_id)
    _assert_tenant_access(user_data, pkg)

    if payload.name is None and payload.description is None and payload.default_policy_id is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=ResponseWrapper.error("No fields to update", "NO_FIELDS_TO_UPDATE"),
        )

    pkg = policy_package_crud.update(
        db=db,
        db_obj=pkg,
        name=payload.name,
        description=payload.description,
        default_policy_id=payload.default_policy_id,
    )
    logger.info(f"PolicyPackage updated: id={pkg.package_id}")
    return ResponseWrapper.success(data=_serialize(pkg), message="Policy package updated successfully")


# ─────────────────────────────────────────────────────────────────────────────
# PATCH /iam/policy-packages/{package_id}/permissions  — Replace permission set
# ─────────────────────────────────────────────────────────────────────────────

class PolicyPackagePermissionsBody(BaseModel):
    # Full replace — send the complete list you want. Anything not listed is removed.
    permission_ids: List[int]


@router.patch("/{package_id}/permissions", status_code=status.HTTP_200_OK)
async def replace_package_permissions(
    package_id: int,
    payload: PolicyPackagePermissionsBody,
    db: Session = Depends(get_db),
    user_data=Depends(PermissionChecker(["policy-package.update"], check_tenant=True)),
):
    """
    **Replace** the full permission set on the package's default policy.

    This is the main "update the company's permission boundary" endpoint.
    Whatever you send becomes the **complete** set — anything not in the list
    is removed from the default policy.

    - Package must have a `default_policy_id` set.
    - All `permission_ids` must exist in the system.
    """
    pkg = _get_package_or_404(db, package_id)
    _assert_tenant_access(user_data, pkg)

    old_count = 0
    if pkg.default_policy_id:
        from app.models.iam.policy import Policy
        old_pol = db.query(Policy).filter(Policy.policy_id == pkg.default_policy_id).first()
        old_count = len(old_pol.permissions) if old_pol and old_pol.permissions else 0

    pkg = policy_package_crud.set_permissions_on_default_policy(
        db=db, db_obj=pkg, permission_ids=payload.permission_ids
    )
    new_count = len(payload.permission_ids)
    logger.info(
        f"PolicyPackage {package_id} permissions replaced: {old_count} → {new_count}"
    )
    return ResponseWrapper.success(
        data=_serialize(pkg),
        message=f"Permission set updated: {new_count} permissions now active on the default policy.",
    )


# ─────────────────────────────────────────────────────────────────────────────
# DELETE /iam/policy-packages/{package_id}  — Delete (cascades to policies)
# ─────────────────────────────────────────────────────────────────────────────

@router.delete("/{package_id}", status_code=status.HTTP_200_OK)
async def delete_policy_package(
    package_id: int,
    db: Session = Depends(get_db),
    user_data=Depends(PermissionChecker(["policy-package.delete"], check_tenant=True)),
):
    """
    Delete a policy package and **all** its associated tenant policies (cascade).
    System policies are NOT affected.
    """
    pkg = _get_package_or_404(db, package_id)
    _assert_tenant_access(user_data, pkg)

    policy_count = len(getattr(pkg, "policies", []) or [])
    policy_package_crud.delete(db=db, db_obj=pkg)
    logger.info(f"PolicyPackage deleted: id={package_id}, {policy_count} policies removed")
    return ResponseWrapper.success(
        data={"deleted_package_id": package_id, "deleted_policy_count": policy_count},
        message="Policy package and its policies deleted successfully",
    )
