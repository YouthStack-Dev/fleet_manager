"""
Firebase Realtime Database (RTDB) operations for the Chat feature.

RTDB path layout
────────────────
chats/
  {tenant_id}/
    booking_{booking_id}/
      session/
        is_active:         true
        activated_at:      "2026-05-25T10:00:00Z"
        employee_language: "en"
        driver_language:   "hi"
        warning_message:   "Warning: Please do not share..."
      messages/
        {push_id}/
          sender_type:       "employee" | "driver" | "system"
          sender_id:         42          (null for system)
          original_text:     "I am at Gate B"
          translated_text:   "मैं गेट B पर हूं"    ← patched async ~1 s after send
          original_language: "en"
          timestamp:         1716624000000  (ms since epoch)
          is_system:         false

──────────────────────────────────────────────────────────────────────────────
How Firebase RTDB delivers real-time updates  (like a managed WebSocket)
──────────────────────────────────────────────────────────────────────────────
1. Mobile app opens a PERSISTENT WebSocket to Firebase servers when the chat
   screen is shown — one connection, stays open.

2. The app calls  .observe(.childAdded)  /  addChildEventListener  on the path
   "chats/{tenant_id}/booking_{booking_id}/messages".
   Firebase servers remember: "this device is watching that path".

3. When THIS backend calls  _messages_ref(...).push(payload)  Firebase servers
   immediately fan the new node out to EVERY connected device that is watching
   the path — no polling, no HTTP round-trip, sub-second latency.

4. Translated-text patch:  update_translated_text() calls  ref.update()  ~1 s
   later.  Firebase servers push a PATCH event (.childChanged) to the same
   listeners — the translated text appears live without a second message.

5. When the chat screen is closed the app removes the listener.  No connection,
   no data — Firebase charges by data transferred, not by open connections.

This is different from a webhook in one key way:
  • Webhook  = YOUR server calls THEIR server (HTTP POST) when something happens.
  • RTDB     = Firebase calls the CLIENT (via WebSocket) when something is written.
  The mobile app IS the subscriber — no endpoint needed on your side.
"""
from __future__ import annotations

import os
from datetime import datetime
from typing import Optional

import firebase_admin
from firebase_admin import db

from app.core.logging_config import get_logger
from app.firebase.config import init_firebase

logger = get_logger(__name__)

# ── Internal helpers ───────────────────────────────────────────────────────────

_rtdb_warned_once = False   # avoid flooding logs with the same warning


def _firebase_ready() -> bool:
    """
    Returns True only when the Firebase Admin SDK is initialised AND a valid
    RTDB database URL has been provided.

    Logs a single clear diagnostic line explaining exactly what is wrong so
    operators can fix the configuration without reading source code.
    """
    global _rtdb_warned_once

    # 1. SDK initialised?
    try:
        firebase_admin.get_app()
    except ValueError:
        # Not initialised yet — try once
        try:
            init_firebase()
            firebase_admin.get_app()
        except Exception as exc:
            if not _rtdb_warned_once:
                logger.error(
                    "[Firebase/RTDB] ❌ NOT READY — SDK init failed: %s  "
                    "→ All RTDB writes will be SKIPPED. "
                    "Fix FIREBASE_KEY_PATH / FIREBASE_DATABASE_URL and restart.",
                    exc,
                )
                _rtdb_warned_once = True
            return False

    # 2. RTDB URL present?
    rtdb_url = os.getenv("FIREBASE_DATABASE_URL", "").strip()
    if not rtdb_url:
        if not _rtdb_warned_once:
            logger.warning(
                "[Firebase/RTDB] ⚠️  NOT READY — FIREBASE_DATABASE_URL is empty.  "
                "FCM push notifications will still work, but chat messages will NOT "
                "appear in real-time on the device screen until this env var is set.  "
                "Set it to: https://<your-project>-default-rtdb.firebaseio.com"
            )
            _rtdb_warned_once = True
        return False

    _rtdb_warned_once = False   # reset if config was fixed at runtime
    return True


def _session_ref(tenant_id: str, booking_id: int):
    return db.reference(f"chats/{tenant_id}/booking_{booking_id}/session")


def _messages_ref(tenant_id: str, booking_id: int):
    return db.reference(f"chats/{tenant_id}/booking_{booking_id}/messages")


def _message_ref(tenant_id: str, booking_id: int, firebase_message_id: str):
    return db.reference(
        f"chats/{tenant_id}/booking_{booking_id}/messages/{firebase_message_id}"
    )


# ── Public API ─────────────────────────────────────────────────────────────────

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
        logger.warning(
            "[Firebase/RTDB] ⚠️  init_chat_session SKIPPED — "
            "booking_id=%s  reason: Firebase not ready (see earlier log for details)",
            booking_id,
        )
        return False
    try:
        path = f"chats/{tenant_id}/booking_{booking_id}/session"
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
            "[Firebase/RTDB] ✅ Session node created — path: %s", path
        )
        return True
    except Exception as exc:
        logger.error(
            "[Firebase/RTDB] ❌ init_chat_session FAILED — booking_id=%s  error: %s",
            booking_id, exc,
        )
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
    Returns the Firebase push key (firebase_message_id) or None on failure/skip.

    ── What happens on the mobile side ───────────────────────────────────────
    The recipient's device has an open WebSocket to Firebase servers.
    The moment this .push() call completes, Firebase servers broadcast a
    childAdded event to every listener on the messages/ path — typically
    within 100–300 ms regardless of whether the app is open or backgrounded
    (backgrounded apps also receive FCM separately for the system tray alert).
    ─────────────────────────────────────────────────────────────────────────
    """
    if not _firebase_ready():
        logger.warning(
            "[Firebase/RTDB] ⚠️  write_message SKIPPED — "
            "booking_id=%s  sender=%s:%s  "
            "→ Message saved to PostgreSQL only. "
            "Real-time delivery to device screen will NOT happen until "
            "FIREBASE_DATABASE_URL is configured.",
            booking_id, sender_type, sender_id,
        )
        return None

    path = f"chats/{tenant_id}/booking_{booking_id}/messages"
    try:
        payload = {
            "sender_type": sender_type,
            "sender_id": sender_id,
            "original_text": original_text,
            "translated_text": translated_text or original_text,
            "original_language": original_language,
            "timestamp": int(datetime.utcnow().timestamp() * 1000),
            "is_system": is_system,
        }
        new_ref = _messages_ref(tenant_id, booking_id).push(payload)
        logger.info(
            "[Firebase/RTDB] ✅ Message written — path: %s/%s  "
            "sender=%s:%s  text_preview='%s'",
            path, new_ref.key,
            sender_type, sender_id,
            original_text[:40] + ("…" if len(original_text) > 40 else ""),
        )
        return new_ref.key
    except Exception as exc:
        logger.error(
            "[Firebase/RTDB] ❌ write_message FAILED — path: %s  "
            "sender=%s:%s  error: %s",
            path, sender_type, sender_id, exc,
        )
        return None


def update_translated_text(
    tenant_id: str,
    booking_id: int,
    firebase_message_id: str,
    translated_text: str,
) -> bool:
    """
    Patch the translated_text field on an existing RTDB message node.

    Called ~1 second after the original write once the async translation
    completes.  Firebase servers push a childChanged event to all listeners —
    the translated text appears live on screen without any extra tap or refresh.
    """
    if not _firebase_ready():
        logger.warning(
            "[Firebase/RTDB] ⚠️  update_translated_text SKIPPED — "
            "firebase_message_id=%s  reason: Firebase not ready",
            firebase_message_id,
        )
        return False
    path = f"chats/{tenant_id}/booking_{booking_id}/messages/{firebase_message_id}"
    try:
        _message_ref(tenant_id, booking_id, firebase_message_id).update(
            {"translated_text": translated_text}
        )
        logger.info(
            "[Firebase/RTDB] ✅ Translation patched — path: %s  "
            "translated_preview='%s'",
            path,
            translated_text[:40] + ("…" if len(translated_text) > 40 else ""),
        )
        return True
    except Exception as exc:
        logger.error(
            "[Firebase/RTDB] ❌ update_translated_text FAILED — path: %s  error: %s",
            path, exc,
        )
        return False


def update_session_language(
    tenant_id: str,
    booking_id: int,
    user_role: str,
    language: str,
) -> bool:
    """Sync a language-preference change to the RTDB session node."""
    if not _firebase_ready():
        logger.warning(
            "[Firebase/RTDB] ⚠️  update_session_language SKIPPED — "
            "booking_id=%s  user_role=%s  reason: Firebase not ready",
            booking_id, user_role,
        )
        return False
    try:
        field = "employee_language" if user_role == "employee" else "driver_language"
        _session_ref(tenant_id, booking_id).update({field: language})
        logger.info(
            "[Firebase/RTDB] ✅ Language updated — booking_id=%s  %s=%s",
            booking_id, field, language,
        )
        return True
    except Exception as exc:
        logger.error(
            "[Firebase/RTDB] ❌ update_session_language FAILED — "
            "booking_id=%s  error: %s",
            booking_id, exc,
        )
        return False


def close_chat_session(tenant_id: str, booking_id: int) -> bool:
    """Mark the RTDB session node as inactive (trip ended)."""
    if not _firebase_ready():
        logger.warning(
            "[Firebase/RTDB] ⚠️  close_chat_session SKIPPED — "
            "booking_id=%s  reason: Firebase not ready",
            booking_id,
        )
        return False
    try:
        _session_ref(tenant_id, booking_id).update({"is_active": False})
        logger.info(
            "[Firebase/RTDB] ✅ Session closed — booking_id=%s", booking_id
        )
        return True
    except Exception as exc:
        logger.error(
            "[Firebase/RTDB] ❌ close_chat_session FAILED — "
            "booking_id=%s  error: %s",
            booking_id, exc,
        )
        return False
