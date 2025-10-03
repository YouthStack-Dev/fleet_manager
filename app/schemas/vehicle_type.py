import re
from datetime import datetime
from typing import Optional, List

from pydantic import BaseModel, Field, ConfigDict, field_validator

# Regex for vehicle type names: allow letters, numbers, spaces, hyphens, up to 100 chars
VEHICLE_TYPE_NAME_REGEX = r'^[a-zA-Z0-9\s-]{2,100}$'


class BaseValidatorsMixin:
    """Reusable validators for VehicleType models."""

    @field_validator("name")
    def validate_name(cls, v: str):
        if not re.match(VEHICLE_TYPE_NAME_REGEX, v):
            raise ValueError(
                "Name must be 2–100 characters, letters/numbers/spaces/hyphens only"
            )
        return v.strip()

    @field_validator("seats")
    def validate_seats(cls, v: int):
        if v <= 0:
            raise ValueError("Seats must be a positive integer")
        if v > 100:
            raise ValueError("Seats cannot exceed 100")  # business rule: limit
        return v

    @field_validator("description")
    def validate_description(cls, v: Optional[str]):
        if v and len(v) > 500:
            raise ValueError("Description must be 500 characters or less")
        return v


class VehicleTypeBase(BaseModel, BaseValidatorsMixin):
    vendor_id: Optional[int] = None  # Will be enforced by role guard / CRUD
    name: str
    seats: int = Field(..., ge=1, le=100, description="Number of seats (1–100)")
    description: Optional[str] = None
    is_active: bool = True

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "vendor_id": 1,
                "name": "Mini Bus",
                "seats": 20,
                "description": "Small bus suitable for city transport",
                "is_active": True,
            }
        }
    )


class VehicleTypeCreate(VehicleTypeBase):
    pass


class VehicleTypeUpdate(BaseModel, BaseValidatorsMixin):
    name: Optional[str] = None
    seats: Optional[int] = Field(None, ge=1, le=100)
    description: Optional[str] = None
    is_active: Optional[bool] = None

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "name": "Updated Mini Bus",
                "seats": 25,
                "description": "Updated description for the vehicle type",
                "is_active": False,
            }
        }
    )


class VehicleTypeResponse(VehicleTypeBase):
    vehicle_type_id: int
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class VehicleTypePaginationResponse(BaseModel):
    total: int
    items: List[VehicleTypeResponse]
