# app/models/review.py
"""
RideReview model — stores optional post-ride reviews submitted by employees.

An employee can review:
  • The overall trip (1-5 stars)
  • The driver  (1-5 stars + predefined word-tags + free-text comment)
  • The vehicle (1-5 stars + predefined word-tags + free-text comment)

All fields are fully optional so employees are never forced to review.
One review per booking (enforced by unique constraint on booking_id).
"""

from sqlalchemy import (
    Column, Integer, String, DateTime, Text,
    ForeignKey, Enum, func, CheckConstraint, UniqueConstraint, Boolean, JSON,
)
from sqlalchemy.dialects.postgresql import JSONB

# Cross-database JSON type: uses JSONB on PostgreSQL, JSON on SQLite/others
_JsonB = JSON().with_variant(JSONB(), "postgresql")
from sqlalchemy.orm import relationship
from app.database.session import Base
from enum import Enum as PyEnum


# ──────────────────────────────────────────────────────────────
# Tag type enum — driver tags vs vehicle tags
# Tags themselves live in the review_tags table so admins can
# add / remove them via the API without any redeployment.
# Employees can also submit free-form custom words at any time.
# ──────────────────────────────────────────────────────────────

class ReviewTagTypeEnum(str, PyEnum):
    DRIVER  = "driver"
    VEHICLE = "vehicle"


class RideReview(Base):
    """
    Stores an employee's optional review for a completed ride (booking).

    Relationships
    -------------
    booking  → Booking  (one-to-one)
    employee → Employee (many-to-one)
    tenant   → Tenant   (many-to-one)
    """

    __tablename__ = "ride_reviews"
    __table_args__ = (
        # One review per booking
        UniqueConstraint("booking_id", name="uq_ride_review_booking_id"),

        # Star ratings must be 1-5 when provided
        CheckConstraint("overall_rating IS NULL OR (overall_rating >= 1 AND overall_rating <= 5)", name="ck_overall_rating"),
        CheckConstraint("driver_rating  IS NULL OR (driver_rating  >= 1 AND driver_rating  <= 5)", name="ck_driver_rating"),
        CheckConstraint("vehicle_rating IS NULL OR (vehicle_rating >= 1 AND vehicle_rating <= 5)", name="ck_vehicle_rating"),
    )

    # ── Primary key ────────────────────────────────────────────
    review_id = Column(Integer, primary_key=True, index=True, autoincrement=True)

    # ── Scope ──────────────────────────────────────────────────
    tenant_id = Column(
        String(50),
        ForeignKey("tenants.tenant_id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    booking_id = Column(
        Integer,
        ForeignKey("bookings.booking_id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    employee_id = Column(
        Integer,
        ForeignKey("employees.employee_id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    # ── Snapshot of trip participants at review time ───────────
    # Stored so reviews stay meaningful even after reassignment
    driver_id = Column(
        Integer,
        ForeignKey("drivers.driver_id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    vehicle_id = Column(
        Integer,
        ForeignKey("vehicles.vehicle_id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    route_id = Column(Integer, nullable=True)  # informational only

    # ── Overall trip rating ────────────────────────────────────
    overall_rating = Column(Integer, nullable=True)  # 1–5 stars, optional

    # ── Driver review (fully optional) ────────────────────────
    driver_rating  = Column(Integer, nullable=True)   # 1–5 stars
    driver_tags    = Column(_JsonB,  nullable=True)   # e.g. ["Punctual", "Polite"]
    driver_comment = Column(Text,    nullable=True)   # free-text, max handled at app layer

    # ── Vehicle review (fully optional) ───────────────────────
    vehicle_rating  = Column(Integer, nullable=True)  # 1–5 stars
    vehicle_tags    = Column(_JsonB,  nullable=True)  # e.g. ["Clean", "Comfortable"]
    vehicle_comment = Column(Text,    nullable=True)  # free-text

    # ── Audit ──────────────────────────────────────────────────
    is_active  = Column(Boolean, default=True, nullable=False)
    created_at = Column(DateTime, default=func.now(), nullable=False)
    updated_at = Column(DateTime, default=func.now(), onupdate=func.now(), nullable=False)

    # ── Relationships ──────────────────────────────────────────
    booking  = relationship("Booking",  back_populates="review", foreign_keys=[booking_id])
    employee = relationship("Employee", back_populates="reviews", foreign_keys=[employee_id])
    driver   = relationship("Driver",   back_populates="reviews", foreign_keys=[driver_id])
    vehicle  = relationship("Vehicle",  back_populates="reviews", foreign_keys=[vehicle_id])


# ──────────────────────────────────────────────────────────────
# ReviewTag — admin-configurable word-tag bank
# ──────────────────────────────────────────────────────────────

class ReviewTag(Base):
    """
    Stores the configurable list of word-tags employees can pick from
    when reviewing a driver or vehicle.

    - tenant_id = None  → global tag, visible to every tenant
    - tenant_id = 'X'   → tenant-specific tag, visible only to tenant X

    Admins add / remove tags via  POST /reviews/tags  and
    DELETE /reviews/tags/{tag_id}  without any redeployment.

    Employees can also submit any free-form custom word alongside or
    instead of these suggestions — there is no server-side enforcement.
    """

    __tablename__ = "review_tags"

    tag_id        = Column(Integer, primary_key=True, autoincrement=True, index=True)
    # NULL → global tag available to all tenants
    tenant_id     = Column(
        String(50),
        ForeignKey("tenants.tenant_id", ondelete="CASCADE"),
        nullable=True,
        index=True,
    )
    tag_type      = Column(Enum(ReviewTagTypeEnum, native_enum=False), nullable=False, index=True)
    tag_name      = Column(String(100), nullable=False)
    display_order = Column(Integer, default=0, nullable=False)
    is_active     = Column(Boolean, default=True, nullable=False)
    created_at    = Column(DateTime, default=func.now(), nullable=False)
    updated_at    = Column(DateTime, default=func.now(), onupdate=func.now(), nullable=False)
