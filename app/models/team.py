from sqlalchemy import Column, Integer, String, DateTime, Text, ForeignKey, func, UniqueConstraint
from sqlalchemy.orm import relationship
from app.database.session import Base


class Team(Base):
    __tablename__ = "teams"

    team_id = Column(Integer, primary_key=True, index=True)
    tenant_id = Column(Integer, ForeignKey("tenants.tenant_id", ondelete="CASCADE"), nullable=False)
    name = Column(String(150), nullable=False)
    description = Column(Text)
    created_at = Column(DateTime, default=func.now(), nullable=False)
    updated_at = Column(DateTime, default=func.now(), onupdate=func.now(), nullable=False)

    # Composite unique constraint: ensures name is unique per tenant
    __table_args__ = (UniqueConstraint("tenant_id", "name", name="uq_team_name_per_tenant"),)
    __table_args__ = {'extend_existing': True}

    # Relationships
    tenant = relationship("Tenant", back_populates="teams")
    employees = relationship("Employee", back_populates="team")
    bookings = relationship("Booking", back_populates="team")
