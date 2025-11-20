from pydantic import BaseModel, Field
from typing import Optional, Dict, Any
from datetime import datetime
from enum import Enum


class ActionEnum(str, Enum):
    CREATE = "CREATE"
    UPDATE = "UPDATE"
    DELETE = "DELETE"
    LOGIN = "LOGIN"
    LOGOUT = "LOGOUT"
    EXPORT = "EXPORT"
    IMPORT = "IMPORT"


class EntityTypeEnum(str, Enum):
    EMPLOYEE = "EMPLOYEE"
    ADMIN = "ADMIN"
    DRIVER = "DRIVER"
    VEHICLE = "VEHICLE"
    VENDOR = "VENDOR"
    VENDOR_USER = "VENDOR_USER"
    BOOKING = "BOOKING"
    TEAM = "TEAM"
    TENANT = "TENANT"
    SHIFT = "SHIFT"
    CUTOFF = "CUTOFF"
    VEHICLE_TYPE = "VEHICLE_TYPE"
    WEEKOFF_CONFIG = "WEEKOFF_CONFIG"


class AuditLogBase(BaseModel):
    entity_type: EntityTypeEnum
    entity_id: str
    action: ActionEnum
    performed_by_type: str
    performed_by_id: int
    performed_by_name: str
    performed_by_email: Optional[str] = None
    tenant_id: Optional[str] = None
    old_values: Optional[Dict[str, Any]] = None
    new_values: Optional[Dict[str, Any]] = None
    description: Optional[str] = None
    ip_address: Optional[str] = None
    user_agent: Optional[str] = None


class AuditLogCreate(AuditLogBase):
    pass


class AuditLogResponse(AuditLogBase):
    audit_id: int
    created_at: datetime

    class Config:
        from_attributes = True


class AuditLogFilter(BaseModel):
    entity_type: Optional[EntityTypeEnum] = None
    entity_id: Optional[str] = None
    action: Optional[ActionEnum] = None
    performed_by_type: Optional[str] = None
    performed_by_id: Optional[int] = None
    tenant_id: Optional[str] = None
    start_date: Optional[datetime] = None
    end_date: Optional[datetime] = None
    page: int = Field(default=1, ge=1)
    page_size: int = Field(default=50, ge=1, le=200)
