from pydantic import BaseModel, field_validator, model_serializer, ConfigDict
from typing import Optional, List, Any
from datetime import datetime, time
from enum import Enum


def _coerce_gender(v):
    """Convert empty string to None so the frontend can send '' instead of null."""
    if v == "" or v is None:
        return None
    return v


def _coerce_female_constraint(v):
    """Convert empty string to None so the frontend can send '' instead of null."""
    if v == "" or v is None:
        return None
    return v


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

class FemaleConstraintEnum(str, Enum):
    """
    Shift-level rule controlling when an escort is deployed for female passengers.

    FIRST_LAST_FEMALE         – escort required if the first OR last stop has a female employee
    SECOND_SECOND_LAST_FEMALE – escort required if the 2nd OR 2nd-last stop has a female employee
    ANY_FEMALE                – escort required if ANY female is on the route
    DISABLE                   – never deploy an escort for this shift (overrides tenant config)
    """
    FIRST_LAST_FEMALE = "First/Last Female"
    SECOND_SECOND_LAST_FEMALE = "Second/Second Last Female"
    ANY_FEMALE = "Any Female"
    DISABLE = "Disable"

class ShiftBase(BaseModel):
    tenant_id: Optional[str] = None
    shift_code: str
    log_type: ShiftLogTypeEnum
    shift_time: Any  # Accept both time and str, serialize to str
    pickup_type: Optional[PickupTypeEnum] = None
    gender: Optional[GenderEnum] = None
    female_constraint: Optional[FemaleConstraintEnum] = None
    waiting_time_minutes: int = 0
    is_active: bool = True

class ShiftCreate(BaseModel):
    tenant_id: Optional[str] = None
    shift_code: str
    log_type: ShiftLogTypeEnum
    shift_time: str
    pickup_type: PickupTypeEnum
    gender: Optional[GenderEnum] = None
    female_constraint: Optional[FemaleConstraintEnum] = None
    waiting_time_minutes: int = 0
    is_active: bool = True

    @field_validator("gender", mode="before")
    @classmethod
    def normalize_gender(cls, v):
        return _coerce_gender(v)

    @field_validator("female_constraint", mode="before")
    @classmethod
    def normalize_female_constraint(cls, v):
        return _coerce_female_constraint(v)

    @field_validator("shift_time")
    def validate_shift_time(cls, v):
        try:
            return datetime.strptime(v, "%H:%M").time()
        except ValueError:
            raise ValueError("shift_time must be in HH:MM format")

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "shift_code": "SHIFT_MRN_001",
                "log_type": "IN",
                "shift_time": "09:00",
                "pickup_type": "Pickup",
                "gender": "Female",
                "female_constraint": "Any Female",
                "waiting_time_minutes": 5,
                "is_active": True
            }
        }
    )

class ShiftUpdate(BaseModel):
    shift_code: Optional[str] = None
    log_type: Optional[ShiftLogTypeEnum] = None
    shift_time: Optional[str] = None
    pickup_type: Optional[PickupTypeEnum] = None
    gender: Optional[GenderEnum] = None
    female_constraint: Optional[FemaleConstraintEnum] = None
    waiting_time_minutes: Optional[int] = None
    is_active: Optional[bool] = None

    @field_validator("gender", mode="before")
    @classmethod
    def normalize_gender(cls, v):
        return _coerce_gender(v)

    @field_validator("female_constraint", mode="before")
    @classmethod
    def normalize_female_constraint(cls, v):
        return _coerce_female_constraint(v)

    @field_validator("shift_time")
    def validate_shift_time(cls, v):
        if v is None:
            return v
        try:
            return datetime.strptime(v, "%H:%M").time()
        except ValueError:
            raise ValueError("shift_time must be in HH:MM format")

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "shift_code": "SHIFT_EVE_002",
                "log_type": "OUT",
                "shift_time": "18:30",
                "pickup_type": "Nodal",
                "gender": None,
                "female_constraint": "First/Last Female",
                "waiting_time_minutes": 10,
                "is_active": True
            }
        }
    )

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

    model_config = ConfigDict(from_attributes=True)

class ShiftPaginationResponse(BaseModel):
    total: int
    items: List[ShiftResponse]
