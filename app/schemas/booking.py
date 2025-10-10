from pydantic import BaseModel, Field
from datetime import date, datetime
from typing import Optional, List
from enum import Enum


class BookingStatusEnum(str, Enum):
    PENDING = "Pending"
    CONFIRMED = "Confirmed"
    ONGOING = "Ongoing"
    COMPLETED = "Completed"
    CANCELED = "Canceled"


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
    tenant_id: str = Field(..., max_length=50)
    employee_id: int
    booking_date: date
    shift_id: Optional[int] = None


class BookingUpdate(BaseModel):
    shift_id: Optional[int] = None
    team_id: Optional[int] = None
    booking_date: Optional[date] = None
    pickup_latitude: Optional[float] = None
    pickup_longitude: Optional[float] = None
    pickup_location: Optional[str] = None
    drop_latitude: Optional[float] = None
    drop_longitude: Optional[float] = None
    drop_location: Optional[str] = None
    status: Optional[BookingStatusEnum] = None
    reason: Optional[str] = None
    is_active: Optional[bool] = None


class BookingResponse(BookingBase):
    booking_id: int
    created_at: datetime
    updated_at: datetime

    class Config:
        orm_mode = True
