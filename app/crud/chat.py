"""
CRUD operations for the Chat feature.

All writes go to PostgreSQL (permanent audit trail).
Firebase RTDB is handled separately in app/firebase/chat.py.
"""
from __future__ import annotations

from typing import List, Optional, Tuple

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.config import settings
from app.core.logging_config import get_logger
from app.models.chat import ChatMessage, ChatSenderType, ChatSession

logger = get_logger(__name__)


# ── Session ────────────────────────────────────────────────────────────────

def get_session(
    db: Session,
    tenant_id: str,
    booking_id: int,
) -> Optional[ChatSession]:
    return (
        db.query(ChatSession)
        .filter_by(tenant_id=tenant_id, booking_id=booking_id)
        .first()
    )


def get_session_by_id(db: Session, session_id: int) -> Optional[ChatSession]:
    return db.query(ChatSession).filter_by(id=session_id).first()


def get_or_create_session(
    db: Session,
    tenant_id: str,
    booking_id: int,
    employee_id: int,
    driver_id: Optional[int] = None,
) -> Tuple[ChatSession, bool]:
    """
    Returns (ChatSession, created: bool).

    On first call for a booking:
      • creates the ChatSession row
      • injects a system warning message into chat_messages
      • caller is responsible for mirroring to Firebase RTDB
    """
    session = get_session(db, tenant_id, booking_id)
    if session:
        return session, False

    session = ChatSession(
        tenant_id=tenant_id,
        booking_id=booking_id,
        employee_id=employee_id,
        driver_id=driver_id,
    )
    db.add(session)
    db.flush()  # get session.id without full commit

    # Auto-inject the safety warning as the first system message
    warning = ChatMessage(
        tenant_id=tenant_id,
        booking_id=booking_id,
        session_id=session.id,
        sender_type=ChatSenderType.SYSTEM,
        sender_id=None,
        original_text=settings.CHAT_WARNING_MESSAGE,
        original_language="en",
        translated_texts={},
        is_system_message=True,
    )
    db.add(warning)
    db.commit()
    db.refresh(session)

    logger.info(
        "[chat_crud] New chat session created: "
        "booking_id=%s  session_id=%s",
        booking_id, session.id,
    )
    return session, True


def update_session_language(
    db: Session,
    session_id: int,
    user_role: str,       # "employee" | "driver"
    language: str,
) -> Optional[ChatSession]:
    session = db.query(ChatSession).filter_by(id=session_id).first()
    if not session:
        return None
    if user_role == "employee":
        session.employee_language = language
    elif user_role == "driver":
        session.driver_language = language
    db.commit()
    db.refresh(session)
    return session


def close_session(db: Session, session_id: int) -> None:
    session = db.query(ChatSession).filter_by(id=session_id).first()
    if session:
        session.is_active = False
        db.commit()


def list_sessions(
    db: Session,
    tenant_id: str,
    skip: int = 0,
    limit: int = 20,
) -> Tuple[List[ChatSession], int]:
    q = db.query(ChatSession).filter_by(tenant_id=tenant_id)
    total = q.count()
    sessions = (
        q.order_by(ChatSession.created_at.desc())
        .offset(skip)
        .limit(limit)
        .all()
    )
    return sessions, total


# ── Messages ───────────────────────────────────────────────────────────────

def save_message(
    db: Session,
    tenant_id: str,
    booking_id: int,
    session_id: int,
    sender_type: ChatSenderType,
    sender_id: Optional[int],
    text: str,
    language: str,
    firebase_message_id: Optional[str] = None,
    is_system: bool = False,
) -> ChatMessage:
    msg = ChatMessage(
        tenant_id=tenant_id,
        booking_id=booking_id,
        session_id=session_id,
        sender_type=sender_type,
        sender_id=sender_id,
        original_text=text,
        original_language=language,
        firebase_message_id=firebase_message_id,
        translated_texts={},
        is_system_message=is_system,
    )
    db.add(msg)
    db.commit()
    db.refresh(msg)
    return msg


def update_firebase_id(
    db: Session,
    message_id: int,
    firebase_id: str,
) -> None:
    msg = db.query(ChatMessage).filter_by(id=message_id).first()
    if msg:
        msg.firebase_message_id = firebase_id
        db.commit()


def update_translation(
    db: Session,
    message_id: int,
    language: str,
    translated_text: str,
) -> None:
    """Append one language translation to the JSONB translated_texts dict."""
    msg = db.query(ChatMessage).filter_by(id=message_id).first()
    if msg:
        existing = dict(msg.translated_texts or {})
        existing[language] = translated_text
        msg.translated_texts = existing
        db.commit()


def get_messages(
    db: Session,
    tenant_id: str,
    booking_id: int,
    skip: int = 0,
    limit: int = 50,
) -> List[ChatMessage]:
    return (
        db.query(ChatMessage)
        .filter_by(tenant_id=tenant_id, booking_id=booking_id)
        .order_by(ChatMessage.created_at.asc())
        .offset(skip)
        .limit(limit)
        .all()
    )


def get_message_count(db: Session, booking_id: int) -> int:
    result = (
        db.query(func.count(ChatMessage.id))
        .filter_by(booking_id=booking_id)
        .scalar()
    )
    return result or 0
