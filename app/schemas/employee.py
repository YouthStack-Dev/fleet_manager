import re
from datetime import datetime, date
from enum import Enum
from typing import Optional, List

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator, ValidationInfo, model_validator

# Regex patterns
PHONE_REGEX = r'^\+?[1-9]\d{1,14}$'   # E.164 format
NAME_REGEX = r'^[a-zA-Z\s\'-]{2,50}$'  # Letters, spaces, hyphens, apostrophes
USERNAME_REGEX = r'^[a-zA-Z0-9_]{3,20}$'
PASSWORD_REGEX = r'^(?=.*[a-z])(?=.*[A-Z])(?=.*\d)(?=.*[@$!%*?&])[A-Za-z\d@$!%*?&]{8,}$'


class GenderEnum(str, Enum):
    MALE = "Male"
    FEMALE = "Female"
    OTHER = "Other"

class SpecialNeedsEnum(str, Enum):
    WHEELCHAIR = "Wheelchair"
    PREGNANT = "Pregnant"
    OTHER = "Other"


class BaseValidatorsMixin:
    """Reusable validators for Employee models."""

    @field_validator("phone")
    def validate_phone(cls, v: str):
        if not re.match(PHONE_REGEX, v):
            raise ValueError("Phone must be in E.164 format (e.g., +1234567890)")
        return v
    @field_validator("address")
    def validate_address(cls, v: Optional[str]):
        if v and not re.match(r'^[a-zA-Z0-9\s.,#-]{1,250}$', v):
            raise ValueError("Address must be 250 characters or less")
        return v

    @field_validator("alternate_phone")
    def validate_alternate_phone(cls, v: Optional[str]):
        if v and not re.match(PHONE_REGEX, v):
            raise ValueError("Alternate phone must be in E.164 format")
        return v

    @field_validator("name")
    def validate_name(cls, v: str):
        if not re.match(NAME_REGEX, v):
            raise ValueError("Name must be 2–50 chars, letters/spaces/hyphens/apostrophes only")
        return v

    @field_validator("employee_code")
    def validate_employee_code(cls, v: str):
        if not re.match(USERNAME_REGEX, v):
            raise ValueError("Employee code must be 3–20 chars (letters, numbers, underscores)")
        return v

    @field_validator("password", check_fields=False)
    def validate_password(cls, v: Optional[str]):
        if v and not re.match(PASSWORD_REGEX, v):
            raise ValueError(
                "Password must have min 8 chars, at least one uppercase, one lowercase, one number, and one special char"
            )
        return v

    @field_validator("latitude", "longitude")
    def validate_coordinates(cls, v: float, info: ValidationInfo):
        if v is None:
            return v
        if info.field_name == "latitude" and not (-90 <= v <= 90):
            raise ValueError("Latitude must be between -90 and 90")
        if info.field_name == "longitude" and not (-180 <= v <= 180):
            raise ValueError("Longitude must be between -180 and 180")
        return v

    @model_validator(mode="after")
    def validate_special_needs_dates(self):
        special_needs = self.special_needs
        start_date = self.special_needs_start_date
        end_date = self.special_needs_end_date
        today = date.today()

        if special_needs:
            if not start_date or not end_date:
                raise ValueError("Both start and end dates are required when special_needs is set.")
            if start_date < today:
                raise ValueError("Special needs start date cannot be in the past.")
            if end_date < start_date:
                raise ValueError("Special needs end date must be after start date.")
        else:
            # If no special needs → clear dates
            self.special_needs_start_date = None
            self.special_needs_end_date = None

        return self


class EmployeeBase(BaseModel):
    name: str
    email: EmailStr
    phone: str
    employee_code: str
    team_id: int
    role_id: Optional[int] = None
    tenant_id: Optional[str] = None
    alternate_phone: Optional[str] = None
    special_needs: Optional[str] = None
    special_needs_start_date: Optional[date] = None
    special_needs_end_date: Optional[date] = None
    address: Optional[str] = None
    latitude: Optional[float] = Field(None, ge=-90, le=90)  # Optional to allow null value when creating employee
    longitude: Optional[float] = Field(None, ge=-180, le=180)
    gender: Optional[GenderEnum] = None
    is_active: bool = True

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "name": "John Doe",
                "email": "john@example.com",
                "phone": "+1234567890",
                "employee_code": "jdoe123",
                "team_id": 1,
                "tenant_id": "tenant_123",
                "alternate_phone": "+1987654321",
                "special_needs": "Wheelchair",
                "special_needs_start_date": "2023-01-01",
                "special_needs_end_date": "2023-12-31",
                "address": "123 Main St, Anytown, USA",
                "latitude": 37.7749,
                "longitude": -122.4194,
                "gender": "Male",
                "is_active": True,
            }
        }
    )


class EmployeeCreate(BaseModel, BaseValidatorsMixin):
    name: str
    email: EmailStr
    phone: str
    employee_code: str
    team_id: int
    tenant_id: Optional[str] = None
    alternate_phone: Optional[str] = None
    special_needs: Optional[SpecialNeedsEnum] = None
    special_needs_start_date: Optional[date] = None
    special_needs_end_date: Optional[date] = None
    address: Optional[str] = None
    latitude: Optional[float] = Field(None, ge=-90, le=90)  # Optional to allow null value when creating employee
    longitude: Optional[float] = Field(None, ge=-180, le=180)
    gender: Optional[GenderEnum] = None
    is_active: bool = True
    password: str  # Required when creating
    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "name": "John Doe",
                "email": "john@example.com",
                "phone": "+1234567890",
                "employee_code": "jdoe123",
                "team_id": 1,
                "tenant_id": "tenant_123",
                "alternate_phone": "+1987654321",
                "special_needs": "Wheelchair",
                "special_needs_start_date": "2023-01-01",
                "special_needs_end_date": "2023-12-31",
                "address": "123 Main St, Anytown, USA",
                "latitude": 37.7749,
                "longitude": -122.4194,
                "gender": "Male",
                "is_active": True,
                "password": "P@ssword123",
            }
        }
    )


class EmployeeUpdate(BaseModel, BaseValidatorsMixin):
    name: Optional[str] = None
    email: Optional[EmailStr] = None
    phone: Optional[str] = None
    employee_code: Optional[str] = None
    team_id: Optional[int] = None
    role_id: Optional[int] = None
    alternate_phone: Optional[str] = None
    special_needs: Optional[SpecialNeedsEnum] = None
    special_needs_start_date: Optional[date] = None
    special_needs_end_date: Optional[date] = None
    address: Optional[str] = None
    latitude: Optional[float] = Field(None, ge=-90, le=90)
    longitude: Optional[float] = Field(None, ge=-180, le=180)
    gender: Optional[GenderEnum] = None
    password: Optional[str] = None
    is_active: Optional[bool] = None

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "name": "John Doe Updated",
                "email": "john@example.com",
                "phone": "+1234567890",
                "employee_code": "jdoe456",
                "team_id": 2,
                "role_id": 1,
                "alternate_phone": "+1987654321",
                "special_needs": "Wheelchair",
                "special_needs_start_date": "2023-01-01",
                "special_needs_end_date": "2023-12-31",
                "address": "123 Main St, Anytown, USA",
                "latitude": 37.7749,
                "longitude": -122.4194,
                "gender": "Male",
                "is_active": True,
                "password": "P@ssword123",
            }
        }
    )

class EmployeeResponse(EmployeeBase):
    employee_id: int
    created_at: datetime
    updated_at: datetime
    tenant_latitude: Optional[float] = None
    tenant_longitude: Optional[float] = None
    tenant_address: Optional[str] = None

    model_config = ConfigDict(from_attributes=True)


class EmployeePaginationResponse(BaseModel):
    total: int
    items: List[EmployeeResponse]
