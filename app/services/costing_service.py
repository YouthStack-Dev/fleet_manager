from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, time
from decimal import Decimal, ROUND_HALF_UP
from typing import Any, Dict, Iterable, List, Optional, Tuple

from fastapi import HTTPException, status
from sqlalchemy import or_, func
from sqlalchemy.orm import Session

from app.models.booking import Booking, BookingStatusEnum
from app.models.costing import (
    CostCenter,
    CostCenterAssignment,
    GarageConfig,
    RateCard,
    RateCardDistanceSlab,
    RateCardSlot,
    RouteBookingCost,
    RouteCost,
    RouteCostAllocation,
    RouteCostLineItem,
    RouteExpense,
)
from app.models.employee import Employee
from app.models.route_management import RouteManagement, RouteManagementBooking, RouteManagementStatusEnum
from app.models.shift import Shift
from app.models.vehicle import Vehicle
from app.models.vehicle_type import VehicleType
from app.models.vendor import Vendor
from app.utils.response_utils import ResponseWrapper


MONEY = Decimal("0.01")
MEASURE = Decimal("0.001")
PERCENT = Decimal("0.0001")


def _value(value: Any) -> Any:
    return value.value if hasattr(value, "value") else value


def dec(value: Any) -> Decimal:
    if value is None:
        return Decimal("0")
    if isinstance(value, Decimal):
        return value
    return Decimal(str(value))


def money(value: Any) -> Decimal:
    return dec(value).quantize(MONEY, rounding=ROUND_HALF_UP)


def measure(value: Any) -> Decimal:
    return dec(value).quantize(MEASURE, rounding=ROUND_HALF_UP)


def percent(value: Any) -> Decimal:
    return dec(value).quantize(PERCENT, rounding=ROUND_HALF_UP)


def json_number(value: Any) -> float:
    return float(dec(value))


def enum_value(value: Any) -> str:
    raw = _value(value)
    return str(raw) if raw is not None else ""


def http_error(status_code: int, message: str, error_code: str, details: Optional[Dict[str, Any]] = None) -> HTTPException:
    return HTTPException(
        status_code=status_code,
        detail=ResponseWrapper.error(message=message, error_code=error_code, details=details),
    )


@dataclass
class CostingContext:
    route: RouteManagement
    vehicle: Vehicle
    vehicle_type: VehicleType
    vendor: Vendor
    shift: Optional[Shift]
    booking_date: date
    rate_card: RateCard
    slot: RateCardSlot
    distance_slab: Optional[RateCardDistanceSlab]
    garage_config: Optional[GarageConfig]


class CostingService:
    """Route costing rules kept outside routers for testability."""

    @staticmethod
    def resolve_route_context(db: Session, route_id: int, tenant_id: str) -> Tuple[RouteManagement, List[Tuple[RouteManagementBooking, Booking]]]:
        route = (
            db.query(RouteManagement)
            .filter(RouteManagement.route_id == route_id, RouteManagement.tenant_id == tenant_id)
            .first()
        )
        if not route:
            raise http_error(status.HTTP_404_NOT_FOUND, "Route not found for this tenant", "ROUTE_NOT_FOUND")

        route_bookings = (
            db.query(RouteManagementBooking, Booking)
            .join(Booking, Booking.booking_id == RouteManagementBooking.booking_id)
            .filter(RouteManagementBooking.route_id == route.route_id, Booking.tenant_id == tenant_id)
            .order_by(RouteManagementBooking.order_id.asc())
            .all()
        )
        if not route_bookings:
            raise http_error(status.HTTP_400_BAD_REQUEST, "Route has no bookings", "ROUTE_HAS_NO_BOOKINGS")

        return route, route_bookings

    @staticmethod
    def resolve_booking_date(bookings: List[Booking]) -> date:
        for booking in bookings:
            if booking.booking_date:
                return booking.booking_date
        return date.today()

    @staticmethod
    def resolve_cost_center_for_booking(db: Session, booking: Booking, as_of: date) -> CostCenter:
        if booking.cost_center_id:
            cc = (
                db.query(CostCenter)
                .filter(
                    CostCenter.cost_center_id == booking.cost_center_id,
                    CostCenter.tenant_id == booking.tenant_id,
                    CostCenter.is_active == True,
                )
                .first()
            )
            if cc:
                return cc

        scopes: List[Tuple[str, str]] = [("employee", str(booking.employee_id))]
        if booking.team_id:
            scopes.append(("team", str(booking.team_id)))
        scopes.append(("tenant", str(booking.tenant_id)))

        for scope_type, scope_id in scopes:
            assignment = (
                db.query(CostCenterAssignment)
                .join(CostCenter, CostCenter.cost_center_id == CostCenterAssignment.cost_center_id)
                .filter(
                    CostCenterAssignment.tenant_id == booking.tenant_id,
                    CostCenterAssignment.scope_type == scope_type,
                    CostCenterAssignment.scope_id == scope_id,
                    CostCenterAssignment.is_active == True,
                    CostCenterAssignment.effective_from <= as_of,
                    or_(CostCenterAssignment.effective_to.is_(None), CostCenterAssignment.effective_to >= as_of),
                    CostCenter.is_active == True,
                )
                .order_by(CostCenterAssignment.effective_from.desc(), CostCenterAssignment.assignment_id.desc())
                .first()
            )
            if assignment:
                return assignment.cost_center

        default_cc = (
            db.query(CostCenter)
            .filter(CostCenter.tenant_id == booking.tenant_id, CostCenter.is_default == True, CostCenter.is_active == True)
            .order_by(CostCenter.cost_center_id.asc())
            .first()
        )
        if default_cc:
            return default_cc

        unallocated = (
            db.query(CostCenter)
            .filter(CostCenter.tenant_id == booking.tenant_id, CostCenter.code == "UNALLOCATED")
            .first()
        )
        if not unallocated:
            unallocated = CostCenter(
                tenant_id=booking.tenant_id,
                code="UNALLOCATED",
                name="Unallocated",
                description="System fallback for bookings without cost center assignment",
                is_default=True,
                is_active=True,
            )
            db.add(unallocated)
            db.flush()
        return unallocated

    @staticmethod
    def validate_asset_context(db: Session, route: RouteManagement, tenant_id: str) -> Tuple[Vendor, Vehicle, VehicleType]:
        if not route.assigned_vendor_id:
            raise http_error(status.HTTP_400_BAD_REQUEST, "Route has no assigned vendor", "VENDOR_NOT_ASSIGNED")
        if not route.assigned_vehicle_id:
            raise http_error(status.HTTP_400_BAD_REQUEST, "Route has no assigned vehicle", "VEHICLE_NOT_ASSIGNED")

        vendor = db.query(Vendor).filter(Vendor.vendor_id == route.assigned_vendor_id, Vendor.tenant_id == tenant_id).first()
        if not vendor:
            raise http_error(status.HTTP_404_NOT_FOUND, "Assigned vendor not found", "VENDOR_NOT_FOUND")

        vehicle = db.query(Vehicle).filter(Vehicle.vehicle_id == route.assigned_vehicle_id, Vehicle.vendor_id == vendor.vendor_id).first()
        if not vehicle:
            raise http_error(status.HTTP_404_NOT_FOUND, "Assigned vehicle not found", "VEHICLE_NOT_FOUND")

        vehicle_type = db.query(VehicleType).filter(VehicleType.vehicle_type_id == vehicle.vehicle_type_id).first()
        if not vehicle_type:
            raise http_error(status.HTTP_400_BAD_REQUEST, "Assigned vehicle has no vehicle type", "VEHICLE_TYPE_NOT_FOUND")

        return vendor, vehicle, vehicle_type

    @staticmethod
    def route_match_time(route: RouteManagement, shift: Optional[Shift]) -> time:
        if shift and shift.shift_time:
            return shift.shift_time
        if route.actual_start_time:
            return route.actual_start_time.time()
        return datetime.now().time()

    @staticmethod
    def slot_matches(slot: RateCardSlot, booking_date: date, match_time: time, shift_log_type: str) -> bool:
        slot_shift = (slot.shift_log_type or "ANY").upper()
        if slot_shift != "ANY" and slot_shift != (shift_log_type or "").upper():
            return False

        day_type = (slot.day_type or "any").lower()
        actual_day_type = "weekend" if booking_date.weekday() >= 5 else "weekday"
        if day_type not in {"any", actual_day_type}:
            return False

        if not slot.start_time or not slot.end_time:
            return True

        start = slot.start_time
        end = slot.end_time
        if start <= end:
            return start <= match_time <= end
        return match_time >= start or match_time <= end

    @staticmethod
    def matching_distance_slab(slot: RateCardSlot, trip_km: Decimal) -> Optional[RateCardDistanceSlab]:
        slabs = [slab for slab in slot.distance_slabs if slab.is_active]
        if not slabs:
            return None

        def effective_max(slab: RateCardDistanceSlab) -> Decimal:
            return dec(slab.max_km) + dec(slab.buffer_km)

        ordered = sorted(slabs, key=lambda slab: (effective_max(slab), dec(slab.min_km), slab.distance_slab_id or 0))
        for slab in ordered:
            if dec(slab.min_km) <= trip_km <= effective_max(slab):
                return slab
        return None

    @staticmethod
    def resolve_rate_slot(
        db: Session,
        tenant_id: str,
        vendor_id: int,
        vehicle_type_id: int,
        booking_date: date,
        route_time: time,
        shift_log_type: str,
        trip_km: Decimal,
    ) -> Tuple[RateCard, RateCardSlot, Optional[RateCardDistanceSlab]]:
        cards = (
            db.query(RateCard)
            .filter(
                RateCard.tenant_id == tenant_id,
                RateCard.status == "active",
                RateCard.effective_from <= booking_date,
                or_(RateCard.effective_to.is_(None), RateCard.effective_to >= booking_date),
                or_(RateCard.vendor_id == vendor_id, RateCard.vendor_id.is_(None)),
                or_(RateCard.vehicle_type_id == vehicle_type_id, RateCard.vehicle_type_id.is_(None)),
            )
            .all()
        )

        def card_rank(card: RateCard) -> Tuple[int, int, date, int]:
            return (
                1 if card.vendor_id == vendor_id else 0,
                1 if card.vehicle_type_id == vehicle_type_id else 0,
                card.effective_from,
                card.rate_card_id,
            )

        for card in sorted(cards, key=card_rank, reverse=True):
            slots = sorted(card.slots, key=lambda s: (s.priority or 0, s.slot_id or 0), reverse=True)
            for slot in slots:
                if not slot.is_active or not CostingService.slot_matches(slot, booking_date, route_time, shift_log_type):
                    continue
                active_slabs = [slab for slab in slot.distance_slabs if slab.is_active]
                if active_slabs:
                    distance_slab = CostingService.matching_distance_slab(slot, trip_km)
                    if distance_slab:
                        return card, slot, distance_slab
                    continue
                return card, slot, None

        raise http_error(
            status.HTTP_400_BAD_REQUEST,
            "No active rate slot matched this route",
            "RATE_SLOT_NOT_FOUND",
            {"vendor_id": vendor_id, "vehicle_type_id": vehicle_type_id, "booking_date": str(booking_date), "trip_km": json_number(trip_km)},
        )

    @staticmethod
    def resolve_garage_config(db: Session, tenant_id: str, vendor_id: int, vehicle_id: int) -> Optional[GarageConfig]:
        configs = (
            db.query(GarageConfig)
            .filter(
                GarageConfig.tenant_id == tenant_id,
                GarageConfig.is_active == True,
                or_(GarageConfig.vendor_id == vendor_id, GarageConfig.vendor_id.is_(None)),
                or_(GarageConfig.vehicle_id == vehicle_id, GarageConfig.vehicle_id.is_(None)),
            )
            .all()
        )
        if not configs:
            return None

        def rank(config: GarageConfig) -> Tuple[int, int, int]:
            return (
                1 if config.vehicle_id == vehicle_id else 0,
                1 if config.vendor_id == vendor_id else 0,
                config.garage_config_id,
            )

        return sorted(configs, key=rank, reverse=True)[0]

    @staticmethod
    def resolve_distance(route: RouteManagement, source: str, manual_trip_km: Optional[Decimal]) -> Tuple[Decimal, str]:
        planned = dec(route.estimated_total_distance)
        actual = dec(route.actual_total_distance) if route.actual_total_distance is not None else None

        if source == "manual":
            if manual_trip_km is None:
                raise http_error(status.HTTP_400_BAD_REQUEST, "manual_trip_km is required", "MANUAL_DISTANCE_REQUIRED")
            return measure(manual_trip_km), "manual"
        if source == "reference":
            raise http_error(status.HTTP_400_BAD_REQUEST, "Reference KM is not implemented yet", "REFERENCE_KM_NOT_IMPLEMENTED")
        if source == "planned":
            return measure(planned), "planned"
        if source == "actual" and actual is not None:
            return measure(actual), "actual"
        return measure(planned), "planned"

    @staticmethod
    def resolve_trip_hours(route: RouteManagement, manual_trip_hours: Optional[Decimal]) -> Decimal:
        # Current costing is KM-only. Keep the field for response/schema compatibility,
        # but do not calculate or bill trip hours.
        return Decimal("0.000")

    @staticmethod
    def garage_values(config: Optional[GarageConfig], slot: RateCardSlot, km_rate: Optional[Decimal] = None) -> Tuple[Decimal, Decimal, Decimal]:
        if not config or config.method == "none":
            return Decimal("0.000"), Decimal("0.000"), Decimal("0.00")
        if config.method != "fixed":
            raise http_error(
                status.HTTP_400_BAD_REQUEST,
                "Only fixed and none garage methods are implemented in this release",
                "GARAGE_METHOD_NOT_SUPPORTED",
                {"method": config.method},
            )

        garage_km = measure(dec(config.fixed_start_km) + dec(config.fixed_end_km))
        garage_hours = Decimal("0.000")
        garage_amount = Decimal("0")
        if config.apply_same_km_rate:
            garage_amount += garage_km * (dec(km_rate) if km_rate is not None else dec(slot.extra_km_rate))
        return garage_km, garage_hours, money(garage_amount)

    @staticmethod
    def approved_expense_total(db: Session, route_id: int) -> Decimal:
        total = (
            db.query(func.coalesce(func.sum(RouteExpense.amount), 0))
            .filter(RouteExpense.route_id == route_id, RouteExpense.status == "approved")
            .scalar()
        )
        return money(total)

    @staticmethod
    def build_allocations(
        db: Session,
        bookings: Iterable[Booking],
        as_of: date,
        total_amount: Decimal,
        basis: str,
    ) -> List[Dict[str, Any]]:
        eligible_statuses = {
            BookingStatusEnum.REQUEST,
            BookingStatusEnum.SCHEDULED,
            BookingStatusEnum.ONGOING,
            BookingStatusEnum.COMPLETED,
            BookingStatusEnum.NO_SHOW,
        }
        eligible = [booking for booking in bookings if booking.status in eligible_statuses]
        if not eligible:
            eligible = list(bookings)

        groups: Dict[int, Dict[str, Any]] = {}
        for booking in eligible:
            cc = CostingService.resolve_cost_center_for_booking(db, booking, as_of)
            booking.cost_center_id = cc.cost_center_id
            group = groups.setdefault(
                cc.cost_center_id,
                {
                    "cost_center_id": cc.cost_center_id,
                    "cost_center_code": cc.code,
                    "cost_center_name": cc.name,
                    "basis": basis,
                    "booking_count": 0,
                    "booking_ids": [],
                },
            )
            group["booking_count"] += 1
            group["booking_ids"].append(booking.booking_id)

        count = len(eligible) or 1
        allocations = []
        allocated_so_far = Decimal("0.00")
        sorted_groups = list(groups.values())
        for index, group in enumerate(sorted_groups):
            ratio = dec(group["booking_count"]) / dec(count)
            allocation_percent = percent(ratio * Decimal("100"))
            if index == len(sorted_groups) - 1:
                allocated_amount = money(total_amount - allocated_so_far)
            else:
                allocated_amount = money(total_amount * ratio)
                allocated_so_far += allocated_amount
            allocations.append(
                {
                    "cost_center_id": group["cost_center_id"],
                    "cost_center_code": group["cost_center_code"],
                    "cost_center_name": group["cost_center_name"],
                    "basis": basis,
                    "booking_count": group["booking_count"],
                    "allocation_percent": allocation_percent,
                    "allocated_amount": allocated_amount,
                    "details": {"booking_ids": group["booking_ids"]},
                }
            )
        return allocations

    @staticmethod
    def build_booking_costs(
        db: Session,
        route_booking_pairs: Iterable[Tuple[RouteManagementBooking, Booking]],
        as_of: date,
        total_amount: Decimal,
        route_total_km: Decimal,
        route_total_hours: Decimal,
        distance_source: str,
        basis: str,
    ) -> List[Dict[str, Any]]:
        eligible_statuses = {
            BookingStatusEnum.REQUEST,
            BookingStatusEnum.SCHEDULED,
            BookingStatusEnum.ONGOING,
            BookingStatusEnum.COMPLETED,
            BookingStatusEnum.NO_SHOW,
        }
        pairs = [(rmb, booking) for rmb, booking in route_booking_pairs if booking.status in eligible_statuses]
        if not pairs:
            pairs = list(route_booking_pairs)

        count = len(pairs) or 1
        allocated_so_far = Decimal("0.00")
        booking_costs: List[Dict[str, Any]] = []
        for index, (rmb, booking) in enumerate(pairs):
            cc = CostingService.resolve_cost_center_for_booking(db, booking, as_of)
            booking.cost_center_id = cc.cost_center_id
            ratio = Decimal("1") / dec(count)
            allocation_percent = percent(ratio * Decimal("100"))
            if index == count - 1:
                allocated_amount = money(total_amount - allocated_so_far)
            else:
                allocated_amount = money(total_amount * ratio)
                allocated_so_far += allocated_amount

            booking_planned_km = measure(rmb.estimated_distance) if rmb.estimated_distance is not None else None
            booking_actual_km = measure(rmb.actual_distance) if rmb.actual_distance is not None else None
            booking_costs.append(
                {
                    "route_booking_cost_id": None,
                    "route_cost_id": None,
                    "route_id": rmb.route_id,
                    "booking_id": booking.booking_id,
                    "tenant_id": booking.tenant_id,
                    "cost_center_id": cc.cost_center_id,
                    "cost_center_code": cc.code,
                    "cost_center_name": cc.name,
                    "distance_source": distance_source,
                    "allocation_basis": basis,
                    "route_total_km": route_total_km,
                    "route_total_hours": route_total_hours,
                    "booking_planned_km": booking_planned_km,
                    "booking_actual_km": booking_actual_km,
                    "allocation_percent": allocation_percent,
                    "allocated_amount": allocated_amount,
                    "calculation_snapshot": {
                        "employee_id": booking.employee_id,
                        "team_id": booking.team_id,
                        "booking_status": enum_value(booking.status),
                        "route_total_km_used_for_slab": json_number(route_total_km),
                        "booking_planned_km": json_number(booking_planned_km) if booking_planned_km is not None else None,
                        "booking_actual_km": json_number(booking_actual_km) if booking_actual_km is not None else None,
                    },
                }
            )
        return booking_costs

    @staticmethod
    def build_allocations_from_booking_costs(booking_costs: Iterable[Dict[str, Any]], basis: str) -> List[Dict[str, Any]]:
        groups: Dict[int, Dict[str, Any]] = {}
        total_amount = Decimal("0.00")
        total_count = 0
        for item in booking_costs:
            total_count += 1
            total_amount += money(item["allocated_amount"])
            group = groups.setdefault(
                item["cost_center_id"],
                {
                    "cost_center_id": item["cost_center_id"],
                    "cost_center_code": item.get("cost_center_code"),
                    "cost_center_name": item.get("cost_center_name"),
                    "basis": basis,
                    "booking_count": 0,
                    "booking_ids": [],
                    "allocated_amount": Decimal("0.00"),
                },
            )
            group["booking_count"] += 1
            group["booking_ids"].append(item["booking_id"])
            group["allocated_amount"] += money(item["allocated_amount"])

        allocations = []
        for group in groups.values():
            allocation_percent = Decimal("0.0000")
            if total_amount > 0:
                allocation_percent = percent((money(group["allocated_amount"]) / total_amount) * Decimal("100"))
            elif total_count:
                allocation_percent = percent((dec(group["booking_count"]) / dec(total_count)) * Decimal("100"))
            allocations.append(
                {
                    "cost_center_id": group["cost_center_id"],
                    "cost_center_code": group["cost_center_code"],
                    "cost_center_name": group["cost_center_name"],
                    "basis": basis,
                    "booking_count": group["booking_count"],
                    "allocation_percent": allocation_percent,
                    "allocated_amount": money(group["allocated_amount"]),
                    "details": {"booking_ids": group["booking_ids"]},
                }
            )
        return allocations

    @staticmethod
    def calculate_route_cost(
        db: Session,
        route_id: int,
        tenant_id: str,
        *,
        dry_run: bool,
        distance_source: Any,
        allocation_basis: Any,
        manual_trip_km: Optional[Decimal] = None,
        manual_trip_hours: Optional[Decimal] = None,
        comment: Optional[str] = None,
    ) -> Dict[str, Any]:
        source = enum_value(distance_source)
        basis = enum_value(allocation_basis) or "headcount"
        if basis != "headcount":
            raise http_error(status.HTTP_400_BAD_REQUEST, "Only headcount allocation is implemented", "ALLOCATION_BASIS_NOT_SUPPORTED")

        route, route_booking_pairs = CostingService.resolve_route_context(db, route_id, tenant_id)
        bookings = [booking for _, booking in route_booking_pairs]
        if not dry_run and route.status != RouteManagementStatusEnum.COMPLETED:
            raise http_error(status.HTTP_400_BAD_REQUEST, "Route must be completed before final costing", "ROUTE_NOT_COMPLETED")

        existing = db.query(RouteCost).filter(RouteCost.route_id == route_id).first()
        if existing and existing.status == "finalized":
            raise http_error(status.HTTP_409_CONFLICT, "Finalized route cost cannot be recalculated", "ROUTE_COST_FINALIZED")

        booking_date = CostingService.resolve_booking_date(bookings)
        vendor, vehicle, vehicle_type = CostingService.validate_asset_context(db, route, tenant_id)
        shift = db.query(Shift).filter(Shift.shift_id == route.shift_id, Shift.tenant_id == tenant_id).first() if route.shift_id else None
        shift_log_type = enum_value(shift.log_type) if shift and shift.log_type else "ANY"
        route_time = CostingService.route_match_time(route, shift)
        trip_km, resolved_distance_source = CostingService.resolve_distance(route, source, manual_trip_km)
        trip_hours = CostingService.resolve_trip_hours(route, manual_trip_hours)
        rate_card, slot, distance_slab = CostingService.resolve_rate_slot(
            db,
            tenant_id,
            vendor.vendor_id,
            vehicle_type.vehicle_type_id,
            booking_date,
            route_time,
            shift_log_type,
            trip_km,
        )
        garage_config = CostingService.resolve_garage_config(db, tenant_id, vendor.vendor_id, vehicle.vehicle_id)

        selected_km_rate = dec(distance_slab.rate_per_km) if distance_slab else dec(slot.extra_km_rate)
        garage_km, garage_hours, garage_amount = CostingService.garage_values(garage_config, slot, selected_km_rate if distance_slab else None)
        expense_amount = CostingService.approved_expense_total(db, route.route_id)

        night_allowance = dec(slot.night_allowance)
        extra_km = Decimal("0")
        extra_hours = Decimal("0")
        extra_hour_amount = Decimal("0.00")
        waiting_amount = Decimal("0.00")
        escort_amount = money(slot.escort_rate) if route.assigned_escort_id else Decimal("0.00")

        if distance_slab:
            km_charge = money(trip_km * selected_km_rate)
            base_amount_raw = km_charge
            base_amount = money(km_charge + night_allowance)
            extra_km_amount = Decimal("0.00")
        else:
            base_amount_raw = dec(slot.base_amount)
            base_amount = money(base_amount_raw + night_allowance)
            extra_km = max(Decimal("0"), trip_km - dec(slot.base_km))
            extra_km_amount = money(extra_km * selected_km_rate)

        subtotal = money(base_amount + extra_km_amount + extra_hour_amount + garage_amount + waiting_amount + escort_amount + expense_amount)
        tax_amount = money(subtotal * (dec(slot.tax_percent) / Decimal("100")))
        total_amount = money(subtotal + tax_amount)

        variance_percent = None
        planned_km = dec(route.estimated_total_distance)
        if planned_km > 0 and route.actual_total_distance is not None:
            variance_percent = percent(((dec(route.actual_total_distance) - planned_km) / planned_km) * Decimal("100"))

        if distance_slab:
            effective_max_km = dec(distance_slab.max_km) + dec(distance_slab.buffer_km)
            line_items = [
                {
                    "item_type": "KM_SLAB",
                    "description": distance_slab.name,
                    "quantity": trip_km,
                    "rate": money(selected_km_rate),
                    "amount": money(base_amount_raw),
                    "details": {
                        "distance_slab_id": distance_slab.distance_slab_id,
                        "min_km": json_number(distance_slab.min_km),
                        "max_km": json_number(distance_slab.max_km),
                        "buffer_km": json_number(distance_slab.buffer_km),
                        "effective_max_km": json_number(effective_max_km),
                        "pricing_mode": "distance_slab",
                    },
                }
            ]
        else:
            line_items = [
                {
                    "item_type": "BASE_PACKAGE",
                    "description": slot.name,
                    "quantity": Decimal("1.000"),
                    "rate": money(base_amount_raw),
                    "amount": money(base_amount_raw),
                    "details": {"base_km": json_number(slot.base_km), "pricing_mode": "base_extra"},
                }
            ]
        if night_allowance > 0:
            line_items.append({"item_type": "NIGHT_ALLOWANCE", "description": "Night allowance", "quantity": Decimal("1.000"), "rate": money(night_allowance), "amount": money(night_allowance), "details": {}})
        if extra_km > 0 or extra_km_amount > 0:
            line_items.append({"item_type": "EXTRA_KM", "description": "Extra kilometers", "quantity": measure(extra_km), "rate": money(selected_km_rate), "amount": extra_km_amount, "details": {}})
        if garage_amount > 0:
            line_items.append({"item_type": "GARAGE", "description": "Garage KM", "quantity": garage_km, "rate": None, "amount": garage_amount, "details": {}})
        if escort_amount > 0:
            line_items.append({"item_type": "ESCORT", "description": "Escort charge", "quantity": Decimal("1.000"), "rate": money(slot.escort_rate), "amount": escort_amount, "details": {}})
        if expense_amount > 0:
            line_items.append({"item_type": "EXPENSES", "description": "Approved route expenses", "quantity": Decimal("1.000"), "rate": expense_amount, "amount": expense_amount, "details": {}})
        if tax_amount > 0:
            line_items.append({"item_type": "TAX", "description": "Tax", "quantity": dec(slot.tax_percent), "rate": None, "amount": tax_amount, "details": {"tax_percent": json_number(slot.tax_percent)}})

        booking_costs = CostingService.build_booking_costs(
            db,
            route_booking_pairs,
            booking_date,
            total_amount,
            trip_km,
            trip_hours,
            resolved_distance_source,
            basis,
        )
        allocations = CostingService.build_allocations_from_booking_costs(booking_costs, basis)
        snapshot = {
            "comment": comment,
            "pricing_mode": "distance_slab" if distance_slab else "base_extra",
            "rate_card": {"rate_card_id": rate_card.rate_card_id, "name": rate_card.name},
            "slot": {"slot_id": slot.slot_id, "name": slot.name},
            "distance_slab": {
                "distance_slab_id": distance_slab.distance_slab_id,
                "name": distance_slab.name,
                "min_km": json_number(distance_slab.min_km),
                "max_km": json_number(distance_slab.max_km),
                "buffer_km": json_number(distance_slab.buffer_km),
                "effective_max_km": json_number(dec(distance_slab.max_km) + dec(distance_slab.buffer_km)),
                "rate_per_km": json_number(distance_slab.rate_per_km),
            } if distance_slab else None,
            "garage_config_id": garage_config.garage_config_id if garage_config else None,
            "inputs": {
                "distance_source_requested": source,
                "distance_source_used": resolved_distance_source,
                "planned_km": json_number(route.estimated_total_distance),
                "actual_km": json_number(route.actual_total_distance) if route.actual_total_distance is not None else None,
                "trip_km": json_number(trip_km),
                "trip_hours": json_number(trip_hours),
                "garage_km": json_number(garage_km),
                "garage_hours": json_number(garage_hours),
            },
            "outputs": {
                "subtotal": json_number(subtotal),
                "tax_amount": json_number(tax_amount),
                "total_amount": json_number(total_amount),
                "variance_percent": json_number(variance_percent) if variance_percent is not None else None,
            },
        }

        result = {
            "route_cost_id": None,
            "route_id": route.route_id,
            "tenant_id": tenant_id,
            "vendor_id": vendor.vendor_id,
            "vehicle_id": vehicle.vehicle_id,
            "vehicle_type_id": vehicle_type.vehicle_type_id,
            "rate_card_id": rate_card.rate_card_id,
            "slot_id": slot.slot_id,
            "status": "draft",
            "distance_source": resolved_distance_source,
            "trip_km": trip_km,
            "trip_hours": trip_hours,
            "garage_km": garage_km,
            "garage_hours": garage_hours,
            "base_amount": base_amount,
            "extra_km_amount": extra_km_amount,
            "extra_hour_amount": extra_hour_amount,
            "garage_amount": garage_amount,
            "waiting_amount": waiting_amount,
            "escort_amount": escort_amount,
            "expense_amount": expense_amount,
            "tax_amount": tax_amount,
            "total_amount": total_amount,
            "variance_percent": variance_percent,
            "calculation_snapshot": snapshot,
            "calculated_at": datetime.utcnow(),
            "approved_at": None,
            "finalized_at": None,
            "line_items": line_items,
            "allocations": allocations,
            "booking_costs": booking_costs,
        }

        if dry_run:
            return result

        route_cost = existing or RouteCost(route_id=route.route_id, tenant_id=tenant_id)
        if not existing:
            db.add(route_cost)
            db.flush()
        else:
            db.query(RouteCostLineItem).filter(RouteCostLineItem.route_cost_id == route_cost.route_cost_id).delete(synchronize_session=False)
            db.query(RouteCostAllocation).filter(RouteCostAllocation.route_cost_id == route_cost.route_cost_id).delete(synchronize_session=False)
            db.query(RouteBookingCost).filter(RouteBookingCost.route_cost_id == route_cost.route_cost_id).delete(synchronize_session=False)

        for field in [
            "vendor_id",
            "vehicle_id",
            "vehicle_type_id",
            "rate_card_id",
            "slot_id",
            "distance_source",
            "trip_km",
            "trip_hours",
            "garage_km",
            "garage_hours",
            "base_amount",
            "extra_km_amount",
            "extra_hour_amount",
            "garage_amount",
            "waiting_amount",
            "escort_amount",
            "expense_amount",
            "tax_amount",
            "total_amount",
            "variance_percent",
            "calculation_snapshot",
            "calculated_at",
        ]:
            setattr(route_cost, field, result[field])
        route_cost.status = "draft"
        route_cost.approved_at = None
        route_cost.finalized_at = None
        db.flush()

        persisted_line_items = []
        for item in line_items:
            db_item = RouteCostLineItem(route_cost_id=route_cost.route_cost_id, **item)
            db.add(db_item)
            persisted_line_items.append(db_item)

        persisted_allocations = []
        for allocation in allocations:
            db_alloc = RouteCostAllocation(
                route_cost_id=route_cost.route_cost_id,
                cost_center_id=allocation["cost_center_id"],
                basis=allocation["basis"],
                booking_count=allocation["booking_count"],
                allocation_percent=allocation["allocation_percent"],
                allocated_amount=allocation["allocated_amount"],
                details=allocation["details"],
            )
            db.add(db_alloc)
            persisted_allocations.append((db_alloc, allocation))

        persisted_booking_costs = []
        for booking_cost in booking_costs:
            db_booking_cost = RouteBookingCost(
                route_cost_id=route_cost.route_cost_id,
                route_id=booking_cost["route_id"],
                booking_id=booking_cost["booking_id"],
                tenant_id=booking_cost["tenant_id"],
                cost_center_id=booking_cost["cost_center_id"],
                distance_source=booking_cost["distance_source"],
                allocation_basis=booking_cost["allocation_basis"],
                route_total_km=booking_cost["route_total_km"],
                route_total_hours=booking_cost["route_total_hours"],
                booking_planned_km=booking_cost["booking_planned_km"],
                booking_actual_km=booking_cost["booking_actual_km"],
                allocation_percent=booking_cost["allocation_percent"],
                allocated_amount=booking_cost["allocated_amount"],
                calculation_snapshot=booking_cost["calculation_snapshot"],
            )
            db.add(db_booking_cost)
            persisted_booking_costs.append((db_booking_cost, booking_cost))

        db.flush()
        result["route_cost_id"] = route_cost.route_cost_id
        result["line_items"] = [CostingService.line_item_to_dict(item) for item in persisted_line_items]
        result["allocations"] = [CostingService.allocation_to_dict(db_alloc, allocation) for db_alloc, allocation in persisted_allocations]
        result["booking_costs"] = [CostingService.booking_cost_to_dict(db_booking_cost, source) for db_booking_cost, source in persisted_booking_costs]
        return result

    @staticmethod
    def line_item_to_dict(item: RouteCostLineItem) -> Dict[str, Any]:
        return {
            "line_item_id": item.line_item_id,
            "item_type": item.item_type,
            "description": item.description,
            "quantity": item.quantity,
            "rate": item.rate,
            "amount": item.amount,
            "details": item.details or {},
        }

    @staticmethod
    def allocation_to_dict(item: RouteCostAllocation, source: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        source = source or {}
        cc = item.cost_center
        return {
            "allocation_id": item.allocation_id,
            "cost_center_id": item.cost_center_id,
            "cost_center_code": source.get("cost_center_code") or (cc.code if cc else None),
            "cost_center_name": source.get("cost_center_name") or (cc.name if cc else None),
            "basis": item.basis,
            "booking_count": item.booking_count,
            "allocation_percent": item.allocation_percent,
            "allocated_amount": item.allocated_amount,
            "details": item.details or {},
        }

    @staticmethod
    def booking_cost_to_dict(item: RouteBookingCost, source: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        source = source or {}
        cc = item.cost_center
        return {
            "route_booking_cost_id": item.route_booking_cost_id,
            "route_cost_id": item.route_cost_id,
            "route_id": item.route_id,
            "booking_id": item.booking_id,
            "tenant_id": item.tenant_id,
            "cost_center_id": item.cost_center_id,
            "cost_center_code": source.get("cost_center_code") or (cc.code if cc else None),
            "cost_center_name": source.get("cost_center_name") or (cc.name if cc else None),
            "distance_source": item.distance_source,
            "allocation_basis": item.allocation_basis,
            "route_total_km": item.route_total_km,
            "route_total_hours": item.route_total_hours,
            "booking_planned_km": item.booking_planned_km,
            "booking_actual_km": item.booking_actual_km,
            "allocation_percent": item.allocation_percent,
            "allocated_amount": item.allocated_amount,
            "calculation_snapshot": item.calculation_snapshot or {},
        }

    @staticmethod
    def route_cost_to_dict(route_cost: RouteCost) -> Dict[str, Any]:
        return {
            "route_cost_id": route_cost.route_cost_id,
            "route_id": route_cost.route_id,
            "tenant_id": route_cost.tenant_id,
            "vendor_id": route_cost.vendor_id,
            "vehicle_id": route_cost.vehicle_id,
            "vehicle_type_id": route_cost.vehicle_type_id,
            "rate_card_id": route_cost.rate_card_id,
            "slot_id": route_cost.slot_id,
            "status": route_cost.status,
            "distance_source": route_cost.distance_source,
            "trip_km": route_cost.trip_km,
            "trip_hours": route_cost.trip_hours,
            "garage_km": route_cost.garage_km,
            "garage_hours": route_cost.garage_hours,
            "base_amount": route_cost.base_amount,
            "extra_km_amount": route_cost.extra_km_amount,
            "extra_hour_amount": route_cost.extra_hour_amount,
            "garage_amount": route_cost.garage_amount,
            "waiting_amount": route_cost.waiting_amount,
            "escort_amount": route_cost.escort_amount,
            "expense_amount": route_cost.expense_amount,
            "tax_amount": route_cost.tax_amount,
            "total_amount": route_cost.total_amount,
            "variance_percent": route_cost.variance_percent,
            "calculation_snapshot": route_cost.calculation_snapshot or {},
            "calculated_at": route_cost.calculated_at,
            "approved_at": route_cost.approved_at,
            "finalized_at": route_cost.finalized_at,
            "line_items": [CostingService.line_item_to_dict(item) for item in route_cost.line_items],
            "allocations": [CostingService.allocation_to_dict(item) for item in route_cost.allocations],
            "booking_costs": [CostingService.booking_cost_to_dict(item) for item in route_cost.booking_costs],
        }
