from sqlalchemy import Column, Integer, String, DateTime, ForeignKey, Text, func
from sqlalchemy.orm import relationship
from app.database.session import Base


class RouteDelayEvent(Base):
    """
    Audit log for every OTA / OTD delay tagging event on a route.

    One RouteManagement row may accumulate multiple events (e.g. one OTA event
    when duty starts and one OTD event when duty ends).  The summary columns on
    RouteManagement (`delay_type`, `delay_minutes`, `delay_tagged_at`) always
    reflect the *latest* tagging action; this table preserves full history.

    Columns
    -------
    delay_type  : "LATE" | "EARLY" | "ON_TIME"
    event_kind  : "OTA" (on-time arrival / trip start) |
                  "OTD" (on-time delivery / trip end)
    delay_minutes : positive = late, negative = early, 0 = on-time
    """

    __tablename__ = "route_delay_events"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)

    route_id = Column(
        Integer,
        ForeignKey("route_management.route_id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    tenant_id = Column(String(50), nullable=False, index=True)

    # "OTA" or "OTD"
    event_kind = Column(String(10), nullable=False)
    # "LATE", "EARLY", or "ON_TIME"
    delay_type = Column(String(20), nullable=False)
    # positive = late, negative = early
    delay_minutes = Column(Integer, nullable=False, default=0)

    # Root-cause category (Feature 4 — OTA/OTD Delay Classification)
    # DRIVER_DELAY | EMPLOYEE_DELAY | TRAFFIC_DELAY | NONE
    # NULL for rows recorded before Feature 4 was deployed.
    delay_category = Column(String(30), nullable=True)

    notes = Column(Text, nullable=True)

    tagged_at = Column(
        DateTime,
        default=func.now(),
        nullable=False,
    )

    # Relationship back to route
    route = relationship("RouteManagement", back_populates="delay_events")
