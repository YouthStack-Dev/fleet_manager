
from sqlalchemy import func
from app.models.cutoff import Cutoff
from app.models.employee import Employee
from app.models.route_management import RouteManagement, RouteManagementBooking, RouteManagementStatusEnum
from app.models.shift import Shift, ShiftLogTypeEnum
from app.models.tenant import Tenant
from app.models.weekoff_config import WeekoffConfig
from fastapi import APIRouter, Depends, HTTPException, Path, status, Query,Body
from sqlalchemy.orm import Session
from typing import Optional, List
from datetime import date, datetime, datetime, timedelta
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
    yesterday = today - timedelta(days=1)

    for d in dates:
        # Allow today, block only <= yesterday
        if d <= yesterday:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=ResponseWrapper.error(
                    message=f"{context} must contain only today or future dates (invalid: {d})",
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


        # employee_id = user_data.get("user_id")
        logger.info(f"Attempting to create bookings for employee_id={booking.employee_id} ")
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

            # 3️⃣ Prevent booking if shift time has already passed today
            shift_datetime = datetime.combine(booking_date, shift.shift_time)
            now = datetime.now()

            if booking_date == date.today() and now >= shift_datetime:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=ResponseWrapper.error(
                        message=f"Cannot create booking for a shift that has already started or passed (Shift time: {shift.shift_time})",
                        error_code="PAST_SHIFT_TIME",
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
                if existing_booking.status != BookingStatusEnum.CANCELLED:  # Only allow if previous booking was cancelled
                    raise HTTPException(
                        status_code=status.HTTP_400_BAD_REQUEST,
                        detail=ResponseWrapper.error(
                            message=f"Employee already has an active booking for this shift and date ({booking_date})",
                            error_code="ALREADY_BOOKED",
                        ),
                    )
                else:
                    logger.info(f"Previous booking was cancelled, proceeding to create a new one for booking_date={booking_date}")

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
                status="Request",
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
    booking_date: date = Query(..., description="Filter by booking date"),
    tenant_id: Optional[str] = None,
    status_filter: Optional[BookingStatusEnum] = Query(None, description="Filter by booking status"),
    skip: int = Query(0, ge=0),
    limit: int = Query(10, ge=1, le=100),
):
    try:
        # --- Determine effective tenant ---
        user_type = user_data.get("user_type")
        if user_type == "admin":
            tenant_id = tenant_id
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
            logger.info(f"Applying date filter: {booking_date}")
            query = query.filter(Booking.booking_date == booking_date)
        if status_filter:
            query = query.filter(Booking.status == status_filter)

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
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=ResponseWrapper.error(
                message="Unexpected error occurred while fetching bookings",
                error_code="UNEXPECTED_ERROR",
            ),
        )



# ============================================================
# 2️⃣ Get bookings for a specific employee (by ID or code)
# ============================================================
@router.get("/employee", response_model=PaginatedResponse[BookingResponse])
def get_bookings_by_employee(
    employee_id: Optional[int] = Query(None, description="Employee ID"),
    employee_code: Optional[str] = Query(None, description="Employee code"),
    booking_date: Optional[date] = Query(None, description="Optional booking date filter"),
    status_filter: Optional[BookingStatusEnum] = Query(None, description="Filter by booking status"),
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
            logger.info(f"Fetching employee bookings for employee_id={employee_id}, employee_code={employee_code}, date={booking_date}")
            query = query.filter(Booking.booking_date == booking_date)
        if status_filter:        
            query = query.filter(Booking.status == status_filter)

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


# ============================================================
# 4️⃣ cancel booking by booking_id
# ============================================================
@router.patch("/cancel/{booking_id}", response_model=BaseResponse[BookingResponse])
def cancel_booking(
    booking_id: int = Path(..., description="Booking ID to cancel"),
    db: Session = Depends(get_db),
    user_data=Depends(PermissionChecker(["booking.update"], check_tenant=True)),
):
    """
    Employee can cancel a booking only if:
    - The booking belongs to them.
    - The booking is in REQUEST state (not yet scheduled into a route).
    - The booking is for today or a future date.
    Otherwise, cancellation requires admin intervention.
    """
    try:
        user_type = user_data.get("user_type")
        tenant_id = user_data.get("tenant_id")
        employee_id = user_data.get("user_id")

        logger.info(f"Attempting to cancel booking_id={booking_id} by employee_id={employee_id}, user_type={user_type}")

        # Only employees can cancel
        if user_type != "employee":
            logger.warning(f"Unauthorized cancellation attempt by employee_id={employee_id}, user_type={user_type}")
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=ResponseWrapper.error(
                    message="Only employees can cancel their bookings",
                    error_code="FORBIDDEN",
                ),
            )

        # --- Fetch booking ---
        booking = db.query(Booking).filter(Booking.booking_id == booking_id).first()
        if not booking:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=ResponseWrapper.error("Booking not found", "BOOKING_NOT_FOUND"),
            )

        # # --- Validate employee ownership ---
        # if booking.employee_id != employee_id:
        #     raise HTTPException(
        #         status_code=status.HTTP_403_FORBIDDEN,
        #         detail=ResponseWrapper.error(
        #             message="You can only cancel your own bookings",
        #             error_code="UNAUTHORIZED_BOOKING_ACCESS",
        #         ),
        #     )

        # --- Validate tenant ---
        if booking.tenant_id != tenant_id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=ResponseWrapper.error(
                    message="Tenant mismatch. You cannot cancel this booking.",
                    error_code="TENANT_MISMATCH",
                ),
            )

        # --- Prevent past cancellations ---
        if booking.booking_date < date.today():
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=ResponseWrapper.error(
                    message="Cannot cancel past bookings",
                    error_code="PAST_BOOKING",
                ),
            )

        # --- Validate allowed statuses ---
        if booking.status not in [BookingStatusEnum.REQUEST]:
            # Booking already routed or completed
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=ResponseWrapper.error(
                    message="Your booking is already scheduled. Please contact your transport admin to cancel it.",
                    error_code="BOOKING_ALREADY_SCHEDULED",
                ),
            )

        # --- Perform cancellation ---
        booking.status = BookingStatusEnum.CANCELLED
        booking.reason = "Cancelled by employee before routing"
        booking.updated_at = func.now()

        db.commit()
        db.refresh(booking)

        logger.info(
            f"Booking {booking.booking_id} cancelled successfully by employee {employee_id}"
        )

        return ResponseWrapper.success(
            data=BookingResponse.model_validate(booking, from_attributes=True),
            message="Booking successfully cancelled",
        )

    except HTTPException as e:
        db.rollback()
        logger.warning(f"HTTPException during booking cancellation: {e.detail}")
        raise handle_http_error(e)

    except SQLAlchemyError as e:
        db.rollback()
        logger.exception("Database error while cancelling booking")
        raise handle_db_error(e)

    except Exception as e:
        db.rollback()
        logger.exception("Unexpected error while cancelling booking")
        raise HTTPException(
            status_code=500,
            detail=ResponseWrapper.error(
                message="Internal Server Error", error_code="INTERNAL_ERROR"
            ),
        )

@router.get("/tenant/{tenant_id}/shifts/bookings", status_code=status.HTTP_200_OK)
async def get_bookings_grouped_by_shift(
    tenant_id: str = Path(..., description="Tenant ID (required for admin users)"),
    booking_date: date = Query(..., description="Filter by booking date (YYYY-MM-DD)"),
    log_type: Optional[ShiftLogTypeEnum] = Query(None, description="Optional shift type filter (e.g., IN, OUT)"),
    shift_id: Optional[int] = Query(None, description="Optional shift ID filter"),
    db: Session = Depends(get_db),
    user_data=Depends(PermissionChecker(["booking.read"], check_tenant=True))
):
    """
    Fetch bookings grouped by shift with clean, accurate stats:
      - total_bookings
      - routed_bookings
      - unrouted_bookings
      - vendor_assigned
      - driver_assigned
      - route_count per status (distinct routes only)
    """
    try:
        user_type = user_data.get("user_type")

        # ---- Tenant context ----
        if user_type == "admin":
            if not tenant_id:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=ResponseWrapper.error("Admin must provide tenant_id", "TENANT_ID_REQUIRED"),
                )
            effective_tenant_id = tenant_id
        elif user_type == "employee":
            effective_tenant_id = user_data.get("tenant_id")
        else:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=ResponseWrapper.error(
                    message="You are not authorized to view bookings",
                    error_code="FORBIDDEN"
                ),
            )

        logger.info(f"[get_bookings_grouped_by_shift] Tenant={effective_tenant_id}, Date={booking_date}")

        # ---- Base bookings ----
        booking_query = (
            db.query(Booking, Shift.shift_code, Shift.shift_time, Shift.log_type)
            .join(Shift, Shift.shift_id == Booking.shift_id)
            .filter(
                Booking.tenant_id == effective_tenant_id,
                func.date(Booking.booking_date) == booking_date,
            )
        )

        if log_type:
            booking_query = booking_query.filter(Shift.log_type == log_type)
        if shift_id:
            booking_query = booking_query.filter(Shift.shift_id == shift_id)

        bookings = booking_query.order_by(Shift.shift_time).all()
        if not bookings:
            return ResponseWrapper.success(
                data={"date": booking_date, "shifts": []},
                message="No bookings found for this date",
            )

        # ---- Fetch route data ----
        route_data = (
            db.query(
                RouteManagement.shift_id,
                RouteManagement.status,
                RouteManagement.assigned_vendor_id,
                RouteManagement.assigned_driver_id,
                RouteManagement.route_id,
                RouteManagementBooking.booking_id,
            )
            .join(RouteManagementBooking, RouteManagementBooking.route_id == RouteManagement.route_id)
            .join(Booking, Booking.booking_id == RouteManagementBooking.booking_id)
            .filter(
                RouteManagement.tenant_id == effective_tenant_id,
                Booking.tenant_id == effective_tenant_id,
                func.date(Booking.booking_date) == booking_date,
            )
        )

        if shift_id:
            route_data = route_data.filter(RouteManagement.shift_id == shift_id)
        if log_type:
            route_data = route_data.join(Shift, Shift.shift_id == RouteManagement.shift_id).filter(
                Shift.log_type == log_type
            )

        route_data = route_data.all()

        # ---- Process route stats ----
        route_stats_by_shift = {}
        routed_booking_ids = set()

        for r in route_data:
            sid = r.shift_id
            if not sid:
                continue
            routed_booking_ids.add(r.booking_id)

            if sid not in route_stats_by_shift:
                route_stats_by_shift[sid] = {
                    "route_ids": set(),
                    "status": {
                        RouteManagementStatusEnum.PLANNED.value: 0,
                        RouteManagementStatusEnum.VENDOR_ASSIGNED.value: 0,
                        RouteManagementStatusEnum.DRIVER_ASSIGNED.value: 0,
                        RouteManagementStatusEnum.ONGOING.value: 0,
                        RouteManagementStatusEnum.COMPLETED.value: 0,
                        RouteManagementStatusEnum.CANCELLED.value: 0,
                    },
                    "vendor_assigned": 0,
                    "driver_assigned": 0,
                }

            # Unique routes only
            route_stats_by_shift[sid]["route_ids"].add(r.route_id)

            # Count route by status (per unique route)
            route_stats_by_shift[sid]["status"][r.status.value] += 1

            # Track vendor/driver assignment (per unique route)
            if r.assigned_vendor_id:
                route_stats_by_shift[sid]["vendor_assigned"] += 1
            if r.assigned_driver_id:
                route_stats_by_shift[sid]["driver_assigned"] += 1

        # ---- Group bookings per shift ----
        grouped = {}
        for booking_obj, shift_code, shift_time, shift_log_type in bookings:
            sid = booking_obj.shift_id
            if sid not in grouped:
                stats = route_stats_by_shift.get(
                    sid,
                    {
                        "route_ids": set(),
                        "status": {
                            RouteManagementStatusEnum.PLANNED.value: 0,
                            RouteManagementStatusEnum.VENDOR_ASSIGNED.value: 0,
                            RouteManagementStatusEnum.DRIVER_ASSIGNED.value: 0,
                            RouteManagementStatusEnum.ONGOING.value: 0,
                            RouteManagementStatusEnum.COMPLETED.value: 0,
                            RouteManagementStatusEnum.CANCELLED.value: 0,
                        },
                        "vendor_assigned": 0,
                        "driver_assigned": 0,
                    },
                )

                grouped[sid] = {
                    "shift_id": sid,
                    "shift_code": shift_code,
                    "shift_time": shift_time,
                    "log_type": shift_log_type,
                    "bookings": [],
                    "stats": {
                        "total_bookings": 0,
                        "routed_bookings": 0,
                        "unrouted_bookings": 0,
                        "vendor_assigned": stats["vendor_assigned"],
                        "driver_assigned": stats["driver_assigned"],
                        "route_count": len(stats["route_ids"]),  # ✅ distinct routes only
                        "route_status_breakdown": stats["status"],
                    },
                }

            grouped[sid]["bookings"].append(
                BookingResponse.model_validate(booking_obj, from_attributes=True)
            )

            # ---- Count booking-level stats ----
            grouped[sid]["stats"]["total_bookings"] += 1
            if booking_obj.booking_id in routed_booking_ids:
                grouped[sid]["stats"]["routed_bookings"] += 1
            else:
                grouped[sid]["stats"]["unrouted_bookings"] += 1

        result = sorted(grouped.values(), key=lambda x: x["shift_time"])

        return ResponseWrapper.success(
            data={"date": booking_date, "shifts": result},
            message="Bookings grouped by shift fetched successfully",
        )

    except SQLAlchemyError as e:
        logger.exception("Database error occurred while fetching grouped bookings")
        raise handle_db_error(e)
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("Unexpected error occurred while fetching grouped bookings")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=ResponseWrapper.error(
                message="Unexpected error occurred while fetching bookings",
                error_code="UNEXPECTED_ERROR",
                details={"error": str(e)},
            ),
        )
