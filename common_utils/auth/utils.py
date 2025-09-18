from datetime import datetime, timedelta
import hashlib
from typing import Optional, Dict, List
import jwt
from fastapi import HTTPException, status

# Configuration
SECRET_KEY = "your-secret-key"  
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 1440  # 1 day
REFRESH_TOKEN_EXPIRE_DAYS = 7

def create_access_token(
    user_id: str,
    tenant_id: Optional[str] = None,
    opaque_token: Optional[str] = None,
    token_context: str = "generic",   # 👈 e.g. "employee", "admin", "driver", "vendor"
    custom_claims: Optional[Dict] = None,  # 👈 flexible extension
    expires_delta: Optional[timedelta] = None
) -> str:
    to_encode = {
        "user_id": user_id,
        "tenant_id": tenant_id,
        "opaque_token": opaque_token,
        "token_type": "access",
        "context": token_context,  # 👈 differentiate token usage
    }

    if custom_claims:
        to_encode.update(custom_claims)  # 👈 allow endpoint-specific claims

    expire = datetime.utcnow() + (expires_delta or timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES))
    to_encode.update({"exp": expire, "iat": datetime.utcnow()})

    return jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)


def create_refresh_token(
    user_id: str,
    token_context: str = "generic",
    custom_claims: Optional[Dict] = None,
) -> str:
    expire = datetime.utcnow() + timedelta(days=REFRESH_TOKEN_EXPIRE_DAYS)
    to_encode = {
        "user_id": user_id,
        "token_type": "refresh",
        "context": token_context,  # 👈 keep it consistent
        "exp": expire,
        "iat": datetime.utcnow(),
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

def verify_password(plain_password: str, hashed_password: str):
    # Replace with actual password hashing in production
    return plain_password == hashed_password