from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy.orm import Session
from typing import Dict, Any

from database.session import get_db
from app.utils.auth import verify_password, create_access_token
from app.models.admin import Admin
from app.models.vendor_user import VendorUser
from app.models.employee import Employee
from app.models.driver import Driver

router = APIRouter(prefix="/auth", tags=["authentication"])

@router.post("/token")
async def login_for_access_token(
    form_data: OAuth2PasswordRequestForm = Depends(),
    db: Session = Depends(get_db)
) -> Dict[str, Any]:
    # Try to find user in different tables
    user = None
    user_type = None
    
    # Check in admin table
    admin = db.query(Admin).filter(Admin.email == form_data.username).first()
    if admin and verify_password(form_data.password, admin.password):
        user = admin
        user_type = "admin"
        user_id = admin.admin_id
    
    # Check in vendor_user table if not found in admin
    if not user:
        vendor_user = db.query(VendorUser).filter(VendorUser.email == form_data.username).first()
        if vendor_user and verify_password(form_data.password, vendor_user.password):
            user = vendor_user
            user_type = "vendor_user"
            user_id = vendor_user.vendor_user_id
    
    # Check in employee table if not found yet
    if not user:
        employee = db.query(Employee).filter(Employee.email == form_data.username).first()
        if employee and verify_password(form_data.password, employee.password):
            user = employee
            user_type = "employee"
            user_id = employee.employee_id
    
    # Check in driver table if not found yet
    if not user:
        driver = db.query(Driver).filter(Driver.email == form_data.username).first()
        if driver and verify_password(form_data.password, driver.password):
            user = driver
            user_type = "driver"
            user_id = driver.driver_id
    
    if not user or not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect email or password",
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    access_token = create_access_token(
        data={"sub": str(user_id), "user_type": user_type, "email": user.email}
    )
    
    return {
        "access_token": access_token,
        "token_type": "bearer",
        "user_type": user_type,
        "user_id": user_id,
        "email": user.email,
        "name": user.name
    }
