from pydantic import BaseModel, Field, EmailStr, validator, field_validator, ConfigDict
import re
from typing import Optional, List
from datetime import datetime

# Regex patterns
PHONE_REGEX = r'^\+?[1-9]\d{1,14}$'  # E.164 format
NAME_REGEX = r'^[a-zA-Z\s\'-]{2,50}$'  # Letters, spaces, hyphens, apostrophes, 2-50 chars
PASSWORD_REGEX = r'^(?=.*[a-z])(?=.*[A-Z])(?=.*\d)(?=.*[@$!%*?&])[A-Za-z\d@$!%*?&]{8,}$'  # Minimum 8 chars with one uppercase, lowercase, number, and special char

class VendorUserBase(BaseModel):
    name: str
    email: EmailStr
    phone: str
    vendor_id: int
    tenant_id: Optional[str] = None
    role_id: Optional[int] = None
    is_active: bool = True

    @field_validator('phone')
    @classmethod
    def validate_phone(cls, v):
        if not re.match(PHONE_REGEX, v):
            raise ValueError('Phone number must be in E.164 format (e.g., +1234567890)')
        return v
    
    @field_validator('name')
    @classmethod
    def validate_name(cls, v):
        if not re.match(NAME_REGEX, v):
            raise ValueError('Name must be 2-50 characters containing only letters, spaces, hyphens, and apostrophes')
        return v
    
class VendorUserCreate(VendorUserBase):
    password: str
    role_id: int = Field(..., description="Required: Role ID to assign to the vendor user")
    
    @field_validator('password')
    @classmethod
    def validate_password(cls, v):
        if not re.match(PASSWORD_REGEX, v):
            raise ValueError('Password must be at least 8 characters with at least one uppercase letter, one lowercase letter, one number, and one special character')
        return v

class VendorUserUpdate(BaseModel):
    name: Optional[str] = None
    email: Optional[EmailStr] = None
    phone: Optional[str] = None
    password: Optional[str] = None
    vendor_id: Optional[int] = None
    role_id: Optional[int] = None
    is_active: Optional[bool] = None
    
    @field_validator('phone')
    @classmethod
    def validate_phone(cls, v):
        if v is not None and not re.match(PHONE_REGEX, v):
            raise ValueError('Phone number must be in E.164 format (e.g., +1234567890)')
        return v
    
    @field_validator('name')
    @classmethod
    def validate_name(cls, v):
        if v is not None and not re.match(NAME_REGEX, v):
            raise ValueError('Name must be 2-50 characters containing only letters, spaces, hyphens, and apostrophes')
        return v
    
    @field_validator('password')
    @classmethod
    def validate_password(cls, v):
        if v is not None and not re.match(PASSWORD_REGEX, v):
            raise ValueError('Password must be at least 8 characters with at least one uppercase letter, one lowercase letter, one number, and one special character')
        return v

class VendorUserResponse(BaseModel):
    vendor_user_id: int
    tenant_id: str
    name: str
    email: EmailStr
    phone: str
    vendor_id: int
    role_id: Optional[int] = None
    is_active: bool
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)  # allows SQLAlchemy model -> Pydantic

class VendorUserPaginationResponse(BaseModel):
    total: int
    items: List[VendorUserResponse]
