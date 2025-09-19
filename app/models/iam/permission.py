from sqlalchemy import Column, Integer, String, Boolean, DateTime, ForeignKey, func
from app.database.session import Base
from sqlalchemy.schema import UniqueConstraint

class Permission(Base):
    __tablename__ = "iam_permissions"

    permission_id = Column(Integer, primary_key=True, index=True)
    module = Column(String(100), nullable=False)
    action = Column(String(50), nullable=False)  # create, read, update, delete, *
    description = Column(String(255))
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=func.now(), nullable=False)
    updated_at = Column(DateTime, default=func.now(), onupdate=func.now(), nullable=False)

    # Composite unique constraint on module and action
    __table_args__ = (UniqueConstraint('module', 'action', name='uq_permission_module_action'),)
