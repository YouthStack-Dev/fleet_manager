from pydantic import BaseModel, field_validator
from typing import Optional
from datetime import datetime


class EscortBase(BaseModel):
    vendor_id: int
    name: str
    phone: str
    email: Optional[str] = None
    address: Optional[str] = None
    gender: Optional[str] = None
    is_active: bool = True
    is_available: bool = True


class EscortCreate(EscortBase):
    @field_validator('phone')
    def validate_phone(cls, v):
        if not v or len(v) < 10:
            raise ValueError('Phone number must be at least 10 digits')
        return v

    @field_validator('gender')
    def validate_gender(cls, v):
        if v and v.upper() not in ['MALE', 'FEMALE', 'OTHER']:
            raise ValueError('Gender must be MALE, FEMALE, or OTHER')
        return v.upper() if v else v


class EscortUpdate(BaseModel):
    vendor_id: Optional[int] = None
    name: Optional[str] = None
    phone: Optional[str] = None
    email: Optional[str] = None
    address: Optional[str] = None
    gender: Optional[str] = None
    is_active: Optional[bool] = None
    is_available: Optional[bool] = None

    @field_validator('phone')
    def validate_phone(cls, v):
        if v and len(v) < 10:
            raise ValueError('Phone number must be at least 10 digits')
        return v

    @field_validator('gender')
    def validate_gender(cls, v):
        if v and v.upper() not in ['MALE', 'FEMALE', 'OTHER']:
            raise ValueError('Gender must be MALE, FEMALE, or OTHER')
        return v.upper() if v else v


class EscortResponse(EscortBase):
    escort_id: int
    tenant_id: str
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True