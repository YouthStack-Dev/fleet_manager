from datetime import datetime
import re
from typing import Optional, List
from pydantic import BaseModel, Field, field_validator, ConfigDict

# Regex patterns
PHONE_REGEX = r'^\+?[1-9]\d{1,14}$'  # E.164 format
NAME_REGEX = r'^[a-zA-Z\s\'-]{2,50}$'  # Letters, spaces, hyphens, apostrophes, 2-50 chars
USERNAME_REGEX = r'^[a-zA-Z0-9_]{3,20}$'  # Alphanumeric and underscores, 3-20 chars
PASSWORD_REGEX = r'^(?=.*[a-z])(?=.*[A-Z])(?=.*\d)(?=.*[@$!%*?&])[A-Za-z\d@$!%*?&]{8,}$'  # Minimum 8 chars with one uppercase, lowercase, number, and special char
longitude: Optional[float] = Field(None, ge=-180, le=180, description="Longitude coordinate")
latitude: Optional[float] = Field(None, ge=-90, le=90, description="Latitude coordinate")

# ------------------------------
# Tenant Base Schema
# ------------------------------
class TenantBase(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    tenant_id: str = Field(..., min_length=3, max_length=50, description="Unique tenant identifier")
    name: str = Field(..., min_length=2, max_length=150, description="Tenant name")
    address: str = Field(..., max_length=255, description="Tenant address")
    longitude: float = Field(..., ge=-180, le=180, description="Longitude coordinate")
    latitude: float = Field(..., ge=-90, le=90, description="Latitude coordinate")
    is_active: bool = Field(default=True, description="Is tenant active?")

    @field_validator("tenant_id")
    def validate_tenant_id(cls, v: str):
        if not re.match(USERNAME_REGEX, v):
            raise ValueError("Tenant ID must be 3–50 chars (letters, numbers, underscores)")
        return v
    @field_validator("name")
    def validate_name(cls, v: str):
        if not re.match(NAME_REGEX, v):
            raise ValueError("Name must be 2–50 chars, letters/spaces/hyphens/apostrophes only")
        return v
    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "tenant_id": "tenant_123",
                "name": "Acme Corp",
                "address": "123 Main St, Anytown, USA",
                "longitude": -75.1652,
                "latitude": 39.9526,
                "is_active": True
            }
        }
    )


# ------------------------------
# Tenant Create Schema
# ------------------------------
class TenantCreate(BaseModel):
    tenant_id: str = Field(..., min_length=3, max_length=50, description="Unique tenant identifier")
    name: str = Field(..., min_length=2, max_length=150, description="Tenant name")
    address: str = Field(..., max_length=255, description="Tenant address")
    longitude: float = Field(..., ge=-180, le=180, description="Longitude coordinate")
    latitude: float = Field(..., ge=-90, le=90, description="Latitude coordinate")
    is_active: bool = Field(default=True, description="Is tenant active?")
    # Optional custom name for the auto-created policy package
    package_name: Optional[str] = Field(None, max_length=100, description="Name for the tenant policy package")
    permission_ids: List[int] = Field(
        ..., min_length=1, description="Permission IDs to load into the tenant's default policy package"
    )

    @field_validator("tenant_id")
    def validate_tenant_id(cls, v: str):
        if not re.match(USERNAME_REGEX, v):
            raise ValueError("Tenant ID must be 3–50 chars (letters, numbers, underscores)")
        return v

    @field_validator("name")
    def validate_name(cls, v: str):
        if not re.match(NAME_REGEX, v):
            raise ValueError("Name must be 2–50 chars, letters/spaces/hyphens/apostrophes only")
        return v

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "tenant_id": "acme",
                "name": "Acme Corp",
                "address": "123 Main St, Anytown, USA",
                "longitude": -75.1652,
                "latitude": 39.9526,
                "is_active": True,
                "package_name": "Acme Default Package",
                "permission_ids": [1, 2, 3],
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
    permission_ids: Optional[List[int]] = Field(None, min_length=1, description="List of permission IDs to assign to tenant admin policy")
    is_active: Optional[bool] = None

    @field_validator('name')
    @classmethod
    def validate_name(cls, v):
        if not re.match(NAME_REGEX, v):
            raise ValueError('Name must be 2-50 characters long and can only contain letters, spaces, hyphens, and apostrophes')
        return v
    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "name": "Acme Corp Updated",
                "address": "456 Market St, Metropolis",
                "longitude": -74.0059,
                "latitude": 40.7128,
                "is_active": False,
            }
        }
    )


# ------------------------------
# Tenant Response Schema
# ------------------------------
class TenantResponse(TenantBase):
    created_at: datetime = Field(..., description="Record creation timestamp")
    updated_at: datetime = Field(..., description="Record last update timestamp")

    model_config = ConfigDict(
        from_attributes=True,
        json_schema_extra={
            "example": {
                "tenant_id": "tenant_123",
                "name": "Acme Corp",
                "address": "123 Main St, Anytown, USA",
                "longitude": -75.1652,
                "latitude": 39.9526,
                "is_active": True,
                "created_at": "2025-09-20T10:00:00Z",
                "updated_at": "2025-09-20T12:00:00Z",
            }
        }
    )


# ------------------------------
# Paginated Response Schema
# ------------------------------
class TenantPaginationResponse(BaseModel):
    total: int = Field(..., description="Total number of tenants")
    items: List[TenantResponse] = Field(..., description="List of tenant records")

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "total": 1,
                "items": [
                    {
                        "tenant_id": "tenant_123",
                        "name": "Acme Corp",
                        "address": "123 Main St, Anytown, USA",
                        "longitude": -75.1652,
                        "latitude": 39.9526,
                        "is_active": True,
                        "created_at": "2025-09-20T10:00:00Z",
                        "updated_at": "2025-09-20T12:00:00Z",
                    }
                ]
            }
        }
    )
