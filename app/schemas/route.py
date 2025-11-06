from pydantic import BaseModel
from typing import Optional, List, Dict
from datetime import datetime
from enum import Enum

class RouteStatusEnum(str, Enum):
    PLANNED = "Planned"
    ASSIGNED = "Assigned"
    ONGOING = "Ongoing"
    COMPLETED = "Completed"
    CANCELLED = "Cancelled"

class RouteManagementBookingBase(BaseModel):
    booking_id: int
    stop_order: int
    estimated_pickup_time: Optional[str] = None
    estimated_drop_time: Optional[str] = None
    distance_from_previous: Optional[float] = None
    cumulative_distance: Optional[float] = None

class RouteManagementBookingCreate(RouteManagementBookingBase):
    pass

class RouteManagementBookingResponse(RouteManagementBookingBase):
    id: int
    route_id: str
    created_at: datetime

    class Config:
        from_attributes = True

class RouteManagementBase(BaseModel):
    route_id: int  # Changed from str to int
    tenant_id: str
    route_code: str
    total_distance_km: Optional[float] = None
    total_time_minutes: Optional[float] = None

class RouteManagementCreate(BaseModel):
    route_id: str
    tenant_id: str
    route_code: str
    bookings: List[RouteManagementBookingCreate]

class RouteManagementUpdate(BaseModel):
    total_distance_km: Optional[float] = None
    total_time_minutes: Optional[float] = None
    bookings: Optional[List[RouteManagementBookingCreate]] = None

class RouteManagementResponse(RouteManagementBase):
    status: RouteStatusEnum
    is_active: bool
    created_at: datetime
    updated_at: datetime
    route_management_bookings: List[RouteManagementBookingResponse] = []

    class Config:
        from_attributes = True

class RouteEstimations(BaseModel):
    total_distance_km: float
    total_time_minutes: float
    estimated_pickup_times: Dict[int, str]  # booking_id -> time
    estimated_drop_times: Dict[int, str]    # booking_id -> time

# Keep the existing RouteWithEstimations but import BookingResponse properly
class RouteWithEstimations(BaseModel):
    route_id: int  # Changed from str to int
    bookings: List[Dict]  # Use Dict instead of BookingResponse to avoid import issues
    estimations: RouteEstimations

# Legacy aliases for backward compatibility
RouteBookingBase = RouteManagementBookingBase
RouteBookingCreate = RouteManagementBookingCreate
RouteBookingResponse = RouteManagementBookingResponse
RouteBase = RouteManagementBase
RouteCreate = RouteManagementCreate
RouteUpdate = RouteManagementUpdate
RouteResponse = RouteManagementResponse
