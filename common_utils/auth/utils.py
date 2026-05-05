from datetime import datetime, timedelta, timezone
import hashlib
import hmac
import re
from typing import Optional, Dict, List
import bcrypt as _bcrypt
import jwt
from fastapi import HTTPException, status
from app.config import settings

# Configuration - use centralized settings
SECRET_KEY = settings.SECRET_KEY
ALGORITHM = settings.ALGORITHM
ACCESS_TOKEN_EXPIRE_MINUTES = settings.ACCESS_TOKEN_EXPIRE_MINUTES
REFRESH_TOKEN_EXPIRE_DAYS = 7

# bcrypt hard limit: passwords longer than 72 bytes are silently truncated by
# the algorithm, which is a security hazard. We reject them instead.
_BCRYPT_MAX_BYTES = 72
_sha256_hex_pattern = re.compile(r"^[a-f0-9]{64}$")

def create_access_token(
    user_id: str,
    tenant_id: Optional[str] = None,
    opaque_token: Optional[str] = None,
    vendor_id: Optional[str] = None,
    user_type: str = "generic",   # 👈 e.g. "employee", "admin", "driver", "vendor"
    custom_claims: Optional[Dict] = None,  # 👈 flexible extension
    expires_delta: Optional[timedelta] = None
) -> str:
    to_encode = {
    "user_id": user_id,
    "tenant_id": tenant_id,
    "opaque_token": opaque_token,
    "token_type": "access",
    "user_type": user_type,
    "vendor_id": vendor_id,
    }

    if custom_claims:
        to_encode.update(custom_claims)

    # 🚨 remove all None values
    to_encode = {k: v for k, v in to_encode.items() if v is not None}

    expire = datetime.now(timezone.utc) + (expires_delta or timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES))
    to_encode.update({"exp": expire, "iat": datetime.now(timezone.utc)})

    return jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)


def create_refresh_token(
    user_id: str,
    user_type: str = "generic",
    custom_claims: Optional[Dict] = None,
) -> str:
    expire = datetime.now(timezone.utc) + timedelta(days=REFRESH_TOKEN_EXPIRE_DAYS)
    to_encode = {
        "user_id": user_id,
        "token_type": "refresh",
        "user_type": user_type,  # 👈 keep it consistent
        "exp": expire,
        "iat": datetime.now(timezone.utc),
    }

    if custom_claims:
        to_encode.update(custom_claims)

    return jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)


def verify_token(token: str) -> Dict:
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        return payload
    
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="Token expired")
    
    except jwt.InvalidTokenError:
        raise HTTPException(status_code=401, detail="Invalid token")
    
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )

def hash_password(password: str) -> str:
    """Hash a plaintext password using bcrypt directly (no passlib).

    Raises:
        HTTPException 422 if the UTF-8 encoded password exceeds bcrypt's
        72-byte hard limit.  The caller receives a clear validation error
        instead of an opaque 500.
    """
    encoded = password.encode("utf-8")
    if len(encoded) > _BCRYPT_MAX_BYTES:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={
                "success": False,
                "message": (
                    f"Password is too long. Maximum allowed length is "
                    f"{_BCRYPT_MAX_BYTES} bytes; the supplied password is "
                    f"{len(encoded)} bytes. Please use a shorter password."
                ),
                "error_code": "PASSWORD_TOO_LONG",
                "details": {
                    "max_bytes": _BCRYPT_MAX_BYTES,
                    "provided_bytes": len(encoded),
                },
            },
        )
    hashed = _bcrypt.hashpw(encoded, _bcrypt.gensalt())
    return hashed.decode("utf-8")


def verify_password(plain_password: str, hashed_password: str) -> bool:
    if not plain_password or not hashed_password:
        return False

    # Modern hashing: bcrypt (handles $2a$, $2b$, $2y$ prefixes)
    if hashed_password.startswith("$2"):
        try:
            return _bcrypt.checkpw(
                plain_password.encode("utf-8"),
                hashed_password.encode("utf-8"),
            )
        except Exception:
            return False

    # Legacy hashing: SHA-256 hex digest
    if _sha256_hex_pattern.fullmatch(hashed_password):
        # Backward compatibility for older call-sites that still pass sha256(input)
        if hmac.compare_digest(plain_password, hashed_password):
            return True
        return hmac.compare_digest(
            hashlib.sha256(plain_password.encode("utf-8")).hexdigest(),
            hashed_password,
        )

    # Final fallback for unexpected legacy/plaintext storage
    return hmac.compare_digest(plain_password, hashed_password)
