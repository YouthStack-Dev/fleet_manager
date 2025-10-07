from pydantic import BaseModel
from typing import Optional, List
from datetime import datetime, date

class VehicleBase(BaseModel):
    vehicle_type_id: int
    vendor_id: Optional[int] = None
    rc_number: str
    driver_id: Optional[int] = None
    rc_expiry_date: Optional[date] = None
    description: Optional[str] = None
    puc_expiry_date: Optional[date] = None
    puc_url: Optional[str] = None
    fitness_expiry_date: Optional[date] = None
    fitness_url: Optional[str] = None
    tax_receipt_date: Optional[date] = None
    tax_receipt_url: Optional[str] = None
    insurance_expiry_date: Optional[date] = None
    insurance_url: Optional[str] = None
    permit_expiry_date: Optional[date] = None
    permit_url: Optional[str] = None
    is_active: bool = True

class VehicleCreate(VehicleBase):
    pass

class VehicleUpdate(BaseModel):
    vehicle_type_id: Optional[int] = None
    driver_id: Optional[int] = None
    rc_number: Optional[str] = None
    rc_expiry_date: Optional[date] = None
    description: Optional[str] = None
    puc_expiry_date: Optional[date] = None
    puc_url: Optional[str] = None
    fitness_expiry_date: Optional[date] = None
    fitness_url: Optional[str] = None
    tax_receipt_date: Optional[date] = None
    tax_receipt_url: Optional[str] = None
    insurance_expiry_date: Optional[date] = None
    insurance_url: Optional[str] = None
    permit_expiry_date: Optional[date] = None
    permit_url: Optional[str] = None
    is_active: Optional[bool] = None

class VehicleResponse(VehicleBase):
    vehicle_id: int
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True

class VehiclePaginationResponse(BaseModel):
    total: int
    items: List[VehicleResponse]
