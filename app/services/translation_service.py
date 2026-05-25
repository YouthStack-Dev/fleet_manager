"""
Translation Service
───────────────────
Uses the free Google Translate public endpoint via httpx (already in
requirements.txt — no new dependency needed).

Features
────────
• Async HTTP calls (httpx.AsyncClient)
• Redis caching — 24 h TTL — keyed on md5(text:src:tgt)
• Auto language detection
• Graceful fallback: returns original text on any failure
• Controlled by settings.TRANSLATION_ENABLED flag

Local Docker testing:  works with no API key (free public endpoint)
Production upgrade:    swap _call_google_translate() for the official
                       google-cloud-translate SDK with a service account.
"""
from __future__ import annotations

import hashlib
import logging
from typing import Optional

import httpx

from app.config import settings
from app.core.logging_config import get_logger

logger = get_logger(__name__)

# Free public endpoint — no API key required for basic use
_GTRANS_URL = "https://translate.googleapis.com/translate_a/single"

# Supported ISO 639-1 language codes (informational / validation helper)
SUPPORTED_LANGUAGES: dict[str, str] = {
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


# ── Redis helpers ──────────────────────────────────────────────────────────

def _get_redis():
    """Return a Redis client if USE_REDIS is enabled and reachable, else None."""
    if not settings.USE_REDIS:
        return None
    try:
        import redis as redis_lib  # already in requirements.txt
        client = redis_lib.Redis(
            host=settings.REDIS_HOST,
            port=settings.REDIS_PORT,
            db=settings.REDIS_DB,
            password=settings.REDIS_PASSWORD or None,
            decode_responses=True,
            socket_connect_timeout=2,
        )
        client.ping()
        return client
    except Exception as exc:
        logger.warning("[translation] Redis unavailable, skipping cache: %s", exc)
        return None


def _cache_key(text: str, src: str, tgt: str) -> str:
    raw = f"{text}:{src}:{tgt}"
    return f"chat_trans:{hashlib.md5(raw.encode()).hexdigest()}"


# ── Core API call ──────────────────────────────────────────────────────────

async def _call_google_translate(
    text: str,
    target_language: str,
    source_language: str = "auto",
) -> Optional[str]:
    """
    Call the free Google Translate endpoint.
    Returns translated string or None on failure.
    """
    try:
        async with httpx.AsyncClient(timeout=6.0) as client:
            resp = await client.get(
                _GTRANS_URL,
                params={
                    "client": "gtx",
                    "sl": source_language,
                    "tl": target_language,
                    "dt": "t",
                    "q": text,
                },
            )
            resp.raise_for_status()
            data = resp.json()

            # Response structure: [[["translated","original",...],...], ..., detected_lang]
            translated_parts = []
            for part in data[0]:
                if part and part[0]:
                    translated_parts.append(part[0])
            result = "".join(translated_parts)
            return result if result else None
    except httpx.TimeoutException:
        logger.warning("[translation] Timeout translating to %s", target_language)
        return None
    except Exception as exc:
        logger.warning("[translation] API call failed: %s", exc)
        return None


# ── Public interface ───────────────────────────────────────────────────────

async def translate_text(
    text: str,
    target_language: str,
    source_language: str = "auto",
) -> str:
    """
    Translate *text* to *target_language*.

    • Returns the translated string.
    • Returns the original *text* if:
        - TRANSLATION_ENABLED is False
        - source == target language
        - translation API call fails (graceful fallback)

    Args:
        text:             The text to translate.
        target_language:  ISO 639-1 target language code (e.g. "hi").
        source_language:  ISO 639-1 source code or "auto" (default).
    """
    if not settings.TRANSLATION_ENABLED:
        return text

    if not text or not text.strip():
        return text

    # Skip if same language
    if source_language != "auto" and source_language == target_language:
        return text

    # ── Cache lookup ───────────────────────────────────────────────────────
    key = _cache_key(text, source_language, target_language)
    redis = _get_redis()
    if redis:
        try:
            cached = redis.get(key)
            if cached:
                logger.debug(
                    "[translation] Cache hit %s→%s", source_language, target_language
                )
                return cached
        except Exception:
            pass

    # ── API call ───────────────────────────────────────────────────────────
    translated = await _call_google_translate(text, target_language, source_language)

    if not translated:
        logger.info(
            "[translation] Falling back to original text (%s→%s)",
            source_language, target_language,
        )
        return text

    # ── Cache result ───────────────────────────────────────────────────────
    if redis:
        try:
            redis.setex(key, settings.TRANSLATION_CACHE_TTL, translated)
        except Exception:
            pass

    logger.info(
        "[translation] %s→%s: '%s' → '%s'",
        source_language, target_language,
        text[:40], translated[:40],
    )
    return translated


async def detect_language(text: str) -> str:
    """
    Detect the language of *text*.
    Returns ISO 639-1 code, defaults to "en" on failure.
    """
    if not settings.TRANSLATION_ENABLED or not text:
        return "en"
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            resp = await client.get(
                _GTRANS_URL,
                params={
                    "client": "gtx",
                    "sl": "auto",
                    "tl": "en",
                    "dt": "t",
                    "q": text[:200],   # send only the first 200 chars for detection
                },
            )
            resp.raise_for_status()
            data = resp.json()
            detected = data[2] if len(data) > 2 and data[2] else "en"
            logger.debug("[translation] Detected language: %s", detected)
            return detected
    except Exception as exc:
        logger.warning("[translation] Language detection failed: %s", exc)
        return "en"
