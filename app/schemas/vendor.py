from pydantic import BaseModel, EmailStr, Field, ConfigDict
from typing import Optional, List
from datetime import datetime

# -------------------
# Base schema
# -------------------
class VendorBase(BaseModel):
    name: str
    vendor_code: str
    email: EmailStr
    phone: str
    is_active: bool = True
    tenant_id: Optional[str] = None  # only set at creation

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "name": "Acme Corp",
                "vendor_code": "ACM123",
                "email": "contact@acme.com",
                "phone": "+1-555-1234",
                "admin_password": "new_secure_password",
                "admin_name": "John Doe",
                "admin_email": "admin@acme.com",
                "admin_phone": "+1-555-6789",
                "is_active": True,
                "tenant_id": "tenant_001"
            }
        }
    )


# -------------------
# Create schema
# -------------------
class VendorCreate(VendorBase):
    admin_name: str
    admin_email: EmailStr
    admin_phone: str
    admin_password: Optional[str] = None


# -------------------
# Update schema
# -------------------
class VendorUpdate(BaseModel):
    tenant_id: Optional[str] = None
    name: Optional[str] = None
    vendor_code: Optional[str] = None
    email: Optional[EmailStr] = None
    phone: Optional[str] = None
    is_active: Optional[bool] = None

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "tenant_id": "tenant_001",
                "name": "Acme Corp Updated",
                "vendor_code": "ACM456",
                "email": "support@acme.com",
                "phone": "+1-555-5678",
                "is_active": False
            }
        }
    )


# -------------------
# Response schema
# -------------------
class VendorResponse(VendorBase):
    vendor_id: int
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(
        from_attributes=True,  # replaces orm_mode=True
        json_schema_extra={
            "example": {
                "vendor_id": 1,
                "name": "Acme Corp",
                "vendor_code": "ACM123",
                "email": "contact@acme.com",
                "phone": "+1-555-1234",
                "is_active": True,
                "tenant_id": "tenant_001",
                "created_at": "2025-09-20T10:00:00Z",
                "updated_at": "2025-09-20T12:00:00Z",
            }
        }
    )



# -------------------
# Pagination wrapper
# -------------------
class VendorPaginationResponse(BaseModel):
    total: int
    items: List[VendorResponse]

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "total": 1,
                "items": [
                    {
                        "vendor_id": 1,
                        "name": "Acme Corp",
                        "vendor_code": "ACM123",
                        "email": "contact@acme.com",
                        "phone": "+1-555-1234",
                        "is_active": True,
                        "tenant_id": "tenant_001",                        
                        "created_at": "2025-09-20T10:00:00Z",
                        "updated_at": "2025-09-20T12:00:00Z",
                    }
                ]
            }
        }
    )
