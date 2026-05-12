from sqlalchemy import (
    Column, Integer, String, Float, DateTime, ForeignKey, Index, func
)
from sqlalchemy.orm import relationship
from app.database.session import Base


class SpeedViolation(Base):
    """
    Records every instance where a driver exceeds the tenant-configured speed limit
    during an active ride (route_management).

    One record = one violation event.  Multiple rows can share the same route_id;
    the total count per ride is derived by querying COUNT(*) WHERE route_id = X.
    """
    __tablename__ = "speed_violations"

    violation_id = Column(Integer, primary_key=True, autoincrement=True, index=True)

    # Tenant scoping
    tenant_id = Column(
        String(50),
        ForeignKey("tenants.tenant_id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    # The ride this violation belongs to (route_management row)
    route_id = Column(
        Integer,
        ForeignKey("route_management.route_id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )

    # Driver who was speeding
    driver_id = Column(
        Integer,
        ForeignKey("drivers.driver_id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )

    # Vehicle in use at the time (denormalised for quick reporting)
    vehicle_id = Column(
        Integer,
        ForeignKey("vehicles.vehicle_id", ondelete="SET NULL"),
        nullable=True,
    )

    # Speed data
    speed_recorded = Column(Float, nullable=False)   # actual GPS speed (km/h)
    speed_limit    = Column(Float, nullable=False)   # snapshot of limit at time of event (km/h)

    # Location at time of violation
    latitude  = Column(Float, nullable=True)
    longitude = Column(Float, nullable=True)

    # When the violation occurred (device/GPS timestamp, timezone-aware)
    recorded_at = Column(DateTime(timezone=True), nullable=False)

    # When the record was inserted into DB
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    # Relationships (lazy load — used only when explicitly needed)
    tenant  = relationship("Tenant",  foreign_keys=[tenant_id],  lazy="select")
    driver  = relationship("Driver",  foreign_keys=[driver_id],  lazy="select")
    vehicle = relationship("Vehicle", foreign_keys=[vehicle_id], lazy="select")

    # Composite index for the most common query patterns
    __table_args__ = (
        Index("ix_speed_violations_tenant_route",  "tenant_id", "route_id"),
        Index("ix_speed_violations_tenant_driver", "tenant_id", "driver_id"),
        Index("ix_speed_violations_recorded_at",   "tenant_id", "recorded_at"),
    )
