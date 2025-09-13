from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.orm import Session
from typing import Optional
from app.database.session import get_db
from app.models.route_booking import RouteBooking
from app.schemas.route_booking import RouteBookingCreate, RouteBookingUpdate, RouteBookingResponse, RouteBookingPaginationResponse
from app.utils.pagination import paginate_query

router = APIRouter(prefix="/route-bookings", tags=["route bookings"])

@router.post("/", response_model=RouteBookingResponse, status_code=status.HTTP_201_CREATED)
def create_route_booking(route_booking: RouteBookingCreate, db: Session = Depends(get_db)):
    db_route_booking = RouteBooking(**route_booking.dict())
    db.add(db_route_booking)
    db.commit()
    db.refresh(db_route_booking)
    return db_route_booking

@router.get("/", response_model=RouteBookingPaginationResponse)
def read_route_bookings(
    skip: int = 0,
    limit: int = 100,
    route_id: Optional[int] = None,
    booking_id: Optional[int] = None,
    db: Session = Depends(get_db)
):
    query = db.query(RouteBooking)
    
    # Apply filters
    if route_id:
        query = query.filter(RouteBooking.route_id == route_id)
    if booking_id:
        query = query.filter(RouteBooking.booking_id == booking_id)
    
    total, items = paginate_query(query, skip, limit)
    return {"total": total, "items": items}

@router.get("/{route_booking_id}", response_model=RouteBookingResponse)
def read_route_booking(route_booking_id: int, db: Session = Depends(get_db)):
    db_route_booking = db.query(RouteBooking).filter(RouteBooking.route_booking_id == route_booking_id).first()
    if not db_route_booking:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Route Booking with ID {route_booking_id} not found"
        )
    return db_route_booking

@router.put("/{route_booking_id}", response_model=RouteBookingResponse)
def update_route_booking(route_booking_id: int, route_booking_update: RouteBookingUpdate, db: Session = Depends(get_db)):
    db_route_booking = db.query(RouteBooking).filter(RouteBooking.route_booking_id == route_booking_id).first()
    if not db_route_booking:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Route Booking with ID {route_booking_id} not found"
        )
    
    update_data = route_booking_update.dict(exclude_unset=True)
    for key, value in update_data.items():
        setattr(db_route_booking, key, value)
    
    db.commit()
    db.refresh(db_route_booking)
    return db_route_booking

@router.delete("/{route_booking_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_route_booking(route_booking_id: int, db: Session = Depends(get_db)):
    db_route_booking = db.query(RouteBooking).filter(RouteBooking.route_booking_id == route_booking_id).first()
    if not db_route_booking:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Route Booking with ID {route_booking_id} not found"
        )
    
    db.delete(db_route_booking)
    db.commit()
    return None
