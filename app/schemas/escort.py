from pydantic import BaseModel, ConfigDict, field_validator
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
    # Optional — if omitted the escort's phone number is used as the default password
    password: Optional[str] = None

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

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "vendor_id": 3,
                "name": "Priya Sharma",
                "phone": "9123456780",
                "email": "priya.sharma@example.com",
                "address": "22 Garden Road, Pune 411001",
                "gender": "FEMALE",
                "is_active": True,
                "is_available": True,
                "password": "Escort@2024"
            }
        }
    )


class EscortSetPassword(BaseModel):
    """Body for the admin set-password endpoint."""
    new_password: str

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "new_password": "NewSecure@2024"
            }
        }
    )


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

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "name": "Priya Sharma",
                "phone": "9123456780",
                "email": "priya.sharma@example.com",
                "gender": "FEMALE",
                "is_active": True,
                "is_available": True
            }
        }
    )


class EscortResponse(EscortBase):
    escort_id: int
    tenant_id: str
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True