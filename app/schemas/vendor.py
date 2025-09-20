from pydantic import BaseModel, EmailStr, Field
from typing import Optional, List
from datetime import datetime

class VendorBase(BaseModel):
    name: str
    vendor_code: str
    email: EmailStr
    phone: str
    is_active: bool = True

class VendorCreate(VendorBase):
    tenant_id: Optional[str] = None

class VendorUpdate(BaseModel):
    name: Optional[str] = None
    vendor_code: Optional[str] = None
    email: Optional[EmailStr] = None
    phone: Optional[str] = None
    is_active: Optional[bool] = None

class VendorResponse(VendorBase):
    vendor_id: int
    created_at: datetime
    updated_at: datetime

    class Config:
        orm_mode = True

class VendorPaginationResponse(BaseModel):
    total: int
    items: List[VendorResponse]
