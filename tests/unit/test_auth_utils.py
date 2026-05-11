"""
Unit tests for common_utils/auth/utils.py

Covers: hash_password, verify_password, create_access_token,
        create_refresh_token, verify_token

All tests are isolated — no DB, no HTTP, no external services.
"""
import hashlib
from datetime import timedelta

import jwt
import pytest

from app.config import settings
from common_utils.auth.utils import (
    _BCRYPT_MAX_BYTES,
    create_access_token,
    create_refresh_token,
    hash_password,
    verify_password,
    verify_token,
)

pytestmark = pytest.mark.unit


# ─────────────────────────────────────────────────────────────────────────────
# hash_password
# ─────────────────────────────────────────────────────────────────────────────
class TestHashPassword:
    """bcrypt hashing: format, salting, and byte-limit enforcement."""

    def test_returns_bcrypt_hash_prefix(self):
        hashed = hash_password("SecurePass@123")
        assert hashed.startswith(("$2b$", "$2a$")), "Expected bcrypt hash format"

    def test_different_calls_produce_different_salts(self):
        """bcrypt is salted — same plaintext must never produce the same hash."""
        h1 = hash_password("SecurePass@123")
        h2 = hash_password("SecurePass@123")
        assert h1 != h2

    def test_exactly_72_bytes_passes(self):
        """72-byte boundary must succeed (inclusive upper limit)."""
        result = hash_password("A" * _BCRYPT_MAX_BYTES)
        assert result.startswith(("$2b$", "$2a$"))

    def test_73_bytes_raises_http_422(self):
        """One byte over the limit must raise HTTP 422 with a clear code."""
        from fastapi import HTTPException

        with pytest.raises(HTTPException) as exc_info:
            hash_password("A" * (_BCRYPT_MAX_BYTES + 1))
        assert exc_info.value.status_code == 422
        assert exc_info.value.detail["error_code"] == "PASSWORD_TOO_LONG"

    def test_unicode_within_byte_limit_hashes_correctly(self):
        # 'é' is 2 UTF-8 bytes; 36 × 2 = 72 bytes — right at the limit.
        result = hash_password("é" * 36)
        assert result.startswith(("$2b$", "$2a$"))

    def test_unicode_exceeding_byte_limit_raises_422(self):
        from fastapi import HTTPException

        # 37 × 2 = 74 bytes → over limit
        with pytest.raises(HTTPException) as exc_info:
            hash_password("é" * 37)
        assert exc_info.value.status_code == 422

    def test_short_password_hashes_correctly(self):
        result = hash_password("Ab1!")
        assert result.startswith(("$2b$", "$2a$"))

    def test_special_characters_in_password(self):
        result = hash_password("P@$$w0rd!#%^&*()")
        assert result.startswith(("$2b$", "$2a$"))


# ─────────────────────────────────────────────────────────────────────────────
# verify_password
# ─────────────────────────────────────────────────────────────────────────────
class TestVerifyPassword:
    """Password verification: bcrypt, legacy SHA-256, and edge cases."""

    def test_correct_bcrypt_password_verifies(self):
        hashed = hash_password("ValidPass1!")
        assert verify_password("ValidPass1!", hashed) is True

    def test_wrong_bcrypt_password_fails(self):
        hashed = hash_password("ValidPass1!")
        assert verify_password("WrongPass1!", hashed) is False

    def test_empty_plain_password_returns_false(self):
        hashed = hash_password("ValidPass1!")
        assert verify_password("", hashed) is False

    def test_empty_hashed_password_returns_false(self):
        assert verify_password("ValidPass1!", "") is False

    def test_both_empty_returns_false(self):
        assert verify_password("", "") is False

    def test_none_plain_password_returns_false(self):
        hashed = hash_password("ValidPass1!")
        assert verify_password(None, hashed) is False  # type: ignore[arg-type]

    def test_legacy_sha256_verifies_correctly(self):
        """Backward-compatibility path: hash stored as sha256 hex digest."""
        plain = "OldLegacyPassword"
        sha256_hash = hashlib.sha256(plain.encode("utf-8")).hexdigest()
        assert verify_password(plain, sha256_hash) is True

    def test_legacy_sha256_wrong_password_fails(self):
        sha256_hash = hashlib.sha256(b"OldLegacyPassword").hexdigest()
        assert verify_password("NotTheSame", sha256_hash) is False

    def test_bcrypt_is_case_sensitive(self):
        hashed = hash_password("Password1!")
        assert verify_password("password1!", hashed) is False

    def test_bcrypt_whitespace_sensitive(self):
        hashed = hash_password("Password 1!")
        assert verify_password("Password1!", hashed) is False


# ─────────────────────────────────────────────────────────────────────────────
# create_access_token
# ─────────────────────────────────────────────────────────────────────────────
class TestCreateAccessToken:
    """JWT access token payload structure and custom claims."""

    def _decode(self, token: str) -> dict:
        return jwt.decode(token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM])

    def test_required_claims_are_present(self):
        token = create_access_token(user_id="42", user_type="employee")
        payload = self._decode(token)
        assert payload["user_id"] == "42"
        assert payload["user_type"] == "employee"
        assert payload["token_type"] == "access"
        assert "exp" in payload
        assert "iat" in payload

    def test_tenant_id_included_when_provided(self):
        token = create_access_token(user_id="1", tenant_id="TENANT001", user_type="admin")
        payload = self._decode(token)
        assert payload["tenant_id"] == "TENANT001"

    def test_none_fields_omitted_from_payload(self):
        """tenant_id=None, vendor_id=None must not appear in the token."""
        token = create_access_token(user_id="1", user_type="generic")
        payload = self._decode(token)
        assert "tenant_id" not in payload
        assert "vendor_id" not in payload
        assert "opaque_token" not in payload

    def test_custom_claims_merged_into_payload(self):
        token = create_access_token(
            user_id="5",
            user_type="employee",
            custom_claims={
                "email": "user@fleet.com",
                "permissions": ["booking.read", "booking.create"],
            },
        )
        payload = self._decode(token)
        assert payload["email"] == "user@fleet.com"
        assert "booking.read" in payload["permissions"]

    def test_custom_expiry_is_respected(self):
        from datetime import datetime, timezone

        token = create_access_token(
            user_id="1", user_type="admin", expires_delta=timedelta(hours=2)
        )
        payload = self._decode(token)
        exp = datetime.fromtimestamp(payload["exp"], tz=timezone.utc)
        iat = datetime.fromtimestamp(payload["iat"], tz=timezone.utc)
        delta_seconds = (exp - iat).total_seconds()
        # Allow ±15 seconds for clock drift in CI
        assert abs(delta_seconds - 7200) <= 15

    def test_different_user_ids_produce_different_tokens(self):
        t1 = create_access_token(user_id="1", user_type="admin")
        t2 = create_access_token(user_id="2", user_type="admin")
        assert t1 != t2

    def test_vendor_id_included_when_provided(self):
        token = create_access_token(user_id="10", user_type="vendor", vendor_id="VENDOR01")
        payload = self._decode(token)
        assert payload["vendor_id"] == "VENDOR01"

    def test_all_user_types_produce_valid_tokens(self):
        for utype in ["employee", "admin", "driver", "vendor", "generic"]:
            token = create_access_token(user_id="1", user_type=utype)
            payload = self._decode(token)
            assert payload["user_type"] == utype

    def test_mixed_permission_formats_in_custom_claims(self):
        """Dict-format permissions (alert module) embed correctly."""
        token = create_access_token(
            user_id="1",
            user_type="employee",
            custom_claims={
                "permissions": [
                    "booking.read",
                    {"module": "alert", "action": ["create", "respond"]},
                ]
            },
        )
        payload = self._decode(token)
        perms = payload["permissions"]
        assert "booking.read" in perms
        assert {"module": "alert", "action": ["create", "respond"]} in perms


# ─────────────────────────────────────────────────────────────────────────────
# create_refresh_token
# ─────────────────────────────────────────────────────────────────────────────
class TestCreateRefreshToken:
    """Refresh token: type claim and 7-day expiry."""

    def _decode(self, token: str) -> dict:
        return jwt.decode(token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM])

    def test_token_type_is_refresh(self):
        token = create_refresh_token(user_id="1", user_type="employee")
        payload = self._decode(token)
        assert payload["token_type"] == "refresh"

    def test_token_expires_in_7_days(self):
        from datetime import datetime, timezone

        token = create_refresh_token(user_id="1", user_type="employee")
        payload = self._decode(token)
        exp = datetime.fromtimestamp(payload["exp"], tz=timezone.utc)
        iat = datetime.fromtimestamp(payload["iat"], tz=timezone.utc)
        # Allow ±30 seconds tolerance
        assert abs((exp - iat).days - 7) == 0

    def test_refresh_token_user_type_preserved(self):
        token = create_refresh_token(user_id="99", user_type="driver")
        payload = self._decode(token)
        assert payload["user_type"] == "driver"
        assert payload["user_id"] == "99"


# ─────────────────────────────────────────────────────────────────────────────
# verify_token
# ─────────────────────────────────────────────────────────────────────────────
class TestVerifyToken:
    """Token verification: valid tokens, expired, tampered, wrong secret."""

    def test_valid_access_token_decoded(self):
        token = create_access_token(user_id="99", user_type="driver")
        payload = verify_token(token)
        assert payload["user_id"] == "99"
        assert payload["user_type"] == "driver"

    def test_expired_token_raises_401(self):
        from fastapi import HTTPException

        expired = create_access_token(
            user_id="1", user_type="admin", expires_delta=timedelta(seconds=-1)
        )
        with pytest.raises(HTTPException) as exc_info:
            verify_token(expired)
        assert exc_info.value.status_code == 401
        assert "expired" in exc_info.value.detail.lower()

    def test_tampered_signature_raises_401(self):
        from fastapi import HTTPException

        token = create_access_token(user_id="1", user_type="admin")
        tampered = token[:-8] + "TAMPERED"
        with pytest.raises(HTTPException) as exc_info:
            verify_token(tampered)
        assert exc_info.value.status_code == 401

    def test_wrong_signing_secret_raises_401(self):
        from fastapi import HTTPException

        bad_token = jwt.encode(
            {"user_id": "1", "user_type": "admin"},
            "wrong_secret_key_xyz",
            algorithm=settings.ALGORITHM,
        )
        with pytest.raises(HTTPException) as exc_info:
            verify_token(bad_token)
        assert exc_info.value.status_code == 401

    def test_completely_invalid_string_raises_http_exception(self):
        from fastapi import HTTPException

        with pytest.raises(HTTPException):
            verify_token("not.a.valid.jwt.at.all")

    def test_empty_string_raises_http_exception(self):
        from fastapi import HTTPException

        with pytest.raises(HTTPException):
            verify_token("")

    def test_refresh_token_verifiable_with_same_secret(self):
        """verify_token should decode both access and refresh tokens."""
        token = create_refresh_token(user_id="5", user_type="vendor")
        payload = verify_token(token)
        assert payload["token_type"] == "refresh"
