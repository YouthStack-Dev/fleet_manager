from pydantic import BaseModel, Field, field_validator
from datetime import date, datetime
from typing import Optional, List
from enum import Enum


class BookingStatusEnum(str, Enum):
    PENDING = "Pending"
    CONFIRMED = "Confirmed"
    ONGOING = "Ongoing"
    COMPLETED = "Completed"
    CANCELLED = "Cancelled"
    NO_SHOW = "No-Show"


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
    status: Optional[BookingStatusEnum] = BookingStatusEnum.PENDING
    reason: Optional[str] = None
    is_active: Optional[bool] = True


class BookingCreate(BaseModel):
    tenant_id: Optional[str] = None
    employee_id: int
    booking_dates: List[date] 
    shift_id: int
    @field_validator("booking_date", check_fields=False)
    def validate_booking_date_not_past(cls, v):
        if v < date.today():
            raise ValueError("Booking date cannot be in the past")
        return v

class BookingUpdate(BaseModel):
    status: Optional[BookingStatusEnum] = None
    reason: Optional[str] = None


class BookingResponse(BookingBase):
    booking_id: int
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True
