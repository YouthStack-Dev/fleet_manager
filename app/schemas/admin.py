import re
from pydantic import BaseModel, EmailStr, validator, field_validator, Field, ConfigDict
from typing import Optional, List
from datetime import datetime

PHONE_REGEX = r'^\+?[1-9]\d{1,14}$'  # E.164 format
NAME_REGEX = r'^[a-zA-Z\s\'-]{2,50}$'  # Letters, spaces, hyphens, apostrophes, 2-50 chars
USERNAME_REGEX = r'^[a-zA-Z0-9_]{3,20}$'  # Alphanumeric and underscores, 3-20 chars
PASSWORD_REGEX = r'^(?=.*[a-z])(?=.*[A-Z])(?=.*\d)(?=.*[@$!%*?&])[A-Za-z\d@$!%*?&]{8,}$'  # Minimum 8 chars with one uppercase, lowercase, number, and special char

class AdminBase(BaseModel):
    name: str
    email: EmailStr
    phone: str
    role_id: int
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
            raise ValueError('Name must be 2-50 characters long and can only contain letters, spaces, hyphens, and apostrophes')
        return v

    @field_validator('email')
    @classmethod
    def validate_email(cls, v):
        if not re.match(r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$', v):
            raise ValueError('Invalid email format')
        return v
    
    

class AdminCreate(AdminBase):
    password: str = Field(..., min_length=8, description="Hashed password will be stored")
    @field_validator('password')
    @classmethod
    def validate_password(cls, v):  
        if not re.match(PASSWORD_REGEX, v):
            raise ValueError('Password must be at least 8 characters with at least one uppercase letter, one lowercase letter, one number, and one special character')
        return v


class AdminUpdate(BaseModel):
    name: Optional[str] = None
    email: Optional[EmailStr] = None
    phone: Optional[str] = None
    role_id: Optional[int] = None
    password: Optional[str] = Field(None, min_length=8)
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
            raise ValueError('Name must be 2-50 characters long and can only contain letters, spaces, hyphens, and apostrophes')
        return v
    @field_validator('email')
    @classmethod
    def validate_email(cls, v):
        if v is not None and not re.match(r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$', v):
            raise ValueError('Invalid email format')
        return v
    @field_validator('password')
    @classmethod
    def validate_password(cls, v):
        if v is not None and not re.match(PASSWORD_REGEX, v):
            raise ValueError('Password must be at least 8 characters with at least one uppercase letter, one lowercase letter, one number, and one special character')
        return v

class AdminResponse(AdminBase):
    admin_id: int
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class AdminPaginationResponse(BaseModel):
    total: int
    items: List[AdminResponse]
