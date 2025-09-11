from pydantic import BaseModel, EmailStr
from typing import Optional, List
from datetime import datetime

class VendorUserBase(BaseModel):
    name: str
    email: EmailStr
    phone: str
    vendor_id: int
    is_active: bool = True

class VendorUserCreate(VendorUserBase):
    password: str

class VendorUserUpdate(BaseModel):
    name: Optional[str] = None
    email: Optional[EmailStr] = None
    phone: Optional[str] = None
    vendor_id: Optional[int] = None
    password: Optional[str] = None
    is_active: Optional[bool] = None

class VendorUserResponse(VendorUserBase):
    vendor_user_id: int
    created_at: datetime
    updated_at: datetime

    class Config:
        orm_mode = True

class VendorUserPaginationResponse(BaseModel):
    total: int
    items: List[VendorUserResponse]
