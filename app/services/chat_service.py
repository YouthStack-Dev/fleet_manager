"""
Chat Service — full message-send orchestration.

Send-message flow
─────────────────
1.  Validate booking belongs to tenant + caller                        (route)
2.  Get-or-create ChatSession (PostgreSQL + optional RTDB session node)(service)
3.  Pre-generate UUID for firebase_message_id
4.  Save message to PostgreSQL with the pre-generated UUID             (sync)
5.  Return HTTP response immediately  ← caller unblocked here (~20–50 ms)
  ↓ (FastAPI BackgroundTasks — run after response is flushed to client)
6.  Write message to Firebase RTDB   → mobile childAdded fires (~100–300 ms)
7.  Send FCM push to recipient        (if app is backgrounded)
8.  Translate original text → target language (~100–400 ms)
9.  Patch RTDB message node with translated_text → mobile childChanged fires
10. Update PostgreSQL translated_texts JSONB column (audit)
"""
from __future__ import annotations

import uuid
from typing import Optional

from fastapi import BackgroundTasks
from sqlalchemy.orm import Session

from app.config import settings
from app.core.logging_config import get_logger
from app.crud import chat as chat_crud
from app.firebase import chat as firebase_chat
from app.models.booking import Booking
from app.models.chat import ChatMessage, ChatSenderType, ChatSession
from app.models.route_management import RouteManagement, RouteManagementBooking
from app.services import translation_service
from app.services.fcm_service import FCMService
from app.services.session_cache import SessionCache
from app.services.session_manager import SessionManager

logger = get_logger(__name__)

# Module-level singleton — Firebase Admin SDK is already a singleton internally,
# but reusing this object avoids per-call allocation and log noise.
_fcm = FCMService()


# ── Driver session reconciliation ─────────────────────────────────────────

def reconcile_session_driver(
    db: Session,
    session: ChatSession,
    auth_driver_id: int,
) -> ChatSession:
    """
    Ensure the ChatSession's driver_id matches the authenticated driver.

    Why this is needed
    ──────────────────
    Route management stores an assigned_driver_id that comes from one specific
    vendor row.  In a multi-vendor setup the same physical driver can have
    multiple DB rows (one per vendor) with different driver_ids.  The session
    may have been created with the route-management driver_id (e.g. 14) while
    the driver logged in through a different vendor row (e.g. 12).

    When _push_notification() looks up `session.driver_id` to find the FCM
    token, it finds no active app session for driver:14 — because the FCM
    token was registered under driver:12.

    Fix: whenever a driver successfully authenticates to a chat endpoint
    (they already passed the assigned_driver_id check), trust the JWT
    identity and overwrite the session driver_id if it differs.
    """
    if session.driver_id != auth_driver_id:
        logger.info(
            "[chat_service] Driver ID mismatch on session_id=%s "
            "— updating %s → %s (multi-vendor reconciliation)",
            session.id, session.driver_id, auth_driver_id,
        )
        chat_crud.update_session_driver_id(db, session.id, auth_driver_id)
        session.driver_id = auth_driver_id   # keep in-memory object in sync
    return session


# ── Booking / driver helpers ───────────────────────────────────────────────

def get_booking_or_404(
    db: Session,
    tenant_id: str,
    booking_id: int,
) -> Booking:
    booking = (
        db.query(Booking)
        .filter_by(tenant_id=tenant_id, booking_id=booking_id)
        .first()
    )
    if not booking:
        from fastapi import HTTPException, status
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Booking {booking_id} not found for this tenant.",
        )
    return booking


def get_driver_id_for_booking(
    db: Session, booking_id: int
) -> Optional[int]:
    """
    Look up the assigned driver via route_management_bookings → route_management.
    Returns driver_id or None if no route is assigned yet.
    """
    rmb = (
        db.query(RouteManagementBooking)
        .filter_by(booking_id=booking_id)
        .first()
    )
    if not rmb:
        return None
    rm = db.query(RouteManagement).filter_by(route_id=rmb.route_id).first()
    return rm.assigned_driver_id if rm else None


# ── Session management ─────────────────────────────────────────────────────

def open_chat_session(
    db: Session,
    tenant_id: str,
    booking_id: int,
    employee_id: int,
    driver_id: Optional[int],
    background_tasks: Optional[BackgroundTasks] = None,
) -> tuple[ChatSession, bool]:
    """
    Get-or-create the ChatSession.  On first creation also:
    • Initialises the Firebase RTDB session node
    • Writes the system warning message to RTDB
    Both Firebase calls are scheduled as BackgroundTasks when background_tasks
    is provided (so they don't block the HTTP response on first-message).
    Returns (session, created).
    """
    session, created = chat_crud.get_or_create_session(
        db=db,
        tenant_id=tenant_id,
        booking_id=booking_id,
        employee_id=employee_id,
        driver_id=driver_id,
    )

    if created:
        warning_key = str(uuid.uuid4())
        if background_tasks is not None:
            background_tasks.add_task(
                firebase_chat.init_chat_session,
                tenant_id=tenant_id,
                booking_id=booking_id,
                employee_language=session.employee_language,
                driver_language=session.driver_language,
                warning_message=settings.CHAT_WARNING_MESSAGE,
            )
            background_tasks.add_task(
                firebase_chat.write_message,
                tenant_id=tenant_id,
                booking_id=booking_id,
                sender_type=ChatSenderType.SYSTEM.value,
                sender_id=None,
                original_text=settings.CHAT_WARNING_MESSAGE,
                original_language="en",
                is_system=True,
                message_key=warning_key,
            )
        else:
            # Fallback: run synchronously (e.g. called from tests or admin tools)
            firebase_chat.init_chat_session(
                tenant_id=tenant_id,
                booking_id=booking_id,
                employee_language=session.employee_language,
                driver_language=session.driver_language,
                warning_message=settings.CHAT_WARNING_MESSAGE,
            )
            firebase_chat.write_message(
                tenant_id=tenant_id,
                booking_id=booking_id,
                sender_type=ChatSenderType.SYSTEM.value,
                sender_id=None,
                original_text=settings.CHAT_WARNING_MESSAGE,
                original_language="en",
                is_system=True,
                message_key=warning_key,
            )
        logger.info(
            "[chat_service] Chat session opened: booking_id=%s", booking_id
        )
    return session, created


# ── Send message ───────────────────────────────────────────────────────────

def send_message_sync(
    db: Session,
    tenant_id: str,
    booking_id: int,
    session: ChatSession,
    sender_type: ChatSenderType,
    sender_id: int,
    text: str,
    sender_language: str,
    background_tasks: BackgroundTasks,
) -> ChatMessage:
    """
    Sync portion of the send flow (steps 3–5 in the module docstring).

    Saves the message to PostgreSQL immediately and schedules the Firebase
    RTDB write + FCM push as BackgroundTasks so the HTTP response is returned
    to the caller WITHOUT waiting for any network I/O to Firebase/FCM (~20–50 ms).

    The firebase_message_id is pre-generated as a UUID so it can be stored in
    PostgreSQL before the RTDB background task runs.  Mobile apps listen via
    .childAdded on the messages/ path and sort by the timestamp field, so the
    UUID key format is functionally identical to a Firebase push key.
    """
    # ── Step 3: Pre-generate RTDB key ─────────────────────────────────────
    firebase_message_id = str(uuid.uuid4())

    # ── Step 4: Save to PostgreSQL (sync — we need msg.id before returning) ─
    msg = chat_crud.save_message(
        db=db,
        tenant_id=tenant_id,
        booking_id=booking_id,
        session_id=session.id,
        sender_type=sender_type,
        sender_id=sender_id,
        text=text,
        language=sender_language,
        firebase_message_id=firebase_message_id,
    )

    # ── Step 5: Schedule RTDB write (background — ~600 ms, non-blocking) ──
    background_tasks.add_task(
        firebase_chat.write_message,
        tenant_id=tenant_id,
        booking_id=booking_id,
        sender_type=sender_type.value,
        sender_id=sender_id,
        original_text=text,
        original_language=sender_language,
        is_system=False,
        translated_text=text,   # placeholder; translation task patches this ~1 s later
        message_key=firebase_message_id,
    )

    # ── Step 6: Schedule FCM push (background — ~170 ms, non-blocking) ────
    background_tasks.add_task(
        _push_notification,
        db=db,
        session=session,
        sender_type=sender_type,
        text=text,
        booking_id=booking_id,
        message_id=msg.id,
    )

    return msg


def _push_notification(
    db: Session,
    session: ChatSession,
    sender_type: ChatSenderType,
    text: str,
    booking_id: int,
    message_id: int,
) -> None:
    """
    Send FCM push to the *recipient* (the side that did NOT send this message).

    FCM is only needed when the recipient's app is in the background / screen
    is off — it delivers the system-tray notification.  When the chat screen
    IS open, Firebase RTDB (write_message) already delivers the message live
    via the persistent WebSocket listener, so FCM is purely a fallback for
    background delivery.
    """
    if not settings.FCM_ENABLED:
        logger.debug(
            "[FCM] Push skipped — FCM_ENABLED=False in config  "
            "(booking_id=%s  message_id=%s)",
            booking_id, message_id,
        )
        return

    try:
        # Determine recipient
        if sender_type == ChatSenderType.EMPLOYEE:
            recipient_type = "driver"
            recipient_id   = session.driver_id
        else:
            recipient_type = "employee"
            recipient_id   = session.employee_id

        if not recipient_id:
            logger.warning(
                "[FCM] ⚠️  Push SKIPPED — booking_id=%s  sender=%s  "
                "reason: no %s assigned to this session yet",
                booking_id, sender_type.value, recipient_type,
            )
            return

        # Look up the recipient's active session (holds the FCM device token)
        session_mgr = SessionManager(db, SessionCache())
        rec_session = session_mgr.get_active_session(
            user_type=recipient_type,
            user_id=recipient_id,
            platform="app",
        )

        if not rec_session:
            logger.warning(
                "[FCM] ⚠️  Push SKIPPED — %s:%s has no active app session  "
                "(booking_id=%s)  "
                "→ Device may be offline or the user has not logged in via the app yet.",
                recipient_type, recipient_id, booking_id,
            )
            return

        if not rec_session.fcm_token:
            logger.warning(
                "[FCM] ⚠️  Push SKIPPED — %s:%s has no FCM token registered  "
                "(booking_id=%s)  "
                "→ The app must call the FCM token registration endpoint after login "
                "so push notifications can be delivered.",
                recipient_type, recipient_id, booking_id,
            )
            return

        # Token present — attempt push
        token_preview = rec_session.fcm_token[:20] + "…"
        logger.info(
            "[FCM] Sending push → %s:%s  token=%s  booking_id=%s  message_id=%s",
            recipient_type, recipient_id, token_preview, booking_id, message_id,
        )

        result = _fcm.send_notification(
            token=rec_session.fcm_token,
            title="New Message",
            body=text[:100],
            data={
                "type":        "chat_message",
                "booking_id":  str(booking_id),
                "sender_type": sender_type.value,
                "message_id":  str(message_id),
            },
            platform="app",
        )

        if result["success"]:
            logger.info(
                "[FCM] ✅ Push delivered → %s:%s  booking_id=%s  message_id=%s",
                recipient_type, recipient_id, booking_id, message_id,
            )
        else:
            error_code = result.get("error", "UNKNOWN")
            error_msg  = result.get("error_message", "")
            if result.get("should_delete"):
                logger.warning(
                    "[FCM] ❌ Push FAILED (invalid/expired token — should remove from DB) "
                    "→ %s:%s  booking_id=%s  error=%s: %s",
                    recipient_type, recipient_id, booking_id, error_code, error_msg,
                )
            else:
                logger.error(
                    "[FCM] ❌ Push FAILED → %s:%s  booking_id=%s  error=%s: %s",
                    recipient_type, recipient_id, booking_id, error_code, error_msg,
                )

    except Exception as exc:
        # FCM failure must never break the message send — RTDB already handled delivery
        logger.warning(
            "[FCM] ❌ Push FAILED (non-critical — RTDB still delivered the message) "
            "booking_id=%s  error: %s",
            booking_id, exc,
        )


# ── Background translation task ────────────────────────────────────────────

async def translate_and_update(
    message_id: int,
    tenant_id: str,
    booking_id: int,
    firebase_message_id: Optional[str],
    text: str,
    source_language: str,
    target_language: str,
) -> None:
    """
    Async background task — called by FastAPI BackgroundTasks after the
    HTTP response has already been returned to the caller.

    1. Calls Google Translate (free public endpoint, no API key needed)
    2. Updates the Firebase RTDB message node → mobile sees the translated
       text appear live (no refresh needed)
    3. Updates the PostgreSQL translated_texts JSONB column (audit)
    """
    if not settings.TRANSLATION_ENABLED:
        return
    if source_language == target_language:
        return

    try:
        translated = await translation_service.translate_text(
            text=text,
            target_language=target_language,
            source_language=source_language,
        )
        if not translated or translated == text:
            return   # no translation available or identical — nothing to update

        # ── Update Firebase RTDB ──────────────────────────────────────────
        if firebase_message_id:
            firebase_chat.update_translated_text(
                tenant_id=tenant_id,
                booking_id=booking_id,
                firebase_message_id=firebase_message_id,
                translated_text=translated,
            )

        # ── Update PostgreSQL ─────────────────────────────────────────────
        from app.database.session import SessionLocal
        db2 = SessionLocal()
        try:
            chat_crud.update_translation(
                db=db2,
                message_id=message_id,
                language=target_language,
                translated_text=translated,
            )
        finally:
            db2.close()

        logger.info(
            "[chat_service] Background translation done: "
            "message_id=%s  %s→%s",
            message_id, source_language, target_language,
        )
    except Exception as exc:
        logger.error(
            "[chat_service] Background translation failed: "
            "message_id=%s  error=%s", message_id, exc,
        )
