from pydantic import BaseModel, ConfigDict
from typing import Optional, List
from datetime import datetime

class RouteBookingBase(BaseModel):
    route_id: int
    booking_id: int
    planned_eta_minutes: Optional[int] = None
    actual_arrival_time: Optional[datetime] = None
    actual_departure_time: Optional[datetime] = None

class RouteBookingCreate(RouteBookingBase):
    pass

class RouteBookingUpdate(BaseModel):
    planned_eta_minutes: Optional[int] = None
    actual_arrival_time: Optional[datetime] = None
    actual_departure_time: Optional[datetime] = None

class RouteBookingResponse(RouteBookingBase):
    route_booking_id: int
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)

class RouteBookingPaginationResponse(BaseModel):
    total: int
    items: List[RouteBookingResponse]
