from math import inf
from typing import Dict, List, Optional

from fastapi import HTTPException, status
from sqlalchemy.orm import Session, joinedload

from app.models.contract import Contract, ContractSlab
from app.models.route_management import RouteManagement, RouteManagementStatusEnum
from app.models.vehicle import Vehicle
from app.utils.response_utils import ResponseWrapper


def calculate_route_cost(db: Session, *, route_id: int, user_data: Optional[dict] = None) -> Dict:
    route = db.query(RouteManagement).filter(RouteManagement.route_id == route_id).first()
    if not route:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=ResponseWrapper.error("Route not found", "ROUTE_NOT_FOUND"),
        )

    _validate_route_access(route, user_data)

    if route.status != RouteManagementStatusEnum.COMPLETED:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=ResponseWrapper.error("Route is not completed", "ROUTE_NOT_COMPLETED"),
        )

    if not route.assigned_vehicle_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=ResponseWrapper.error("Route has no assigned vehicle", "ROUTE_VEHICLE_REQUIRED"),
        )

    total_distance = float(route.actual_total_distance or 0)
    if total_distance <= 0:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=ResponseWrapper.error("Route actual distance is required", "ROUTE_DISTANCE_REQUIRED"),
        )

    vehicle = (
        db.query(Vehicle)
        .options(joinedload(Vehicle.vehicle_type), joinedload(Vehicle.contract))
        .filter(Vehicle.vehicle_id == route.assigned_vehicle_id)
        .first()
    )
    if not vehicle:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=ResponseWrapper.error("Assigned vehicle not found", "VEHICLE_NOT_FOUND"),
        )

    _validate_vehicle_access(vehicle, user_data)

    if not vehicle.contract_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=ResponseWrapper.error("Vehicle has no contract assigned", "VEHICLE_CONTRACT_REQUIRED"),
        )

    contract = (
        db.query(Contract)
        .options(joinedload(Contract.slabs), joinedload(Contract.vehicle_type))
        .filter(Contract.contract_id == vehicle.contract_id)
        .first()
    )
    if not contract:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=ResponseWrapper.error("Contract not found", "CONTRACT_NOT_FOUND"),
        )

    if not contract.is_active:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=ResponseWrapper.error("Contract is inactive", "CONTRACT_INACTIVE"),
        )

    if contract.vendor_id != vehicle.vendor_id or contract.vehicle_type_id != vehicle.vehicle_type_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=ResponseWrapper.error(
                "Vehicle contract does not match vehicle vendor/type",
                "CONTRACT_VEHICLE_MISMATCH",
            ),
        )

    slabs = (
        db.query(ContractSlab)
        .filter(ContractSlab.contract_id == contract.contract_id, ContractSlab.is_active.is_(True))
        .order_by(ContractSlab.min_km.asc())
        .all()
    )
    if not slabs:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=ResponseWrapper.error("No active slabs found for this contract", "CONTRACT_SLABS_REQUIRED"),
        )

    total_cost, breakdown = _calculate_progressive_cost(total_distance, slabs)
    effective_rate = round(total_cost / total_distance, 2) if total_distance else 0

    return {
        "route_id": route.route_id,
        "contract_id": contract.contract_id,
        "contract_name": contract.contract_name,
        "vehicle_id": vehicle.vehicle_id,
        "vehicle_type_name": vehicle.vehicle_type.name if vehicle.vehicle_type else None,
        "vendor_id": contract.vendor_id,
        "total_distance_km": round(total_distance, 2),
        "total_cost": round(total_cost, 2),
        "effective_rate": effective_rate,
        "slab_breakdown": breakdown,
    }


def _calculate_progressive_cost(total_distance: float, slabs: List[ContractSlab]) -> tuple[float, List[Dict]]:
    remaining_distance = total_distance
    total_cost = 0.0
    breakdown: List[Dict] = []
    covered_until = 0.0
    tolerance = 0.000001

    for slab in slabs:
        if abs(slab.min_km - covered_until) > tolerance:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=ResponseWrapper.error(
                    "Contract slabs do not cover the route distance without gaps",
                    "INVALID_SLAB_CHAIN",
                ),
            )

        slab_end = slab.max_km if slab.max_km is not None else inf
        slab_capacity = slab_end - slab.min_km
        km_used = min(remaining_distance, slab_capacity)

        if km_used > tolerance:
            cost = round(km_used * slab.rate, 2)
            total_cost += cost
            breakdown.append(
                {
                    "min_km": float(slab.min_km),
                    "max_km": float(slab.max_km) if slab.max_km is not None else None,
                    "km_used": round(km_used, 2),
                    "rate": round(float(slab.rate), 2),
                    "cost": cost,
                }
            )

        remaining_distance -= km_used
        covered_until = slab_end if slab.max_km is not None else total_distance

        if remaining_distance <= tolerance:
            break

    if remaining_distance > tolerance:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=ResponseWrapper.error(
                "Route distance exceeds configured contract slabs",
                "DISTANCE_NOT_COVERED_BY_SLABS",
                details={"uncovered_distance_km": round(remaining_distance, 2)},
            ),
        )

    return round(total_cost, 2), breakdown


def _validate_route_access(route: RouteManagement, user_data: Optional[dict]) -> None:
    if not user_data:
        return

    user_type = user_data.get("user_type")
    if user_type == "vendor":
        token_vendor_id = user_data.get("vendor_id")
        if token_vendor_id and route.assigned_vendor_id and int(route.assigned_vendor_id) != int(token_vendor_id):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=ResponseWrapper.error("You cannot access this route", "FORBIDDEN"),
            )
    elif user_type == "employee":
        token_tenant_id = user_data.get("tenant_id")
        if token_tenant_id and route.tenant_id != token_tenant_id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=ResponseWrapper.error("You cannot access this route", "FORBIDDEN"),
            )
    elif user_type not in {"admin", "superadmin"}:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=ResponseWrapper.error("You cannot calculate route costs", "FORBIDDEN"),
        )


def _validate_vehicle_access(vehicle: Vehicle, user_data: Optional[dict]) -> None:
    if not user_data or user_data.get("user_type") != "vendor":
        return

    token_vendor_id = user_data.get("vendor_id")
    if token_vendor_id and int(vehicle.vendor_id) != int(token_vendor_id):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=ResponseWrapper.error("You cannot access this vehicle", "FORBIDDEN"),
        )
