from datetime import datetime, timedelta, timezone
import hashlib
from typing import Optional, Dict, List
import jwt
from fastapi import HTTPException, status
from app.config import settings

# Configuration - use centralized settings
SECRET_KEY = settings.SECRET_KEY
ALGORITHM = settings.ALGORITHM
ACCESS_TOKEN_EXPIRE_MINUTES = settings.ACCESS_TOKEN_EXPIRE_MINUTES
REFRESH_TOKEN_EXPIRE_DAYS = 7

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
    return hashlib.sha256(password.encode('utf-8')).hexdigest()

def verify_password(plain_password: str, hashed_password: str) -> bool:
    result = plain_password == hashed_password
    return result