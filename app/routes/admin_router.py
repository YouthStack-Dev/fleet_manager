from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from typing import List

from database.session import get_db
from models.admin import Admin
from schemas.admin import AdminCreate, AdminResponse, AdminUpdate

router = APIRouter(
    prefix="/admins",
    tags=["Admins"],
    responses={404: {"description": "Not found"}},
)

@router.post("/", response_model=AdminResponse, status_code=status.HTTP_201_CREATED)
def create_admin(admin: AdminCreate, db: Session = Depends(get_db)):
    # Check if admin with email already exists
    db_admin = db.query(Admin).filter(Admin.email == admin.email).first()
    if db_admin:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Email already registered"
        )
    
    # Create new admin
    # Note: In real app, we would hash the password here
    new_admin = Admin(**admin.model_dump())
    db.add(new_admin)
    db.commit()
    db.refresh(new_admin)
    return new_admin

@router.get("/", response_model=List[AdminResponse])
def get_admins(skip: int = 0, limit: int = 100, db: Session = Depends(get_db)):
    admins = db.query(Admin).offset(skip).limit(limit).all()
    return admins

@router.get("/{admin_id}", response_model=AdminResponse)
def get_admin(admin_id: int, db: Session = Depends(get_db)):
    admin = db.query(Admin).filter(Admin.admin_id == admin_id).first()
    if not admin:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Admin with ID {admin_id} not found"
        )
    return admin

@router.put("/{admin_id}", response_model=AdminResponse)
def update_admin(admin_id: int, admin_update: AdminUpdate, db: Session = Depends(get_db)):
    db_admin = db.query(Admin).filter(Admin.admin_id == admin_id).first()
    if not db_admin:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Admin with ID {admin_id} not found"
        )
    
    # Update only provided fields
    update_data = admin_update.model_dump(exclude_unset=True)
    for key, value in update_data.items():
        setattr(db_admin, key, value)
    
    db.commit()
    db.refresh(db_admin)
    return db_admin

@router.delete("/{admin_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_admin(admin_id: int, db: Session = Depends(get_db)):
    db_admin = db.query(Admin).filter(Admin.admin_id == admin_id).first()
    if not db_admin:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Admin with ID {admin_id} not found"
        )
    
    db.delete(db_admin)
    db.commit()
    return None
