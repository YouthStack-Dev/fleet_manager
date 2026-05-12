from pydantic import BaseModel, Field, field_validator, ConfigDict
from typing import Optional, List
from datetime import datetime


# ─────────────────────────────────────────────
# Nodal Point schemas
# ─────────────────────────────────────────────

class NodalPointCreate(BaseModel):
    """Used by admin / tenant-ops to register a new nodal point."""
    tenant_id: Optional[str] = None  # injected from token when not admin
    name: str = Field(..., min_length=2, max_length=150)
    address: Optional[str] = None
    latitude: float = Field(..., ge=-90, le=90)
    longitude: float = Field(..., ge=-180, le=180)
    is_active: bool = True

    @field_validator("latitude", "longitude", mode="before")
    def coerce_float(cls, v):
        try:
            return float(v)
        except (TypeError, ValueError):
            raise ValueError("Coordinate must be a valid number")

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "name": "Gate A Pickup Point",
                "address": "Main Gate, Industrial Area, Sector 5",
                "latitude": 12.9716,
                "longitude": 77.5946,
                "is_active": True,
            }
        }
    )


class NodalPointUpdate(BaseModel):
    """Partial update for a nodal point."""
    name: Optional[str] = Field(None, min_length=2, max_length=150)
    address: Optional[str] = None
    latitude: Optional[float] = Field(None, ge=-90, le=90)
    longitude: Optional[float] = Field(None, ge=-180, le=180)
    is_active: Optional[bool] = None

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "name": "Gate B Pickup Point",
                "is_active": False,
            }
        }
    )


class NodalPointResponse(BaseModel):
    nodal_point_id: int
    tenant_id: str
    name: str
    address: Optional[str] = None
    latitude: float
    longitude: float
    is_active: bool
    created_at: datetime
    updated_at: datetime

    @field_validator("latitude", "longitude", mode="before")
    def coerce_decimal(cls, v):
        if v is None:
            return v
        return float(v)

    model_config = ConfigDict(from_attributes=True)


class NodalPointPaginationResponse(BaseModel):
    total: int
    items: List[NodalPointResponse]


# ─────────────────────────────────────────────
# Employee ↔ Nodal Point assignment schemas
# ─────────────────────────────────────────────

class EmployeeNodalAssignRequest(BaseModel):
    """
    Assign (or re-assign) a nodal point to an employee.
    When nodal_point_id is omitted the system auto-assigns the nearest active point.
    Set is_overridden=True to record that this was a manual admin choice.
    """
    nodal_point_id: Optional[int] = None  # None → nearest
    is_overridden: bool = False

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "nodal_point_id": 3,
                "is_overridden": True,
            }
        }
    )


class EmployeeNodalAssignmentResponse(BaseModel):
    id: int
    employee_id: int
    nodal_point_id: int
    tenant_id: str
    is_overridden: bool
    nodal_point: Optional[NodalPointResponse] = None
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


# ─────────────────────────────────────────────
# Nearest nodal point response
# ─────────────────────────────────────────────

class NearestNodalPointResponse(NodalPointResponse):
    """Extends the basic response with the calculated distance."""
    distance_km: float
