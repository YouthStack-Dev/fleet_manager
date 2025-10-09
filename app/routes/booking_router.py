
from app.models.cutoff import Cutoff
from app.models.employee import Employee
from app.models.shift import Shift
from app.models.tenant import Tenant
from app.models.weekoff_config import WeekoffConfig
from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.orm import Session
from typing import Optional, List
from datetime import date, datetime, datetime
from app.database.session import get_db
from app.models.booking import Booking
from app.schemas.booking import BookingCreate, BookingUpdate, BookingResponse,  BookingStatusEnum
from app.utils.pagination import paginate_query
from common_utils.auth.permission_checker import PermissionChecker
from app.schemas.base import BaseResponse, PaginatedResponse
from app.utils.response_utils import ResponseWrapper, handle_http_error, validate_pagination_params, handle_db_error
from sqlalchemy.exc import SQLAlchemyError
from app.core.logging_config import get_logger

logger = get_logger(__name__)
router = APIRouter(prefix="/bookings", tags=["bookings"])



@router.post("/", status_code=status.HTTP_201_CREATED)
def create_booking(
    booking: BookingCreate,
    db: Session = Depends(get_db),
    user_data=Depends(PermissionChecker(["booking.create"], check_tenant=True)),
):
    try:
        logger.info(
            f"Attempting to create booking for employee_id={booking.employee_id} "
            f"on date={booking.booking_date} by user_id={user_data.get('user_id')}"
        )

        # --- 1️⃣ Check employee ---
        employee = (
            db.query(Employee)
            .filter(
                Employee.employee_id == booking.employee_id,
                Employee.tenant_id == user_data["tenant_id"],
                Employee.is_active == True
            )
            .first()
        )
        if not employee:
            logger.warning(f"Employee not found or inactive: employee_id={booking.employee_id}")
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=ResponseWrapper.error(
                    message="Employee not found in this tenant or inactive",
                    error_code="EMPLOYEE_NOT_FOUND",
                ),
            )

        if user_data.get("user_type") != "employee":
            logger.warning(f"User is not an employee: user_type={user_data.get('user_type')}")
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=ResponseWrapper.error(
                    message="Only employees can create bookings",
                    error_code="FORBIDDEN",
                ),
            )

        # --- 2️⃣ Check shift ---
        shift = None
        if booking.shift_id:
            shift = (
                db.query(Shift)
                .filter(
                    Shift.shift_id == booking.shift_id,
                    Shift.tenant_id == user_data["tenant_id"]
                )
                .first()
            )
            if not shift:
                logger.warning(f"Shift not found: shift_id={booking.shift_id}")
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail=ResponseWrapper.error(
                        message="Shift not found for this tenant",
                        error_code="SHIFT_NOT_FOUND",
                    ),
                )

        # --- 3️⃣ Check weekoff ---
        weekday = booking.booking_date.weekday()
        weekoff_config = db.query(WeekoffConfig).filter(
            WeekoffConfig.employee_id == booking.employee_id
        ).first()
        weekday_map = {0: "monday", 1: "tuesday", 2: "wednesday", 3: "thursday",
                       4: "friday", 5: "saturday", 6: "sunday"}
        if weekoff_config and getattr(weekoff_config, weekday_map[weekday], False):
            logger.info(f"Booking on weekoff day: employee_id={booking.employee_id}, weekday={weekday_map[weekday]}")
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=ResponseWrapper.error(
                    message="Cannot create booking on employee's weekoff day",
                    error_code="WEEKOFF_DAY",
                ),
            )

        # --- 4️⃣ Check cutoff ---
        cutoff = db.query(Cutoff).filter(Cutoff.tenant_id == user_data["tenant_id"]).first()
        if cutoff and shift:
            shift_datetime = datetime.combine(booking.booking_date, shift.shift_time)
            booking_cutoff_datetime = shift_datetime - cutoff.booking_cutoff
            now = datetime.now()
            if now > booking_cutoff_datetime:
                logger.info(
                    f"Booking cutoff passed: now={now}, cutoff_datetime={booking_cutoff_datetime}, "
                    f"employee_id={booking.employee_id}"
                )
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=ResponseWrapper.error(
                        message=f"Booking cutoff time has passed for this shift (cutoff: {cutoff.booking_cutoff})",
                        error_code="BOOKING_CUTOFF",
                    ),
                )

        # --- 5️⃣ Determine pickup & drop locations ---
        tenant = db.query(Tenant).filter(Tenant.tenant_id == user_data["tenant_id"]).first()
        if not tenant:
            logger.error(f"Tenant not found: tenant_id={user_data['tenant_id']}")
            raise HTTPException(status_code=404, detail="Tenant not found")

        if shift:
            if shift.log_type == "IN":  # home → office
                pickup_lat, pickup_lng = float(employee.latitude), float(employee.longitude)
                pickup_addr = employee.address
                drop_lat, drop_lng = float(tenant.latitude), float(tenant.longitude)
                drop_addr = tenant.address
            elif shift.log_type == "OUT":  # office → home
                pickup_lat, pickup_lng = float(tenant.latitude), float(tenant.longitude)
                pickup_addr = tenant.address
                drop_lat, drop_lng = float(employee.latitude), float(employee.longitude)
                drop_addr = employee.address
        else:
            pickup_lat = pickup_lng = drop_lat = drop_lng = None
            pickup_addr = drop_addr = None

        # --- 6️⃣ Create booking ---
        db_booking = Booking(
            tenant_id=user_data["tenant_id"],
            employee_id=employee.employee_id,
            employee_code=employee.employee_code,
            shift_id=booking.shift_id,
            booking_date=booking.booking_date,
            pickup_latitude=pickup_lat,
            pickup_longitude=pickup_lng,
            pickup_location=pickup_addr,
            drop_latitude=drop_lat,
            drop_longitude=drop_lng,
            drop_location=drop_addr,
            status="Pending",
        )
        db.add(db_booking)
        db.commit()
        db.refresh(db_booking)

        logger.info(f"Booking created successfully: booking_id={db_booking.booking_id}")

        return ResponseWrapper.created(
            data=BookingResponse.model_validate(db_booking),
            message="Booking created successfully"
        )

    except SQLAlchemyError as e:
        db.rollback()
        logger.exception("Database error occurred while creating booking")
        raise handle_db_error(e)

    except HTTPException as e:
        db.rollback()
        logger.warning(f"HTTPException: {e.detail}")
        raise handle_http_error(e)

    except Exception as e:
        db.rollback()
        logger.exception("Unexpected error occurred while creating booking")
        raise HTTPException(
            status_code=500,
            detail=ResponseWrapper.error(message="Internal Server Error", error_code="INTERNAL_ERROR")
        )



# @router.get("/")
# def read_bookings(
#     skip: int = 0,
#     limit: int = 100,
#     employee_id: Optional[int] = None,
#     shift_id: Optional[int] = None,
#     booking_date: Optional[date] = None,
#     status_filter: Optional[BookingStatusEnum] = None,
#     team_id: Optional[int] = None,
#     db: Session = Depends(get_db),
#     user_data=Depends(PermissionChecker(["booking.read"], check_tenant=True))
# ):
#     page, per_page = validate_pagination_params(skip, limit)
    
#     query = db.query(Booking)
    
#     # Apply filters
#     if employee_id:
#         query = query.filter(Booking.employee_id == employee_id)
#     if shift_id:
#         query = query.filter(Booking.shift_id == shift_id)
#     if booking_date:
#         query = query.filter(Booking.booking_date == booking_date)
#     if status_filter:
#         query = query.filter(Booking.status == status_filter)
#     if team_id:
#         query = query.filter(Booking.team_id == team_id)
    
#     total = query.count()
#     items = query.offset(skip).limit(limit).all()
    
#     booking_responses = [BookingResponse.model_validate(item) for item in items]
    
#     return ResponseWrapper.paginated(
#         items=booking_responses,
#         total=total,
#         page=page,
#         per_page=per_page,
#         message="Bookings retrieved successfully"
#     )

# @router.get("/{booking_id}")
# def read_booking(
#     booking_id: int, 
#     db: Session = Depends(get_db),
#     user_data=Depends(PermissionChecker(["booking.read"], check_tenant=True))
# ):
#     db_booking = db.query(Booking).filter(Booking.booking_id == booking_id).first()
#     if not db_booking:
#         raise HTTPException(
#             status_code=status.HTTP_404_NOT_FOUND,
#             detail=ResponseWrapper.error(
#                 message=f"Booking with ID {booking_id} not found",
#                 error_code="BOOKING_NOT_FOUND"
#             )
#         )
    
#     return ResponseWrapper.success(
#         data=BookingResponse.model_validate(db_booking),
#         message="Booking retrieved successfully"
#     )

# @router.put("/{booking_id}")
# def update_booking(
#     booking_id: int, 
#     booking_update: BookingUpdate, 
#     db: Session = Depends(get_db),
#     user_data=Depends(PermissionChecker(["booking.update"], check_tenant=True))
# ):
#     db_booking = db.query(Booking).filter(Booking.booking_id == booking_id).first()
#     if not db_booking:
#         raise HTTPException(
#             status_code=status.HTTP_404_NOT_FOUND,
#             detail=ResponseWrapper.error(
#                 message=f"Booking with ID {booking_id} not found",
#                 error_code="BOOKING_NOT_FOUND"
#             )
#         )
    
#     try:
#         update_data = booking_update.dict(exclude_unset=True)
#         for key, value in update_data.items():
#             setattr(db_booking, key, value)
        
#         db.commit()
#         db.refresh(db_booking)
        
#         return ResponseWrapper.updated(
#             data=BookingResponse.model_validate(db_booking),
#             message="Booking updated successfully"
#         )
#     except Exception as e:
#         db.rollback()
#         raise handle_db_error(e)

# @router.delete("/{booking_id}", status_code=status.HTTP_200_OK)
# def delete_booking(
#     booking_id: int, 
#     db: Session = Depends(get_db),
#     user_data=Depends(PermissionChecker(["booking.delete"], check_tenant=True))
# ):
#     db_booking = db.query(Booking).filter(Booking.booking_id == booking_id).first()
#     if not db_booking:
#         raise HTTPException(
#             status_code=status.HTTP_404_NOT_FOUND,
#             detail=ResponseWrapper.error(
#                 message=f"Booking with ID {booking_id} not found",
#                 error_code="BOOKING_NOT_FOUND"
#             )
#         )
    
#     try:
#         db.delete(db_booking)
#         db.commit()
        
#         return ResponseWrapper.deleted(message="Booking deleted successfully")
#     except Exception as e:
#         db.rollback()
#         raise handle_db_error(e)
