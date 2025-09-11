from sqlalchemy import Column, Integer, String, Boolean, DateTime, Date, Text, ForeignKey, Numeric, Enum, func
from sqlalchemy.orm import relationship
from database.session import Base
from enum import Enum as PyEnum

class GenderEnum(str, PyEnum):
    MALE = "Male"
    FEMALE = "Female"
    OTHER = "Other"

class Employee(Base):
    __tablename__ = "employees"

    employee_id = Column(Integer, primary_key=True, index=True)
    name = Column(String(150), nullable=False)
    employee_code = Column(String(50), unique=True)
    email = Column(String(150), unique=True, nullable=False)
    password = Column(String(255), nullable=False)
    team_id = Column(Integer, ForeignKey("teams.team_id", ondelete="SET NULL"))
    phone = Column(String(20), unique=True, nullable=False)
    alternate_phone = Column(String(20))
    special_needs = Column(Text)
    special_needs_start_date = Column(Date)
    special_needs_end_date = Column(Date)
    address = Column(Text)
    latitude = Column(Numeric(9, 6))
    longitude = Column(Numeric(9, 6))
    gender = Column(Enum(GenderEnum, native_enum=False))
    is_active = Column(Boolean, default=True, nullable=False)
    created_at = Column(DateTime, default=func.now(), nullable=False)
    updated_at = Column(DateTime, default=func.now(), onupdate=func.now(), nullable=False)

    # Relationships
    team = relationship("Team", back_populates="employees")
    bookings = relationship("Booking", back_populates="employee")
    weekoff_config = relationship("WeekoffConfig", back_populates="employee", uselist=False)
