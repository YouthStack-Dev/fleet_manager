from sqlalchemy import CheckConstraint, Column, Integer, String, Boolean, DateTime, ForeignKey, UniqueConstraint, func, Table
from sqlalchemy.orm import relationship
from app.database.session import Base

# Association table for Policy-Permission many-to-many relationship
policy_permission = Table(
    'iam_policy_permission',
    Base.metadata,
    Column('policy_id', Integer, ForeignKey('iam_policies.policy_id', ondelete="CASCADE")),
    Column('permission_id', Integer, ForeignKey('iam_permissions.permission_id', ondelete="CASCADE"))
)


# New: PolicyPackage model to group policies per tenant

class PolicyPackage(Base):
    __tablename__ = "iam_policy_packages"
    package_id = Column(Integer, primary_key=True, index=True)
    tenant_id = Column(String(50), ForeignKey("tenants.tenant_id", ondelete="CASCADE"), nullable=False, unique=True, index=True)
    name = Column(String(100), nullable=False, default="Default Package")
    description = Column(String(255))

    # Pointer to the primary/main policy for this tenant.
    # Nullable because the package is inserted before any policy exists.
    # ON DELETE SET NULL: if the default policy is deleted, this resets to NULL automatically.
    # This is the correct ownership model: the Package decides its default, not the Policy.
    default_policy_id = Column(
        Integer,
        ForeignKey("iam_policies.policy_id", ondelete="SET NULL", use_alter=True, name="fk_package_default_policy"),
        nullable=True,
        index=True,
    )

    created_at = Column(DateTime, default=func.now(), nullable=False)
    updated_at = Column(DateTime, default=func.now(), onupdate=func.now(), nullable=False)

    # All policies that belong to this package
    policies = relationship(
        "Policy",
        back_populates="package",
        cascade="all, delete-orphan",
        foreign_keys="[Policy.package_id]",
    )
    # The single chosen default policy.
    # post_update=True tells SQLAlchemy to resolve the circular FK
    # (Package → Policy and Policy → Package) by emitting the UPDATE in a
    # second pass, after both rows have been INSERTed.
    default_policy = relationship(
        "Policy",
        foreign_keys="[PolicyPackage.default_policy_id]",
        post_update=True,
    )
    # Relationship: one package belongs to one tenant
    tenant = relationship("Tenant", back_populates="policy_package")


class Policy(Base):
    __tablename__ = "iam_policies"

    policy_id = Column(Integer, primary_key=True, index=True)
    tenant_id = Column(String(50), ForeignKey("tenants.tenant_id", ondelete="CASCADE"), nullable=True, index=True)
    package_id = Column(Integer, ForeignKey("iam_policy_packages.package_id", ondelete="CASCADE"), nullable=True, index=True)

    name = Column(String(100), nullable=False)
    description = Column(String(255))
    is_active = Column(Boolean, default=True)
    is_system_policy = Column(Boolean, default=False)  # system/global policy

    created_at = Column(DateTime, default=func.now(), nullable=False)
    updated_at = Column(DateTime, default=func.now(), onupdate=func.now(), nullable=False)

    # Relationship with permissions
    permissions = relationship("Permission", secondary=policy_permission, backref="policies")

    # Relationship back to the package that contains this policy
    package = relationship(
        "PolicyPackage",
        back_populates="policies",
        foreign_keys="[Policy.package_id]",
    )

    __table_args__ = (
        UniqueConstraint("tenant_id", "name", name="uq_policy_tenant_name"),
        CheckConstraint(
            "(is_system_policy = TRUE AND tenant_id IS NULL) OR "
            "(is_system_policy = FALSE AND tenant_id IS NOT NULL)",
            name="ck_policy_system_or_tenant"
        ),
    )

