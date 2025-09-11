from sqlalchemy import Column, Integer, Boolean, DateTime, ForeignKey, func
from sqlalchemy.orm import relationship
from database.session import Base

class WeekoffConfig(Base):
    __tablename__ = "weekoff_configs"

    weekoff_id = Column(Integer, primary_key=True, index=True)
    employee_id = Column(Integer, ForeignKey("employees.employee_id", ondelete="CASCADE"), unique=True, nullable=False)
    monday = Column(Boolean, default=False, nullable=False)
    tuesday = Column(Boolean, default=False, nullable=False)
    wednesday = Column(Boolean, default=False, nullable=False)
    thursday = Column(Boolean, default=False, nullable=False)
    friday = Column(Boolean, default=False, nullable=False)
    saturday = Column(Boolean, default=False, nullable=False)
    sunday = Column(Boolean, default=False, nullable=False)
    created_at = Column(DateTime, default=func.now(), nullable=False)
    updated_at = Column(DateTime, default=func.now(), onupdate=func.now(), nullable=False)

    # Relationships
    employee = relationship("Employee", back_populates="weekoff_config")
