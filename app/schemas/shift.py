from pydantic import BaseModel, field_validator, model_serializer
from typing import Optional, List, Any
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
    tenant_id: Optional[str] = None
    shift_code: str
    log_type: ShiftLogTypeEnum
    shift_time: Any  # Accept both time and str, serialize to str
    pickup_type: Optional[PickupTypeEnum] = None
    gender: Optional[GenderEnum] = None
    waiting_time_minutes: int = 0
    is_active: bool = True

class ShiftCreate(BaseModel):
    tenant_id: Optional[str] = None
    shift_code: str
    log_type: ShiftLogTypeEnum
    shift_time: str
    pickup_type: PickupTypeEnum
    gender: Optional[GenderEnum] = None
    waiting_time_minutes: int = 0
    is_active: bool = True


    @field_validator("shift_time")
    def validate_shift_time(cls, v):
        try:
            return datetime.strptime(v, "%H:%M").time()
        except ValueError:
            raise ValueError("shift_time must be in HH:MM format")

class ShiftUpdate(BaseModel):
    shift_code: Optional[str] = None
    log_type: Optional[ShiftLogTypeEnum] = None
    shift_time: Optional[str] = None
    pickup_type: Optional[PickupTypeEnum] = None
    gender: Optional[GenderEnum] = None
    waiting_time_minutes: Optional[int] = None
    is_active: Optional[bool] = None

    @field_validator("shift_time")
    def validate_shift_time(cls, v):
        if v is None:
            return v
        try:
            return datetime.strptime(v, "%H:%M").time()
        except ValueError:
            raise ValueError("shift_time must be in HH:MM format")
        
class ShiftResponse(ShiftBase):
    shift_id: int
    created_at: datetime
    updated_at: datetime

    @model_serializer(mode='wrap')
    def serialize_model(self, serializer):
        """Custom serializer to handle time object conversion"""
        data = serializer(self)
        # Convert shift_time from time object to string
        if 'shift_time' in data and data['shift_time'] is not None:
            shift_time = data['shift_time']
            if isinstance(shift_time, time):
                data['shift_time'] = shift_time.strftime("%H:%M")
        return data

    class Config:
        from_attributes = True

class ShiftPaginationResponse(BaseModel):
    total: int
    items: List[ShiftResponse]
