from pydantic import BaseModel, Field
from typing import Optional, List
from datetime import datetime, date
from enum import Enum

class BookingStatusEnum(str, Enum):
    PENDING = "Pending"
    CONFIRMED = "Confirmed"
    ONGOING = "Ongoing"
    COMPLETED = "Completed"
    CANCELED = "Canceled"

class BookingBase(BaseModel):
    employee_id: int
    shift_id: Optional[int] = None
    booking_date: date
    pickup_latitude: Optional[float] = Field(None, ge=-90, le=90)
    pickup_longitude: Optional[float] = Field(None, ge=-180, le=180)
    pickup_location: Optional[str] = None
    drop_latitude: Optional[float] = Field(None, ge=-90, le=90)
    drop_longitude: Optional[float] = Field(None, ge=-180, le=180)
    drop_location: Optional[str] = None
    status: BookingStatusEnum = BookingStatusEnum.PENDING
    team_id: Optional[int] = None

class BookingCreate(BookingBase):
    pass

class BookingUpdate(BaseModel):
    employee_id: Optional[int] = None
    shift_id: Optional[int] = None
    booking_date: Optional[date] = None
    pickup_latitude: Optional[float] = Field(None, ge=-90, le=90)
    pickup_longitude: Optional[float] = Field(None, ge=-180, le=180)
    pickup_location: Optional[str] = None
    drop_latitude: Optional[float] = Field(None, ge=-90, le=90)
    drop_longitude: Optional[float] = Field(None, ge=-180, le=180)
    drop_location: Optional[str] = None
    status: Optional[BookingStatusEnum] = None
    team_id: Optional[int] = None

class BookingResponse(BookingBase):
    booking_id: int
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True

class BookingPaginationResponse(BaseModel):
    total: int
    items: List[BookingResponse]
