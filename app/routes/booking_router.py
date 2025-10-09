
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

        # --- 6️⃣ Check for existing booking ---
        existing_booking = (
            db.query(Booking)
            .filter(
                Booking.employee_id == employee.employee_id,
                Booking.booking_date == booking.booking_date,
                Booking.shift_id == booking.shift_id,
            )
            .first()
        )
        if existing_booking:
            logger.warning(
                f"Employee already has booking for this shift: "
                f"employee_id={employee.employee_id}, date={booking.booking_date}, shift_id={booking.shift_id}"
            )
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=ResponseWrapper.error(
                    message="Employee already has a booking for this shift and date",
                    error_code="ALREADY_BOOKED",
                ),
            )

        # --- 7️⃣ Create booking with team_id ---
        db_booking = Booking(
            tenant_id=user_data["tenant_id"],
            employee_id=employee.employee_id,
            employee_code=employee.employee_code,
            team_id=employee.team_id,
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



# ============================================================
# 1️⃣ Get all bookings (filtered by tenant_id and optional date)
# ============================================================
@router.get("/tenant/{tenant_id}", response_model=PaginatedResponse[BookingResponse])
def get_bookings(
    db: Session = Depends(get_db),
    user_data=Depends(PermissionChecker(["booking.read"], check_tenant=True)),
    booking_date: Optional[date] = Query(None, description="Filter by booking date"),
    tenant_id: str = Path(..., description="Tenant ID"),
    skip: int = Query(0, ge=0),
    limit: int = Query(10, ge=1, le=100),
):
    try:
        # Normalize skip/limit
        skip = max(skip, 0)
        limit = max(min(limit, 100), 1)

        logger.info(
            f"Fetching bookings for tenant_id={user_data['tenant_id']} "
            f"date_filter={booking_date}, skip={skip}, limit={limit}"
        )

        # Admins can query any tenant, employees limited to their own
        effective_tenant_id = tenant_id if user_data["user_type"] == "admin" else user_data["tenant_id"]
        logger.info(f"Fetching bookings for tenant_id={effective_tenant_id}, date={booking_date}, skip={skip}, limit={limit}")

        query = db.query(Booking).filter(Booking.tenant_id == effective_tenant_id)
        if booking_date:
            query = query.filter(Booking.booking_date == booking_date)

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
