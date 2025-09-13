from pydantic import BaseModel, Field, EmailStr, validator, ConfigDict
import re
from typing import Optional, List
from datetime import datetime

# Regex patterns
PHONE_REGEX = r'^\+?[1-9]\d{1,14}$'  # E.164 format
NAME_REGEX = r'^[a-zA-Z\s\'-]{2,50}$'  # Letters, spaces, hyphens, apostrophes, 2-50 chars
USERNAME_REGEX = r'^[a-zA-Z0-9_]{3,20}$'  # Alphanumeric and underscores, 3-20 chars
PASSWORD_REGEX = r'^(?=.*[a-z])(?=.*[A-Z])(?=.*\d)(?=.*[@$!%*?&])[A-Za-z\d@$!%*?&]{8,}$'  # Minimum 8 chars with one uppercase, lowercase, number, and special char

class VendorUserBase(BaseModel):
    name: str
    email: EmailStr
    phone: str
    username: str 
    vendor_id: int
    is_active: bool = True

    @validator('phone')
    def validate_phone(cls, v):
        if not re.match(PHONE_REGEX, v):
            raise ValueError('Phone number must be in E.164 format (e.g., +1234567890)')
        return v
    
    @validator('name')
    def validate_name(cls, v):
        if not re.match(NAME_REGEX, v):
            raise ValueError('Name must be 2-50 characters containing only letters, spaces, hyphens, and apostrophes')
        return v
    
    @validator('username')
    def validate_username(cls, v):
        if not re.match(USERNAME_REGEX, v):
            raise ValueError('Username must be 3-20 characters containing only letters, numbers, and underscores')
        return v
    
class VendorUserCreate(VendorUserBase):
    password: str
    
    @validator('password')
    def validate_password(cls, v):
        if not re.match(PASSWORD_REGEX, v):
            raise ValueError('Password must be at least 8 characters with at least one uppercase letter, one lowercase letter, one number, and one special character')
        return v

class VendorUserUpdate(BaseModel):
    name: Optional[str] = None
    email: Optional[EmailStr] = None
    phone: Optional[str] = None
    username: Optional[str] = None
    password: Optional[str] = None
    vendor_id: Optional[int] = None
    is_active: Optional[bool] = None
    
    @validator('phone')
    def validate_phone(cls, v):
        if v is not None and not re.match(PHONE_REGEX, v):
            raise ValueError('Phone number must be in E.164 format (e.g., +1234567890)')
        return v
    
    @validator('name')
    def validate_name(cls, v):
        if v is not None and not re.match(NAME_REGEX, v):
            raise ValueError('Name must be 2-50 characters containing only letters, spaces, hyphens, and apostrophes')
        return v
    
    @validator('username')
    def validate_username(cls, v):
        if v is not None and not re.match(USERNAME_REGEX, v):
            raise ValueError('Username must be 3-20 characters containing only letters, numbers, and underscores')
        return v
    
    @validator('password')
    def validate_password(cls, v):
        if v is not None and not re.match(PASSWORD_REGEX, v):
            raise ValueError('Password must be at least 8 characters with at least one uppercase letter, one lowercase letter, one number, and one special character')
        return v

class VendorUserResponse(BaseModel):
    vendor_user_id: int
    name: str
    email: EmailStr
    phone: str
    username: Optional[str] = None  # Make username optional to handle cases where it's not in the database
    vendor_id: int
    is_active: bool
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)

class VendorUserPaginationResponse(BaseModel):
    total: int
    items: List[VendorUserResponse]
