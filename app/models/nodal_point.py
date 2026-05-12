from sqlalchemy import (
    Column, Integer, String, Boolean, DateTime, Text, ForeignKey,
    Numeric, func, UniqueConstraint
)
from sqlalchemy.orm import relationship
from app.database.session import Base


class NodalPoint(Base):
    """
    A nodal point is a company-defined pickup or drop location that employees
    travel to instead of being picked up / dropped at their home address.
    """
    __tablename__ = "nodal_points"

    nodal_point_id = Column(Integer, primary_key=True, index=True)
    tenant_id = Column(
        String(50),
        ForeignKey("tenants.tenant_id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    name = Column(String(150), nullable=False)
    address = Column(Text, nullable=True)
    latitude = Column(Numeric(9, 6), nullable=False)
    longitude = Column(Numeric(9, 6), nullable=False)
    is_active = Column(Boolean, default=True, nullable=False)
    created_at = Column(DateTime, default=func.now(), nullable=False)
    updated_at = Column(DateTime, default=func.now(), onupdate=func.now(), nullable=False)

    # Relationships
    tenant = relationship("Tenant", back_populates="nodal_points")
    employee_nodal_points = relationship(
        "EmployeeNodalPoint",
        back_populates="nodal_point",
        cascade="all, delete-orphan",
    )
    bookings = relationship("Booking", back_populates="nodal_point")


class EmployeeNodalPoint(Base):
    """
    Links an employee to a specific nodal point.
    One employee has exactly one assigned nodal point per tenant.
    is_overridden=True means an admin manually chose this point
    instead of the system-suggested nearest one.
    """
    __tablename__ = "employee_nodal_points"

    id = Column(Integer, primary_key=True, index=True)
    employee_id = Column(
        Integer,
        ForeignKey("employees.employee_id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    nodal_point_id = Column(
        Integer,
        ForeignKey("nodal_points.nodal_point_id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    tenant_id = Column(
        String(50),
        ForeignKey("tenants.tenant_id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    # True = admin manually chose this point; False = auto-assigned (nearest)
    is_overridden = Column(Boolean, default=False, nullable=False)
    created_at = Column(DateTime, default=func.now(), nullable=False)
    updated_at = Column(DateTime, default=func.now(), onupdate=func.now(), nullable=False)

    # One employee → one nodal point assignment
    __table_args__ = (
        UniqueConstraint("employee_id", name="uq_employee_nodal_point"),
    )

    # Relationships
    employee = relationship("Employee", back_populates="nodal_point_assignment")
    nodal_point = relationship("NodalPoint", back_populates="employee_nodal_points")
