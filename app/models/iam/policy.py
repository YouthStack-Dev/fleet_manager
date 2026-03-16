from sqlalchemy import CheckConstraint, Column, Integer, String, Boolean, DateTime, ForeignKey, JSON, UniqueConstraint, func, Table
from sqlalchemy.orm import relationship
from app.database.session import Base

# Association table for Policy-Permission many-to-many relationship
policy_permission = Table(
    'iam_policy_permission',
    Base.metadata,
    Column('policy_id', Integer, ForeignKey('iam_policies.policy_id', ondelete="CASCADE")),
    Column('permission_id', Integer, ForeignKey('iam_permissions.permission_id', ondelete="CASCADE"))
)


class PolicyPackage(Base):
    """
    Per-tenant permission boundary set by super-admin only.
    Permissions are stored as a JSON array of permission_ids directly in this table.
    No separate junction table needed — iam_policies is purely for tenant-managed role policies.
    """
    __tablename__ = "iam_policy_packages"
    package_id = Column(Integer, primary_key=True, index=True)
    tenant_id = Column(String(50), ForeignKey("tenants.tenant_id", ondelete="CASCADE"), nullable=False, unique=True, index=True)
    name = Column(String(100), nullable=False, default="Default Package")
    description = Column(String(255))

    # Permissions stored as a plain list of permission IDs directly in this column.
    # e.g. [1, 2, 3, 4]  — super-admin managed only.
    permission_ids = Column(JSON, nullable=False, default=list)

    created_at = Column(DateTime, default=func.now(), nullable=False)
    updated_at = Column(DateTime, default=func.now(), onupdate=func.now(), nullable=False)

    # Relationship: one package belongs to one tenant
    tenant = relationship("Tenant", back_populates="policy_package")


class Policy(Base):
    __tablename__ = "iam_policies"

    policy_id = Column(Integer, primary_key=True, index=True)
    tenant_id = Column(String(50), ForeignKey("tenants.tenant_id", ondelete="CASCADE"), nullable=True, index=True)

    name = Column(String(100), nullable=False)
    description = Column(String(255))
    is_active = Column(Boolean, default=True)
    is_system_policy = Column(Boolean, default=False)  # system/global policy

    created_at = Column(DateTime, default=func.now(), nullable=False)
    updated_at = Column(DateTime, default=func.now(), onupdate=func.now(), nullable=False)

    # Relationship with permissions
    permissions = relationship("Permission", secondary=policy_permission, backref="policies")

    __table_args__ = (
        UniqueConstraint("tenant_id", "name", name="uq_policy_tenant_name"),
        CheckConstraint(
            "(is_system_policy = TRUE AND tenant_id IS NULL) OR "
            "(is_system_policy = FALSE AND tenant_id IS NOT NULL)",
            name="ck_policy_system_or_tenant"
        ),
    )
