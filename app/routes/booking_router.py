
from app.models.cutoff import Cutoff
from app.models.employee import Employee
from app.models.shift import Shift
from app.models.tenant import Tenant
from app.models.weekoff_config import WeekoffConfig
from fastapi import APIRouter, Depends, HTTPException, Path, status, Query
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

def booking_validate_future_dates(dates: list[date], context: str = "dates"):
    today = date.today()
    for d in dates:
        if d <= today:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=ResponseWrapper.error(
                    message=f"{context} must contain only future dates (invalid: {d})",
                    error_code="INVALID_DATE",
                ),
            )


@router.post("/", status_code=status.HTTP_201_CREATED)
def create_booking(
    booking: BookingCreate,
    db: Session = Depends(get_db),
    user_data=Depends(PermissionChecker(["booking.create"], check_tenant=True)),
):
    try:
        user_type = user_data.get("user_type")


        user_id = user_data.get("user_id")
        logger.info(f"Attempting to create bookings for employee_id={booking.employee_id} by user_id={user_id}")
        logger.info(f"booking: {booking.booking_dates}")
        # --- Tenant validation ---
        if user_type == "admin":
            tenant_id = booking.tenant_id
            if not tenant_id:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=ResponseWrapper.error(
                        message="Admin must provide tenant_id to create drivers",
                        error_code="TENANT_ID_REQUIRED",
                    ),
                )
        elif user_type == "employee":
            tenant_id = user_data.get("tenant_id")
        else:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=ResponseWrapper.error(
                    message="You don't have permission to create drivers",
                    error_code="FORBIDDEN",
                ),
            )

        # --- Employee validation ---
        employee = (
            db.query(Employee)
            .filter(
                Employee.employee_id == booking.employee_id,
                Employee.tenant_id == tenant_id,
                Employee.is_active.is_(True)
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

        # --- Shift validation ---
        shift = (
            db.query(Shift)
            .filter(Shift.shift_id == booking.shift_id, Shift.tenant_id == tenant_id)
            .first()
        )
        if not shift:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=ResponseWrapper.error("Shift not found for this tenant", "SHIFT_NOT_FOUND"),
            )

        # --- Tenant lookup ---
        tenant = db.query(Tenant).filter(Tenant.tenant_id == tenant_id).first()
        if not tenant:
            raise HTTPException(status_code=404, detail="Tenant not found")

        # --- Weekoff & Cutoff configs ---
        weekoff_config = db.query(WeekoffConfig).filter(
            WeekoffConfig.employee_id == employee.employee_id
        ).first()
        cutoff = db.query(Cutoff).filter(Cutoff.tenant_id == tenant_id).first()

        created_bookings = []
        weekday_map = {0: "monday", 1: "tuesday", 2: "wednesday", 3: "thursday",
                       4: "friday", 5: "saturday", 6: "sunday"}
        booking_validate_future_dates(booking.booking_dates, context="dates")
        unique_dates = sorted(set(booking.booking_dates))
        for booking_date in unique_dates:
            
            weekday = booking_date.weekday()

            # 1️⃣ Weekoff validation
            if weekoff_config and getattr(weekoff_config, weekday_map[weekday], False):
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=ResponseWrapper.error(
                        f"Cannot create booking on weekoff day ({weekday_map[weekday]})",
                        "WEEKOFF_DAY",
                    ),
                )
            

            # 2️⃣ Cutoff validation
            if cutoff and shift and cutoff.booking_cutoff and cutoff.booking_cutoff.total_seconds() > 0:
                shift_datetime = datetime.combine(booking_date, shift.shift_time)
                now = datetime.now()
                time_until_shift = shift_datetime - now
                logger.info(
                    f"Cutoff check: now={now}, shift_datetime={shift_datetime}, "
                    f"time_until_shift={time_until_shift}, cutoff={cutoff.booking_cutoff}"
                )
                if time_until_shift < cutoff.booking_cutoff:
                    raise HTTPException(
                        status_code=status.HTTP_400_BAD_REQUEST,
                        detail=ResponseWrapper.error(
                            f"Booking cutoff time has passed for this shift (cutoff: {cutoff.booking_cutoff})",
                            "BOOKING_CUTOFF",
                        ),
                    )



            # 3️⃣ Duplicate booking check
            existing_booking = (
                db.query(Booking)
                .filter(
                    Booking.employee_id == employee.employee_id,
                    Booking.booking_date == booking_date,
                    Booking.shift_id == booking.shift_id,
                )
                .first()
            )
            logger.info(
                    f"Existing booking check: employee_id={employee.employee_id}, booking_date={booking_date}, shift_id={shift.shift_id}"
                )

            if existing_booking:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=ResponseWrapper.error(
                        message=f"Employee already has a booking for this shift and date ({booking_date})",
                        error_code="ALREADY_BOOKED",
                    ),
                )

            # 4️⃣ Compute pickup/drop based on shift
            if shift.log_type == "IN":  # home → office
                pickup_lat, pickup_lng = employee.latitude, employee.longitude
                pickup_addr = employee.address
                drop_lat, drop_lng = tenant.latitude, tenant.longitude
                drop_addr = tenant.address
            else:  # OUT: office → home
                pickup_lat, pickup_lng = tenant.latitude, tenant.longitude
                pickup_addr = tenant.address
                drop_lat, drop_lng = employee.latitude, employee.longitude
                drop_addr = employee.address

            # 5️⃣ Create booking object
            db_booking = Booking(
                tenant_id=tenant_id,
                employee_id=employee.employee_id,
                employee_code=employee.employee_code,
                team_id=employee.team_id,
                shift_id=booking.shift_id,
                booking_date=booking_date,
                pickup_latitude=pickup_lat,
                pickup_longitude=pickup_lng,
                pickup_location=pickup_addr,
                drop_latitude=drop_lat,
                drop_longitude=drop_lng,
                drop_location=drop_addr,
                status="Pending",
            )
            db.add(db_booking)
            db.flush()
            created_bookings.append(db_booking)

        db.commit()
        for b in created_bookings:
            db.refresh(b)

        logger.info(
            f"Created {len(created_bookings)} bookings for employee_id={employee.employee_id} "
            f"on dates={[b.booking_date for b in created_bookings]}"
        )

        return ResponseWrapper.created(
            data=[BookingResponse.model_validate(b) for b in created_bookings],
            message=f"{len(created_bookings)} booking(s) created successfully",
        )

    except HTTPException as e:
        db.rollback()
        logger.warning(f"HTTPException during booking creation: {e.detail}")
        raise handle_http_error(e)

    except SQLAlchemyError as e:
        db.rollback()
        logger.exception("Database error occurred while creating booking")
        raise handle_db_error(e)


    except Exception as e:
        db.rollback()
        logger.exception("Unexpected error occurred while creating booking")
        raise HTTPException(
            status_code=500,
            detail=ResponseWrapper.error(message="Internal Server Error", error_code="INTERNAL_ERROR")
        )



# ============================================================
# 1️⃣ Get all bookings (filtered by tenant_id and optional date)
# ============================================================
@router.get("/tenant/{tenant_id}", response_model=PaginatedResponse[BookingResponse])
def get_bookings(
    db: Session = Depends(get_db),
    user_data=Depends(PermissionChecker(["booking.read"], check_tenant=True)),
    booking_date: Optional[date] = Query(None, description="Filter by booking date"),
    tenant_id: Optional[str] = None,
    skip: int = Query(0, ge=0),
    limit: int = Query(10, ge=1, le=100),
):
    try:
        # --- Determine effective tenant ---
        user_type = user_data.get("user_type")
        if user_type == "admin":
            if not tenant_id:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=ResponseWrapper.error(
                        message="Admin must provide tenant_id",
                        error_code="TENANT_ID_REQUIRED",
                    ),
                )
            effective_tenant_id = tenant_id
        elif user_type == "employee":
            effective_tenant_id = user_data.get("tenant_id")
        else:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=ResponseWrapper.error(
                    message="You don't have permission to view bookings",
                    error_code="FORBIDDEN",
                ),
            )

        skip = max(skip, 0)
        limit = max(min(limit, 100), 1)

        logger.info(
            f"Fetching bookings: user_type={user_type}, effective_tenant_id={effective_tenant_id}, "
            f"date_filter={booking_date}, skip={skip}, limit={limit}"
        )

        # --- Build query ---
        query = db.query(Booking).filter(Booking.tenant_id == effective_tenant_id)
        if booking_date:
            query = query.filter(Booking.booking_date == booking_date)

        # 🔹 Log total filtered records before pagination
        filtered_count = query.count()
        logger.info(
            f"Filtered bookings count for tenant_id={effective_tenant_id} "
            f"with date={booking_date}: {filtered_count}"
        )

        total, items = paginate_query(query, skip, limit)

        return ResponseWrapper.paginated(
            items=[BookingResponse.model_validate(b, from_attributes=True) for b in items],
            total=total,
            page=(skip // limit) + 1,
            per_page=limit,
            message="Bookings fetched successfully"
        )

    except SQLAlchemyError as e:
        logger.exception("Database error occurred while fetching bookings")
        raise handle_db_error(e)
    except HTTPException as e:
        raise handle_http_error(e)
    except Exception as e:
        logger.exception("Unexpected error occurred while fetching bookings")
        raise handle_http_error(e)



# ============================================================
# 2️⃣ Get bookings for a specific employee (by ID or code)
# ============================================================
@router.get("/employee", response_model=PaginatedResponse[BookingResponse])
def get_bookings_by_employee(
    employee_id: Optional[int] = Query(None, description="Employee ID"),
    employee_code: Optional[str] = Query(None, description="Employee code"),
    booking_date: Optional[date] = Query(None, description="Optional booking date filter"),
    db: Session = Depends(get_db),
    user_data=Depends(PermissionChecker(["booking.read"], check_tenant=True)),
    skip: int = Query(0, ge=0),
    limit: int = Query(10, ge=1, le=100),
):
    try:
        if not employee_id and not employee_code:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=ResponseWrapper.error(
                    message="Either employee_id or employee_code is required",
                    error_code="MISSING_FILTER",
                ),
            )

        skip = max(skip, 0)
        limit = max(min(limit, 100), 1)

        user_type = user_data.get("user_type")
        tenant_id = user_data.get("tenant_id")
        logger.info(f"Fetching bookings for employee_id={employee_id}, employee_code={employee_code}, user_type={user_type}")

        if user_type in {"vendor", "driver"}:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=ResponseWrapper.error(
                    message="You don't have permission to view employee bookings",
                    error_code="FORBIDDEN",
                ),
            )

        # Base query
        query = db.query(Booking)
        if employee_id:
            query = query.filter(Booking.employee_id == employee_id)
        elif employee_code:
            query = query.filter(Booking.employee_code == employee_code)

        if booking_date:
            query = query.filter(Booking.booking_date == booking_date)

        # Tenant enforcement for non-admin employees
        if user_type != "admin":
            query = query.filter(Booking.tenant_id == tenant_id)

        total, items = paginate_query(query, skip, limit)

        return ResponseWrapper.paginated(
            items=[BookingResponse.model_validate(b, from_attributes=True) for b in items],
            total=total,
            page=(skip // limit) + 1,
            per_page=limit,
            message="Employee bookings fetched successfully"
        )

    except SQLAlchemyError as e:
        logger.exception("Database error occurred while fetching employee bookings")
        raise handle_db_error(e)
    except HTTPException as e:
        raise handle_http_error(e)
    except Exception as e:
        logger.exception("Unexpected error occurred while fetching employee bookings")
        raise handle_http_error(e)


# ============================================================
# 3️⃣ Get single booking by booking_id
# ============================================================
@router.get("/{booking_id}", response_model=BaseResponse[BookingResponse])
def get_booking_by_id(
    booking_id: int,
    db: Session = Depends(get_db),
    user_data=Depends(PermissionChecker(["booking.read"], check_tenant=True)),
):
    try:
        user_type = user_data.get("user_type")
        tenant_id = user_data.get("tenant_id")
        logger.info(f"Fetching booking_id={booking_id} for user_type={user_type}")

        query = db.query(Booking).filter(Booking.booking_id == booking_id)
        if user_type != "admin":
            query = query.filter(Booking.tenant_id == tenant_id)

        booking = query.first()
        if not booking:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=ResponseWrapper.error(
                    message="Booking not found",
                    error_code="BOOKING_NOT_FOUND",
                ),
            )

        return ResponseWrapper.success(
            data=BookingResponse.model_validate(booking, from_attributes=True),
            message="Booking fetched successfully"
        )

    except SQLAlchemyError as e:
        logger.exception("Database error occurred while fetching booking by ID")
        raise handle_db_error(e)
    except HTTPException as e:
        raise handle_http_error(e)
    except Exception as e:
        logger.exception("Unexpected error occurred while fetching booking by ID")
        raise handle_http_error(e)



from fastapi import Body, Path

# ============================================================
# 4️⃣ Update booking by booking_id
# ============================================================
@router.put("/{booking_id}", response_model=BaseResponse[BookingResponse])
def update_booking(
    booking_id: int = Path(..., description="Booking ID to update"),
    booking_update: BookingUpdate = Body(...),
    db: Session = Depends(get_db),
    user_data=Depends(PermissionChecker(["booking.update"], check_tenant=True)),
):
    try:
        user_type = user_data.get("user_type")
        tenant_id = user_data.get("tenant_id")

        logger.info(f"Updating booking_id={booking_id} by user_id={user_data.get('user_id')}")

        # Fetch the booking
        query = db.query(Booking).filter(Booking.booking_id == booking_id)
        if user_type != "admin":
            query = query.filter(Booking.tenant_id == tenant_id)

        booking = query.first()
        if not booking:
            logger.warning(f"Booking not found: booking_id={booking_id}")
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=ResponseWrapper.error(
                    message="Booking not found",
                    error_code="BOOKING_NOT_FOUND",
                ),
            )

        # Only allow certain roles to update bookings
        if user_type in {"vendor", "driver"}:
            logger.warning(f"Unauthorized update attempt by user_type={user_type}")
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=ResponseWrapper.error(
                    message="You don't have permission to update bookings",
                    error_code="FORBIDDEN",
                ),
            )

        # Apply updates
        updated_fields = []
        if booking_update.status is not None:
            booking.status = booking_update.status
            updated_fields.append("status")
        if booking_update.reason is not None:
            booking.reason = booking_update.reason
            updated_fields.append("reason")
        

        if not updated_fields:
            logger.warning(f"No fields provided to update for booking_id={booking_id}")
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=ResponseWrapper.error(
                    message="No valid fields provided for update",
                    error_code="NO_UPDATE_FIELDS",
                ),
            )

        # Commit changes
        db.commit()
        db.refresh(booking)

        logger.info(f"Booking updated successfully: booking_id={booking_id}, fields={updated_fields}")

        return ResponseWrapper.success(
            data=BookingResponse.model_validate(booking, from_attributes=True),
            message="Booking updated successfully"
        )

    except SQLAlchemyError as e:
        db.rollback()
        logger.exception("Database error occurred while updating booking")
        raise handle_db_error(e)
    except HTTPException as e:
        db.rollback()
        raise handle_http_error(e)
    except Exception as e:
        db.rollback()
        logger.exception("Unexpected error occurred while updating booking")
        raise HTTPException(
            status_code=500,
            detail=ResponseWrapper.error(message="Internal Server Error", error_code="INTERNAL_ERROR")
        )
