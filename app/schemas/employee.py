from pydantic import BaseModel, EmailStr, Field
from typing import Optional, List
from datetime import datetime, date
from enum import Enum

class GenderEnum(str, Enum):
    MALE = "Male"
    FEMALE = "Female"
    OTHER = "Other"

class EmployeeBase(BaseModel):
    name: str
    email: EmailStr
    phone: str
    employee_code: Optional[str] = None
    team_id: Optional[int] = None
    alternate_phone: Optional[str] = None
    special_needs: Optional[str] = None
    special_needs_start_date: Optional[date] = None
    special_needs_end_date: Optional[date] = None
    address: Optional[str] = None
    latitude: Optional[float] = Field(None, ge=-90, le=90)
    longitude: Optional[float] = Field(None, ge=-180, le=180)
    gender: Optional[GenderEnum] = None
    is_active: bool = True

class EmployeeCreate(EmployeeBase):
    password: str

class EmployeeUpdate(BaseModel):
    name: Optional[str] = None
    email: Optional[EmailStr] = None
    phone: Optional[str] = None
    employee_code: Optional[str] = None
    team_id: Optional[int] = None
    alternate_phone: Optional[str] = None
    special_needs: Optional[str] = None
    special_needs_start_date: Optional[date] = None
    special_needs_end_date: Optional[date] = None
    address: Optional[str] = None
    latitude: Optional[float] = Field(None, ge=-90, le=90)
    longitude: Optional[float] = Field(None, ge=-180, le=180)
    gender: Optional[GenderEnum] = None
    password: Optional[str] = None
    is_active: Optional[bool] = None

class EmployeeResponse(EmployeeBase):
    employee_id: int
    created_at: datetime
    updated_at: datetime

    class Config:
        orm_mode = True

class EmployeePaginationResponse(BaseModel):
    total: int
    items: List[EmployeeResponse]
