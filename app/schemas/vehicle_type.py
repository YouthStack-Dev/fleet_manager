from pydantic import BaseModel
from typing import Optional, List
from datetime import datetime

class VehicleTypeBase(BaseModel):
    name: str
    vendor_id: int
    description: Optional[str] = None
    is_active: bool = True

class VehicleTypeCreate(VehicleTypeBase):
    pass

class VehicleTypeUpdate(BaseModel):
    name: Optional[str] = None
    vendor_id: Optional[int] = None
    description: Optional[str] = None
    is_active: Optional[bool] = None

class VehicleTypeResponse(VehicleTypeBase):
    vehicle_type_id: int
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True

class VehicleTypePaginationResponse(BaseModel):
    total: int
    items: List[VehicleTypeResponse]
