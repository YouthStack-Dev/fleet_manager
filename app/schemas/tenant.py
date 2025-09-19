from pydantic import BaseModel, Field
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
    pass

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
