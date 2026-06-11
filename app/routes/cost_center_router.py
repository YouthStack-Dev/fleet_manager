from datetime import date
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from sqlalchemy import or_
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.database.session import get_db
from app.models.booking import Booking
from app.models.costing import CostCenter, CostCenterAssignment
from app.models.employee import Employee
from app.models.team import Team
from app.models.tenant import Tenant
from app.schemas.costing import CostCenterAssignmentCreate, CostCenterAssignmentResponse, CostCenterCreate, CostCenterResponse, CostCenterUpdate
from app.services.costing_service import CostingService
from app.utils.response_utils import ResponseWrapper, handle_db_error
from common_utils.auth.permission_checker import PermissionChecker


router = APIRouter(prefix="/cost-centers", tags=["cost-centers"])


def resolve_tenant(user_data: dict, tenant_id: Optional[str]) -> str:
    user_type = user_data.get("user_type")
    token_tenant_id = user_data.get("tenant_id")
    if user_type == "employee":
        tenant_id = token_tenant_id
    elif user_type == "admin":
        tenant_id = token_tenant_id or tenant_id
    else:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=ResponseWrapper.error("You do not have permission to manage cost centers", "FORBIDDEN"),
        )
    if not tenant_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=ResponseWrapper.error("tenant_id is required", "TENANT_ID_REQUIRED"),
        )
    return tenant_id


def validate_tenant(db: Session, tenant_id: str) -> Tenant:
    tenant = db.query(Tenant).filter(Tenant.tenant_id == tenant_id).first()
    if not tenant:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=ResponseWrapper.error("Tenant not found", "TENANT_NOT_FOUND"),
        )
    return tenant


def validate_scope(db: Session, tenant_id: str, scope_type: str, scope_id: str) -> None:
    if scope_type == "tenant":
        if scope_id != tenant_id:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=ResponseWrapper.error("Tenant scope_id must match tenant_id", "INVALID_SCOPE_ID"),
            )
        validate_tenant(db, tenant_id)
        return
    if scope_type == "team":
        exists = db.query(Team).filter(Team.team_id == int(scope_id), Team.tenant_id == tenant_id).first()
    elif scope_type == "employee":
        exists = db.query(Employee).filter(Employee.employee_id == int(scope_id), Employee.tenant_id == tenant_id).first()
    else:
        exists = None
    if not exists:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=ResponseWrapper.error("Assignment scope not found for this tenant", "SCOPE_NOT_FOUND"),
        )


def ensure_no_assignment_overlap(
    db: Session,
    tenant_id: str,
    scope_type: str,
    scope_id: str,
    effective_from: date,
    effective_to: Optional[date],
) -> None:
    end = effective_to or date.max
    overlap = (
        db.query(CostCenterAssignment)
        .filter(
            CostCenterAssignment.tenant_id == tenant_id,
            CostCenterAssignment.scope_type == scope_type,
            CostCenterAssignment.scope_id == scope_id,
            CostCenterAssignment.is_active == True,
            CostCenterAssignment.effective_from <= end,
            or_(CostCenterAssignment.effective_to.is_(None), CostCenterAssignment.effective_to >= effective_from),
        )
        .first()
    )
    if overlap:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=ResponseWrapper.error("Active cost center assignment overlaps this date range", "ASSIGNMENT_OVERLAP"),
        )


@router.post("/", status_code=status.HTTP_201_CREATED)
def create_cost_center(
    payload: CostCenterCreate,
    request: Request,
    db: Session = Depends(get_db),
    user_data=Depends(PermissionChecker(["cost_center.create"], check_tenant=True)),
):
    try:
        tenant_id = resolve_tenant(user_data, payload.tenant_id)
        validate_tenant(db, tenant_id)
        if payload.is_default:
            db.query(CostCenter).filter(CostCenter.tenant_id == tenant_id, CostCenter.is_default == True).update({CostCenter.is_default: False})
        cost_center = CostCenter(
            tenant_id=tenant_id,
            code=payload.code,
            name=payload.name,
            description=payload.description,
            is_default=payload.is_default,
            is_active=payload.is_active,
        )
        db.add(cost_center)
        db.commit()
        db.refresh(cost_center)
        return ResponseWrapper.success({"cost_center": CostCenterResponse.model_validate(cost_center)}, "Cost center created successfully")
    except HTTPException:
        raise
    except SQLAlchemyError as exc:
        db.rollback()
        raise handle_db_error(exc)


@router.get("/resolve", status_code=status.HTTP_200_OK)
def resolve_cost_center(
    booking_id: Optional[int] = Query(None),
    employee_id: Optional[int] = Query(None),
    as_of: Optional[date] = Query(None),
    tenant_id: Optional[str] = Query(None),
    db: Session = Depends(get_db),
    user_data=Depends(PermissionChecker(["cost_center.read"], check_tenant=True)),
):
    tenant_id = resolve_tenant(user_data, tenant_id)
    as_of = as_of or date.today()
    if booking_id:
        booking = db.query(Booking).filter(Booking.booking_id == booking_id, Booking.tenant_id == tenant_id).first()
        if not booking:
            raise HTTPException(status_code=404, detail=ResponseWrapper.error("Booking not found", "BOOKING_NOT_FOUND"))
    elif employee_id:
        employee = db.query(Employee).filter(Employee.employee_id == employee_id, Employee.tenant_id == tenant_id).first()
        if not employee:
            raise HTTPException(status_code=404, detail=ResponseWrapper.error("Employee not found", "EMPLOYEE_NOT_FOUND"))
        booking = Booking(tenant_id=tenant_id, employee_id=employee.employee_id, employee_code=employee.employee_code, team_id=employee.team_id, booking_date=as_of)
    else:
        raise HTTPException(status_code=400, detail=ResponseWrapper.error("booking_id or employee_id is required", "RESOLVE_TARGET_REQUIRED"))

    cc = CostingService.resolve_cost_center_for_booking(db, booking, as_of)
    db.commit()
    return ResponseWrapper.success({"cost_center": CostCenterResponse.model_validate(cc)}, "Cost center resolved successfully")


@router.get("/", status_code=status.HTTP_200_OK)
def list_cost_centers(
    tenant_id: Optional[str] = Query(None),
    is_active: Optional[bool] = Query(None),
    db: Session = Depends(get_db),
    user_data=Depends(PermissionChecker(["cost_center.read"], check_tenant=True)),
):
    tenant_id = resolve_tenant(user_data, tenant_id)
    query = db.query(CostCenter).filter(CostCenter.tenant_id == tenant_id)
    if is_active is not None:
        query = query.filter(CostCenter.is_active == is_active)
    cost_centers = query.order_by(CostCenter.code.asc()).all()
    return ResponseWrapper.success(
        {"cost_centers": [CostCenterResponse.model_validate(cc) for cc in cost_centers], "total": len(cost_centers)},
        "Cost centers fetched successfully",
    )


@router.get("/{cost_center_id}", status_code=status.HTTP_200_OK)
def get_cost_center(
    cost_center_id: int,
    tenant_id: Optional[str] = Query(None),
    db: Session = Depends(get_db),
    user_data=Depends(PermissionChecker(["cost_center.read"], check_tenant=True)),
):
    tenant_id = resolve_tenant(user_data, tenant_id)
    cost_center = db.query(CostCenter).filter(CostCenter.cost_center_id == cost_center_id, CostCenter.tenant_id == tenant_id).first()
    if not cost_center:
        raise HTTPException(status_code=404, detail=ResponseWrapper.error("Cost center not found", "COST_CENTER_NOT_FOUND"))
    return ResponseWrapper.success({"cost_center": CostCenterResponse.model_validate(cost_center)}, "Cost center fetched successfully")


@router.patch("/{cost_center_id}", status_code=status.HTTP_200_OK)
def update_cost_center(
    cost_center_id: int,
    payload: CostCenterUpdate,
    tenant_id: Optional[str] = Query(None),
    db: Session = Depends(get_db),
    user_data=Depends(PermissionChecker(["cost_center.update"], check_tenant=True)),
):
    try:
        tenant_id = resolve_tenant(user_data, tenant_id)
        cost_center = db.query(CostCenter).filter(CostCenter.cost_center_id == cost_center_id, CostCenter.tenant_id == tenant_id).first()
        if not cost_center:
            raise HTTPException(status_code=404, detail=ResponseWrapper.error("Cost center not found", "COST_CENTER_NOT_FOUND"))
        updates = payload.model_dump(exclude_unset=True)
        if updates.get("is_default") is True:
            db.query(CostCenter).filter(CostCenter.tenant_id == tenant_id, CostCenter.cost_center_id != cost_center_id).update({CostCenter.is_default: False})
        for key, value in updates.items():
            setattr(cost_center, key, value)
        db.commit()
        db.refresh(cost_center)
        return ResponseWrapper.success({"cost_center": CostCenterResponse.model_validate(cost_center)}, "Cost center updated successfully")
    except HTTPException:
        raise
    except SQLAlchemyError as exc:
        db.rollback()
        raise handle_db_error(exc)


@router.delete("/{cost_center_id}", status_code=status.HTTP_200_OK)
def deactivate_cost_center(
    cost_center_id: int,
    tenant_id: Optional[str] = Query(None),
    db: Session = Depends(get_db),
    user_data=Depends(PermissionChecker(["cost_center.delete"], check_tenant=True)),
):
    tenant_id = resolve_tenant(user_data, tenant_id)
    cost_center = db.query(CostCenter).filter(CostCenter.cost_center_id == cost_center_id, CostCenter.tenant_id == tenant_id).first()
    if not cost_center:
        raise HTTPException(status_code=404, detail=ResponseWrapper.error("Cost center not found", "COST_CENTER_NOT_FOUND"))
    cost_center.is_active = False
    db.commit()
    return ResponseWrapper.success(None, "Cost center deactivated successfully")


@router.post("/{cost_center_id}/assignments", status_code=status.HTTP_201_CREATED)
def create_assignment(
    cost_center_id: int,
    payload: CostCenterAssignmentCreate,
    tenant_id: Optional[str] = Query(None),
    db: Session = Depends(get_db),
    user_data=Depends(PermissionChecker(["cost_center.update"], check_tenant=True)),
):
    try:
        tenant_id = resolve_tenant(user_data, tenant_id)
        cost_center = db.query(CostCenter).filter(CostCenter.cost_center_id == cost_center_id, CostCenter.tenant_id == tenant_id, CostCenter.is_active == True).first()
        if not cost_center:
            raise HTTPException(status_code=404, detail=ResponseWrapper.error("Cost center not found", "COST_CENTER_NOT_FOUND"))
        scope_id = str(payload.scope_id)
        validate_scope(db, tenant_id, payload.scope_type.value, scope_id)
        ensure_no_assignment_overlap(db, tenant_id, payload.scope_type.value, scope_id, payload.effective_from, payload.effective_to)
        assignment = CostCenterAssignment(
            tenant_id=tenant_id,
            cost_center_id=cost_center_id,
            scope_type=payload.scope_type.value,
            scope_id=scope_id,
            effective_from=payload.effective_from,
            effective_to=payload.effective_to,
            is_active=payload.is_active,
        )
        db.add(assignment)
        db.commit()
        db.refresh(assignment)
        return ResponseWrapper.success({"assignment": CostCenterAssignmentResponse.model_validate(assignment)}, "Cost center assignment created successfully")
    except HTTPException:
        raise
    except SQLAlchemyError as exc:
        db.rollback()
        raise handle_db_error(exc)
