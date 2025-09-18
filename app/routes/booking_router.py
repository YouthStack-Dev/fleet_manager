from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.orm import Session
from typing import Optional, List
from datetime import date
from app.database.session import get_db
from app.models.booking import Booking
from app.schemas.booking import BookingCreate, BookingUpdate, BookingResponse, BookingPaginationResponse, BookingStatusEnum
from app.utils.pagination import paginate_query
from common_utils.auth.permission_checker import PermissionChecker
from app.schemas.base import BaseResponse, PaginatedResponse
from app.utils.response_utils import ResponseWrapper, validate_pagination_params, handle_db_error

router = APIRouter(prefix="/bookings", tags=["bookings"])

@router.post("/", status_code=status.HTTP_201_CREATED)
def create_booking(
    booking: BookingCreate, 
    db: Session = Depends(get_db),
    user_data=Depends(PermissionChecker(["booking.create"], check_tenant=True))
):
    try:
        db_booking = Booking(**booking.dict())
        db.add(db_booking)
        db.commit()
        db.refresh(db_booking)
        
        return ResponseWrapper.created(
            data=BookingResponse.model_validate(db_booking),
            message="Booking created successfully"
        )
    except Exception as e:
        db.rollback()
        raise handle_db_error(e)

@router.get("/")
def read_bookings(
    skip: int = 0,
    limit: int = 100,
    employee_id: Optional[int] = None,
    shift_id: Optional[int] = None,
    booking_date: Optional[date] = None,
    status_filter: Optional[BookingStatusEnum] = None,
    team_id: Optional[int] = None,
    db: Session = Depends(get_db),
    user_data=Depends(PermissionChecker(["booking.read"], check_tenant=True))
):
    page, per_page = validate_pagination_params(skip, limit)
    
    query = db.query(Booking)
    
    # Apply filters
    if employee_id:
        query = query.filter(Booking.employee_id == employee_id)
    if shift_id:
        query = query.filter(Booking.shift_id == shift_id)
    if booking_date:
        query = query.filter(Booking.booking_date == booking_date)
    if status_filter:
        query = query.filter(Booking.status == status_filter)
    if team_id:
        query = query.filter(Booking.team_id == team_id)
    
    total = query.count()
    items = query.offset(skip).limit(limit).all()
    
    booking_responses = [BookingResponse.model_validate(item) for item in items]
    
    return ResponseWrapper.paginated(
        items=booking_responses,
        total=total,
        page=page,
        per_page=per_page,
        message="Bookings retrieved successfully"
    )

@router.get("/{booking_id}")
def read_booking(
    booking_id: int, 
    db: Session = Depends(get_db),
    user_data=Depends(PermissionChecker(["booking.read"], check_tenant=True))
):
    db_booking = db.query(Booking).filter(Booking.booking_id == booking_id).first()
    if not db_booking:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=ResponseWrapper.error(
                message=f"Booking with ID {booking_id} not found",
                error_code="BOOKING_NOT_FOUND"
            )
        )
    
    return ResponseWrapper.success(
        data=BookingResponse.model_validate(db_booking),
        message="Booking retrieved successfully"
    )

@router.put("/{booking_id}")
def update_booking(
    booking_id: int, 
    booking_update: BookingUpdate, 
    db: Session = Depends(get_db),
    user_data=Depends(PermissionChecker(["booking.update"], check_tenant=True))
):
    db_booking = db.query(Booking).filter(Booking.booking_id == booking_id).first()
    if not db_booking:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=ResponseWrapper.error(
                message=f"Booking with ID {booking_id} not found",
                error_code="BOOKING_NOT_FOUND"
            )
        )
    
    try:
        update_data = booking_update.dict(exclude_unset=True)
        for key, value in update_data.items():
            setattr(db_booking, key, value)
        
        db.commit()
        db.refresh(db_booking)
        
        return ResponseWrapper.updated(
            data=BookingResponse.model_validate(db_booking),
            message="Booking updated successfully"
        )
    except Exception as e:
        db.rollback()
        raise handle_db_error(e)

@router.delete("/{booking_id}", status_code=status.HTTP_200_OK)
def delete_booking(
    booking_id: int, 
    db: Session = Depends(get_db),
    user_data=Depends(PermissionChecker(["booking.delete"], check_tenant=True))
):
    db_booking = db.query(Booking).filter(Booking.booking_id == booking_id).first()
    if not db_booking:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=ResponseWrapper.error(
                message=f"Booking with ID {booking_id} not found",
                error_code="BOOKING_NOT_FOUND"
            )
        )
    
    try:
        db.delete(db_booking)
        db.commit()
        
        return ResponseWrapper.deleted(message="Booking deleted successfully")
    except Exception as e:
        db.rollback()
        raise handle_db_error(e)
