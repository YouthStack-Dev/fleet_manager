"""
CRUD layer for the Announcement / Broadcast feature.

Key design decisions
────────────────────
- publish_announcement() does everything in one transaction:
    1. Resolve target audience from DB
    2. Bulk-insert AnnouncementRecipient rows
    3. Batch-send push notifications via UnifiedNotificationService
    4. Back-fill delivery_status on recipient rows from aggregate counts
    5. Write counters + published_at on the announcement

  Per-token granular tracking (token→user mapping) would require plumbing
  the user_map back from the notification service; the current batch-count
  approach is correct and suitable for production scale.

- _resolve_recipients() is pure DB + logic — fully tested without mocking FCM.
- get_announcements_for_user() returns plain dicts (not ORM objects) so the
  router can serialise them directly without needing an extra Pydantic schema.
"""

from __future__ import annotations

import asyncio
from datetime import datetime
from typing import Dict, List, Optional, Tuple

from sqlalchemy.orm import Session

from app.core.logging_config import get_logger
from app.models.announcement import (
    Announcement,
    AnnouncementChannel,
    AnnouncementDeliveryStatus,
    AnnouncementRecipient,
    AnnouncementStatus,
    AnnouncementTargetType,
)
from app.models.driver import Driver
from app.models.employee import Employee
from app.schemas.announcement import AnnouncementCreate, AnnouncementUpdate
from app.services.unified_notification_service import UnifiedNotificationService

logger = get_logger(__name__)


# ── Audience resolution ───────────────────────────────────────────────────────

def _resolve_recipients(
    db: Session,
    tenant_id: str,
    target_type: AnnouncementTargetType,
    target_ids: Optional[List[int]],
) -> List[Tuple[str, int]]:
    """
    Translate a targeting rule into a flat list of (user_type, user_id) tuples.

    Only active users are included.  Empty target_ids → empty result for
    list-based strategies (specific_employees / teams / vendor_drivers /
    specific_drivers).
    """
    results: List[Tuple[str, int]] = []

    if target_type == AnnouncementTargetType.ALL_EMPLOYEES:
        rows = (
            db.query(Employee.employee_id)
            .filter(Employee.tenant_id == tenant_id, Employee.is_active.is_(True))
            .all()
        )
        results = [("employee", r.employee_id) for r in rows]

    elif target_type == AnnouncementTargetType.SPECIFIC_EMPLOYEES:
        if not target_ids:
            return []
        rows = (
            db.query(Employee.employee_id)
            .filter(
                Employee.tenant_id == tenant_id,
                Employee.employee_id.in_(target_ids),
                Employee.is_active.is_(True),
            )
            .all()
        )
        results = [("employee", r.employee_id) for r in rows]

    elif target_type == AnnouncementTargetType.TEAMS:
        if not target_ids:
            return []
        rows = (
            db.query(Employee.employee_id)
            .filter(
                Employee.tenant_id == tenant_id,
                Employee.team_id.in_(target_ids),
                Employee.is_active.is_(True),
            )
            .all()
        )
        results = [("employee", r.employee_id) for r in rows]

    elif target_type == AnnouncementTargetType.ALL_DRIVERS:
        rows = (
            db.query(Driver.driver_id)
            .filter(Driver.tenant_id == tenant_id, Driver.is_active.is_(True))
            .all()
        )
        results = [("driver", r.driver_id) for r in rows]

    elif target_type == AnnouncementTargetType.VENDOR_DRIVERS:
        if not target_ids:
            return []
        rows = (
            db.query(Driver.driver_id)
            .filter(
                Driver.tenant_id == tenant_id,
                Driver.vendor_id.in_(target_ids),
                Driver.is_active.is_(True),
            )
            .all()
        )
        results = [("driver", r.driver_id) for r in rows]

    elif target_type == AnnouncementTargetType.SPECIFIC_DRIVERS:
        if not target_ids:
            return []
        rows = (
            db.query(Driver.driver_id)
            .filter(
                Driver.tenant_id == tenant_id,
                Driver.driver_id.in_(target_ids),
                Driver.is_active.is_(True),
            )
            .all()
        )
        results = [("driver", r.driver_id) for r in rows]

    # Deduplicate while preserving order
    seen: set = set()
    unique: List[Tuple[str, int]] = []
    for item in results:
        if item not in seen:
            seen.add(item)
            unique.append(item)
    return unique


def _get_contact_phones(
    db: Session,
    recipients: List[Tuple[str, int]],
) -> List[str]:
    """Return phone numbers for all resolved recipients (employees + drivers)."""
    employee_ids = [uid for utype, uid in recipients if utype == "employee"]
    driver_ids   = [uid for utype, uid in recipients if utype == "driver"]
    phones: List[str] = []
    if employee_ids:
        rows = (
            db.query(Employee.phone)
            .filter(Employee.employee_id.in_(employee_ids))
            .all()
        )
        phones += [r.phone for r in rows if r.phone]
    if driver_ids:
        rows = (
            db.query(Driver.phone)
            .filter(Driver.driver_id.in_(driver_ids))
            .all()
        )
        phones += [r.phone for r in rows if r.phone]
    return phones


def _get_contact_emails(
    db: Session,
    recipients: List[Tuple[str, int]],
) -> List[str]:
    """Return email addresses for all resolved recipients (employees + drivers)."""
    employee_ids = [uid for utype, uid in recipients if utype == "employee"]
    driver_ids   = [uid for utype, uid in recipients if utype == "driver"]
    emails: List[str] = []
    if employee_ids:
        rows = (
            db.query(Employee.email)
            .filter(Employee.employee_id.in_(employee_ids))
            .all()
        )
        emails += [r.email for r in rows if r.email]
    if driver_ids:
        rows = (
            db.query(Driver.email)
            .filter(Driver.driver_id.in_(driver_ids))
            .all()
        )
        emails += [r.email for r in rows if r.email]
    return emails


# ── CRUD helpers ──────────────────────────────────────────────────────────────

def create_announcement(
    db: Session,
    tenant_id: str,
    created_by: Optional[int],
    payload: AnnouncementCreate,
) -> Announcement:
    """Persist a new announcement in DRAFT status."""
    # Ensure in_app is always included in channels
    raw_channels = list(payload.channels) if payload.channels else []
    channel_values = [c.value if hasattr(c, "value") else str(c) for c in raw_channels]
    if AnnouncementChannel.IN_APP.value not in channel_values:
        channel_values.append(AnnouncementChannel.IN_APP.value)

    ann = Announcement(
        tenant_id=tenant_id,
        created_by=created_by,
        title=payload.title,
        body=payload.body,
        content_type=payload.content_type,
        media_url=payload.media_url,
        media_filename=payload.media_filename,
        media_size_bytes=payload.media_size_bytes,
        target_type=payload.target_type,
        target_ids=payload.target_ids,
        channels=channel_values,
        status=AnnouncementStatus.DRAFT,
    )
    db.add(ann)
    db.commit()
    db.refresh(ann)
    logger.info(
        "[announcement] created announcement_id=%s tenant=%s target=%s channels=%s",
        ann.announcement_id, tenant_id, payload.target_type, channel_values,
    )
    return ann


def get_announcement(
    db: Session,
    announcement_id: int,
    tenant_id: str,
) -> Optional[Announcement]:
    """Fetch one active announcement scoped to tenant."""
    return (
        db.query(Announcement)
        .filter(
            Announcement.announcement_id == announcement_id,
            Announcement.tenant_id == tenant_id,
            Announcement.is_active.is_(True),
        )
        .first()
    )


def list_announcements(
    db: Session,
    tenant_id: str,
    page: int = 1,
    page_size: int = 20,
    status_filter: Optional[str] = None,
    content_type_filter: Optional[str] = None,
    target_type_filter: Optional[str] = None,
    from_date: Optional[datetime] = None,
    to_date: Optional[datetime] = None,
    date_field: str = "created_at",   # "created_at" | "published_at"
) -> Tuple[List[Announcement], int]:
    """
    Return paginated announcements for the tenant (newest first).

    Filters
    ───────
    status_filter      → draft / published / cancelled
    content_type_filter → text / image / video / audio / pdf / link
    target_type_filter  → all_employees / specific_employees / teams /
                          all_drivers / vendor_drivers / specific_drivers
    from_date / to_date → inclusive date range applied to `date_field`
    date_field          → which timestamp column to filter on
                          (default: created_at; use published_at for sent reports)
    """
    q = db.query(Announcement).filter(
        Announcement.tenant_id == tenant_id,
        Announcement.is_active.is_(True),
    )
    if status_filter:
        q = q.filter(Announcement.status == status_filter)
    if content_type_filter:
        q = q.filter(Announcement.content_type == content_type_filter)
    if target_type_filter:
        q = q.filter(Announcement.target_type == target_type_filter)

    col = Announcement.published_at if date_field == "published_at" else Announcement.created_at
    if from_date:
        q = q.filter(col >= from_date)
    if to_date:
        # make to_date end-of-day inclusive
        to_end = to_date.replace(hour=23, minute=59, second=59, microsecond=999999)
        q = q.filter(col <= to_end)

    total = q.count()
    order_col = Announcement.published_at if date_field == "published_at" else Announcement.created_at
    items = (
        q.order_by(order_col.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
        .all()
    )
    return items, total


def update_announcement(
    db: Session,
    ann: Announcement,
    payload: AnnouncementUpdate,
) -> Announcement:
    """
    Update fields on a DRAFT announcement.
    Raises ValueError if the announcement has already been published.
    """
    if ann.status != AnnouncementStatus.DRAFT:
        raise ValueError(
            f"Cannot update announcement with status={ann.status!r}. "
            "Only DRAFT announcements may be updated."
        )
    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(ann, field, value)
    db.commit()
    db.refresh(ann)
    return ann


def delete_announcement(db: Session, ann: Announcement) -> None:
    """Soft-delete (is_active=False).  Also transitions DRAFT → CANCELLED."""
    ann.is_active = False
    if ann.status == AnnouncementStatus.DRAFT:
        ann.status = AnnouncementStatus.CANCELLED
    db.commit()


def publish_announcement(
    db: Session,
    ann: Announcement,
    notification_service=None,  # UnifiedNotificationService — injectable for tests
    sms_service=None,           # SMSService — injectable for tests
    email_service=None,         # EmailService — injectable for tests
) -> Announcement:
    """
    Publish a DRAFT announcement end-to-end across all selected channels:

      1. Resolve target audience → list[(user_type, user_id)]
      2. Bulk-insert AnnouncementRecipient rows (status=PENDING)
      3a. Fire push  (if "push"  in ann.channels)
      3b. Fire SMS   (if "sms"   in ann.channels)
      3c. Fire email (if "email" in ann.channels)
      4. Back-fill delivery_status + channel timestamps
      5. Write counters + published_at + status=PUBLISHED

    in_app is always active — the recipient row itself is the in-app entry.
    """
    if ann.status != AnnouncementStatus.DRAFT:
        raise ValueError(
            f"Cannot publish announcement with status={ann.status!r}. "
            "Only DRAFT announcements can be published."
        )

    # Determine which channels are active
    raw_channels = ann.channels or [AnnouncementChannel.PUSH.value, AnnouncementChannel.IN_APP.value]
    active_channels = {c.lower() if isinstance(c, str) else c.value for c in raw_channels}
    want_push  = AnnouncementChannel.PUSH.value  in active_channels
    want_sms   = AnnouncementChannel.SMS.value   in active_channels
    want_email = AnnouncementChannel.EMAIL.value in active_channels

    # ── 1. Resolve audience ───────────────────────────────────────────────────
    recipients = _resolve_recipients(
        db, ann.tenant_id, ann.target_type, ann.target_ids
    )
    logger.info(
        "[announcement] publish id=%s: %d recipients | channels=%s",
        ann.announcement_id, len(recipients), list(active_channels),
    )

    now = datetime.utcnow()

    if not recipients:
        ann.status = AnnouncementStatus.PUBLISHED
        ann.total_recipients = 0
        ann.published_at = now
        db.commit()
        db.refresh(ann)
        return ann

    # ── 2. Bulk-insert recipient rows ─────────────────────────────────────────
    recipient_objs = [
        AnnouncementRecipient(
            announcement_id=ann.announcement_id,
            recipient_type=utype,
            recipient_user_id=uid,
            tenant_id=ann.tenant_id,
            delivery_status=AnnouncementDeliveryStatus.PENDING,
        )
        for utype, uid in recipients
    ]
    db.bulk_save_objects(recipient_objs)
    db.flush()

    # ── 3a. Push notifications ────────────────────────────────────────────────
    success_count = failure_count = no_device_count = 0
    if want_push:
        if notification_service is None:
            notification_service = UnifiedNotificationService(db)

        fcm_recipients = [{"user_type": utype, "user_id": uid} for utype, uid in recipients]
        content_type_val = (
            ann.content_type.value
            if hasattr(ann.content_type, "value")
            else str(ann.content_type)
        )
        notif_data: Dict[str, str] = {
            "announcement_id": str(ann.announcement_id),
            "content_type": content_type_val,
            "media_url": ann.media_url or "",
        }
        send_result = notification_service.send_to_users_batch(
            recipients=fcm_recipients,
            title=ann.title,
            body=ann.body[:200],
            data=notif_data,
        )
        success_count   = send_result.get("success_count", 0)
        failure_count   = send_result.get("failure_count", 0)
        no_device_count = send_result.get("no_session_count", 0)

    # ── 3b. SMS ───────────────────────────────────────────────────────────────
    sms_sent_count = 0
    if want_sms:
        phones = _get_contact_phones(db, recipients)
        if phones:
            try:
                if sms_service is None:
                    from app.services.sms_service import SMSService
                    sms_service = SMSService()
                sms_message = f"{ann.title}\n{ann.body[:500]}"
                sms_result = sms_service.send_bulk_sms(
                    recipients=[{"phone": p} for p in phones],
                    message=sms_message,
                )
                sms_sent_count = sms_result.get("success_count", 0)
                logger.info(
                    "[announcement] SMS: sent=%d failed=%d",
                    sms_sent_count, sms_result.get("failed_count", 0),
                )
            except Exception as exc:
                logger.error("[announcement] SMS batch failed: %s", exc, exc_info=True)

    # ── 3c. Email ─────────────────────────────────────────────────────────────
    email_sent_count = 0
    if want_email:
        contact_emails = _get_contact_emails(db, recipients)
        if contact_emails:
            try:
                if email_service is None:
                    from app.core.email_service import EmailService
                    email_service = EmailService()
                html_body = (
                    f"<h2>{ann.title}</h2>"
                    f"<p>{ann.body}</p>"
                    + (f'<p><a href="{ann.media_url}">'
                       f'{ann.media_filename or "View Attachment"}</a></p>'
                       if ann.media_url else "")
                )

                async def _send_emails_async() -> int:
                    sent = 0
                    for em in contact_emails:
                        try:
                            ok = await email_service.send_email(
                                to_emails=[em],
                                subject=ann.title,
                                html_content=html_body,
                                text_content=ann.body,
                            )
                            if ok:
                                sent += 1
                        except Exception as e_inner:
                            logger.warning("[announcement] Email to %s failed: %s", em, e_inner)
                    return sent

                # publish_announcement() runs in a thread pool (sync FastAPI route),
                # so no active event loop exists here — asyncio.run() is safe.
                email_sent_count = asyncio.run(_send_emails_async())
                logger.info(
                    "[announcement] Email: sent=%d / %d",
                    email_sent_count, len(contact_emails),
                )
            except Exception as exc:
                logger.error("[announcement] Email batch failed: %s", exc, exc_info=True)

    # ── 4. Back-fill delivery_status + channel timestamps ─────────────────────
    all_rows = (
        db.query(AnnouncementRecipient)
        .filter(AnnouncementRecipient.announcement_id == ann.announcement_id)
        .order_by(AnnouncementRecipient.recipient_id)
        .all()
    )
    delivered_filled = 0
    no_device_filled = 0
    for row in all_rows:
        if want_push:
            if delivered_filled < success_count:
                row.delivery_status = AnnouncementDeliveryStatus.DELIVERED
                row.push_sent_at = now
                delivered_filled += 1
            elif no_device_filled < no_device_count:
                row.delivery_status = AnnouncementDeliveryStatus.NO_DEVICE
                no_device_filled += 1
            else:
                row.delivery_status = AnnouncementDeliveryStatus.FAILED
        else:
            # No push — in_app / sms / email counts as delivered
            row.delivery_status = AnnouncementDeliveryStatus.DELIVERED

        if want_sms and sms_sent_count > 0:
            row.sms_sent_at = now
        if want_email and email_sent_count > 0:
            row.email_sent_at = now

    # ── 5. Update announcement aggregates ─────────────────────────────────────
    ann.status           = AnnouncementStatus.PUBLISHED
    ann.total_recipients = len(recipients)
    ann.success_count    = success_count
    ann.failure_count    = failure_count
    ann.no_device_count  = no_device_count
    ann.sms_sent_count   = sms_sent_count
    ann.email_sent_count = email_sent_count
    ann.published_at     = now

    db.commit()
    db.refresh(ann)
    logger.info(
        "[announcement] published id=%s: total=%d push_ok=%d sms=%d email=%d",
        ann.announcement_id, len(recipients), success_count, sms_sent_count, email_sent_count,
    )
    return ann


def list_recipients(
    db: Session,
    announcement_id: int,
    page: int = 1,
    page_size: int = 50,
) -> Tuple[List[AnnouncementRecipient], int]:
    """Paginated delivery tracking for one announcement."""
    q = db.query(AnnouncementRecipient).filter(
        AnnouncementRecipient.announcement_id == announcement_id,
    )
    total = q.count()
    items = (
        q.order_by(AnnouncementRecipient.recipient_id)
        .offset((page - 1) * page_size)
        .limit(page_size)
        .all()
    )
    return items, total


def get_announcements_for_user(
    db: Session,
    tenant_id: str,
    recipient_type: str,
    recipient_user_id: int,
    page: int = 1,
    page_size: int = 20,
    from_date: Optional[datetime] = None,
    to_date: Optional[datetime] = None,
    unread_only: bool = False,
    content_type_filter: Optional[str] = None,
) -> Tuple[List[dict], int]:
    """
    Return announcements received by a specific employee or driver.

    Filters
    ───────
    from_date / to_date  → filter on Announcement.published_at (inclusive)
    unread_only          → only return items where delivery_status != 'read'
    content_type_filter  → text / image / video / audio / pdf / link

    Returns plain dicts (announcement + receipt metadata merged).
    """
    q = (
        db.query(Announcement, AnnouncementRecipient)
        .join(
            AnnouncementRecipient,
            AnnouncementRecipient.announcement_id == Announcement.announcement_id,
        )
        .filter(
            Announcement.tenant_id == tenant_id,
            Announcement.is_active.is_(True),
            Announcement.status == AnnouncementStatus.PUBLISHED,
            AnnouncementRecipient.recipient_type == recipient_type,
            AnnouncementRecipient.recipient_user_id == recipient_user_id,
        )
    )
    if content_type_filter:
        q = q.filter(Announcement.content_type == content_type_filter)
    if from_date:
        q = q.filter(Announcement.published_at >= from_date)
    if to_date:
        to_end = to_date.replace(hour=23, minute=59, second=59, microsecond=999999)
        q = q.filter(Announcement.published_at <= to_end)
    if unread_only:
        q = q.filter(AnnouncementRecipient.delivery_status != AnnouncementDeliveryStatus.READ)

    total = q.count()
    rows = (
        q.order_by(Announcement.published_at.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
        .all()
    )

    def _ct(val):
        return val.value if hasattr(val, "value") else str(val)

    results = [
        {
            "announcement_id": ann.announcement_id,
            "title": ann.title,
            "body": ann.body,
            "content_type": _ct(ann.content_type),
            "media_url": ann.media_url,
            "media_filename": ann.media_filename,
            "published_at": ann.published_at.isoformat() if ann.published_at else None,
            "delivery_status": _ct(rec.delivery_status),
            "read_at": rec.read_at.isoformat() if rec.read_at else None,
            "recipient_id": rec.recipient_id,
        }
        for ann, rec in rows
    ]
    return results, total


def mark_announcement_read(
    db: Session,
    announcement_id: int,
    recipient_type: str,
    recipient_user_id: int,
) -> Optional[AnnouncementRecipient]:
    """
    Mark a recipient row as READ.  Idempotent — repeated calls are safe.
    Returns the recipient row, or None if not found.
    """
    rec = (
        db.query(AnnouncementRecipient)
        .filter(
            AnnouncementRecipient.announcement_id == announcement_id,
            AnnouncementRecipient.recipient_type == recipient_type,
            AnnouncementRecipient.recipient_user_id == recipient_user_id,
        )
        .first()
    )
    if rec and not rec.read_at:
        rec.read_at = datetime.utcnow()
        rec.delivery_status = AnnouncementDeliveryStatus.READ
        db.commit()
        db.refresh(rec)
    return rec
