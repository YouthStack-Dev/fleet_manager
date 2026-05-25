"""
Pydantic request / response schemas for the Chat feature.
"""
from __future__ import annotations

from datetime import datetime
from typing import Dict, List, Optional

from pydantic import BaseModel, ConfigDict, Field


# ── Supported languages (for validation and swagger docs) ──────────────────

SUPPORTED_LANGUAGES: Dict[str, str] = {
    "en": "English",
    "hi": "Hindi",
    "ar": "Arabic",
    "fr": "French",
    "de": "German",
    "es": "Spanish",
    "zh": "Chinese (Simplified)",
    "ja": "Japanese",
    "ko": "Korean",
    "pt": "Portuguese",
    "ru": "Russian",
    "it": "Italian",
    "ta": "Tamil",
    "te": "Telugu",
    "kn": "Kannada",
    "ml": "Malayalam",
    "mr": "Marathi",
    "bn": "Bengali",
    "gu": "Gujarati",
    "pa": "Punjabi",
    "ur": "Urdu",
}


# ── Request schemas ────────────────────────────────────────────────────────

class SendMessageRequest(BaseModel):
    """Body for POST /employee/chat/{booking_id}/send
              and POST /driver/chat/{booking_id}/send"""

    text: str = Field(
        ...,
        min_length=1,
        max_length=500,
        description="Message text (max 500 characters)",
    )

    model_config = ConfigDict(
        json_schema_extra={"example": {"text": "I am waiting at Gate B"}}
    )


class SetLanguageRequest(BaseModel):
    """Body for POST .../chat/{booking_id}/language"""

    language: str = Field(
        ...,
        min_length=2,
        max_length=10,
        description=(
            "ISO 639-1 language code. Supported: "
            + ", ".join(f"{k} ({v})" for k, v in SUPPORTED_LANGUAGES.items())
        ),
    )

    model_config = ConfigDict(
        json_schema_extra={"example": {"language": "hi"}}
    )


# ── Response schemas ───────────────────────────────────────────────────────

class ChatMessageResponse(BaseModel):
    """Single message — returned to the requesting user.
    translated_text is pre-filled with the caller's preferred language.
    """

    id: int
    booking_id: int
    sender_type: str
    sender_id: Optional[int]
    original_text: str
    original_language: str

    # translated_text: the version in the caller's language
    # (original_text if no translation available)
    translated_text: Optional[str] = None

    firebase_message_id: Optional[str]
    is_system_message: bool
    created_at: datetime

    class Config:
        from_attributes = True


class ChatMessageAdminResponse(ChatMessageResponse):
    """Admin variant — includes all translations in all languages."""

    translated_texts: Optional[Dict[str, str]] = None


class ChatSessionResponse(BaseModel):
    """Session detail returned when opening a chat."""

    id: int
    booking_id: int
    employee_id: int
    driver_id: Optional[int]
    employee_language: str
    driver_language: str
    is_active: bool
    activated_at: datetime
    created_at: datetime

    # Always injected at response time (from settings)
    warning_message: str

    class Config:
        from_attributes = True


class ChatSessionListItem(BaseModel):
    """Compact session row for admin listing."""

    id: int
    booking_id: int
    employee_id: int
    driver_id: Optional[int]
    employee_language: str
    driver_language: str
    is_active: bool
    message_count: int
    activated_at: datetime
    created_at: datetime

    class Config:
        from_attributes = True


class ChatHistoryResponse(BaseModel):
    """Paginated message history."""

    session: ChatSessionResponse
    messages: List[ChatMessageResponse]
    total: int
    page: int
    per_page: int
