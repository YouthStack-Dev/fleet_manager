from sqlalchemy import Column, Integer, DateTime, ForeignKey, func, Index, UniqueConstraint
from sqlalchemy.orm import relationship
from app.database.session import Base


class RouteBooking(Base):
    __tablename__ = "route_bookings"
    __table_args__ = (
        Index("ix_route_bookings_route", "route_id"),
        UniqueConstraint("route_id", "booking_id", name="uq_route_booking_unique"),
    )
    __table_args__ = {'extend_existing': True}

    route_booking_id = Column(Integer, primary_key=True, index=True)
    route_id = Column(Integer, ForeignKey("routes.route_id", ondelete="CASCADE"), nullable=False)
    booking_id = Column(Integer, ForeignKey("bookings.booking_id", ondelete="CASCADE"), nullable=False)
    planned_eta_minutes = Column(Integer)
    actual_arrival_time = Column(DateTime)
    actual_departure_time = Column(DateTime)
    created_at = Column(DateTime, default=func.now(), nullable=False)
    updated_at = Column(DateTime, default=func.now(), onupdate=func.now(), nullable=False)

    # Relationships
    route = relationship("Route", back_populates="bookings")
    booking = relationship("Booking", back_populates="route_bookings")
