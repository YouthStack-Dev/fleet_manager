from sqlalchemy import Column, Integer, String, DateTime, Text, func
from sqlalchemy.orm import relationship
from database.session import Base

class Team(Base):
    __tablename__ = "teams"

    team_id = Column(Integer, primary_key=True, index=True)
    name = Column(String(150), unique=True, nullable=False)
    description = Column(Text)
    created_at = Column(DateTime, default=func.now(), nullable=False)
    updated_at = Column(DateTime, default=func.now(), onupdate=func.now(), nullable=False)

    # Relationships
    employees = relationship("Employee", back_populates="team")
    bookings = relationship("Booking", back_populates="team")
