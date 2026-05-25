"""
Firebase Realtime Database (RTDB) operations for the Chat feature.

RTDB path layout
────────────────
chats/
  {tenant_id}/
    booking_{booking_id}/
      session/
        is_active:        true
        activated_at:     "2026-05-25T10:00:00Z"
        employee_language: "en"
        driver_language:  "hi"
        warning_message:  "Warning: Please do not share..."
      messages/
        {push_id}/
          sender_type:       "employee" | "driver" | "system"
          sender_id:         42          (null for system)
          original_text:     "I am at Gate B"
          translated_text:   "मैं गेट B पर हूं"    ← updated async ~1 s after send
          original_language: "en"
          timestamp:         1716624000000  (ms since epoch)
          is_system:         false

Mobile apps attach a ChildEventListener / .observe(.childAdded) on the
messages/ path — Firebase pushes every new node in real-time.
"""
from __future__ import annotations

from datetime import datetime
from typing import Optional

import firebase_admin
from firebase_admin import db

from app.core.logging_config import get_logger
from app.firebase.config import init_firebase

logger = get_logger(__name__)


# ── Internal helpers ───────────────────────────────────────────────────────

def _firebase_ready() -> bool:
    """Returns True if Firebase Admin SDK is initialised (or can be initialised)."""
    try:
        firebase_admin.get_app()
        return True
    except ValueError:
        try:
            init_firebase()
            firebase_admin.get_app()
            return True
        except Exception as exc:
            logger.error("[firebase_chat] Firebase not available: %s", exc)
            return False


def _session_ref(tenant_id: str, booking_id: int):
    return db.reference(f"chats/{tenant_id}/booking_{booking_id}/session")


def _messages_ref(tenant_id: str, booking_id: int):
    return db.reference(f"chats/{tenant_id}/booking_{booking_id}/messages")


def _message_ref(tenant_id: str, booking_id: int, firebase_message_id: str):
    return db.reference(
        f"chats/{tenant_id}/booking_{booking_id}/messages/{firebase_message_id}"
    )


# ── Public API ─────────────────────────────────────────────────────────────

def init_chat_session(
    tenant_id: str,
    booking_id: int,
    employee_language: str = "en",
    driver_language: str = "en",
    warning_message: str = "",
) -> bool:
    """
    Create (or overwrite) the session node in RTDB.
    Called once when a ChatSession row is first created in PostgreSQL.
    Returns True on success, False if Firebase is unavailable.
    """
    if not _firebase_ready():
        return False
    try:
        _session_ref(tenant_id, booking_id).set(
            {
                "is_active": True,
                "activated_at": datetime.utcnow().isoformat(),
                "employee_language": employee_language,
                "driver_language": driver_language,
                "warning_message": warning_message,
            }
        )
        logger.info(
            "[firebase_chat] Session initialised: booking_id=%s", booking_id
        )
        return True
    except Exception as exc:
        logger.error("[firebase_chat] init_chat_session error: %s", exc)
        return False


def write_message(
    tenant_id: str,
    booking_id: int,
    sender_type: str,
    sender_id: Optional[int],
    original_text: str,
    original_language: str,
    is_system: bool = False,
    translated_text: Optional[str] = None,
) -> Optional[str]:
    """
    Push a new message node to RTDB.
    Returns the Firebase push key (firebase_message_id) or None on failure.

    Mobile clients receive this via their ChildEventListener / childAdded
    observer immediately (sub-second latency via Firebase WebSocket).
    """
    if not _firebase_ready():
        return None
    try:
        payload = {
            "sender_type": sender_type,
            "sender_id": sender_id,
            "original_text": original_text,
            "translated_text": translated_text or original_text,
            "original_language": original_language,
            "timestamp": int(datetime.utcnow().timestamp() * 1000),  # ms
            "is_system": is_system,
        }
        new_ref = _messages_ref(tenant_id, booking_id).push(payload)
        logger.info(
            "[firebase_chat] Message written: booking_id=%s  key=%s",
            booking_id, new_ref.key,
        )
        return new_ref.key
    except Exception as exc:
        logger.error("[firebase_chat] write_message error: %s", exc)
        return None


def update_translated_text(
    tenant_id: str,
    booking_id: int,
    firebase_message_id: str,
    translated_text: str,
) -> bool:
    """
    Patch the translated_text field on an existing RTDB message node.

    Called ~1 second after the original write, once the async translation
    completes.  Mobile apps see the update live (Firebase real-time patch).
    """
    if not _firebase_ready():
        return False
    try:
        _message_ref(tenant_id, booking_id, firebase_message_id).update(
            {"translated_text": translated_text}
        )
        logger.info(
            "[firebase_chat] Translation updated: key=%s", firebase_message_id
        )
        return True
    except Exception as exc:
        logger.error("[firebase_chat] update_translated_text error: %s", exc)
        return False


def update_session_language(
    tenant_id: str,
    booking_id: int,
    user_role: str,   # "employee" | "driver"
    language: str,
) -> bool:
    """Sync a language-preference change to the RTDB session node."""
    if not _firebase_ready():
        return False
    try:
        field = (
            "employee_language" if user_role == "employee" else "driver_language"
        )
        _session_ref(tenant_id, booking_id).update({field: language})
        return True
    except Exception as exc:
        logger.error("[firebase_chat] update_session_language error: %s", exc)
        return False


def close_chat_session(tenant_id: str, booking_id: int) -> bool:
    """Mark the RTDB session node as inactive (trip ended)."""
    if not _firebase_ready():
        return False
    try:
        _session_ref(tenant_id, booking_id).update({"is_active": False})
        return True
    except Exception as exc:
        logger.error("[firebase_chat] close_chat_session error: %s", exc)
        return False
