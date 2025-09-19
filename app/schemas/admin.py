from pydantic import BaseModel, EmailStr, Field
from typing import Optional, List
from datetime import datetime


class AdminBase(BaseModel):
    name: str
    email: EmailStr
    phone: str
    role_id: int
    is_active: bool = True


class AdminCreate(AdminBase):
    password: str = Field(..., min_length=8, description="Hashed password will be stored")


class AdminUpdate(BaseModel):
    name: Optional[str] = None
    email: Optional[EmailStr] = None
    phone: Optional[str] = None
    role_id: Optional[int] = None
    password: Optional[str] = Field(None, min_length=8)
    is_active: Optional[bool] = None


class AdminResponse(AdminBase):
    admin_id: int
    created_at: datetime
    updated_at: datetime

    class Config:
        orm_mode = True


class AdminPaginationResponse(BaseModel):
    total: int
    items: List[AdminResponse]
