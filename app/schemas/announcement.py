"""
Pydantic request / response schemas for the Announcement / Broadcast feature.
"""

from __future__ import annotations

from datetime import datetime
from typing import List, Optional

from pydantic import BaseModel, ConfigDict, Field

from app.models.announcement import (
    AnnouncementChannel,
    AnnouncementContentType,
    AnnouncementDeliveryStatus,  # noqa: F401 — re-exported for convenience
    AnnouncementStatus,          # noqa: F401
    AnnouncementTargetType,
)


# ── Request schemas ───────────────────────────────────────────────────────────

class AnnouncementCreate(BaseModel):
    """Body for  POST /announcements"""

    title: str = Field(..., min_length=1, max_length=200, description="Announcement title")
    body: str = Field(..., min_length=1, description="Plain-text or HTML body")
    content_type: AnnouncementContentType = Field(
        AnnouncementContentType.TEXT,
        description="Media type of the announcement",
    )
    media_url: Optional[str] = Field(
        None,
        description="URL/path of media attachment (video / audio / PDF / image / link)",
    )
    media_filename: Optional[str] = Field(
        None,
        max_length=255,
        description="Friendly display filename shown to recipients",
    )
    media_size_bytes: Optional[int] = Field(None, description="File size in bytes")
    target_type: AnnouncementTargetType = Field(
        ...,
        description="Audience resolution strategy",
    )
    target_ids: Optional[List[int]] = Field(
        None,
        description=(
            "IDs whose meaning depends on target_type:\n"
            "  specific_employees → employee_ids\n"
            "  teams              → team_ids\n"
            "  vendor_drivers     → vendor_ids\n"
            "  specific_drivers   → driver_ids\n"
            "  all_employees / all_drivers → omit or null"
        ),
    )
    channels: List[AnnouncementChannel] = Field(
        default=[AnnouncementChannel.PUSH, AnnouncementChannel.IN_APP],
        description=(
            "Delivery channels to use when publishing.\n"
            "  push   → FCM push notification\n"
            "  sms    → Twilio SMS to recipient phone\n"
            "  email  → SMTP email to recipient email\n"
            "  in_app → in-app inbox (always persisted; cannot be removed)\n"
            "Select any combination e.g. ['push','sms','email','in_app']"
        ),
    )
    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "title": "Office Closure Notice",
                "body": "The office will be closed on 26th Jan due to Republic Day.",
                "content_type": "TEXT",
                "target_type": "all_employees",
                "target_ids": None,
                "channels": ["push", "in_app"]
            }
        }
    )

class AnnouncementUpdate(BaseModel):
    """Body for  PUT /announcements/{id}  — DRAFT status only."""

    title: Optional[str] = Field(None, min_length=1, max_length=200)
    body: Optional[str] = Field(None, min_length=1)
    content_type: Optional[AnnouncementContentType] = None
    media_url: Optional[str] = None
    media_filename: Optional[str] = Field(None, max_length=255)
    media_size_bytes: Optional[int] = None
    target_type: Optional[AnnouncementTargetType] = None
    target_ids: Optional[List[int]] = None
    channels: Optional[List[AnnouncementChannel]] = Field(
        None,
        description="Update delivery channels (DRAFT status only)",
    )

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "title": "Updated: Office Closure Notice",
                "body": "The office will be closed on 26th Jan. Bus service will NOT run.",
                "channels": ["push", "sms", "in_app"]
            }
        }
    )


# ── Response schemas ──────────────────────────────────────────────────────────

class AnnouncementResponse(BaseModel):
    announcement_id: int
    tenant_id: str
    title: str
    body: str
    content_type: str
    media_url: Optional[str]
    media_filename: Optional[str]
    media_size_bytes: Optional[int]
    target_type: str
    target_ids: Optional[List[int]]
    channels: Optional[List[str]]
    status: str
    is_active: bool
    total_recipients: int
    success_count: int
    failure_count: int
    no_device_count: int
    sms_sent_count: int
    email_sent_count: int
    created_by: Optional[int]
    published_at: Optional[datetime]
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class AnnouncementRecipientResponse(BaseModel):
    recipient_id: int
    announcement_id: int
    recipient_type: str
    recipient_user_id: int
    delivery_status: str
    push_sent_at: Optional[datetime]
    sms_sent_at: Optional[datetime]
    email_sent_at: Optional[datetime]
    read_at: Optional[datetime]
    created_at: datetime

    class Config:
        from_attributes = True
