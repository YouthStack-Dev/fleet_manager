from datetime import datetime
from typing import Optional, List, Literal
from pydantic import BaseModel, EmailStr, Field, ConfigDict


# ------------------------------
# Tenant Base Schema
# ------------------------------
class TenantBase(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    tenant_id: str = Field(..., min_length=3, max_length=50, description="Unique tenant identifier")
    name: str = Field(..., min_length=2, max_length=150, description="Tenant name")
    address: Optional[str] = Field(None, max_length=255, description="Tenant address")
    longitude: Optional[float] = Field(None, ge=-180, le=180, description="Longitude coordinate")
    latitude: Optional[float] = Field(None, ge=-90, le=90, description="Latitude coordinate")
    is_active: bool = Field(default=True, description="Is tenant active?")


# ------------------------------
# Tenant Create Schema
# ------------------------------
class TenantCreate(TenantBase):
    permission_ids: List[int] = Field(
        ..., min_items=1, description="List of permission IDs to assign to tenant admin policy"
    )
    employee_email: EmailStr = Field(..., description="Admin employee email")
    employee_phone: str = Field(..., min_length=7, max_length=20, description="Admin employee phone")
    employee_password: str = Field(..., min_length=8, description="Admin employee password")
    employee_name: Optional[str] = Field(None, max_length=150, description="Admin employee full name")
    employee_address: Optional[str] = Field(None, max_length=255, description="Admin employee address")
    employee_longitude: Optional[float] = Field(None, ge=-180, le=180, description="Employee longitude")
    employee_latitude: Optional[float] = Field(None, ge=-90, le=90, description="Employee latitude")
    employee_code: Optional[str] = Field(None, max_length=50, description="Custom employee code like EMP123")
    employee_gender: Optional[Literal["Male", "Female", "Other"]] = Field(None, description="Employee gender")

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "tenant_id": "tenant_123",
                "name": "Acme Corp",
                "address": "123 Main St, Anytown, USA",
                "longitude": -75.1652,
                "latitude": 39.9526,
                "is_active": True,
                "permission_ids": [1, 2, 3],
                "employee_email": "john@example.com",
                "employee_phone": "+1-234-567-8900",
                "employee_password": "P@ssword123",
                "employee_name": "John Doe",
                "employee_address": "123 Main St, Anytown, USA",
                "employee_longitude": -75.1652,
                "employee_latitude": 39.9526,
                "employee_code": "EMP123",
                "employee_gender": "Male",
            }
        }
    )


# ------------------------------
# Tenant Update Schema
# ------------------------------
class TenantUpdate(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    name: Optional[str] = Field(None, min_length=2, max_length=150)
    address: Optional[str] = Field(None, max_length=255)
    longitude: Optional[float] = Field(None, ge=-180, le=180)
    latitude: Optional[float] = Field(None, ge=-90, le=90)
    is_active: Optional[bool] = None

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "name": "Acme Corp",
                "address": "123 Main St, Anytown, USA",
                "longitude": -75.1652,
                "latitude": 39.9526,
                "is_active": True,
            }
        }
    )


# ------------------------------
# Tenant Response Schema
# ------------------------------
class TenantResponse(TenantBase):
    created_at: datetime = Field(..., description="Record creation timestamp")
    updated_at: datetime = Field(..., description="Record last update timestamp")


# ------------------------------
# Paginated Response Schema
# ------------------------------
class TenantPaginationResponse(BaseModel):
    total: int = Field(..., description="Total number of tenants")
    items: List[TenantResponse] = Field(..., description="List of tenant records")
