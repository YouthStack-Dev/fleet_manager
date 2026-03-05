"""
Announcement / Broadcast ORM models.

Two tables
──────────
  announcements           — one row per admin-created broadcast
  announcement_recipients — one row per (announcement × recipient) delivery record

Design decisions
────────────────
- target_ids stored as JSON so a single row expresses "these 50 employees" or
  "these 3 vendor IDs" without extra join tables.
- All SA Enum columns use native_enum=False so they work with SQLite in tests
  and PostgreSQL in production without dialect gymnastics.
- _JsonB resolves to JSONB on PostgreSQL (binary, indexed) and plain JSON on
  SQLite (tests) — identical to the pattern used in driver.py and review.py.
"""

from __future__ import annotations

from enum import Enum as PyEnum

from sqlalchemy import (
    Boolean, Column, DateTime, Enum, ForeignKey,
    Integer, String, Text, func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import relationship
from sqlalchemy.types import JSON

from app.database.session import Base

# ── Cross-database JSON type ──────────────────────────────────────────────────
# JSONB on PostgreSQL (binary + operator support), plain JSON on SQLite (tests)
_JsonB = JSON().with_variant(JSONB(), "postgresql")


# ── Enums ─────────────────────────────────────────────────────────────────────

class AnnouncementContentType(str, PyEnum):
    TEXT  = "text"
    IMAGE = "image"
    VIDEO = "video"
    AUDIO = "audio"
    PDF   = "pdf"
    LINK  = "link"


class AnnouncementTargetType(str, PyEnum):
    ALL_EMPLOYEES      = "all_employees"       # every active employee in tenant
    SPECIFIC_EMPLOYEES = "specific_employees"  # target_ids = [employee_id, …]
    TEAMS              = "teams"               # target_ids = [team_id, …]
    ALL_DRIVERS        = "all_drivers"         # every active driver in tenant
    VENDOR_DRIVERS     = "vendor_drivers"      # target_ids = [vendor_id, …]
    SPECIFIC_DRIVERS   = "specific_drivers"    # target_ids = [driver_id, …]


class AnnouncementChannel(str, PyEnum):
    PUSH   = "push"    # FCM push notification
    SMS    = "sms"     # Twilio SMS to phone number
    EMAIL  = "email"   # SMTP email
    IN_APP = "in_app"  # in-app inbox (always persisted; cannot be disabled)


class AnnouncementStatus(str, PyEnum):
    DRAFT     = "draft"
    PUBLISHED = "published"
    CANCELLED = "cancelled"


class AnnouncementDeliveryStatus(str, PyEnum):
    PENDING   = "pending"    # notification queued but not yet sent
    DELIVERED = "delivered"  # push notification sent successfully
    FAILED    = "failed"     # FCM returned a permanent error
    NO_DEVICE = "no_device"  # recipient has no active FCM session
    READ      = "read"       # recipient opened / read the announcement


# ── ORM models ────────────────────────────────────────────────────────────────

class Announcement(Base):
    """Admin-created broadcast sent to a targeted audience."""

    __tablename__ = "announcements"

    announcement_id  = Column(Integer, primary_key=True, index=True)
    tenant_id        = Column(
        String(50),
        ForeignKey("tenants.tenant_id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    # Content
    title            = Column(String(200), nullable=False)
    body             = Column(Text, nullable=False)
    content_type     = Column(
        Enum(AnnouncementContentType, native_enum=False),
        nullable=False,
        default=AnnouncementContentType.TEXT,
    )
    # Rich-media attachment (video / audio / PDF / image / external link)
    media_url        = Column(Text, nullable=True)
    media_filename   = Column(String(255), nullable=True)   # friendly display name
    media_size_bytes = Column(Integer, nullable=True)

    # Targeting
    target_type = Column(
        Enum(AnnouncementTargetType, native_enum=False),
        nullable=False,
    )
    # Meaning varies by target_type:
    #   specific_employees → [employee_id, …]
    #   teams              → [team_id, …]
    #   vendor_drivers     → [vendor_id, …]
    #   specific_drivers   → [driver_id, …]
    #   all_employees / all_drivers → null (not used)
    target_ids = Column(_JsonB, nullable=True)

    # Lifecycle
    status    = Column(
        Enum(AnnouncementStatus, native_enum=False),
        nullable=False,
        default=AnnouncementStatus.DRAFT,
    )
    is_active    = Column(Boolean, default=True, nullable=False)
    created_by   = Column(Integer, nullable=True)   # admin user_id who sent this
    published_at = Column(DateTime, nullable=True)

    # Delivery channels chosen by admin at creation time
    # e.g. ["push", "sms", "email", "in_app"] — any subset
    channels = Column(_JsonB, nullable=True)  # defaults to ["push", "in_app"]

    # Delivery counters — populated atomically at publish time
    total_recipients = Column(Integer, default=0, nullable=False)
    success_count    = Column(Integer, default=0, nullable=False)   # push delivered
    failure_count    = Column(Integer, default=0, nullable=False)   # push failed
    no_device_count  = Column(Integer, default=0, nullable=False)   # no FCM token
    sms_sent_count   = Column(Integer, default=0, nullable=False)   # SMS sent
    email_sent_count = Column(Integer, default=0, nullable=False)   # emails sent

    created_at = Column(DateTime, default=func.now(), nullable=False)
    updated_at = Column(DateTime, default=func.now(), onupdate=func.now(), nullable=False)

    # Relationship
    recipients = relationship(
        "AnnouncementRecipient",
        back_populates="announcement",
        cascade="all, delete-orphan",
    )


class AnnouncementRecipient(Base):
    """Per-user delivery tracking row created in bulk at publish time."""

    __tablename__ = "announcement_recipients"

    recipient_id      = Column(Integer, primary_key=True, index=True)
    announcement_id   = Column(
        Integer,
        ForeignKey("announcements.announcement_id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    recipient_type    = Column(String(20), nullable=False)   # "employee" | "driver"
    recipient_user_id = Column(Integer, nullable=False, index=True)
    tenant_id         = Column(String(50), nullable=False, index=True)

    delivery_status = Column(
        Enum(AnnouncementDeliveryStatus, native_enum=False),
        nullable=False,
        default=AnnouncementDeliveryStatus.PENDING,
    )
    push_sent_at  = Column(DateTime, nullable=True)
    sms_sent_at   = Column(DateTime, nullable=True)
    email_sent_at = Column(DateTime, nullable=True)
    read_at       = Column(DateTime, nullable=True)
    created_at    = Column(DateTime, default=func.now(), nullable=False)

    # Relationship
    announcement = relationship("Announcement", back_populates="recipients")
