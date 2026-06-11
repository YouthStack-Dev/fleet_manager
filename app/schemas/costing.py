from datetime import date, datetime, time
from decimal import Decimal
from enum import Enum
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class CostCenterScopeEnum(str, Enum):
    EMPLOYEE = "employee"
    TEAM = "team"
    TENANT = "tenant"


class RateCardStatusEnum(str, Enum):
    DRAFT = "draft"
    ACTIVE = "active"
    EXPIRED = "expired"
    ARCHIVED = "archived"


class SlotShiftLogTypeEnum(str, Enum):
    ANY = "ANY"
    IN = "IN"
    OUT = "OUT"


class DayTypeEnum(str, Enum):
    ANY = "any"
    WEEKDAY = "weekday"
    WEEKEND = "weekend"
    HOLIDAY = "holiday"


class GarageMethodEnum(str, Enum):
    NONE = "none"
    FIXED = "fixed"
    VENDOR_GEOCODE = "vendor_geocode"
    EMPTY_LEG = "empty_leg"
    CAB_GEOCODE = "cab_geocode"


class DistanceSourceEnum(str, Enum):
    ACTUAL = "actual"
    PLANNED = "planned"
    REFERENCE = "reference"
    MANUAL = "manual"


class AllocationBasisEnum(str, Enum):
    HEADCOUNT = "headcount"
    PLANNED_KM = "planned_km"
    ACTUAL_KM = "actual_km"
    MANUAL_PERCENT = "manual_percent"


class RouteCostStatusEnum(str, Enum):
    DRAFT = "draft"
    SUBMITTED = "submitted"
    APPROVED = "approved"
    REJECTED = "rejected"
    FINALIZED = "finalized"


class RouteExpenseStatusEnum(str, Enum):
    DRAFT = "draft"
    PENDING_APPROVAL = "pending_approval"
    APPROVED = "approved"
    REJECTED = "rejected"


class RouteExpenseTypeEnum(str, Enum):
    TOLL = "toll"
    PARKING = "parking"
    PERMIT = "permit"
    FUEL = "fuel"
    DRIVER_BATA = "driver_bata"
    OTHER = "other"


class CostCenterCreate(BaseModel):
    tenant_id: Optional[str] = None
    code: str = Field(..., min_length=2, max_length=50)
    name: str = Field(..., min_length=2, max_length=150)
    description: Optional[str] = None
    is_default: bool = False
    is_active: bool = True

    @field_validator("code")
    def normalize_code(cls, value: str) -> str:
        return value.strip().upper()

class CostCenterUpdate(BaseModel):
    code: Optional[str] = Field(None, min_length=2, max_length=50)
    name: Optional[str] = Field(None, min_length=2, max_length=150)
    description: Optional[str] = None
    is_default: Optional[bool] = None
    is_active: Optional[bool] = None

    @field_validator("code")
    def normalize_code(cls, value: Optional[str]) -> Optional[str]:
        return value.strip().upper() if value else value

class CostCenterResponse(BaseModel):
    cost_center_id: int
    tenant_id: str
    code: str
    name: str
    description: Optional[str] = None
    is_default: bool
    is_active: bool
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class CostCenterAssignmentCreate(BaseModel):
    scope_type: CostCenterScopeEnum
    scope_id: str
    effective_from: date
    effective_to: Optional[date] = None
    is_active: bool = True

    @field_validator("effective_to")
    def validate_effective_range(cls, value: Optional[date], info):
        effective_from = info.data.get("effective_from")
        if value and effective_from and value < effective_from:
            raise ValueError("effective_to cannot be before effective_from")
        return value


class CostCenterAssignmentResponse(BaseModel):
    assignment_id: int
    tenant_id: str
    cost_center_id: int
    scope_type: str
    scope_id: str
    effective_from: date
    effective_to: Optional[date]
    is_active: bool
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class RateCardCreate(BaseModel):
    tenant_id: Optional[str] = None
    vendor_id: Optional[int] = None
    vehicle_type_id: Optional[int] = None
    name: str = Field(..., min_length=2, max_length=150)
    currency: str = Field("INR", min_length=3, max_length=3)
    effective_from: date
    effective_to: Optional[date] = None
    status: RateCardStatusEnum = RateCardStatusEnum.DRAFT

    @field_validator("effective_to")
    def validate_effective_range(cls, value: Optional[date], info):
        effective_from = info.data.get("effective_from")
        if value and effective_from and value < effective_from:
            raise ValueError("effective_to cannot be before effective_from")
        return value

    @field_validator("currency")
    def normalize_currency(cls, value: str) -> str:
        return value.strip().upper()


class RateCardUpdate(BaseModel):
    vendor_id: Optional[int] = None
    vehicle_type_id: Optional[int] = None
    name: Optional[str] = Field(None, min_length=2, max_length=150)
    currency: Optional[str] = Field(None, min_length=3, max_length=3)
    effective_from: Optional[date] = None
    effective_to: Optional[date] = None
    status: Optional[RateCardStatusEnum] = None


class RateCardResponse(BaseModel):
    rate_card_id: int
    tenant_id: str
    vendor_id: Optional[int]
    vehicle_type_id: Optional[int]
    name: str
    currency: str
    effective_from: date
    effective_to: Optional[date]
    status: str
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class RateCardDistanceSlabCreate(BaseModel):
    name: str = Field(..., min_length=2, max_length=150)
    min_km: Decimal = Field(Decimal("0"), ge=0)
    max_km: Decimal = Field(..., gt=0)
    buffer_km: Decimal = Field(Decimal("0"), ge=0)
    rate_per_km: Decimal = Field(..., ge=0)
    is_active: bool = True

    @model_validator(mode="after")
    def validate_range(self):
        if self.max_km < self.min_km:
            raise ValueError("max_km cannot be less than min_km")
        return self


class RateCardDistanceSlabResponse(BaseModel):
    distance_slab_id: int
    slot_id: int
    name: str
    min_km: Decimal
    max_km: Decimal
    buffer_km: Decimal
    rate_per_km: Decimal
    is_active: bool
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class RateCardSlotCreate(BaseModel):
    name: str = Field(..., min_length=2, max_length=150)
    shift_log_type: SlotShiftLogTypeEnum = SlotShiftLogTypeEnum.ANY
    day_type: DayTypeEnum = DayTypeEnum.ANY
    start_time: Optional[time] = None
    end_time: Optional[time] = None
    base_amount: Decimal = Field(Decimal("0"), ge=0)
    base_km: Decimal = Field(Decimal("0"), ge=0)
    base_hours: Decimal = Field(Decimal("0"), ge=0)
    extra_km_rate: Decimal = Field(Decimal("0"), ge=0)
    extra_hour_rate: Decimal = Field(Decimal("0"), ge=0)
    waiting_rate_per_hour: Decimal = Field(Decimal("0"), ge=0)
    escort_rate: Decimal = Field(Decimal("0"), ge=0)
    night_allowance: Decimal = Field(Decimal("0"), ge=0)
    tax_percent: Decimal = Field(Decimal("0"), ge=0)
    priority: int = 0
    is_active: bool = True
    distance_slabs: List[RateCardDistanceSlabCreate] = Field(default_factory=list)


class RateCardSlotUpdate(BaseModel):
    name: Optional[str] = Field(None, min_length=2, max_length=150)
    shift_log_type: Optional[SlotShiftLogTypeEnum] = None
    day_type: Optional[DayTypeEnum] = None
    start_time: Optional[time] = None
    end_time: Optional[time] = None
    base_amount: Optional[Decimal] = Field(None, ge=0)
    base_km: Optional[Decimal] = Field(None, ge=0)
    base_hours: Optional[Decimal] = Field(None, ge=0)
    extra_km_rate: Optional[Decimal] = Field(None, ge=0)
    extra_hour_rate: Optional[Decimal] = Field(None, ge=0)
    waiting_rate_per_hour: Optional[Decimal] = Field(None, ge=0)
    escort_rate: Optional[Decimal] = Field(None, ge=0)
    night_allowance: Optional[Decimal] = Field(None, ge=0)
    tax_percent: Optional[Decimal] = Field(None, ge=0)
    priority: Optional[int] = None
    is_active: Optional[bool] = None
    distance_slabs: Optional[List[RateCardDistanceSlabCreate]] = None


class RateCardSlotResponse(BaseModel):
    slot_id: int
    rate_card_id: int
    name: str
    shift_log_type: str
    day_type: str
    start_time: Optional[time]
    end_time: Optional[time]
    base_amount: Decimal
    base_km: Decimal
    base_hours: Decimal
    extra_km_rate: Decimal
    extra_hour_rate: Decimal
    waiting_rate_per_hour: Decimal
    escort_rate: Decimal
    night_allowance: Decimal
    tax_percent: Decimal
    priority: int
    is_active: bool
    distance_slabs: List[RateCardDistanceSlabResponse] = Field(default_factory=list)
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class GarageConfigCreate(BaseModel):
    tenant_id: Optional[str] = None
    vendor_id: Optional[int] = None
    vehicle_id: Optional[int] = None
    method: GarageMethodEnum = GarageMethodEnum.NONE
    garage_latitude: Optional[float] = None
    garage_longitude: Optional[float] = None
    fixed_start_km: Decimal = Field(Decimal("0"), ge=0)
    fixed_end_km: Decimal = Field(Decimal("0"), ge=0)
    fixed_start_hours: Decimal = Field(Decimal("0"), ge=0)
    fixed_end_hours: Decimal = Field(Decimal("0"), ge=0)
    apply_same_km_rate: bool = True
    apply_same_hour_rate: bool = True
    is_active: bool = True


class GarageConfigUpdate(BaseModel):
    vendor_id: Optional[int] = None
    vehicle_id: Optional[int] = None
    method: Optional[GarageMethodEnum] = None
    garage_latitude: Optional[float] = None
    garage_longitude: Optional[float] = None
    fixed_start_km: Optional[Decimal] = Field(None, ge=0)
    fixed_end_km: Optional[Decimal] = Field(None, ge=0)
    fixed_start_hours: Optional[Decimal] = Field(None, ge=0)
    fixed_end_hours: Optional[Decimal] = Field(None, ge=0)
    apply_same_km_rate: Optional[bool] = None
    apply_same_hour_rate: Optional[bool] = None
    is_active: Optional[bool] = None


class GarageConfigResponse(BaseModel):
    garage_config_id: int
    tenant_id: str
    vendor_id: Optional[int]
    vehicle_id: Optional[int]
    method: str
    garage_latitude: Optional[float]
    garage_longitude: Optional[float]
    fixed_start_km: Decimal
    fixed_end_km: Decimal
    fixed_start_hours: Decimal
    fixed_end_hours: Decimal
    apply_same_km_rate: bool
    apply_same_hour_rate: bool
    is_active: bool
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class RouteCostCalculateRequest(BaseModel):
    dry_run: bool = False
    distance_source: DistanceSourceEnum = DistanceSourceEnum.ACTUAL
    allocation_basis: AllocationBasisEnum = AllocationBasisEnum.HEADCOUNT
    manual_trip_km: Optional[Decimal] = Field(None, ge=0)
    manual_trip_hours: Optional[Decimal] = Field(None, ge=0)
    comment: Optional[str] = None


class RouteCostActionRequest(BaseModel):
    comment: Optional[str] = None


class RouteCostLineItemResponse(BaseModel):
    line_item_id: Optional[int] = None
    item_type: str
    description: Optional[str] = None
    quantity: Optional[Decimal] = None
    rate: Optional[Decimal] = None
    amount: Decimal
    details: Dict[str, Any] = {}

    model_config = ConfigDict(from_attributes=True)


class RouteCostAllocationResponse(BaseModel):
    allocation_id: Optional[int] = None
    cost_center_id: int
    cost_center_code: Optional[str] = None
    cost_center_name: Optional[str] = None
    basis: str
    booking_count: int
    allocation_percent: Decimal
    allocated_amount: Decimal
    details: Dict[str, Any] = {}

    model_config = ConfigDict(from_attributes=True)


class RouteBookingCostResponse(BaseModel):
    route_booking_cost_id: Optional[int] = None
    route_cost_id: Optional[int] = None
    route_id: int
    booking_id: int
    tenant_id: str
    cost_center_id: int
    cost_center_code: Optional[str] = None
    cost_center_name: Optional[str] = None
    distance_source: str
    allocation_basis: str
    route_total_km: Decimal
    route_total_hours: Decimal
    booking_planned_km: Optional[Decimal] = None
    booking_actual_km: Optional[Decimal] = None
    allocation_percent: Decimal
    allocated_amount: Decimal
    calculation_snapshot: Dict[str, Any] = {}

    model_config = ConfigDict(from_attributes=True)


class RouteCostResponse(BaseModel):
    route_cost_id: Optional[int] = None
    route_id: int
    tenant_id: str
    vendor_id: Optional[int]
    vehicle_id: Optional[int]
    vehicle_type_id: Optional[int]
    rate_card_id: Optional[int]
    slot_id: Optional[int]
    status: str
    distance_source: str
    trip_km: Decimal
    trip_hours: Decimal
    garage_km: Decimal
    garage_hours: Decimal
    base_amount: Decimal
    extra_km_amount: Decimal
    extra_hour_amount: Decimal
    garage_amount: Decimal
    waiting_amount: Decimal
    escort_amount: Decimal
    expense_amount: Decimal
    tax_amount: Decimal
    total_amount: Decimal
    variance_percent: Optional[Decimal]
    calculation_snapshot: Dict[str, Any]
    calculated_at: Optional[datetime]
    approved_at: Optional[datetime]
    finalized_at: Optional[datetime]
    line_items: List[RouteCostLineItemResponse] = []
    allocations: List[RouteCostAllocationResponse] = []
    booking_costs: List[RouteBookingCostResponse] = []

    model_config = ConfigDict(from_attributes=True)


class RouteExpenseCreate(BaseModel):
    expense_type: RouteExpenseTypeEnum
    amount: Decimal = Field(..., gt=0)
    comment: Optional[str] = None
    attachment_url: Optional[str] = None


class RouteExpenseUpdate(BaseModel):
    expense_type: Optional[RouteExpenseTypeEnum] = None
    amount: Optional[Decimal] = Field(None, gt=0)
    comment: Optional[str] = None
    attachment_url: Optional[str] = None


class RouteExpenseRejectRequest(BaseModel):
    reason: str = Field(..., min_length=2)


class RouteExpenseResponse(BaseModel):
    expense_id: int
    route_id: int
    tenant_id: str
    vendor_id: int
    expense_type: str
    amount: Decimal
    comment: Optional[str]
    attachment_url: Optional[str]
    status: str
    rejection_reason: Optional[str]
    created_by_type: Optional[str]
    created_by_id: Optional[str]
    approved_by_type: Optional[str]
    approved_by_id: Optional[str]
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)
