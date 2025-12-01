from pydantic import BaseModel, Field
from typing import Optional, Dict, Any
from datetime import datetime


class AuditLogBase(BaseModel):
    tenant_id: str
    module: str  # 'employee', 'driver', 'vehicle', etc.
    audit_data: Dict[str, Any]  # All details in JSON


class AuditLogCreate(AuditLogBase):
    pass


class AuditLogResponse(AuditLogBase):
    audit_id: int
    created_at: datetime

    class Config:
        from_attributes = True


class AuditLogFilter(BaseModel):
    tenant_id: Optional[str] = None
    module: Optional[str] = None
    employee_id: Optional[int] = None
    start_date: Optional[datetime] = None
    end_date: Optional[datetime] = None
    page: int = Field(default=1, ge=1)
    page_size: int = Field(default=50, ge=1, le=200)
