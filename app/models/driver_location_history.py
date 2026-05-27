from sqlalchemy import (
    Column, Integer, String, Float, DateTime, ForeignKey, Index, func
)
from sqlalchemy.orm import relationship
from app.database.session import Base


class DriverLocationHistory(Base):
    """
    GPS breadcrumb trail for every driver ping during an active route.

    One record = one location ping.  Multiple rows share the same route_id;
    the full trail is retrieved by querying WHERE route_id = X ORDER BY recorded_at.

    Dual-write strategy:
      - Firebase RTDB  → latest position only (real-time display, overwritten on each ping)
      - This table      → full audit trail    (playback, distance calc, compliance reports)
    """
    __tablename__ = "driver_location_history"

    id = Column(Integer, primary_key=True, autoincrement=True, index=True)

    # Tenant scoping
    tenant_id = Column(
        String(50),
        ForeignKey("tenants.tenant_id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    # The active ride this ping belongs to (route_management row)
    route_id = Column(
        Integer,
        ForeignKey("route_management.route_id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )

    # Driver who sent the ping
    driver_id = Column(
        Integer,
        ForeignKey("drivers.driver_id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )

    # Vendor the driver belongs to (denormalised for fast tenant-vendor queries)
    vendor_id = Column(
        Integer,
        ForeignKey("vendors.vendor_id", ondelete="SET NULL"),
        nullable=True,
    )

    # GPS coordinates
    latitude  = Column(Float, nullable=False)
    longitude = Column(Float, nullable=False)

    # Optional speed reported by the device (km/h) — used for speed-violation checks
    speed = Column(Float, nullable=True)

    # Device/GPS timestamp (timezone-aware) — the moment the fix was taken on the device
    recorded_at = Column(DateTime(timezone=True), nullable=False)

    # DB insert timestamp
    created_at = Column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    # Relationships (lazy load — used only when explicitly needed)
    tenant = relationship("Tenant",  foreign_keys=[tenant_id], lazy="select")
    driver = relationship("Driver",  foreign_keys=[driver_id], lazy="select")

    # Composite indexes for the most common query patterns
    __table_args__ = (
        # Playback / distance calc for a single ride
        Index("ix_dlh_route_recorded_at",    "route_id",   "recorded_at"),
        # Driver history across rides
        Index("ix_dlh_driver_recorded_at",   "driver_id",  "recorded_at"),
        # Tenant-scoped driver queries (dashboards, reports)
        Index("ix_dlh_tenant_driver",        "tenant_id",  "driver_id"),
    )
