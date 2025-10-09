from app.models.cutoff import Cutoff
from app.models.employee import Employee
from app.models.shift import Shift
from app.models.weekoff_config import WeekoffConfig
from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.orm import Session
from typing import Optional, List
from datetime import date, datetime, datetime
from app.database.session import get_db
from app.models.booking import Booking
from app.schemas.booking import BookingCreate, BookingUpdate, BookingResponse, BookingPaginationResponse, BookingStatusEnum
from app.utils.pagination import paginate_query
from common_utils.auth.permission_checker import PermissionChecker
from app.schemas.base import BaseResponse, PaginatedResponse
from app.utils.response_utils import ResponseWrapper, handle_http_error, validate_pagination_params, handle_db_error
from tests.conftest import db
from sqlalchemy.exc import SQLAlchemyError

router = APIRouter(prefix="/bookings", tags=["bookings"])


router = APIRouter()


@router.post("/", status_code=status.HTTP_201_CREATED)
def create_booking(
    booking: BookingCreate,
    db: Session = Depends(get_db),
    user_data=Depends(PermissionChecker(["booking.create"], check_tenant=True)),
):
    try:
        # --- 1️⃣ Check employee ---
        employee = db.query(Employee).filter(
            Employee.employee_id == booking.employee_id,
            Employee.tenant_id == user_data["tenant_id"],
            Employee.is_active == True
        ).first()
        if not employee:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=ResponseWrapper.error(
                    message="Employee not found in this tenant or inactive",
                    error_code="EMPLOYEE_NOT_FOUND",
                ),
            )
        
        # Ensure the user type is employee
        if user_data.get("user_type") != "employee":
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=ResponseWrapper.error(
                    message="Only employees can create bookings",
                    error_code="FORBIDDEN",
                ),
            )

        # --- 2️⃣ Check shift belongs to tenant ---
        if booking.shift_id:
            shift = db.query(Shift).filter(
                Shift.shift_id == booking.shift_id,
                Shift.tenant_id == user_data["tenant_id"]
            ).first()
            if not shift:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail=ResponseWrapper.error(
                        message="Shift not found for this tenant",
                        error_code="SHIFT_NOT_FOUND",
                    ),
                )

        # --- 3️⃣ Check weekoff ---
        weekday = booking.booking_date.weekday()  # Monday=0, Sunday=6

        weekoff_config = db.query(WeekoffConfig).filter(
            WeekoffConfig.employee_id == booking.employee_id
        ).first()

        weekday_map = {
            0: "monday",
            1: "tuesday",
            2: "wednesday",
            3: "thursday",
            4: "friday",
            5: "saturday",
            6: "sunday",
        }

        if weekoff_config:
            is_weekoff = getattr(weekoff_config, weekday_map[weekday], False)
            if is_weekoff:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=ResponseWrapper.error(
                        message="Cannot create booking on employee's weekoff day",
                        error_code="WEEKOFF_DAY",
                    ),
                )


        # --- 4️⃣ Check booking cutoff ---
        cutoff = db.query(Cutoff).filter(Cutoff.tenant_id == user_data["tenant_id"]).first()
        if cutoff:
            now = datetime.now()
            today_date = now.date()
            cutoff_time = (datetime.min + cutoff.booking_cutoff).time()  # convert timedelta to time
            cutoff_datetime = datetime.combine(today_date, cutoff_time)

            if now > cutoff_datetime:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=ResponseWrapper.error(
                        message=f"Booking cutoff time passed for today ({cutoff.booking_cutoff})",
                        error_code="BOOKING_CUTOFF",
                    ),
                )

        # --- 5️⃣ Create booking ---
        db_booking = Booking(
            tenant_id=user_data["tenant_id"],
            employee_id=employee.employee_id,
            employee_code=employee.employee_code,
            shift_id=booking.shift_id,
            booking_date=booking.booking_date
        )
        db.add(db_booking)
        db.commit()
        db.refresh(db_booking)

        return ResponseWrapper.created(
            data=BookingResponse.model_validate(db_booking),
            message="Booking created successfully"
        )
    except SQLAlchemyError as e:
        db.rollback()
        raise handle_db_error(e)
    except HTTPException as e:
        db.rollback()
        raise handle_http_error(e)

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
