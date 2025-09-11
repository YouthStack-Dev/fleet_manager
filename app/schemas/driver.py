from pydantic import BaseModel, EmailStr, Field
from typing import Optional, List
from datetime import datetime, date
from enum import Enum

class GenderEnum(str, Enum):
    MALE = "Male"
    FEMALE = "Female"
    OTHER = "Other"

class VerificationStatusEnum(str, Enum):
    PENDING = "Pending"
    APPROVED = "Approved"
    REJECTED = "Rejected"

class DriverBase(BaseModel):
    name: str
    code: str
    email: EmailStr
    phone: str
    vendor_id: int
    gender: Optional[GenderEnum] = None
    date_of_joining: Optional[date] = None
    date_of_birth: Optional[date] = None
    permanent_address: Optional[str] = None
    current_address: Optional[str] = None
    
    bg_verify_status: Optional[VerificationStatusEnum] = None
    bg_verify_date: Optional[date] = None
    bg_verify_url: Optional[str] = None
    
    police_verify_status: Optional[VerificationStatusEnum] = None
    police_verify_date: Optional[date] = None
    police_verify_url: Optional[str] = None
    
    medical_verify_status: Optional[VerificationStatusEnum] = None
    medical_verify_date: Optional[date] = None
    medical_verify_url: Optional[str] = None
    
    training_verify_status: Optional[VerificationStatusEnum] = None
    training_verify_date: Optional[date] = None
    training_verify_url: Optional[str] = None
    
    eye_verify_status: Optional[VerificationStatusEnum] = None
    eye_verify_date: Optional[date] = None
    eye_verify_url: Optional[str] = None
    
    license_number: Optional[str] = None
    license_expiry_date: Optional[date] = None
    
    induction_status: Optional[VerificationStatusEnum] = None
    induction_date: Optional[date] = None
    induction_url: Optional[str] = None
    
    badge_number: Optional[str] = None
    badge_expiry_date: Optional[date] = None
    badge_url: Optional[str] = None
    
    alt_govt_id_number: Optional[str] = None
    alt_govt_id_type: Optional[str] = None
    alt_govt_id_url: Optional[str] = None
    
    photo_url: Optional[str] = None
    is_active: bool = True

class DriverCreate(DriverBase):
    password: str

class DriverUpdate(BaseModel):
    name: Optional[str] = None
    code: Optional[str] = None
    email: Optional[EmailStr] = None
    phone: Optional[str] = None
    vendor_id: Optional[int] = None
    gender: Optional[GenderEnum] = None
    password: Optional[str] = None
    date_of_joining: Optional[date] = None
    date_of_birth: Optional[date] = None
    permanent_address: Optional[str] = None
    current_address: Optional[str] = None
    
    bg_verify_status: Optional[VerificationStatusEnum] = None
    bg_verify_date: Optional[date] = None
    bg_verify_url: Optional[str] = None
    
    police_verify_status: Optional[VerificationStatusEnum] = None
    police_verify_date: Optional[date] = None
    police_verify_url: Optional[str] = None
    
    medical_verify_status: Optional[VerificationStatusEnum] = None
    medical_verify_date: Optional[date] = None
    medical_verify_url: Optional[str] = None
    
    training_verify_status: Optional[VerificationStatusEnum] = None
    training_verify_date: Optional[date] = None
    training_verify_url: Optional[str] = None
    
    eye_verify_status: Optional[VerificationStatusEnum] = None
    eye_verify_date: Optional[date] = None
    eye_verify_url: Optional[str] = None
    
    license_number: Optional[str] = None
    license_expiry_date: Optional[date] = None
    
    induction_status: Optional[VerificationStatusEnum] = None
    induction_date: Optional[date] = None
    induction_url: Optional[str] = None
    
    badge_number: Optional[str] = None
    badge_expiry_date: Optional[date] = None
    badge_url: Optional[str] = None
    
    alt_govt_id_number: Optional[str] = None
    alt_govt_id_type: Optional[str] = None
    alt_govt_id_url: Optional[str] = None
    
    photo_url: Optional[str] = None
    is_active: Optional[bool] = None

class DriverResponse(DriverBase):
    driver_id: int
    created_at: datetime
    updated_at: datetime

    class Config:
        orm_mode = True

class DriverPaginationResponse(BaseModel):
    total: int
    items: List[DriverResponse]
