from pydantic import BaseModel, ConfigDict, field_validator
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

    # Speed limit configuration (km/h)
    speed_limit_kmph: Optional[float] = 60.0

    # One-trip-per-shift enforcement
    one_trip_per_shift_enabled: bool = True
    auto_move_on_conflict: bool = True

    # Schedule reminder notifications
    schedule_reminder_enabled: bool = False
    schedule_reminder_minutes: int = 30

    # OTA/OTD Delay Classification (Feature 4)
    delay_driver_grace_minutes: int = 10
    delay_employee_grace_minutes: int = 5

    # Driver Duty Hours & Rest-Time Enforcement (Feature 1)
    driver_max_duty_minutes: int = 600
    driver_rest_enforcement: str = "warn"

    @field_validator('escort_required_start_time', 'escort_required_end_time')
    def validate_time_format(cls, v):
        """Validate time format"""
        if v is not None and not isinstance(v, time):
            raise ValueError('Time must be a valid time object')
        return v

    @field_validator('schedule_reminder_minutes')
    def validate_reminder_minutes(cls, v):
        """Reminder window must be between 1 and 240 minutes"""
        if not (1 <= v <= 240):
            raise ValueError('schedule_reminder_minutes must be between 1 and 240')
        return v

    @field_validator('delay_driver_grace_minutes')
    def validate_driver_grace(cls, v):
        """Driver grace must be between 0 and 60 minutes"""
        if not (0 <= v <= 60):
            raise ValueError('delay_driver_grace_minutes must be between 0 and 60')
        return v

    @field_validator('delay_employee_grace_minutes')
    def validate_employee_grace(cls, v):
        """Employee grace must be between 0 and 60 minutes"""
        if not (0 <= v <= 60):
            raise ValueError('delay_employee_grace_minutes must be between 0 and 60')
        return v

    @field_validator('driver_max_duty_minutes')
    def validate_max_duty_minutes(cls, v):
        """Max duty must be between 60 and 1440 minutes (1 hour – 24 hours)"""
        if not (60 <= v <= 1440):
            raise ValueError('driver_max_duty_minutes must be between 60 and 1440')
        return v

    @field_validator('driver_rest_enforcement')
    def validate_rest_enforcement(cls, v):
        """Enforcement mode must be 'warn' or 'block'"""
        if v not in ("warn", "block"):
            raise ValueError("driver_rest_enforcement must be 'warn' or 'block'")
        return v

class TenantConfigCreate(TenantConfigBase):
    """Schema for creating tenant config"""
    tenant_id: str

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "tenant_id": "tenant_123",
                "escort_required_start_time": "22:00:00",
                "escort_required_end_time": "06:00:00",
                "escort_required_for_women": True,
                "login_boarding_otp": True,
                "login_deboarding_otp": True,
                "logout_boarding_otp": True,
                "logout_deboarding_otp": False,
                "speed_limit_kmph": 60.0,
                "schedule_reminder_enabled": True,
                "schedule_reminder_minutes": 30,
                "delay_driver_grace_minutes": 10,
                "delay_employee_grace_minutes": 5,
                "driver_max_duty_minutes": 600,
                "driver_rest_enforcement": "warn"
            }
        }
    )

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

    # Speed limit configuration (km/h)
    speed_limit_kmph: Optional[float] = None

    # One-trip-per-shift enforcement
    one_trip_per_shift_enabled: Optional[bool] = None
    auto_move_on_conflict: Optional[bool] = None

    # Schedule reminder notifications
    schedule_reminder_enabled: Optional[bool] = None
    schedule_reminder_minutes: Optional[int] = None

    # OTA/OTD Delay Classification (Feature 4)
    delay_driver_grace_minutes: Optional[int] = None
    delay_employee_grace_minutes: Optional[int] = None

    # Driver Duty Hours & Rest-Time Enforcement (Feature 1)
    driver_max_duty_minutes: Optional[int] = None
    driver_rest_enforcement: Optional[str] = None

    @field_validator('escort_required_start_time', 'escort_required_end_time')
    def validate_time_format(cls, v):
        """Validate time format"""
        if v is not None and not isinstance(v, time):
            raise ValueError('Time must be a valid time object')
        return v

    @field_validator('schedule_reminder_minutes')
    def validate_reminder_minutes(cls, v):
        """Reminder window must be between 1 and 240 minutes"""
        if v is not None and not (1 <= v <= 240):
            raise ValueError('schedule_reminder_minutes must be between 1 and 240')
        return v

    @field_validator('delay_driver_grace_minutes')
    def validate_driver_grace(cls, v):
        """Driver grace must be between 0 and 60 minutes"""
        if v is not None and not (0 <= v <= 60):
            raise ValueError('delay_driver_grace_minutes must be between 0 and 60')
        return v

    @field_validator('delay_employee_grace_minutes')
    def validate_employee_grace(cls, v):
        """Employee grace must be between 0 and 60 minutes"""
        if v is not None and not (0 <= v <= 60):
            raise ValueError('delay_employee_grace_minutes must be between 0 and 60')
        return v

    @field_validator('driver_max_duty_minutes')
    def validate_max_duty_minutes(cls, v):
        """Max duty must be between 60 and 1440 minutes"""
        if v is not None and not (60 <= v <= 1440):
            raise ValueError('driver_max_duty_minutes must be between 60 and 1440')
        return v

    @field_validator('driver_rest_enforcement')
    def validate_rest_enforcement(cls, v):
        """Enforcement mode must be 'warn' or 'block'"""
        if v is not None and v not in ("warn", "block"):
            raise ValueError("driver_rest_enforcement must be 'warn' or 'block'")
        return v

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "escort_required_start_time": "21:00:00",
                "escort_required_end_time": "05:30:00",
                "escort_required_for_women": True,
                "login_boarding_otp": True,
                "logout_deboarding_otp": True,
                "schedule_reminder_enabled": True,
                "schedule_reminder_minutes": 30,
                "delay_driver_grace_minutes": 10,
                "delay_employee_grace_minutes": 5,
                "driver_max_duty_minutes": 600,
                "driver_rest_enforcement": "warn"
            }
        }
    )

class TenantConfigResponse(TenantConfigBase):
    """Schema for tenant config response"""
    tenant_id: str
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True