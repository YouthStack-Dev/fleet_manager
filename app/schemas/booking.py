from pydantic import BaseModel, Field, field_validator, ConfigDict
from datetime import date, datetime, time
from typing import Optional, List
from enum import Enum


class BookingStatusEnum(str, Enum):
    REQUEST = "Request"
    SCHEDULED = "Scheduled"
    ONGOING = "Ongoing"
    COMPLETED = "Completed"
    CANCELLED = "Cancelled"
    NO_SHOW = "No-Show"
    EXPIRED = "Expired"

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "REQUEST": "Request",
                "SCHEDULED": "Scheduled",
                "ONGOING": "Ongoing",
                "COMPLETED": "Completed",
                "CANCELLED": "Cancelled",
                "NO_SHOW": "No-Show",
                "EXPIRED": "Expired",
            }
        }
    )


class BookingTypeEnum(str, Enum):
    REGULAR = "regular"
    ADHOC = "adhoc"
    MEDICAL_EMERGENCY = "medical_emergency"

    class Config:
        schema_extra = {
            "example": {
                "REGULAR": "regular",
                "ADHOC": "adhoc",
                "MEDICAL_EMERGENCY": "medical_emergency",
            }
        }


class BookingBase(BaseModel):
    tenant_id: str
    employee_id: int
    employee_code: str
    shift_id: Optional[int] = None
    team_id: Optional[int] = None
    booking_date: date
    pickup_latitude: Optional[float] = None
    pickup_longitude: Optional[float] = None
    pickup_location: Optional[str] = None
    drop_latitude: Optional[float] = None
    drop_longitude: Optional[float] = None
    drop_location: Optional[str] = None
    status: Optional[BookingStatusEnum] = BookingStatusEnum.REQUEST
    booking_type: Optional[BookingTypeEnum] = BookingTypeEnum.REGULAR
    reason: Optional[str] = None
    boarding_otp: Optional[int] = None
    deboarding_otp: Optional[int] = None
    is_active: Optional[bool] = True


class BookingCreate(BaseModel):
    tenant_id: Optional[str] = None
    employee_id: int
    booking_dates: List[date] = Field(..., min_length=1)
    shift_id: int
    booking_type: Optional[BookingTypeEnum] = BookingTypeEnum.REGULAR

    @field_validator("booking_dates")
    def validate_booking_dates_not_empty(cls, v):
        if not v:
            raise ValueError("booking_dates must contain at least one date")
        return v

    @field_validator("booking_date", check_fields=False)
    def validate_booking_date_not_past(cls, v):
        if v < date.today():
            raise ValueError("Booking date cannot be in the past")
        return v

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "employee_id": 5,
                "booking_dates": ["2026-04-15", "2026-04-16", "2026-04-17"],
                "shift_id": 3,
                "booking_type": "regular"
            }
        }
    )

class BulkAllEmployeesBookingCreate(BaseModel):
    """Request body for booking all (or selected) employees for a shift on a given date."""
    tenant_id: Optional[str] = None
    employee_ids: Optional[List[int]] = Field(
        default=None,
        description="List of employee IDs to book. If omitted or empty, all active employees are booked.",
    )
    shift_id: int
    booking_date: date
    booking_type: Optional[BookingTypeEnum] = BookingTypeEnum.REGULAR

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "tenant_id": "HS001",
                "employee_ids": [],
                "shift_id": 3,
                "booking_date": "2026-05-22",
                "booking_type": "regular",
            }
        }
    )


class UpdateBookingRequest(BaseModel):
    shift_id: Optional[int] = None

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "shift_id": 4
            }
        }
    )

class BookingUpdate(BaseModel):
    status: Optional[BookingStatusEnum] = None
    reason: Optional[str] = None

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "status": "Cancelled",
                "reason": "Employee working from home"
            }
        }
    )


class BookingResponse(BookingBase):
    booking_id: int
    shift_time: Optional[time] = None
    route_details: Optional[dict] = None
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)
