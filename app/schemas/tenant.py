from pydantic import BaseModel, EmailStr, Field
from typing import Optional, List
from datetime import datetime

class TenantBase(BaseModel):
    tenant_id: str
    name: str
    address: Optional[str] = None
    longitude: Optional[float] = Field(None, ge=-180, le=180)
    latitude: Optional[float] = Field(None, ge=-90, le=90)
    is_active: bool = True

class TenantCreate(TenantBase):
    permission_ids: List[int] = Field(..., description="List of permission IDs to assign to tenant admin policy")
    employee_email: EmailStr
    employee_phone: str
    employee_password: str
    employee_name: Optional[str] = None
    employee_address: Optional[str] = None
    employee_longitude: Optional[float] = Field(None, ge=-180, le=180)
    employee_latitude: Optional[float] = Field(None, ge=-90, le=90)
    employee_code: Optional[str] = None
    employee_gender: Optional[str] = None

class TenantUpdate(BaseModel):
    name: Optional[str] = None
    address: Optional[str] = None
    longitude: Optional[float] = Field(None, ge=-180, le=180)
    latitude: Optional[float] = Field(None, ge=-90, le=90)
    is_active: Optional[bool] = None

class TenantResponse(TenantBase):
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True

class TenantPaginationResponse(BaseModel):
    total: int
    items: List[TenantResponse]
