"""
Chat Router — Employee ↔ Driver real-time chat with async translation.

Endpoint groups
───────────────
Employee App  /employee/chat/{booking_id}/...
Driver App    /driver/chat/{booking_id}/...
Admin         /chat/sessions/...              (read-only transparency)

Auth
────
• Employee endpoints  → PermissionChecker(["employee_app.read"])
• Driver endpoints    → PermissionChecker(["driver_app.read", "driver_app.update"])
• Admin endpoints     → PermissionChecker(["booking.read"])
"""
from __future__ import annotations

from typing import List, Optional

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.config import settings
from app.core.logging_config import get_logger
from app.crud import chat as chat_crud
from app.database.session import get_db
from app.firebase import chat as firebase_chat
from app.models.chat import ChatSenderType
from app.schemas.chat import (
    ChatHistoryResponse,
    ChatMessageAdminResponse,
    ChatMessageResponse,
    ChatSessionListItem,
    ChatSessionResponse,
    SendMessageRequest,
    SetLanguageRequest,
    SUPPORTED_LANGUAGES,
)
from app.services import chat_service
from app.utils.response_utils import ResponseWrapper
from common_utils.auth.permission_checker import PermissionChecker

logger = get_logger(__name__)
router = APIRouter(tags=["Chat"])


# ── Auth dependencies (mirrors existing driver/employee routers) ───────────

def EmployeeAuth(
    user_data=Depends(PermissionChecker(["employee_app.read"])),
):
    if user_data.get("user_type") != "employee":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Employee access only",
        )
    tenant_id   = user_data.get("tenant_id")
    employee_id = user_data.get("user_id")
    if not tenant_id or not employee_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Employee or tenant not resolved from token",
        )
    return {"tenant_id": tenant_id, "employee_id": int(employee_id)}


async def DriverAuth(
    user_data=Depends(
        PermissionChecker(["driver_app.read", "driver_app.update"])
    ),
):
    if user_data.get("user_type") != "driver":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Driver access only",
        )
    tenant_id = user_data.get("tenant_id")
    driver_id = user_data.get("user_id")
    if not tenant_id or not driver_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Driver or tenant not resolved from token",
        )
    return {"tenant_id": tenant_id, "driver_id": int(driver_id)}


def AdminAuth(
    user_data=Depends(PermissionChecker(["booking.read"])),
):
    tenant_id = user_data.get("tenant_id")
    if not tenant_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin tenant not resolved from token",
        )
    return {"tenant_id": tenant_id, "user_data": user_data}


# ── Internal serialisers ───────────────────────────────────────────────────

def _serialize_message(
    msg,
    viewer_language: str,
    include_all_translations: bool = False,
) -> dict:
    """
    Build a ChatMessageResponse dict.
    translated_text is chosen for the viewer's language:
      1. Exact match in translated_texts
      2. Falls back to original_text
    """
    translations: dict = msg.translated_texts or {}
    translated_text = translations.get(viewer_language) or msg.original_text

    base = {
        "id":                   msg.id,
        "booking_id":           msg.booking_id,
        "sender_type":          msg.sender_type.value if hasattr(msg.sender_type, "value") else msg.sender_type,
        "sender_id":            msg.sender_id,
        "original_text":        msg.original_text,
        "original_language":    msg.original_language,
        "translated_text":      translated_text,
        "firebase_message_id":  msg.firebase_message_id,
        "is_system_message":    msg.is_system_message,
        "created_at":           msg.created_at,
    }
    if include_all_translations:
        base["translated_texts"] = translations
    return base


def _serialize_session(session) -> dict:
    return {
        "id":               session.id,
        "booking_id":       session.booking_id,
        "employee_id":      session.employee_id,
        "driver_id":        session.driver_id,
        "employee_language": session.employee_language,
        "driver_language":  session.driver_language,
        "is_active":        session.is_active,
        "activated_at":     session.activated_at,
        "created_at":       session.created_at,
        "warning_message":  settings.CHAT_WARNING_MESSAGE,
    }


# ═══════════════════════════════════════════════════════════════════════════
# EMPLOYEE APP ENDPOINTS
# ═══════════════════════════════════════════════════════════════════════════

@router.get(
    "/employee/chat/{booking_id}",
    summary="Employee: Open / get chat session for a booking",
)
def employee_open_chat(
    booking_id: int,
    db: Session = Depends(get_db),
    auth: dict = Depends(EmployeeAuth),
):
    """
    Open (or retrieve) the chat session for a booking.

    • Creates the session on first call (injects warning system message).
    • Returns session metadata + warning message.
    • Use the Firebase path in the response to attach a real-time listener.
    """
    tenant_id   = auth["tenant_id"]
    employee_id = auth["employee_id"]

    booking = chat_service.get_booking_or_404(db, tenant_id, booking_id)
    if booking.employee_id != employee_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="This booking does not belong to you.",
        )

    driver_id = chat_service.get_driver_id_for_booking(db, booking_id)
    session, created = chat_service.open_chat_session(
        db=db,
        tenant_id=tenant_id,
        booking_id=booking_id,
        employee_id=employee_id,
        driver_id=driver_id,
    )

    return ResponseWrapper.success(
        data={
            **_serialize_session(session),
            "firebase_path": f"chats/{tenant_id}/booking_{booking_id}/messages",
            "created": created,
        },
        message="Chat session ready",
    )


@router.post(
    "/employee/chat/{booking_id}/send",
    summary="Employee: Send a message to the driver",
    status_code=status.HTTP_201_CREATED,
)
def employee_send_message(
    booking_id: int,
    body: SendMessageRequest,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    auth: dict = Depends(EmployeeAuth),
):
    tenant_id   = auth["tenant_id"]
    employee_id = auth["employee_id"]

    booking = chat_service.get_booking_or_404(db, tenant_id, booking_id)
    if booking.employee_id != employee_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="This booking does not belong to you.",
        )

    driver_id = chat_service.get_driver_id_for_booking(db, booking_id)
    session, _ = chat_service.open_chat_session(
        db=db,
        tenant_id=tenant_id,
        booking_id=booking_id,
        employee_id=employee_id,
        driver_id=driver_id,
    )

    msg = chat_service.send_message_sync(
        db=db,
        tenant_id=tenant_id,
        booking_id=booking_id,
        session=session,
        sender_type=ChatSenderType.EMPLOYEE,
        sender_id=employee_id,
        text=body.text,
        sender_language=session.employee_language,
    )

    # Schedule async translation (fires after HTTP response is sent)
    if (
        settings.TRANSLATION_ENABLED
        and session.employee_language != session.driver_language
    ):
        background_tasks.add_task(
            chat_service.translate_and_update,
            message_id=msg.id,
            tenant_id=tenant_id,
            booking_id=booking_id,
            firebase_message_id=msg.firebase_message_id,
            text=body.text,
            source_language=session.employee_language,
            target_language=session.driver_language,
        )

    return ResponseWrapper.created(
        data=_serialize_message(msg, viewer_language=session.employee_language),
        message="Message sent",
    )


@router.get(
    "/employee/chat/{booking_id}/messages",
    summary="Employee: Get chat message history for a booking",
)
def employee_get_messages(
    booking_id: int,
    skip:  int = Query(0,  ge=0, description="Offset"),
    limit: int = Query(50, ge=1, le=100, description="Max messages to return"),
    db: Session = Depends(get_db),
    auth: dict = Depends(EmployeeAuth),
):
    tenant_id   = auth["tenant_id"]
    employee_id = auth["employee_id"]

    booking = chat_service.get_booking_or_404(db, tenant_id, booking_id)
    if booking.employee_id != employee_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="This booking does not belong to you.",
        )

    session = chat_crud.get_session(db, tenant_id, booking_id)
    if not session:
        return ResponseWrapper.success(
            data={"messages": [], "total": 0},
            message="No chat session found for this booking",
        )

    messages = chat_crud.get_messages(db, tenant_id, booking_id, skip, limit)
    total    = chat_crud.get_message_count(db, booking_id)

    return ResponseWrapper.success(
        data={
            "session":   _serialize_session(session),
            "messages":  [_serialize_message(m, session.employee_language) for m in messages],
            "total":     total,
            "page":      (skip // limit) + 1,
            "per_page":  limit,
        },
        message="Messages retrieved",
    )


@router.post(
    "/employee/chat/{booking_id}/language",
    summary="Employee: Set preferred language for this chat",
)
def employee_set_language(
    booking_id: int,
    body: SetLanguageRequest,
    db: Session = Depends(get_db),
    auth: dict = Depends(EmployeeAuth),
):
    tenant_id   = auth["tenant_id"]
    employee_id = auth["employee_id"]

    if body.language not in SUPPORTED_LANGUAGES:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=(
                f"Language '{body.language}' is not supported. "
                f"Supported codes: {list(SUPPORTED_LANGUAGES.keys())}"
            ),
        )

    booking = chat_service.get_booking_or_404(db, tenant_id, booking_id)
    if booking.employee_id != employee_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="This booking does not belong to you.",
        )

    driver_id = chat_service.get_driver_id_for_booking(db, booking_id)
    session, _ = chat_service.open_chat_session(
        db=db,
        tenant_id=tenant_id,
        booking_id=booking_id,
        employee_id=employee_id,
        driver_id=driver_id,
    )

    updated = chat_crud.update_session_language(db, session.id, "employee", body.language)
    firebase_chat.update_session_language(tenant_id, booking_id, "employee", body.language)

    return ResponseWrapper.updated(
        data=_serialize_session(updated),
        message=f"Language set to {SUPPORTED_LANGUAGES.get(body.language, body.language)}",
    )


# ═══════════════════════════════════════════════════════════════════════════
# DRIVER APP ENDPOINTS
# ═══════════════════════════════════════════════════════════════════════════

@router.get(
    "/driver/chat/{booking_id}",
    summary="Driver: Open / get chat session for a booking",
)
def driver_open_chat(
    booking_id: int,
    db: Session = Depends(get_db),
    auth: dict = Depends(DriverAuth),
):
    tenant_id = auth["tenant_id"]
    driver_id = auth["driver_id"]

    booking = chat_service.get_booking_or_404(db, tenant_id, booking_id)

    # Verify driver is assigned to this booking's route
    assigned_driver_id = chat_service.get_driver_id_for_booking(db, booking_id)
    if assigned_driver_id and assigned_driver_id != driver_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You are not assigned to this booking.",
        )

    session, created = chat_service.open_chat_session(
        db=db,
        tenant_id=tenant_id,
        booking_id=booking_id,
        employee_id=booking.employee_id,
        driver_id=driver_id,
    )

    return ResponseWrapper.success(
        data={
            **_serialize_session(session),
            "firebase_path": f"chats/{tenant_id}/booking_{booking_id}/messages",
            "created": created,
        },
        message="Chat session ready",
    )


@router.post(
    "/driver/chat/{booking_id}/send",
    summary="Driver: Send a message to the employee",
    status_code=status.HTTP_201_CREATED,
)
def driver_send_message(
    booking_id: int,
    body: SendMessageRequest,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    auth: dict = Depends(DriverAuth),
):
    tenant_id = auth["tenant_id"]
    driver_id = auth["driver_id"]

    booking = chat_service.get_booking_or_404(db, tenant_id, booking_id)

    assigned_driver_id = chat_service.get_driver_id_for_booking(db, booking_id)
    if assigned_driver_id and assigned_driver_id != driver_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You are not assigned to this booking.",
        )

    session, _ = chat_service.open_chat_session(
        db=db,
        tenant_id=tenant_id,
        booking_id=booking_id,
        employee_id=booking.employee_id,
        driver_id=driver_id,
    )

    msg = chat_service.send_message_sync(
        db=db,
        tenant_id=tenant_id,
        booking_id=booking_id,
        session=session,
        sender_type=ChatSenderType.DRIVER,
        sender_id=driver_id,
        text=body.text,
        sender_language=session.driver_language,
    )

    # Schedule async translation
    if (
        settings.TRANSLATION_ENABLED
        and session.driver_language != session.employee_language
    ):
        background_tasks.add_task(
            chat_service.translate_and_update,
            message_id=msg.id,
            tenant_id=tenant_id,
            booking_id=booking_id,
            firebase_message_id=msg.firebase_message_id,
            text=body.text,
            source_language=session.driver_language,
            target_language=session.employee_language,
        )

    return ResponseWrapper.created(
        data=_serialize_message(msg, viewer_language=session.driver_language),
        message="Message sent",
    )


@router.get(
    "/driver/chat/{booking_id}/messages",
    summary="Driver: Get chat message history for a booking",
)
def driver_get_messages(
    booking_id: int,
    skip:  int = Query(0,  ge=0),
    limit: int = Query(50, ge=1, le=100),
    db: Session = Depends(get_db),
    auth: dict = Depends(DriverAuth),
):
    tenant_id = auth["tenant_id"]
    driver_id = auth["driver_id"]

    booking = chat_service.get_booking_or_404(db, tenant_id, booking_id)

    assigned_driver_id = chat_service.get_driver_id_for_booking(db, booking_id)
    if assigned_driver_id and assigned_driver_id != driver_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You are not assigned to this booking.",
        )

    session = chat_crud.get_session(db, tenant_id, booking_id)
    if not session:
        return ResponseWrapper.success(
            data={"messages": [], "total": 0},
            message="No chat session found for this booking",
        )

    messages = chat_crud.get_messages(db, tenant_id, booking_id, skip, limit)
    total    = chat_crud.get_message_count(db, booking_id)

    return ResponseWrapper.success(
        data={
            "session":   _serialize_session(session),
            "messages":  [_serialize_message(m, session.driver_language) for m in messages],
            "total":     total,
            "page":      (skip // limit) + 1,
            "per_page":  limit,
        },
        message="Messages retrieved",
    )


@router.post(
    "/driver/chat/{booking_id}/language",
    summary="Driver: Set preferred language for this chat",
)
def driver_set_language(
    booking_id: int,
    body: SetLanguageRequest,
    db: Session = Depends(get_db),
    auth: dict = Depends(DriverAuth),
):
    tenant_id = auth["tenant_id"]
    driver_id = auth["driver_id"]

    if body.language not in SUPPORTED_LANGUAGES:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Language '{body.language}' not supported.",
        )

    booking = chat_service.get_booking_or_404(db, tenant_id, booking_id)
    assigned_driver_id = chat_service.get_driver_id_for_booking(db, booking_id)
    if assigned_driver_id and assigned_driver_id != driver_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You are not assigned to this booking.",
        )

    session, _ = chat_service.open_chat_session(
        db=db,
        tenant_id=tenant_id,
        booking_id=booking_id,
        employee_id=booking.employee_id,
        driver_id=driver_id,
    )

    updated = chat_crud.update_session_language(db, session.id, "driver", body.language)
    firebase_chat.update_session_language(tenant_id, booking_id, "driver", body.language)

    return ResponseWrapper.updated(
        data=_serialize_session(updated),
        message=f"Language set to {SUPPORTED_LANGUAGES.get(body.language, body.language)}",
    )


# ═══════════════════════════════════════════════════════════════════════════
# ADMIN ENDPOINTS  (read-only — transparency only, no write access)
# ═══════════════════════════════════════════════════════════════════════════

@router.get(
    "/chat/sessions",
    summary="Admin: List all chat sessions",
)
def admin_list_sessions(
    skip:  int = Query(0,  ge=0,  description="Offset"),
    limit: int = Query(20, ge=1, le=100, description="Page size"),
    db: Session = Depends(get_db),
    auth: dict = Depends(AdminAuth),
):
    """
    Returns paginated list of all chat sessions for the tenant.
    Includes message count per session.
    """
    tenant_id = auth["tenant_id"]
    sessions, total = chat_crud.list_sessions(db, tenant_id, skip, limit)

    rows = []
    for s in sessions:
        rows.append({
            "id":               s.id,
            "booking_id":       s.booking_id,
            "employee_id":      s.employee_id,
            "driver_id":        s.driver_id,
            "employee_language": s.employee_language,
            "driver_language":  s.driver_language,
            "is_active":        s.is_active,
            "message_count":    chat_crud.get_message_count(db, s.booking_id),
            "activated_at":     s.activated_at,
            "created_at":       s.created_at,
        })

    return ResponseWrapper.paginated(
        items=rows,
        total=total,
        page=(skip // limit) + 1,
        per_page=limit,
        message="Chat sessions retrieved",
    )


@router.get(
    "/chat/sessions/{booking_id}",
    summary="Admin: Get chat session details for a booking",
)
def admin_get_session(
    booking_id: int,
    db: Session = Depends(get_db),
    auth: dict = Depends(AdminAuth),
):
    tenant_id = auth["tenant_id"]
    session = chat_crud.get_session(db, tenant_id, booking_id)
    if not session:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"No chat session for booking {booking_id}",
        )

    return ResponseWrapper.success(
        data={
            **_serialize_session(session),
            "message_count": chat_crud.get_message_count(db, booking_id),
        },
        message="Chat session retrieved",
    )


@router.get(
    "/chat/sessions/{booking_id}/messages",
    summary="Admin: View full chat transcript (original + all translations)",
)
def admin_get_transcript(
    booking_id: int,
    skip:  int = Query(0,  ge=0),
    limit: int = Query(50, ge=1, le=200),
    db: Session = Depends(get_db),
    auth: dict = Depends(AdminAuth),
):
    """
    Returns every message with:
    - original_text    — what was actually typed
    - translated_texts — all language variants cached so far
    - firebase_message_id — RTDB key for reference

    Admin has read-only access for transparency — cannot send messages.
    """
    tenant_id = auth["tenant_id"]

    session = chat_crud.get_session(db, tenant_id, booking_id)
    if not session:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"No chat session for booking {booking_id}",
        )

    messages = chat_crud.get_messages(db, tenant_id, booking_id, skip, limit)
    total    = chat_crud.get_message_count(db, booking_id)

    return ResponseWrapper.success(
        data={
            "session":  _serialize_session(session),
            "messages": [
                _serialize_message(m, viewer_language="en", include_all_translations=True)
                for m in messages
            ],
            "total":    total,
            "page":     (skip // limit) + 1,
            "per_page": limit,
        },
        message="Chat transcript retrieved",
    )


# ── Utility endpoints ──────────────────────────────────────────────────────

@router.get(
    "/chat/supported-languages",
    summary="List all supported translation languages",
)
def get_supported_languages():
    """Returns all ISO 639-1 language codes supported by the translation engine."""
    return ResponseWrapper.success(
        data={"languages": SUPPORTED_LANGUAGES},
        message="Supported languages",
    )
