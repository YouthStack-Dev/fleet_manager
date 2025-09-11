from pydantic import BaseModel, EmailStr
from typing import Optional
from datetime import datetime

class AdminBase(BaseModel):
    name: str
    email: EmailStr
    phone: Optional[str] = None
    is_active: bool = True

class AdminCreate(AdminBase):
    password: str

class AdminUpdate(BaseModel):
    name: Optional[str] = None
    email: Optional[EmailStr] = None
    phone: Optional[str] = None
    is_active: Optional[bool] = None
    password: Optional[str] = None

class AdminResponse(AdminBase):
    admin_id: int
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True
