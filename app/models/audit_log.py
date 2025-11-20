from sqlalchemy import Column, Integer, String, DateTime, Text, JSON, Enum, func
from sqlalchemy.orm import relationship
from app.database.session import Base
from enum import Enum as PyEnum


class ActionEnum(str, PyEnum):
    CREATE = "CREATE"
    UPDATE = "UPDATE"
    DELETE = "DELETE"
    LOGIN = "LOGIN"
    LOGOUT = "LOGOUT"
    EXPORT = "EXPORT"
    IMPORT = "IMPORT"


class EntityTypeEnum(str, PyEnum):
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


class AuditLog(Base):
    __tablename__ = "audit_logs"

    audit_id = Column(Integer, primary_key=True, index=True)
    entity_type = Column(Enum(EntityTypeEnum, native_enum=False), nullable=False, index=True)
    entity_id = Column(String(100), nullable=False, index=True)
    action = Column(Enum(ActionEnum, native_enum=False), nullable=False, index=True)
    performed_by_type = Column(String(50), nullable=False)  # 'admin', 'employee', 'vendor_user'
    performed_by_id = Column(Integer, nullable=False)
    performed_by_name = Column(String(150), nullable=False)
    performed_by_email = Column(String(150))
    tenant_id = Column(String(50), nullable=True)  # for tenant-specific operations
    old_values = Column(JSON, nullable=True)  # JSON field to store old values
    new_values = Column(JSON, nullable=True)  # JSON field to store new values
    description = Column(Text, nullable=True)  # additional description
    ip_address = Column(String(50), nullable=True)
    user_agent = Column(String(255), nullable=True)
    created_at = Column(DateTime, default=func.now(), nullable=False, index=True)

    __table_args__ = (
        {"extend_existing": True}
    )
