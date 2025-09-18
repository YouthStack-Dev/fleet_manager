from sqlalchemy import Column, Integer, String, Boolean, DateTime, ForeignKey, func, Table
from sqlalchemy.orm import relationship
from app.database.session import Base

# Association table for Role-Policy many-to-many relationship
role_policy = Table(
    'iam_role_policy',
    Base.metadata,
    Column('role_id', Integer, ForeignKey('iam_roles.role_id', ondelete="CASCADE")),
    Column('policy_id', Integer, ForeignKey('iam_policies.policy_id', ondelete="CASCADE"))
)

class Role(Base):
    __tablename__ = "iam_roles"

    role_id = Column(Integer, primary_key=True, index=True)
    name = Column(String(100), unique=True, nullable=False)
    description = Column(String(255))
    is_active = Column(Boolean, default=True)
    tenant_id = Column(Integer, ForeignKey("tenants.tenant_id", ondelete="CASCADE"), nullable=True)
    is_system_role = Column(Boolean, default=False)  # Indicates if this is a system-defined role
    created_at = Column(DateTime, default=func.now(), nullable=False)
    updated_at = Column(DateTime, default=func.now(), onupdate=func.now(), nullable=False)

    # Relationship with policies
    policies = relationship("Policy", secondary=role_policy, backref="roles")
    # Relationship with tenant
    tenant = relationship("Tenant", back_populates="roles")
    admins = relationship("Admin", back_populates="roles")
    vendor_users = relationship("VendorUser", back_populates="roles")
    employees = relationship("Employee", back_populates="roles")

