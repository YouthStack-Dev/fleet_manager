from pydantic import BaseModel, ConfigDict
from typing import Optional, List, Dict, Any
from datetime import datetime
from enum import Enum

class RouteStatusEnum(str, Enum):
    PLANNED = "Planned"
    VENDOR_ASSIGNED = "Vendor Assigned"
    DRIVER_ASSIGNED = "Driver Assigned"
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

    model_config = ConfigDict(from_attributes=True)

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

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "route_id": "RT001",
                "tenant_id": "tenant_123",
                "route_code": "MNG-BLR-001",
                "bookings": [
                    {
                        "booking_id": 101,
                        "stop_order": 1,
                        "estimated_pickup_time": "08:15",
                        "estimated_drop_time": "09:00",
                        "distance_from_previous": 0.0,
                        "cumulative_distance": 0.0
                    },
                    {
                        "booking_id": 102,
                        "stop_order": 2,
                        "estimated_pickup_time": "08:30",
                        "estimated_drop_time": "09:15",
                        "distance_from_previous": 5.2,
                        "cumulative_distance": 5.2
                    }
                ]
            }
        }
    )

class RouteManagementUpdate(BaseModel):
    total_distance_km: Optional[float] = None
    total_time_minutes: Optional[float] = None
    bookings: Optional[List[RouteManagementBookingCreate]] = None

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "total_distance_km": 22.5,
                "total_time_minutes": 55.0,
                "bookings": [
                    {
                        "booking_id": 103,
                        "stop_order": 3,
                        "estimated_pickup_time": "08:45",
                        "estimated_drop_time": "09:30"
                    }
                ]
            }
        }
    )

class RouteManagementResponse(RouteManagementBase):
    status: RouteStatusEnum
    is_active: bool
    created_at: datetime
    updated_at: datetime
    route_management_bookings: List[RouteManagementBookingResponse] = []

    model_config = ConfigDict(from_attributes=True)

class RouteEstimations(BaseModel):
    start_time: str
    total_distance_km: str
    total_time_minutes: str

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
