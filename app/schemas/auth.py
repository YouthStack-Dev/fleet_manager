from pydantic import BaseModel, EmailStr, Field, validator, ConfigDict
from typing import Optional, List, Dict, Any
from app.schemas.employee import EmployeeResponse
import re

# Password regex pattern: minimum 8 characters with at least one uppercase, lowercase, number, and special character
PASSWORD_PATTERN = r"^(?=.*[a-z])(?=.*[A-Z])(?=.*\d)(?=.*[@$!%*?&])[A-Za-z\d@$!%*?&]{8,}$"

class TokenResponse(BaseModel):
    """Schema for token response"""
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    
    model_config = ConfigDict(from_attributes=True)

class RefreshTokenRequest(BaseModel):
    """Schema for refresh token request"""
    refresh_token: str

class LoginRequest(BaseModel):
    """Schema for employee login"""
    tenant_id: str = Field(..., description="Tenant code")
    username: EmailStr = Field(..., description="Employee email address")
    password: str = Field(..., min_length=8)


class AdminLoginRequest(BaseModel):
    """Schema for admin login"""
    username: EmailStr = Field(..., description="Admin email address")
    password: str = Field(..., min_length=2)
    
class AdminLoginResponse(TokenResponse):
    """Schema for login response with user info"""
    
    
    model_config = ConfigDict(from_attributes=True)
class LoginResponse(TokenResponse):
    """Schema for login response with user info"""
    
    model_config = ConfigDict(from_attributes=True)

class PasswordResetRequest(BaseModel):
    """Schema for password reset request"""
    email: EmailStr

class PasswordChangeRequest(BaseModel):
    """Schema for password change request"""
    current_password: str
    new_password: str
    
    @validator('new_password')
    def password_strength(cls, v):
        if not re.match(PASSWORD_PATTERN, v):
            raise ValueError(
                "Password must be at least 8 characters long and contain "
                "at least one uppercase letter, one lowercase letter, "
                "one number, and one special character"
            )
        return v

class TokenData(BaseModel):
    """Schema for token payload data"""
    user_id: str
    tenant_id: Optional[str] = None
    roles: List[str] = []
    permissions: List[Dict[str, Any]] = []
    
    model_config = ConfigDict(from_attributes=True)
