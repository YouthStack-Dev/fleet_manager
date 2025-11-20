from sqlalchemy import Column, Integer, String, DateTime, JSON, func, Index
from app.database.session import Base


class AuditLog(Base):
    __tablename__ = "audit_logs"

    audit_id = Column(Integer, primary_key=True, index=True)
    tenant_id = Column(String(50), nullable=False, index=True)
    module = Column(String(50), nullable=False, index=True)  # 'employee', 'driver', 'vehicle', etc.
    audit_data = Column(JSON, nullable=False)  # All audit details in JSON
    created_at = Column(DateTime, default=func.now(), nullable=False, index=True)

    __table_args__ = (
        Index('idx_tenant_module', 'tenant_id', 'module'),
        Index('idx_module_created', 'module', 'created_at'),
        {"extend_existing": True}
    )
