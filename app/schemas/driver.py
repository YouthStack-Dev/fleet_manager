from pydantic import BaseModel, EmailStr, ConfigDict
from typing import Optional, List
from datetime import datetime, date
from enum import Enum


# ---------- ENUMS ----------
class GenderEnum(str, Enum):
    MALE = "Male"
    FEMALE = "Female"
    OTHER = "Other"


class VerificationStatusEnum(str, Enum):
    PENDING = "Pending"
    APPROVED = "Approved"
    REJECTED = "Rejected"
class GovtIDTypeEnum(str, Enum):
    AADHAAR = "Aadhaar"
    PAN = "PAN"
    VOTER_ID = "Voter ID"
    PASSPORT = "Passport"

# ---------- BASE ----------
class DriverBase(BaseModel):
    vendor_id: int
    name: str
    code: str
    email: EmailStr
    phone: str
    gender: Optional[GenderEnum] = None
    date_of_joining: Optional[date] = None
    date_of_birth: Optional[date] = None
    permanent_address: Optional[str] = None
    current_address: Optional[str] = None
    photo_url: Optional[str] = None

    # Verification details
    bg_verify_status: Optional[VerificationStatusEnum] = None
    bg_expiry_date: Optional[date] = None
    bg_verify_url: Optional[str] = None

    police_verify_status: Optional[VerificationStatusEnum] = None
    police_expiry_date: Optional[date] = None
    police_verify_url: Optional[str] = None

    medical_verify_status: Optional[VerificationStatusEnum] = None
    medical_expiry_date: Optional[date] = None
    medical_verify_url: Optional[str] = None

    training_verify_status: Optional[VerificationStatusEnum] = None
    training_expiry_date: Optional[date] = None
    training_verify_url: Optional[str] = None

    eye_verify_status: Optional[VerificationStatusEnum] = None
    eye_expiry_date: Optional[date] = None
    eye_verify_url: Optional[str] = None

    # License info
    license_number: Optional[str] = None
    license_expiry_date: Optional[date] = None
    license_url: Optional[str] = None

    # Badge info
    badge_number: Optional[str] = None
    badge_expiry_date: Optional[date] = None
    badge_url: Optional[str] = None

    # Alternate govt ID
    alt_govt_id_number: Optional[str] = None
    alt_govt_id_type: Optional[str] = None
    alt_govt_id_url: Optional[str] = None

    # Induction
    induction_date: Optional[date] = None
    induction_url: Optional[str] = None

    # System flags
    is_active: bool = True


# ---------- CREATE ----------
class DriverCreate(BaseModel):
    vendor_id: int
    name: str
    code: str
    email: str
    phone: str
    gender: Optional[GenderEnum]
    password: str
    date_of_birth: Optional[date]
    date_of_joining: Optional[date]
    permanent_address: Optional[str]
    current_address: Optional[str]
    photo_url: Optional[str]

    # Verifications
    bg_verify_status: Optional[VerificationStatusEnum]
    bg_expiry_date: Optional[date]
    bg_verify_url: Optional[str]
    police_verify_status: Optional[VerificationStatusEnum]
    police_expiry_date: Optional[date]
    police_verify_url: Optional[str]
    medical_verify_status: Optional[VerificationStatusEnum]
    medical_expiry_date: Optional[date]
    medical_verify_url: Optional[str]
    training_verify_status: Optional[VerificationStatusEnum]
    training_expiry_date: Optional[date]
    training_verify_url: Optional[str]
    eye_verify_status: Optional[VerificationStatusEnum]
    eye_expiry_date: Optional[date]
    eye_verify_url: Optional[str]

    # License & Badge
    license_number: str
    license_expiry_date: date
    license_url: Optional[str]
    badge_number: str
    badge_expiry_date: date
    badge_url: Optional[str]

    # Govt ID
    alt_govt_id_number: str
    alt_govt_id_type: str
    alt_govt_id_url: Optional[str]

    # Induction
    induction_date: date
    induction_url: Optional[str]



# ---------- UPDATE ----------
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
    photo_url: Optional[str] = None

    # Verification details
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

    # License info
    license_number: Optional[str] = None
    license_expiry_date: Optional[date] = None
    license_url: Optional[str] = None

    # Badge info
    badge_number: Optional[str] = None
    badge_expiry_date: Optional[date] = None
    badge_url: Optional[str] = None

    # Alternate govt ID
    alt_govt_id_number: Optional[str] = None
    alt_govt_id_type: Optional[str] = None
    alt_govt_id_url: Optional[str] = None

    # Induction
    induction_date: Optional[date] = None
    induction_url: Optional[str] = None

    # Background verification docs
    bgv_doc_url: Optional[str] = None

    # System flags
    is_active: Optional[bool] = True


# ---------- RESPONSE ----------
class DriverResponse(DriverBase):
    driver_id: int
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class DriverPaginationResponse(BaseModel):
    total: int
    items: List[DriverResponse]
