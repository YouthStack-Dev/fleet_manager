from pydantic import BaseModel
from typing import Optional, List
from datetime import datetime
from enum import Enum

class RouteStatusEnum(str, Enum):
    PLANNED = "Planned"
    ASSIGNED = "Assigned"
    IN_PROGRESS = "InProgress"
    COMPLETED = "Completed"
    CANCELLED = "Cancelled"

class RouteBase(BaseModel):
    shift_id: Optional[int] = None
    route_code: str
    status: RouteStatusEnum = RouteStatusEnum.PLANNED
    planned_distance_km: Optional[float] = None
    planned_duration_minutes: Optional[int] = None
    actual_distance_km: Optional[float] = None
    actual_duration_minutes: Optional[int] = None
    actual_start_time: Optional[datetime] = None
    actual_end_time: Optional[datetime] = None
    optimized_polyline: Optional[str] = None
    assigned_vendor_id: Optional[int] = None
    assigned_vehicle_id: Optional[int] = None
    assigned_driver_id: Optional[int] = None
    is_active: bool = True
    version: int = 1

class RouteCreate(RouteBase):
    pass

class RouteUpdate(BaseModel):
    shift_id: Optional[int] = None
    route_code: Optional[str] = None
    status: Optional[RouteStatusEnum] = None
    planned_distance_km: Optional[float] = None
    planned_duration_minutes: Optional[int] = None
    actual_distance_km: Optional[float] = None
    actual_duration_minutes: Optional[int] = None
    actual_start_time: Optional[datetime] = None
    actual_end_time: Optional[datetime] = None
    optimized_polyline: Optional[str] = None
    assigned_vendor_id: Optional[int] = None
    assigned_vehicle_id: Optional[int] = None
    assigned_driver_id: Optional[int] = None
    is_active: Optional[bool] = None
    version: Optional[int] = None

class RouteResponse(RouteBase):
    route_id: int
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True

class RoutePaginationResponse(BaseModel):
    total: int
    items: List[RouteResponse]
