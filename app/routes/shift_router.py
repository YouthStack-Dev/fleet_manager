from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.orm import Session
from typing import Optional
from app.database.session import get_db
from app.models.shift import Shift
from app.schemas.shift import ShiftCreate, ShiftUpdate, ShiftResponse, ShiftPaginationResponse
from app.utils.pagination import paginate_query

router = APIRouter(prefix="/shifts", tags=["shifts"])

@router.post("/", response_model=ShiftResponse, status_code=status.HTTP_201_CREATED)
def create_shift(shift: ShiftCreate, db: Session = Depends(get_db)):
    db_shift = Shift(**shift.dict())
    db.add(db_shift)
    db.commit()
    db.refresh(db_shift)
    return db_shift

@router.get("/", response_model=ShiftPaginationResponse)
def read_shifts(
    skip: int = 0,
    limit: int = 100,
    shift_code: Optional[str] = None,
    log_type: Optional[str] = None,
    pickup_type: Optional[str] = None,
    gender: Optional[str] = None,
    is_active: Optional[bool] = None,
    db: Session = Depends(get_db)
):
    query = db.query(Shift)
    
    # Apply filters
    if shift_code:
        query = query.filter(Shift.shift_code.ilike(f"%{shift_code}%"))
    if log_type:
        query = query.filter(Shift.log_type == log_type)
    if pickup_type:
        query = query.filter(Shift.pickup_type == pickup_type)
    if gender:
        query = query.filter(Shift.gender == gender)
    if is_active is not None:
        query = query.filter(Shift.is_active == is_active)
    
    total, items = paginate_query(query, skip, limit)
    return {"total": total, "items": items}

@router.get("/{shift_id}", response_model=ShiftResponse)
def read_shift(shift_id: int, db: Session = Depends(get_db)):
    db_shift = db.query(Shift).filter(Shift.shift_id == shift_id).first()
    if not db_shift:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Shift with ID {shift_id} not found"
        )
    return db_shift

@router.put("/{shift_id}", response_model=ShiftResponse)
def update_shift(shift_id: int, shift_update: ShiftUpdate, db: Session = Depends(get_db)):
    db_shift = db.query(Shift).filter(Shift.shift_id == shift_id).first()
    if not db_shift:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Shift with ID {shift_id} not found"
        )
    
    update_data = shift_update.dict(exclude_unset=True)
    for key, value in update_data.items():
        setattr(db_shift, key, value)
    
    db.commit()
    db.refresh(db_shift)
    return db_shift

@router.delete("/{shift_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_shift(shift_id: int, db: Session = Depends(get_db)):
    db_shift = db.query(Shift).filter(Shift.shift_id == shift_id).first()
    if not db_shift:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Shift with ID {shift_id} not found"
        )
    
    db.delete(db_shift)
    db.commit()
    return None
