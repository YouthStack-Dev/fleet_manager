"""
Nodal Point Management
======================
Endpoints for managing nodal points (company-defined pickup / drop hubs) and
linking employees to their assigned nodal point.

Base path: /api/v1/nodal-points
"""

from fastapi import APIRouter, Depends, HTTPException, Query, Path, status
from sqlalchemy.orm import Session
from typing import Optional, List
from geopy.distance import geodesic

from app.database.session import get_db
from app.models.nodal_point import NodalPoint, EmployeeNodalPoint
from app.models.employee import Employee
from app.schemas.nodal_point import (
    NodalPointCreate,
    NodalPointUpdate,
    NodalPointResponse,
    NodalPointPaginationResponse,
    NearestNodalPointResponse,
    EmployeeNodalAssignRequest,
    EmployeeNodalAssignmentResponse,
)
from app.utils.response_utils import ResponseWrapper, handle_http_error, handle_db_error
from common_utils.auth.permission_checker import PermissionChecker
from app.core.logging_config import get_logger
from sqlalchemy.exc import SQLAlchemyError

logger = get_logger(__name__)
router = APIRouter(prefix="/nodal-points", tags=["nodal-points"])


# ──────────────────────────────────────────────────────────────
# Helpers
# ──────────────────────────────────────────────────────────────

def _resolve_tenant(user_data: dict, provided_tenant_id: Optional[str]) -> str:
    """Return the correct tenant_id, enforcing tenant-scoping for non-admin users."""
    user_type = user_data.get("user_type")
    if user_type == "admin":
        if not provided_tenant_id:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=ResponseWrapper.error(
                    "Admin must supply tenant_id", "TENANT_ID_REQUIRED"
                ),
            )
        return provided_tenant_id
    return user_data.get("tenant_id")


def _nearest_active_nodal_point(
    db: Session,
    tenant_id: str,
    lat: float,
    lng: float,
) -> Optional[NodalPoint]:
    """Return the active nodal point closest to (lat, lng) using geodesic distance."""
    points = (
        db.query(NodalPoint)
        .filter(
            NodalPoint.tenant_id == tenant_id,
            NodalPoint.is_active.is_(True),
        )
        .all()
    )
    if not points:
        return None

    def _dist(p: NodalPoint) -> float:
        return geodesic(
            (lat, lng), (float(p.latitude), float(p.longitude))
        ).km

    return min(points, key=_dist)


# ──────────────────────────────────────────────────────────────
# Nodal Point CRUD
# ──────────────────────────────────────────────────────────────

@router.post("/", status_code=status.HTTP_201_CREATED)
def create_nodal_point(
    payload: NodalPointCreate,
    db: Session = Depends(get_db),
    user_data=Depends(PermissionChecker(["nodal_point.create"], check_tenant=True)),
):
    """
    Create a new nodal point for a tenant.
    Admin must provide tenant_id; tenant users inherit it from their token.
    """
    try:
        tenant_id = _resolve_tenant(user_data, payload.tenant_id)

        nodal_point = NodalPoint(
            tenant_id=tenant_id,
            name=payload.name,
            address=payload.address,
            latitude=payload.latitude,
            longitude=payload.longitude,
            is_active=payload.is_active,
        )
        db.add(nodal_point)
        db.commit()
        db.refresh(nodal_point)

        logger.info(
            f"[nodal_point.create] tenant={tenant_id} "
            f"id={nodal_point.nodal_point_id} name={nodal_point.name}"
        )
        return ResponseWrapper.created(
            data=NodalPointResponse.model_validate(nodal_point).model_dump(),
            message="Nodal point created successfully",
        )

    except HTTPException:
        raise
    except SQLAlchemyError as e:
        db.rollback()
        raise handle_db_error(e)
    except Exception as e:
        db.rollback()
        logger.exception("Unexpected error creating nodal point")
        raise handle_http_error(e)


@router.get("/", status_code=status.HTTP_200_OK)
def list_nodal_points(
    tenant_id: Optional[str] = Query(None),
    is_active: Optional[bool] = Query(None),
    page: int = Query(1, ge=1),
    per_page: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db),
    user_data=Depends(PermissionChecker(["nodal_point.read"], check_tenant=True)),
):
    """List all nodal points for the tenant with optional active-only filter."""
    try:
        tenant_id = _resolve_tenant(user_data, tenant_id)

        q = db.query(NodalPoint).filter(NodalPoint.tenant_id == tenant_id)
        if is_active is not None:
            q = q.filter(NodalPoint.is_active.is_(is_active))

        total = q.count()
        items = q.offset((page - 1) * per_page).limit(per_page).all()

        return ResponseWrapper.paginated(
            items=[NodalPointResponse.model_validate(n).model_dump() for n in items],
            total=total,
            page=page,
            per_page=per_page,
            message="Nodal points fetched successfully",
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.exception("Error listing nodal points")
        raise handle_http_error(e)


@router.get("/nearest", status_code=status.HTTP_200_OK)
def get_nearest_nodal_points(
    latitude: float = Query(..., ge=-90, le=90),
    longitude: float = Query(..., ge=-180, le=180),
    limit: int = Query(3, ge=1, le=20, description="How many nearest points to return"),
    tenant_id: Optional[str] = Query(None),
    db: Session = Depends(get_db),
    user_data=Depends(PermissionChecker(["nodal_point.read"], check_tenant=True)),
):
    """
    Return the N nearest active nodal points to the supplied coordinates,
    sorted by geodesic distance ascending.
    """
    try:
        tenant_id = _resolve_tenant(user_data, tenant_id)

        points = (
            db.query(NodalPoint)
            .filter(
                NodalPoint.tenant_id == tenant_id,
                NodalPoint.is_active.is_(True),
            )
            .all()
        )

        if not points:
            return ResponseWrapper.success(
                data=[], message="No active nodal points found for this tenant"
            )

        # Compute distances and sort
        def _dist(p: NodalPoint) -> float:
            return geodesic(
                (latitude, longitude),
                (float(p.latitude), float(p.longitude)),
            ).km

        sorted_points = sorted(points, key=_dist)[:limit]

        result = []
        for p in sorted_points:
            d = _dist(p)
            base = NodalPointResponse.model_validate(p).model_dump()
            result.append({**base, "distance_km": round(d, 3)})

        return ResponseWrapper.success(
            data=result, message="Nearest nodal points fetched"
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.exception("Error fetching nearest nodal points")
        raise handle_http_error(e)


@router.get("/{nodal_point_id}", status_code=status.HTTP_200_OK)
def get_nodal_point(
    nodal_point_id: int = Path(...),
    tenant_id: Optional[str] = Query(None),
    db: Session = Depends(get_db),
    user_data=Depends(PermissionChecker(["nodal_point.read"], check_tenant=True)),
):
    """Fetch a single nodal point by ID."""
    try:
        tid = _resolve_tenant(user_data, tenant_id)

        nodal_point = (
            db.query(NodalPoint)
            .filter(
                NodalPoint.nodal_point_id == nodal_point_id,
                NodalPoint.tenant_id == tid,
            )
            .first()
        )
        if not nodal_point:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=ResponseWrapper.error(
                    "Nodal point not found", "NODAL_POINT_NOT_FOUND"
                ),
            )

        return ResponseWrapper.success(
            data=NodalPointResponse.model_validate(nodal_point).model_dump(),
            message="Nodal point fetched successfully",
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.exception("Error fetching nodal point")
        raise handle_http_error(e)


@router.put("/{nodal_point_id}", status_code=status.HTTP_200_OK)
def update_nodal_point(
    nodal_point_id: int = Path(...),
    payload: NodalPointUpdate = ...,
    tenant_id: Optional[str] = Query(None),
    db: Session = Depends(get_db),
    user_data=Depends(PermissionChecker(["nodal_point.update"], check_tenant=True)),
):
    """Update a nodal point (partial update — only supplied fields are changed)."""
    try:
        tid = _resolve_tenant(user_data, tenant_id)

        nodal_point = (
            db.query(NodalPoint)
            .filter(
                NodalPoint.nodal_point_id == nodal_point_id,
                NodalPoint.tenant_id == tid,
            )
            .first()
        )
        if not nodal_point:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=ResponseWrapper.error(
                    "Nodal point not found", "NODAL_POINT_NOT_FOUND"
                ),
            )

        update_data = payload.model_dump(exclude_unset=True)
        for field, value in update_data.items():
            setattr(nodal_point, field, value)

        db.commit()
        db.refresh(nodal_point)

        logger.info(
            f"[nodal_point.update] id={nodal_point_id} fields={list(update_data.keys())}"
        )
        return ResponseWrapper.updated(
            data=NodalPointResponse.model_validate(nodal_point).model_dump(),
            message="Nodal point updated successfully",
        )

    except HTTPException:
        raise
    except SQLAlchemyError as e:
        db.rollback()
        raise handle_db_error(e)
    except Exception as e:
        db.rollback()
        logger.exception("Unexpected error updating nodal point")
        raise handle_http_error(e)


@router.delete("/{nodal_point_id}", status_code=status.HTTP_200_OK)
def deactivate_nodal_point(
    nodal_point_id: int = Path(...),
    tenant_id: Optional[str] = Query(None),
    db: Session = Depends(get_db),
    user_data=Depends(PermissionChecker(["nodal_point.delete"], check_tenant=True)),
):
    """
    Soft-delete (deactivate) a nodal point.
    Existing employee assignments and bookings are kept intact for audit.
    """
    try:
        tid = _resolve_tenant(user_data, tenant_id)

        nodal_point = (
            db.query(NodalPoint)
            .filter(
                NodalPoint.nodal_point_id == nodal_point_id,
                NodalPoint.tenant_id == tid,
            )
            .first()
        )
        if not nodal_point:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=ResponseWrapper.error(
                    "Nodal point not found", "NODAL_POINT_NOT_FOUND"
                ),
            )

        nodal_point.is_active = False
        db.commit()

        logger.info(f"[nodal_point.deactivate] id={nodal_point_id} tenant={tid}")
        return ResponseWrapper.deleted(
            message=f"Nodal point '{nodal_point.name}' deactivated successfully"
        )

    except HTTPException:
        raise
    except SQLAlchemyError as e:
        db.rollback()
        raise handle_db_error(e)
    except Exception as e:
        db.rollback()
        logger.exception("Unexpected error deactivating nodal point")
        raise handle_http_error(e)


# ──────────────────────────────────────────────────────────────
# Employee ↔ Nodal Point assignment
# ──────────────────────────────────────────────────────────────

@router.post("/employees/{employee_id}/assign", status_code=status.HTTP_200_OK)
def assign_nodal_point_to_employee(
    employee_id: int = Path(...),
    payload: EmployeeNodalAssignRequest = ...,
    tenant_id: Optional[str] = Query(None),
    db: Session = Depends(get_db),
    user_data=Depends(PermissionChecker(["nodal_point.update"], check_tenant=True)),
):
    """
    Assign (or re-assign) a nodal point to an employee.

    - If nodal_point_id is supplied → explicit / override assignment.
    - If nodal_point_id is omitted → system picks the nearest active nodal point
      based on the employee's stored latitude/longitude.
    """
    try:
        tid = _resolve_tenant(user_data, tenant_id)

        # Validate employee belongs to tenant
        employee = (
            db.query(Employee)
            .filter(
                Employee.employee_id == employee_id,
                Employee.tenant_id == tid,
                Employee.is_active.is_(True),
            )
            .first()
        )
        if not employee:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=ResponseWrapper.error(
                    "Employee not found or inactive", "EMPLOYEE_NOT_FOUND"
                ),
            )

        # Determine which nodal point to assign
        if payload.nodal_point_id:
            nodal_point = (
                db.query(NodalPoint)
                .filter(
                    NodalPoint.nodal_point_id == payload.nodal_point_id,
                    NodalPoint.tenant_id == tid,
                    NodalPoint.is_active.is_(True),
                )
                .first()
            )
            if not nodal_point:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail=ResponseWrapper.error(
                        "Nodal point not found or inactive", "NODAL_POINT_NOT_FOUND"
                    ),
                )
            is_overridden = payload.is_overridden
        else:
            # Auto-assign nearest
            if not employee.latitude or not employee.longitude:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=ResponseWrapper.error(
                        "Employee has no location coordinates — cannot auto-assign nearest nodal point. "
                        "Please provide nodal_point_id explicitly or update employee coordinates first.",
                        "EMPLOYEE_NO_COORDINATES",
                    ),
                )
            nodal_point = _nearest_active_nodal_point(
                db, tid, float(employee.latitude), float(employee.longitude)
            )
            if not nodal_point:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail=ResponseWrapper.error(
                        "No active nodal points found for this tenant",
                        "NO_NODAL_POINTS",
                    ),
                )
            is_overridden = False  # system-assigned

        # Upsert: update existing record or create new one
        assignment = (
            db.query(EmployeeNodalPoint)
            .filter(EmployeeNodalPoint.employee_id == employee_id)
            .first()
        )
        if assignment:
            assignment.nodal_point_id = nodal_point.nodal_point_id
            assignment.is_overridden = is_overridden
        else:
            assignment = EmployeeNodalPoint(
                employee_id=employee_id,
                nodal_point_id=nodal_point.nodal_point_id,
                tenant_id=tid,
                is_overridden=is_overridden,
            )
            db.add(assignment)

        db.commit()
        db.refresh(assignment)

        distance_km = None
        if employee.latitude and employee.longitude:
            distance_km = round(
                geodesic(
                    (float(employee.latitude), float(employee.longitude)),
                    (float(nodal_point.latitude), float(nodal_point.longitude)),
                ).km,
                3,
            )

        logger.info(
            f"[nodal_point.assign] employee={employee_id} "
            f"nodal_point={nodal_point.nodal_point_id} "
            f"override={is_overridden} distance_km={distance_km}"
        )

        response_data = {
            "id": assignment.id,
            "employee_id": assignment.employee_id,
            "nodal_point_id": assignment.nodal_point_id,
            "tenant_id": assignment.tenant_id,
            "is_overridden": assignment.is_overridden,
            "nodal_point": NodalPointResponse.model_validate(nodal_point).model_dump(),
            "distance_km": distance_km,
            "created_at": assignment.created_at,
            "updated_at": assignment.updated_at,
        }
        return ResponseWrapper.success(
            data=response_data,
            message="Nodal point assigned to employee successfully",
        )

    except HTTPException:
        raise
    except SQLAlchemyError as e:
        db.rollback()
        raise handle_db_error(e)
    except Exception as e:
        db.rollback()
        logger.exception("Unexpected error assigning nodal point")
        raise handle_http_error(e)


@router.get("/employees/{employee_id}", status_code=status.HTTP_200_OK)
def get_employee_nodal_assignment(
    employee_id: int = Path(...),
    tenant_id: Optional[str] = Query(None),
    db: Session = Depends(get_db),
    user_data=Depends(PermissionChecker(["nodal_point.read"], check_tenant=True)),
):
    """Return the nodal point currently assigned to the given employee."""
    try:
        tid = _resolve_tenant(user_data, tenant_id)

        assignment = (
            db.query(EmployeeNodalPoint)
            .join(Employee, EmployeeNodalPoint.employee_id == Employee.employee_id)
            .filter(
                EmployeeNodalPoint.employee_id == employee_id,
                Employee.tenant_id == tid,
            )
            .first()
        )
        if not assignment:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=ResponseWrapper.error(
                    "No nodal point assigned to this employee",
                    "ASSIGNMENT_NOT_FOUND",
                ),
            )

        response_data = {
            "id": assignment.id,
            "employee_id": assignment.employee_id,
            "nodal_point_id": assignment.nodal_point_id,
            "tenant_id": assignment.tenant_id,
            "is_overridden": assignment.is_overridden,
            "nodal_point": NodalPointResponse.model_validate(assignment.nodal_point).model_dump(),
            "created_at": assignment.created_at,
            "updated_at": assignment.updated_at,
        }
        return ResponseWrapper.success(
            data=response_data,
            message="Employee nodal assignment fetched successfully",
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.exception("Error fetching employee nodal assignment")
        raise handle_http_error(e)


@router.delete("/employees/{employee_id}", status_code=status.HTTP_200_OK)
def remove_employee_nodal_assignment(
    employee_id: int = Path(...),
    tenant_id: Optional[str] = Query(None),
    db: Session = Depends(get_db),
    user_data=Depends(PermissionChecker(["nodal_point.update"], check_tenant=True)),
):
    """Remove a nodal point assignment from an employee."""
    try:
        tid = _resolve_tenant(user_data, tenant_id)

        assignment = (
            db.query(EmployeeNodalPoint)
            .join(Employee, EmployeeNodalPoint.employee_id == Employee.employee_id)
            .filter(
                EmployeeNodalPoint.employee_id == employee_id,
                Employee.tenant_id == tid,
            )
            .first()
        )
        if not assignment:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=ResponseWrapper.error(
                    "No nodal point assignment found for this employee",
                    "ASSIGNMENT_NOT_FOUND",
                ),
            )

        db.delete(assignment)
        db.commit()

        logger.info(
            f"[nodal_point.remove_assignment] employee={employee_id} tenant={tid}"
        )
        return ResponseWrapper.deleted(
            message="Nodal point assignment removed from employee"
        )

    except HTTPException:
        raise
    except SQLAlchemyError as e:
        db.rollback()
        raise handle_db_error(e)
    except Exception as e:
        db.rollback()
        logger.exception("Unexpected error removing nodal assignment")
        raise handle_http_error(e)


# ──────────────────────────────────────────────────────────────
# Bulk-assign nearest nodal point for multiple employees at once
# ──────────────────────────────────────────────────────────────

@router.post("/employees/bulk-assign-nearest", status_code=status.HTTP_200_OK)
def bulk_assign_nearest(
    tenant_id: Optional[str] = Query(None),
    db: Session = Depends(get_db),
    user_data=Depends(PermissionChecker(["nodal_point.update"], check_tenant=True)),
):
    """
    Auto-assign the nearest active nodal point to every employee in the tenant
    who does not yet have an assignment (or whose assignment is not overridden).

    Employees without coordinates are skipped and reported back.
    """
    try:
        tid = _resolve_tenant(user_data, tenant_id)

        active_nodal_points = (
            db.query(NodalPoint)
            .filter(
                NodalPoint.tenant_id == tid,
                NodalPoint.is_active.is_(True),
            )
            .all()
        )
        if not active_nodal_points:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=ResponseWrapper.error(
                    "No active nodal points exist for this tenant",
                    "NO_NODAL_POINTS",
                ),
            )

        employees = (
            db.query(Employee)
            .filter(
                Employee.tenant_id == tid,
                Employee.is_active.is_(True),
            )
            .all()
        )

        assigned_count = 0
        skipped = []

        for emp in employees:
            # Skip employees already manually overridden
            existing = (
                db.query(EmployeeNodalPoint)
                .filter(
                    EmployeeNodalPoint.employee_id == emp.employee_id,
                    EmployeeNodalPoint.is_overridden.is_(True),
                )
                .first()
            )
            if existing:
                continue

            if not emp.latitude or not emp.longitude:
                skipped.append(
                    {"employee_id": emp.employee_id, "reason": "no coordinates"}
                )
                continue

            nearest = min(
                active_nodal_points,
                key=lambda p: geodesic(
                    (float(emp.latitude), float(emp.longitude)),
                    (float(p.latitude), float(p.longitude)),
                ).km,
            )

            # Upsert
            assignment = (
                db.query(EmployeeNodalPoint)
                .filter(EmployeeNodalPoint.employee_id == emp.employee_id)
                .first()
            )
            if assignment:
                assignment.nodal_point_id = nearest.nodal_point_id
                assignment.is_overridden = False
            else:
                db.add(
                    EmployeeNodalPoint(
                        employee_id=emp.employee_id,
                        nodal_point_id=nearest.nodal_point_id,
                        tenant_id=tid,
                        is_overridden=False,
                    )
                )
            assigned_count += 1

        db.commit()

        logger.info(
            f"[nodal_point.bulk_assign] tenant={tid} "
            f"assigned={assigned_count} skipped={len(skipped)}"
        )
        return ResponseWrapper.success(
            data={"assigned": assigned_count, "skipped": skipped},
            message=f"Bulk assignment complete: {assigned_count} employee(s) assigned",
        )

    except HTTPException:
        raise
    except SQLAlchemyError as e:
        db.rollback()
        raise handle_db_error(e)
    except Exception as e:
        db.rollback()
        logger.exception("Unexpected error during bulk nodal assignment")
        raise handle_http_error(e)
