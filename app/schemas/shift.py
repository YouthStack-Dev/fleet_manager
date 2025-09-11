from pydantic import BaseModel
from typing import Optional, List
from datetime import datetime, time
from enum import Enum

class ShiftLogTypeEnum(str, Enum):
    IN = "IN"
    OUT = "OUT"

class PickupTypeEnum(str, Enum):
    PICKUP = "Pickup"
    NODAL = "Nodal"

class GenderEnum(str, Enum):
    MALE = "Male"
    FEMALE = "Female"
    OTHER = "Other"

class ShiftBase(BaseModel):
    shift_code: str
    log_type: ShiftLogTypeEnum
    shift_time: time
    pickup_type: Optional[PickupTypeEnum] = None
    gender: Optional[GenderEnum] = None
    waiting_time_minutes: int = 0
    is_active: bool = True

class ShiftCreate(ShiftBase):
    pass

class ShiftUpdate(BaseModel):
    shift_code: Optional[str] = None
    log_type: Optional[ShiftLogTypeEnum] = None
    shift_time: Optional[time] = None
    pickup_type: Optional[PickupTypeEnum] = None
    gender: Optional[GenderEnum] = None
    waiting_time_minutes: Optional[int] = None
    is_active: Optional[bool] = None

class ShiftResponse(ShiftBase):
    shift_id: int
    created_at: datetime
    updated_at: datetime

    class Config:
        orm_mode = True

class ShiftPaginationResponse(BaseModel):
    total: int
    items: List[ShiftResponse]
