"""
Chat Models — per-booking real-time chat between Employee and Driver.

Tables
──────
  chat_sessions   — one session per booking (created on booking assignment)
  chat_messages   — every message sent (employee / driver / system)

Real-time delivery: Firebase Realtime Database (RTDB)
  Path: chats/{tenant_id}/booking_{booking_id}/
Permanent audit:    PostgreSQL (this table)
"""

from sqlalchemy import (
    Column, Integer, String, Boolean, DateTime, Text,
    ForeignKey, Enum, func, JSON, Index
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import relationship
from app.database.session import Base
from enum import Enum as PyEnum

# Cross-database JSON: JSONB on PostgreSQL, plain JSON elsewhere (tests / SQLite)
_JsonB = JSON().with_variant(JSONB(), "postgresql")


class ChatSenderType(str, PyEnum):
    EMPLOYEE = "employee"
    DRIVER   = "driver"
    SYSTEM   = "system"


class ChatSession(Base):
    """One row per booking — created the moment a booking is assigned."""

    __tablename__ = "chat_sessions"

    id          = Column(Integer, primary_key=True, index=True)
    tenant_id   = Column(
        String(50),
        ForeignKey("tenants.tenant_id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    booking_id  = Column(
        Integer,
        ForeignKey("bookings.booking_id", ondelete="CASCADE"),
        nullable=False,
        unique=True,   # one session per booking
        index=True,
    )
    employee_id = Column(
        Integer,
        ForeignKey("employees.employee_id", ondelete="CASCADE"),
        nullable=False,
    )
    driver_id   = Column(
        Integer,
        ForeignKey("drivers.driver_id", ondelete="SET NULL"),
        nullable=True,   # may not be assigned yet at session-creation time
    )

    # Language preferences (ISO 639-1 codes — set by each user in the app)
    employee_language = Column(String(10), nullable=False, default="en")
    driver_language   = Column(String(10), nullable=False, default="en")

    is_active    = Column(Boolean, default=True,      nullable=False)
    activated_at = Column(DateTime, default=func.now(), nullable=False)
    created_at   = Column(DateTime, default=func.now(), nullable=False)
    updated_at   = Column(
        DateTime,
        default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    # Relationships
    messages = relationship(
        "ChatMessage",
        back_populates="session",
        cascade="all, delete-orphan",
        order_by="ChatMessage.created_at",
    )


class ChatMessage(Base):
    """Every chat message — employee, driver, or auto-injected system notices."""

    __tablename__ = "chat_messages"

    id          = Column(Integer, primary_key=True, index=True)
    tenant_id   = Column(
        String(50),
        ForeignKey("tenants.tenant_id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    booking_id  = Column(
        Integer,
        ForeignKey("bookings.booking_id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    session_id  = Column(
        Integer,
        ForeignKey("chat_sessions.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    sender_type = Column(
        Enum(ChatSenderType, native_enum=False),
        nullable=False,
    )
    sender_id   = Column(Integer, nullable=True)   # null for system messages

    # Original content
    original_text     = Column(Text, nullable=False)
    original_language = Column(String(10), nullable=False, default="en")

    # All translated variants cached here:  {"hi": "...", "ar": "..."}
    # Updated async once translation completes (~1 second after send)
    translated_texts  = Column(_JsonB, nullable=True, default=dict, server_default="{}")

    # Firebase RTDB push key — used to push translation update back to RTDB
    firebase_message_id = Column(String(200), nullable=True)

    is_system_message   = Column(Boolean, default=False, nullable=False)
    created_at          = Column(DateTime, default=func.now(), nullable=False)

    # Relationships
    session = relationship("ChatSession", back_populates="messages")

    __table_args__ = (
        # Fast lookup: latest N messages for a booking
        Index("ix_chat_messages_booking_created", "booking_id", "created_at"),
    )
