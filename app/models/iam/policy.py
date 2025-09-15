from sqlalchemy import Column, Integer, String, Boolean, DateTime, ForeignKey, func, Table
from sqlalchemy.orm import relationship
from app.database.session import Base

# Association table for Policy-Permission many-to-many relationship
policy_permission = Table(
    'iam_policy_permission',
    Base.metadata,
    Column('policy_id', Integer, ForeignKey('iam_policies.policy_id', ondelete="CASCADE")),
    Column('permission_id', Integer, ForeignKey('iam_permissions.permission_id', ondelete="CASCADE"))
)

class Policy(Base):
    __tablename__ = "iam_policies"

    policy_id = Column(Integer, primary_key=True, index=True)
    name = Column(String(100), unique=True, nullable=False)
    description = Column(String(255))
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=func.now(), nullable=False)
    updated_at = Column(DateTime, default=func.now(), onupdate=func.now(), nullable=False)

    # Relationship with permissions
    permissions = relationship("Permission", secondary=policy_permission, backref="policies")
