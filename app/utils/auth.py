from passlib.context import CryptContext
from jose import JWTError, jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from datetime import datetime, timedelta
from typing import Optional, Dict, Any, Union
from sqlalchemy.orm import Session
from database.session import get_db
from app.models.admin import Admin
from app.models.vendor_user import VendorUser
from app.models.employee import Employee
from app.models.driver import Driver
import os

# Password hashing context
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

# JWT settings - in production these should come from environment variables
SECRET_KEY = os.getenv("JWT_SECRET_KEY", "your-super-secret-key-for-jwt-should-be-loaded-from-env")
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 60 * 24  # 24 hours

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="api/auth/token")

def verify_password(plain_password: str, hashed_password: str) -> bool:
    return pwd_context.verify(plain_password, hashed_password)

def get_password_hash(password: str) -> str:
    return pwd_context.hash(password)

def create_access_token(data: Dict[str, Any], expires_delta: Optional[timedelta] = None) -> str:
    to_encode = data.copy()
    expire = datetime.utcnow() + (expires_delta or timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES))
    to_encode.update({"exp": expire})
    return jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)

def decode_token(token: str) -> Dict[str, Any]:
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        return payload
    except JWTError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Could not validate credentials",
            headers={"WWW-Authenticate": "Bearer"},
        )

async def get_current_user(
    token: str = Depends(oauth2_scheme), 
    db: Session = Depends(get_db)
) -> Union[Admin, VendorUser, Employee, Driver]:
    payload = decode_token(token)
    user_id: int = payload.get("sub")
    user_type: str = payload.get("user_type")
    
    if user_id is None or user_type is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid authentication credentials",
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    if user_type == "admin":
        user = db.query(Admin).filter(Admin.admin_id == user_id).first()
    elif user_type == "vendor_user":
        user = db.query(VendorUser).filter(VendorUser.vendor_user_id == user_id).first()
    elif user_type == "employee":
        user = db.query(Employee).filter(Employee.employee_id == user_id).first()
    elif user_type == "driver":
        user = db.query(Driver).filter(Driver.driver_id == user_id).first()
    else:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid user type",
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    if user is None or not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Inactive user or invalid credentials",
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    return user
