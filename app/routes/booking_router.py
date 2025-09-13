from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.orm import Session
from typing import Optional, List
from datetime import date
from app.database.session import get_db
from app.models.booking import Booking
from app.schemas.booking import BookingCreate, BookingUpdate, BookingResponse, BookingPaginationResponse, BookingStatusEnum
from app.utils.pagination import paginate_query

router = APIRouter(prefix="/bookings", tags=["bookings"])

@router.post("/", response_model=BookingResponse, status_code=status.HTTP_201_CREATED)
def create_booking(booking: BookingCreate, db: Session = Depends(get_db)):
    db_booking = Booking(**booking.dict())
    db.add(db_booking)
    db.commit()
    db.refresh(db_booking)
    return db_booking

@router.get("/", response_model=BookingPaginationResponse)
def read_bookings(
    skip: int = 0,
    limit: int = 100,
    employee_id: Optional[int] = None,
    shift_id: Optional[int] = None,
    booking_date: Optional[date] = None,
    status: Optional[BookingStatusEnum] = None,
    team_id: Optional[int] = None,
    db: Session = Depends(get_db)
):
    query = db.query(Booking)
    
    # Apply filters
    if employee_id:
        query = query.filter(Booking.employee_id == employee_id)
    if shift_id:
        query = query.filter(Booking.shift_id == shift_id)
    if booking_date:
        query = query.filter(Booking.booking_date == booking_date)
    if status:
        query = query.filter(Booking.status == status)
    if team_id:
        query = query.filter(Booking.team_id == team_id)
    
    total, items = paginate_query(query, skip, limit)
    return {"total": total, "items": items}

@router.get("/{booking_id}", response_model=BookingResponse)
def read_booking(booking_id: int, db: Session = Depends(get_db)):
    db_booking = db.query(Booking).filter(Booking.booking_id == booking_id).first()
    if not db_booking:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Booking with ID {booking_id} not found"
        )
    return db_booking

@router.put("/{booking_id}", response_model=BookingResponse)
def update_booking(booking_id: int, booking_update: BookingUpdate, db: Session = Depends(get_db)):
    db_booking = db.query(Booking).filter(Booking.booking_id == booking_id).first()
    if not db_booking:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Booking with ID {booking_id} not found"
        )
    
    update_data = booking_update.dict(exclude_unset=True)
    for key, value in update_data.items():
        setattr(db_booking, key, value)
    
    db.commit()
    db.refresh(db_booking)
    return db_booking

@router.delete("/{booking_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_booking(booking_id: int, db: Session = Depends(get_db)):
    db_booking = db.query(Booking).filter(Booking.booking_id == booking_id).first()
    if not db_booking:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Booking with ID {booking_id} not found"
        )
    
    db.delete(db_booking)
    db.commit()
    return None
