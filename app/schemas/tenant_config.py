from pydantic import BaseModel, field_validator
from datetime import datetime, time
from typing import Optional

class TenantConfigBase(BaseModel):
    """Base schema for tenant configuration"""
    escort_required_start_time: Optional[time] = None
    escort_required_end_time: Optional[time] = None
    escort_required_for_women: bool = True
    
    # OTP requirements (boarding/deboarding flags)
    login_boarding_otp: bool = True
    login_deboarding_otp: bool = True
    logout_boarding_otp: bool = True
    logout_deboarding_otp: bool = True

    @field_validator('escort_required_start_time', 'escort_required_end_time')
    def validate_time_format(cls, v):
        """Validate time format"""
        if v is not None and not isinstance(v, time):
            raise ValueError('Time must be a valid time object')
        return v

class TenantConfigCreate(TenantConfigBase):
    """Schema for creating tenant config"""
    tenant_id: str

class TenantConfigUpdate(BaseModel):
    """Schema for updating tenant config"""
    escort_required_start_time: Optional[time] = None
    escort_required_end_time: Optional[time] = None
    escort_required_for_women: Optional[bool] = None
    
    # OTP requirements (boarding/deboarding flags)
    login_boarding_otp: Optional[bool] = None
    login_deboarding_otp: Optional[bool] = None
    logout_boarding_otp: Optional[bool] = None
    logout_deboarding_otp: Optional[bool] = None

    @field_validator('escort_required_start_time', 'escort_required_end_time')
    def validate_time_format(cls, v):
        """Validate time format"""
        if v is not None and not isinstance(v, time):
            raise ValueError('Time must be a valid time object')
        return v

class TenantConfigResponse(TenantConfigBase):
    """Schema for tenant config response"""
    tenant_id: str
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True