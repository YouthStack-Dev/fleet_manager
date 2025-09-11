from pydantic import BaseModel, Field
from typing import Optional, List
from datetime import datetime

class TenantBase(BaseModel):
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
    tenant_id: int
    created_at: datetime
    updated_at: datetime

    class Config:
        orm_mode = True

class TenantPaginationResponse(BaseModel):
    total: int
    items: List[TenantResponse]
