from pydantic import BaseModel, EmailStr, Field
from typing import Optional, List
from datetime import datetime

class VendorBase(BaseModel):
    name: str
    code: Optional[str] = None
    email: Optional[EmailStr] = None
    phone: Optional[str] = None
    is_active: bool = True

class VendorCreate(VendorBase):
    pass

class VendorUpdate(BaseModel):
    name: Optional[str] = None
    code: Optional[str] = None
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
