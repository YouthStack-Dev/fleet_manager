from pydantic import BaseModel, ConfigDict, field_validator
from datetime import datetime
from typing import Optional, List


# ---------------------------------------------------------------------------
# Request schemas
# ---------------------------------------------------------------------------

class SpeedViolationCreate(BaseModel):
    """
    Payload sent by the driver app when a speed violation is detected.

    The server automatically resolves tenant_id and driver_id from the
    caller's JWT token.  The caller only needs to supply ride context +
    telemetry data.
    """
    route_id:       Optional[int]   = None   # Active route/ride ID
    vehicle_id:     Optional[int]   = None   # Vehicle assigned to this ride
    speed_recorded: float                    # GPS speed at time of event (km/h)
    latitude:       Optional[float] = None
    longitude:      Optional[float] = None
    recorded_at:    datetime                 # Device timestamp of the event (ISO-8601 with tz)

    @field_validator("speed_recorded")
    @classmethod
    def speed_must_be_positive(cls, v: float) -> float:
        if v < 0:
            raise ValueError("speed_recorded must be a non-negative number")
        return v

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "route_id": 42,
                "vehicle_id": 7,
                "speed_recorded": 87.5,
                "latitude": 28.6139,
                "longitude": 77.2090,
                "recorded_at": "2026-05-12T14:35:00+05:30",
            }
        }
    )


# ---------------------------------------------------------------------------
# Response schemas
# ---------------------------------------------------------------------------

class SpeedViolationResponse(BaseModel):
    """Full detail for a single speed violation."""
    violation_id:   int
    tenant_id:      str
    route_id:       Optional[int]
    driver_id:      Optional[int]
    driver_name:    Optional[str]   = None
    vehicle_id:     Optional[int]
    vehicle_rc:     Optional[str]   = None   # vehicle RC number for quick identification
    speed_recorded: float
    speed_limit:    float
    overspeed_by:   float                    # computed: speed_recorded - speed_limit
    latitude:       Optional[float]
    longitude:      Optional[float]
    recorded_at:    datetime
    created_at:     datetime

    model_config = ConfigDict(from_attributes=True)


class SpeedViolationListResponse(BaseModel):
    """Paginated list of violations."""
    items:       List[SpeedViolationResponse]
    total:       int
    page:        int
    limit:       int
    total_pages: int


class SpeedViolationRouteSummary(BaseModel):
    """
    Aggregated speed-violation summary for a single route/ride.
    Returned by GET /speed-violations/route/{route_id}/summary
    """
    route_id:          int
    total_violations:  int
    driver_id:         Optional[int]
    driver_name:       Optional[str]
    vehicle_id:        Optional[int]
    vehicle_rc:        Optional[str]
    max_speed_recorded: Optional[float]  # highest speed seen across all violations
    avg_speed_recorded: Optional[float]  # average speed across all violations
    speed_limit:       Optional[float]   # limit in effect (from first violation record)
    first_violation_at: Optional[datetime]
    last_violation_at:  Optional[datetime]
    violations:        List[SpeedViolationResponse]  # full detail list
