
from sqlalchemy import func
from app.models.cutoff import Cutoff
from app.models.driver import Driver
from app.models.employee import Employee
from app.models.route_management import RouteManagement, RouteManagementBooking, RouteManagementStatusEnum
from app.models.shift import Shift, ShiftLogTypeEnum
from app.models.tenant import Tenant
from app.models.vehicle import Vehicle
from app.models.vendor import Vendor
from app.models.weekoff_config import WeekoffConfig
from fastapi import APIRouter, Depends, HTTPException, Path, status, Query,Body
from sqlalchemy.orm import Session, joinedload, selectinload
from typing import Optional, List
from datetime import date, datetime, datetime, timedelta, timezone
from app.database.session import get_db
from app.models.booking import Booking
from app.schemas.booking import BookingCreate, BookingUpdate, BookingResponse,  BookingStatusEnum ,UpdateBookingRequest
from app.utils.pagination import paginate_query
from common_utils.auth.permission_checker import PermissionChecker
from common_utils.auth.token_validation import validate_bearer_token
from common_utils import get_current_ist_time
from app.utils import cache_manager
from app.schemas.base import BaseResponse, PaginatedResponse
from app.utils.response_utils import ResponseWrapper, handle_http_error, validate_pagination_params, handle_db_error
from sqlalchemy.exc import SQLAlchemyError
from app.core.logging_config import get_logger

logger = get_logger(__name__)
router = APIRouter(prefix="/bookings", tags=["bookings"])

# Custom dependency for booking update - allows either app-employee.update OR booking.update
async def BookingUpdatePermission(user_data: dict = Depends(validate_bearer_token(use_cache=True))):
    """
    Custom dependency that allows either app-employee.update OR booking.update permission.
    Checks if user has at least one of the two permissions.
    """
    user_permissions = user_data.get("permissions", [])
    
    # Extract permission strings from the permissions list
    permission_strings = set()
    for p in user_permissions:
        if isinstance(p, dict):
            module = p.get("module", "")
            actions = p.get("action", [])
            if module and actions:
                if isinstance(actions, list):
                    for action in actions:
                        permission_strings.add(f"{module}.{action}")
                else:
                    permission_strings.add(f"{module}.{actions}")
        elif isinstance(p, str):
            permission_strings.add(p)
    
    # Check if user has either permission
    has_app_employee_update = "app-employee.update" in permission_strings
    has_booking_update = "booking.update" in permission_strings
    
    if not (has_app_employee_update or has_booking_update):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=ResponseWrapper.error(
                message="Insufficient permissions. Required: app-employee.update or booking.update",
                error_code="INSUFFICIENT_PERMISSIONS",
                details={
                    "required_permissions": ["app-employee.update", "booking.update"],
                    "user_permissions": sorted(permission_strings)
                }
            ),
        )
    
    return user_data

# Helper functions for cached configuration retrieval (using DRY helpers)

def get_shift_time(shift):
    """Extract shift_time from shift (handles both cached and DB objects)"""
    if isinstance(shift, dict):
        time_str = shift.get("shift_time")
        if time_str:
            from datetime import time as dt_time
            h, m, s = map(int, time_str.split(":"))
            return dt_time(h, m, s)
        return None
    if hasattr(shift, "shift_time"):
        shift_time = shift.shift_time
        # If it's already a string (from cache), parse it
        if isinstance(shift_time, str):
            from datetime import time as dt_time
            h, m, s = map(int, shift_time.split(":"))
            return dt_time(h, m, s)
        # If it's a time object (from DB), return as-is
        return shift_time
    return None

def get_shift_log_type(shift):
    """Extract log_type from shift (handles both cached and DB objects)"""
    if isinstance(shift, dict):
        return shift.get("log_type")
    if hasattr(shift, "log_type") and shift.log_type:
        # If it's already a string (from cache), return as-is
        if isinstance(shift.log_type, str):
            return shift.log_type
        # If it's an enum (from DB), get the value
        return shift.log_type.value if hasattr(shift.log_type, 'value') else str(shift.log_type)
    return None

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

        # --- Shift validation (with caching) ---
        shift = cache_manager.get_shift_with_cache(db, tenant_id, booking.shift_id)
        if not shift:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=ResponseWrapper.error("Shift not found for this tenant", "SHIFT_NOT_FOUND"),
            )

        # --- Tenant lookup (with caching) ---
        tenant = cache_manager.get_tenant_with_cache(db, tenant_id)
        if not tenant:
            raise HTTPException(status_code=404, detail="Tenant not found")

        # --- Weekoff & Cutoff configs (with caching) ---
        weekoff_config = cache_manager.get_weekoff_with_cache(db, employee.employee_id)
        cutoff = cache_manager.get_cutoff_with_cache(db, tenant_id)

        # Collect booking data for bulk insert
        bookings_to_create = []
        weekday_map = {0: "monday", 1: "tuesday", 2: "wednesday", 3: "thursday",
                       4: "friday", 5: "saturday", 6: "sunday"}
        booking_validate_future_dates(booking.booking_dates, context="dates")
        unique_dates = sorted(set(booking.booking_dates))
        
        # First pass: Validate all dates and collect booking data
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
            cutoff_interval = None
            
            # Check booking type and apply appropriate validations
            if booking.booking_type == "adhoc":
                # Validate that adhoc booking is enabled for this tenant
                if not cutoff or not cutoff.allow_adhoc_booking:
                    raise HTTPException(
                        status_code=status.HTTP_400_BAD_REQUEST,
                        detail=ResponseWrapper.error(
                            "Ad-hoc booking is not enabled for this tenant",
                            "ADHOC_BOOKING_DISABLED",
                        ),
                    )
                # Use adhoc cutoff for both login and logout shifts
                cutoff_interval = cutoff.adhoc_booking_cutoff
                logger.info(f"Using adhoc booking cutoff: {cutoff_interval}")
                
            elif booking.booking_type == "medical_emergency":
                # Validate that medical emergency booking is enabled for this tenant
                if not cutoff or not cutoff.allow_medical_emergency_booking:
                    raise HTTPException(
                        status_code=status.HTTP_400_BAD_REQUEST,
                        detail=ResponseWrapper.error(
                            "Medical emergency booking is not enabled for this tenant",
                            "MEDICAL_EMERGENCY_BOOKING_DISABLED",
                        ),
                    )
                # Use medical emergency cutoff for both login and logout shifts
                cutoff_interval = cutoff.medical_emergency_booking_cutoff
                logger.info(f"Using medical emergency booking cutoff: {cutoff_interval}")
                
            else:
                # Regular booking - use shift-type specific cutoffs
                if cutoff:
                    shift_log_type = get_shift_log_type(shift)
                    if shift_log_type == "IN":  # Login shift (home → office)
                        cutoff_interval = cutoff.booking_login_cutoff
                    elif shift_log_type == "OUT":  # Logout shift (office → home)  
                        cutoff_interval = cutoff.booking_logout_cutoff
                else:
                    # No cutoff configuration for this tenant - skip cutoff validation
                    cutoff_interval = None
                    logger.info(f"No cutoff configuration found for tenant {tenant_id} - skipping cutoff validation")
            
            if cutoff and shift and cutoff_interval and cutoff_interval.total_seconds() > 0:
                shift_time = get_shift_time(shift)
                shift_datetime = datetime.combine(booking_date, shift_time).replace(tzinfo=timezone(timedelta(hours=5, minutes=30)))
                now = get_current_ist_time()
                time_until_shift = shift_datetime - now
                shift_log_type = get_shift_log_type(shift)
                logger.info(
                    f"Cutoff check: shift_type={shift_log_type}, booking_type={booking.booking_type}, now={now}, shift_datetime={shift_datetime}, "
                    f"time_until_shift={time_until_shift}, cutoff={cutoff_interval}"
                )
                if time_until_shift < cutoff_interval:
                    if booking.booking_type == "adhoc":
                        booking_type_name = "ad-hoc"
                    elif booking.booking_type == "medical_emergency":
                        booking_type_name = "medical emergency"
                    else:
                        shift_log_type = get_shift_log_type(shift)
                        booking_type_name = "login" if shift_log_type == "IN" else "logout"
                    raise HTTPException(
                        status_code=status.HTTP_400_BAD_REQUEST,
                        detail=ResponseWrapper.error(
                            f"Booking cutoff time has passed for this {booking_type_name} shift (cutoff: {cutoff_interval})",
                            "BOOKING_CUTOFF",
                        ),
                    )

            # 3️⃣ Prevent booking if shift time has already passed today
            shift_time = get_shift_time(shift)
            shift_datetime = datetime.combine(booking_date, shift_time).replace(tzinfo=timezone(timedelta(hours=5, minutes=30)))
            now = get_current_ist_time()

            if booking_date == date.today() and now >= shift_datetime:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=ResponseWrapper.error(
                        message=f"Cannot create booking for a shift that has already started or passed (Shift time: {shift_time})",
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
            shift_id = shift.get("shift_id") if isinstance(shift, dict) else shift.shift_id
            logger.info(
                    f"Existing booking check: employee_id={employee.employee_id}, booking_date={booking_date}, shift_id={shift_id}"
                )

            if existing_booking:
                if existing_booking.status == BookingStatusEnum.CANCELLED:
                    # Reject and ask to update the existing cancelled booking
                    raise HTTPException(
                        status_code=status.HTTP_400_BAD_REQUEST,
                        detail=ResponseWrapper.error(
                            message=f"Employee already has a cancelled booking for this shift and date ({booking_date}). Please update the existing booking (ID: {existing_booking.booking_id}) instead of creating a new one.",
                            error_code="CANCELLED_BOOKING_EXISTS",
                        ),
                    )
                else:
                    # Reject if booking has any other active status
                    raise HTTPException(
                        status_code=status.HTTP_400_BAD_REQUEST,
                        detail=ResponseWrapper.error(
                            message=f"Employee already has an active booking for this shift and date ({booking_date})",
                            error_code="ALREADY_BOOKED",
                        ),
                    )

            # 4️⃣ Compute pickup/drop based on shift
            shift_log_type = get_shift_log_type(shift)
            if shift_log_type == "IN":  # home → office
                pickup_lat, pickup_lng = employee.latitude, employee.longitude
                pickup_addr = employee.address
                drop_lat, drop_lng = tenant.latitude, tenant.longitude
                drop_addr = tenant.address
            else:  # OUT: office → home
                pickup_lat, pickup_lng = tenant.latitude, tenant.longitude
                pickup_addr = tenant.address
                drop_lat, drop_lng = employee.latitude, employee.longitude
                drop_addr = employee.address

            # 5️⃣ Collect booking data for bulk insert
            booking_data = {
                'tenant_id': tenant_id,
                'employee_id': employee.employee_id,
                'employee_code': employee.employee_code,
                'team_id': employee.team_id,
                'shift_id': booking.shift_id,
                'booking_date': booking_date,
                'pickup_latitude': pickup_lat,
                'pickup_longitude': pickup_lng,
                'pickup_location': pickup_addr,
                'drop_latitude': drop_lat,
                'drop_longitude': drop_lng,
                'drop_location': drop_addr,
                'status': BookingStatusEnum.REQUEST,
                'booking_type': booking.booking_type,
            }
            bookings_to_create.append(booking_data)

        # Bulk insert all bookings in a single operation
        created_bookings = []
        if bookings_to_create:
            db.bulk_insert_mappings(Booking, bookings_to_create)
            db.commit()
            
            # Query back the created bookings to get IDs and return to user
            created_bookings = (
                db.query(Booking)
                .filter(
                    Booking.employee_id == employee.employee_id,
                    Booking.shift_id == booking.shift_id,
                    Booking.booking_date.in_([bd['booking_date'] for bd in bookings_to_create])
                )
                .all()
            )
            
            logger.info(
                f"Bulk created {len(created_bookings)} bookings for employee_id={employee.employee_id} "
                f"on dates={[b.booking_date for b in created_bookings]}"
            )
        else:
            logger.warning(f"No bookings to create for employee_id={employee.employee_id}")

        # Add shift_time to each created booking
        bookings_with_shift = []
        for booking_item in created_bookings:
            booking_dict = BookingResponse.model_validate(booking_item).dict()
            if shift:
                shift_time = get_shift_time(shift)
                booking_dict["shift_time"] = shift_time
            bookings_with_shift.append(booking_dict)

        return ResponseWrapper.created(
            data=bookings_with_shift,
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

        # --- Build query with eager loading to prevent N+1 queries ---
        query = db.query(Booking).options(
            joinedload(Booking.employee),
            joinedload(Booking.shift)
        ).filter(Booking.tenant_id == effective_tenant_id)
        
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

        # Fetch route data with eager loading for efficiency (single optimized query)
        booking_ids = [b.booking_id for b in items]
        
        # Get route bookings
        route_bookings = db.query(RouteManagementBooking).options(
            joinedload(RouteManagementBooking.route_management)
        ).filter(RouteManagementBooking.booking_id.in_(booking_ids)).all()
        
        route_ids = list(set(rb.route_id for rb in route_bookings))
        route_dict = {rb.booking_id: rb for rb in route_bookings}
        route_obj_dict = {rb.route_management.route_id: rb.route_management for rb in route_bookings if rb.route_management}
        
        # Fetch all related data for routes in batch queries to prevent N+1
        from app.models.vehicle import Vehicle
        from app.models.driver import Driver
        from app.models.vendor import Vendor
        
        # Get vehicles with vehicle types
        vehicles_dict = {}
        if route_obj_dict:
            vehicle_ids = [r.assigned_vehicle_id for r in route_obj_dict.values() if r.assigned_vehicle_id]
            if vehicle_ids:
                vehicles = db.query(Vehicle).options(
                    joinedload(Vehicle.vehicle_type)
                ).filter(Vehicle.vehicle_id.in_(vehicle_ids)).all()
                vehicles_dict = {v.vehicle_id: v for v in vehicles}
        
        # Get drivers
        drivers_dict = {}
        if route_obj_dict:
            driver_ids = [r.assigned_driver_id for r in route_obj_dict.values() if r.assigned_driver_id]
            if driver_ids:
                drivers = db.query(Driver).filter(Driver.driver_id.in_(driver_ids)).all()
                drivers_dict = {d.driver_id: d for d in drivers}
        
        # Get vendors
        vendors_dict = {}
        if route_obj_dict:
            vendor_ids = [r.assigned_vendor_id for r in route_obj_dict.values() if r.assigned_vendor_id]
            if vendor_ids:
                vendors = db.query(Vendor).filter(Vendor.vendor_id.in_(vendor_ids)).all()
                vendors_dict = {v.vendor_id: v for v in vendors}
        
        # Get shifts (using cached version)
        shifts_dict = {}
        if route_obj_dict:
            shift_ids = [r.shift_id for r in route_obj_dict.values() if r.shift_id]
            for shift_id in shift_ids:
                shift_data = cache_manager.get_shift_with_cache(db, tenant_id or effective_tenant_id, shift_id)
                if shift_data:
                    shifts_dict[shift_id] = shift_data

        # Fetch all route bookings for passengers
        # Note: RouteManagementBooking doesn't have a direct 'booking' relationship
        logger.info(f"Fetching route bookings for {len(route_ids)} routes in get_bookings endpoint")
        all_route_bookings = db.query(RouteManagementBooking).filter(
            RouteManagementBooking.route_id.in_(route_ids)
        ).all() if route_ids else []
        
        logger.info(f"Found {len(all_route_bookings)} route bookings")
        
        # Fetch all bookings associated with these route bookings
        route_booking_ids = [rb.booking_id for rb in all_route_bookings]
        logger.info(f"Fetching {len(route_booking_ids)} bookings for route passengers")
        
        passenger_bookings = db.query(Booking).options(
            joinedload(Booking.employee)
        ).filter(Booking.booking_id.in_(route_booking_ids)).all() if route_booking_ids else []
        
        # Create a mapping of booking_id to booking object
        booking_map = {b.booking_id: b for b in passenger_bookings}
        logger.info(f"Created booking map with {len(booking_map)} entries")
        
        # Create a mapping of booking_id to booking object
        booking_map = {b.booking_id: b for b in passenger_bookings}
        logger.info(f"Created booking map with {len(booking_map)} entries")
        
        # Build passengers per route
        route_passengers = {}
        for route_id in route_ids:
            passengers = []
            for rb in all_route_bookings:
                if rb.route_id == route_id:
                    booking_obj = booking_map.get(rb.booking_id)
                    if booking_obj and booking_obj.employee:
                        passengers.append({
                            "employee_name": booking_obj.employee.employee_name if hasattr(booking_obj.employee, 'employee_name') else booking_obj.employee.name if hasattr(booking_obj.employee, 'name') else 'Unknown',
                            "headcount": 1,
                            "position": rb.order_id,
                            "booking_status": booking_obj.status.value if booking_obj.status else 'Unknown'
                        })
                    else:
                        logger.warning(f"Missing booking or employee data for booking_id={rb.booking_id} in route_id={route_id}")
            passengers.sort(key=lambda x: x['position'])
            route_passengers[route_id] = passengers
            logger.info(f"Route {route_id} has {len(passengers)} passengers")

        # Add shift_time and route_details to each booking
        bookings_with_shift = []
        for booking in items:
            booking_dict = BookingResponse.model_validate(booking, from_attributes=True).model_dump()
            if booking.shift:
                booking_dict["shift_time"] = booking.shift.shift_time
            
            # Add route details if booking is routed (using eager-loaded data)
            route_booking = route_dict.get(booking.booking_id)
            if route_booking and route_booking.route_management:
                route = route_booking.route_management
                
                vehicle_details = None
                if route.assigned_vehicle_id and route.assigned_vehicle_id in vehicles_dict:
                    vehicle = vehicles_dict[route.assigned_vehicle_id]
                    vehicle_details = {
                        "vehicle_id": vehicle.vehicle_id,
                        "vehicle_number": vehicle.rc_number,
                        "vehicle_type": vehicle.vehicle_type.name if vehicle.vehicle_type else None,
                        "capacity": vehicle.vehicle_type.seats if vehicle.vehicle_type else None,
                    }

                driver_details = None
                if route.assigned_driver_id and route.assigned_driver_id in drivers_dict:
                    driver = drivers_dict[route.assigned_driver_id]
                    driver_details = {
                        "driver_id": driver.driver_id,
                        "driver_name": driver.name,
                        "driver_phone": driver.phone,
                        "license_number": driver.license_number,
                    }

                vendor_details = None
                if route.assigned_vendor_id and route.assigned_vendor_id in vendors_dict:
                    vendor = vendors_dict[route.assigned_vendor_id]
                    vendor_details = {
                        "vendor_id": vendor.vendor_id,
                        "vendor_name": vendor.name,
                        "vendor_code": vendor.vendor_code,
                    }

                shift_details = None
                if route.shift_id:
                    shift_data = cache_manager.get_shift_with_cache(db, tenant_id, route.shift_id)
                    if shift_data:
                        shift_details = shift_data
                    elif route.shift_id in shifts_dict:
                        shift_details = shifts_dict[route.shift_id]

                route_info = {
                    "route_id": route.route_id,
                    "route_code": route.route_code,
                    "status": route.status.value,
                    "shift_details": shift_details,
                    "vehicle_details": vehicle_details,
                    "driver_details": driver_details,
                    "vendor_details": vendor_details,
                    "escort_required": route.escort_required,
                    "estimated_total_time": route.estimated_total_time,
                    "estimated_total_distance": route.estimated_total_distance,
                    "actual_total_time": route.actual_total_time,
                    "actual_total_distance": route.actual_total_distance,
                }
                booking_dict["route_details"] = route_info
            else:
                booking_dict["route_details"] = None
            
            bookings_with_shift.append(booking_dict)

        return ResponseWrapper.paginated(
            items=bookings_with_shift,
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
            logger.info(f"Applying status filter: {status_filter}")
            query = query.filter(Booking.status == status_filter)

        # Tenant enforcement for non-admin employees
        if user_type != "admin":
            query = query.filter(Booking.tenant_id == tenant_id)
            logger.info(f"Applied tenant filter: {tenant_id}")
        
        # Add eager loading to prevent N+1 queries
        query = query.options(
            joinedload(Booking.employee),
            joinedload(Booking.shift)
        )

        total, items = paginate_query(query, skip, limit)
        logger.info(f"Found {total} total bookings, returning {len(items)} items")

        # Fetch route data with eager loading for efficiency (single optimized query)
        booking_ids = [b.booking_id for b in items]
        logger.info(f"Fetching route data for {len(booking_ids)} bookings")
        
        # Get route bookings
        route_bookings = db.query(RouteManagementBooking).options(
            joinedload(RouteManagementBooking.route_management)
        ).filter(RouteManagementBooking.booking_id.in_(booking_ids)).all()
        
        route_ids = list(set(rb.route_id for rb in route_bookings))
        route_dict = {rb.booking_id: rb for rb in route_bookings}
        route_obj_dict = {rb.route_management.route_id: rb.route_management for rb in route_bookings if rb.route_management}
        
        # Fetch all related data for routes in batch queries to prevent N+1
        from app.models.vehicle import Vehicle
        from app.models.driver import Driver
        from app.models.vendor import Vendor
        
        # Get vehicles with vehicle types
        vehicles_dict = {}
        if route_obj_dict:
            vehicle_ids = [r.assigned_vehicle_id for r in route_obj_dict.values() if r.assigned_vehicle_id]
            if vehicle_ids:
                vehicles = db.query(Vehicle).options(
                    joinedload(Vehicle.vehicle_type)
                ).filter(Vehicle.vehicle_id.in_(vehicle_ids)).all()
                vehicles_dict = {v.vehicle_id: v for v in vehicles}
        
        # Get drivers
        drivers_dict = {}
        if route_obj_dict:
            driver_ids = [r.assigned_driver_id for r in route_obj_dict.values() if r.assigned_driver_id]
            if driver_ids:
                drivers = db.query(Driver).filter(Driver.driver_id.in_(driver_ids)).all()
                drivers_dict = {d.driver_id: d for d in drivers}
        
        # Get vendors
        vendors_dict = {}
        if route_obj_dict:
            vendor_ids = [r.assigned_vendor_id for r in route_obj_dict.values() if r.assigned_vendor_id]
            if vendor_ids:
                vendors = db.query(Vendor).filter(Vendor.vendor_id.in_(vendor_ids)).all()
                vendors_dict = {v.vendor_id: v for v in vendors}
        
        # Get shifts (using cached version)
        shifts_dict = {}
        if route_obj_dict:
            shift_ids = [r.shift_id for r in route_obj_dict.values() if r.shift_id]
            for shift_id in shift_ids:
                shift_data = cache_manager.get_shift_with_cache(db, tenant_id, shift_id)
                if shift_data:
                    shifts_dict[shift_id] = shift_data

        # Fetch all route bookings for passengers
        # Note: RouteManagementBooking doesn't have a direct 'booking' relationship,
        # so we need to fetch bookings separately using booking_ids
        logger.info(f"Fetching route bookings for {len(route_ids)} routes")
        all_route_bookings = db.query(RouteManagementBooking).filter(
            RouteManagementBooking.route_id.in_(route_ids)
        ).all() if route_ids else []
        
        logger.info(f"Found {len(all_route_bookings)} route bookings")
        
        # Fetch all bookings associated with these route bookings
        route_booking_ids = [rb.booking_id for rb in all_route_bookings]
        logger.info(f"Fetching {len(route_booking_ids)} bookings for route passengers")
        
        passenger_bookings = db.query(Booking).options(
            joinedload(Booking.employee)
        ).filter(Booking.booking_id.in_(route_booking_ids)).all() if route_booking_ids else []
        
        # Create a mapping of booking_id to booking object
        booking_map = {b.booking_id: b for b in passenger_bookings}
        logger.info(f"Created booking map with {len(booking_map)} entries")
        
        # Build passengers per route
        route_passengers = {}
        for route_id in route_ids:
            passengers = []
            for rb in all_route_bookings:
                if rb.route_id == route_id:
                    booking_obj = booking_map.get(rb.booking_id)
                    if booking_obj and booking_obj.employee:
                        passengers.append({
                            "employee_name": booking_obj.employee.employee_name if hasattr(booking_obj.employee, 'employee_name') else booking_obj.employee.name if hasattr(booking_obj.employee, 'name') else 'Unknown',
                            "headcount": 1,
                            "position": rb.order_id,
                            "booking_status": booking_obj.status.value if booking_obj.status else 'Unknown'
                        })
                    else:
                        logger.warning(f"Missing booking or employee data for booking_id={rb.booking_id} in route_id={route_id}")
            passengers.sort(key=lambda x: x['position'])
            route_passengers[route_id] = passengers
            logger.info(f"Route {route_id} has {len(passengers)} passengers")

        # Add shift_time and route_details to each booking
        bookings_with_shift = []
        for booking in items:
            booking_dict = BookingResponse.model_validate(booking, from_attributes=True).model_dump()
            if booking.shift:
                booking_dict["shift_time"] = booking.shift.shift_time
            
            # Add route details if booking is routed (using eager-loaded data)
            route_booking = route_dict.get(booking.booking_id)
            if route_booking and route_booking.route_management:
                route = route_booking.route_management
                
                vehicle_details = None
                if route.assigned_vehicle_id and route.assigned_vehicle_id in vehicles_dict:
                    vehicle = vehicles_dict[route.assigned_vehicle_id]
                    vehicle_details = {
                        "vehicle_id": vehicle.vehicle_id,
                        "vehicle_number": vehicle.rc_number,
                        "vehicle_type": vehicle.vehicle_type.name if vehicle.vehicle_type else None,
                        "capacity": vehicle.vehicle_type.seats if vehicle.vehicle_type else None,
                    }

                driver_details = None
                if route.assigned_driver_id and route.assigned_driver_id in drivers_dict:
                    driver = drivers_dict[route.assigned_driver_id]
                    driver_details = {
                        "driver_id": driver.driver_id,
                        "driver_name": driver.name,
                        "driver_phone": driver.phone,
                        "license_number": driver.license_number,
                    }

                vendor_details = None
                if route.assigned_vendor_id and route.assigned_vendor_id in vendors_dict:
                    vendor = vendors_dict[route.assigned_vendor_id]
                    vendor_details = {
                        "vendor_id": vendor.vendor_id,
                        "vendor_name": vendor.name,
                        "vendor_code": vendor.vendor_code,
                    }

                shift_details = None
                if route.shift_id:
                    shift_data = cache_manager.get_shift_with_cache(db, tenant_id, route.shift_id)
                    if shift_data:
                        shift_details = shift_data
                    elif route.shift_id in shifts_dict:
                        shift_details = shifts_dict[route.shift_id]

                route_info = {
                    "route_id": route.route_id,
                    "route_code": route.route_code,
                    "status": route.status.value,
                    "shift_details": shift_details,
                    "vehicle_details": vehicle_details,
                    "driver_details": driver_details,
                    "vendor_details": vendor_details,
                    "escort_required": route.escort_required,
                    "estimated_total_time": route.estimated_total_time,
                    "estimated_total_distance": route.estimated_total_distance,
                    "actual_total_time": route.actual_total_time,
                    "actual_total_distance": route.actual_total_distance,
                }
                booking_dict["route_details"] = route_info
            else:
                booking_dict["route_details"] = None
            
            bookings_with_shift.append(booking_dict)

        return ResponseWrapper.paginated(
            items=bookings_with_shift,
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

        booking_dict = BookingResponse.model_validate(booking, from_attributes=True).model_dump()
        if booking.shift:
            booking_dict["shift_time"] = booking.shift.shift_time

        # Add route details if booking is routed
        route_booking = db.query(RouteManagementBooking).filter(RouteManagementBooking.booking_id == booking.booking_id).first()
        if route_booking:
            route = db.query(RouteManagement).filter(RouteManagement.route_id == route_booking.route_id).first()
            if route:
                # Fetch passengers
                all_route_bookings = db.query(RouteManagementBooking).filter(RouteManagementBooking.route_id == route.route_id).all()
                all_booking_ids = [rb.booking_id for rb in all_route_bookings]
                all_bookings = db.query(Booking).filter(Booking.booking_id.in_(all_booking_ids)).all()
                all_employee_ids = [b.employee_id for b in all_bookings]
                all_employees = db.query(Employee).filter(Employee.employee_id.in_(all_employee_ids)).all()
                booking_pass_dict = {b.booking_id: b for b in all_bookings}
                employee_pass_dict = {e.employee_id: e for e in all_employees}
                passengers = []
                for rb in all_route_bookings:
                    booking_pass = booking_pass_dict.get(rb.booking_id)
                    if booking_pass:
                        employee = employee_pass_dict.get(booking_pass.employee_id)
                        if employee:
                            passengers.append({
                                "employee_name": employee.name,
                                "headcount": 1,
                                "position": rb.order_id,
                                "booking_status": booking_pass.status.value
                            })
                passengers.sort(key=lambda x: x['position'])

                vehicle_details = None
                if route.assigned_vehicle_id:
                    vehicle = db.query(Vehicle).filter(Vehicle.vehicle_id == route.assigned_vehicle_id).first()
                    if vehicle:
                        vehicle_details = {
                            "vehicle_id": vehicle.vehicle_id,
                            "vehicle_number": vehicle.rc_number,
                            "vehicle_type": vehicle.vehicle_type.name if vehicle.vehicle_type else None,
                            "capacity": vehicle.vehicle_type.seats if vehicle.vehicle_type else None,
                        }

                driver_details = None
                if route.assigned_driver_id:
                    driver = db.query(Driver).filter(Driver.driver_id == route.assigned_driver_id).first()
                    if driver:
                        driver_details = {
                            "driver_id": driver.driver_id,
                            "driver_name": driver.name,
                            "driver_phone": driver.phone,
                            "license_number": driver.license_number,
                        }

                vendor_details = None
                if route.assigned_vendor_id:
                    vendor = db.query(Vendor).filter(Vendor.vendor_id == route.assigned_vendor_id).first()
                    if vendor:
                        vendor_details = {
                            "vendor_id": vendor.vendor_id,
                            "vendor_name": vendor.name,
                            "vendor_code": vendor.vendor_code,
                        }

                shift_details = None
                if route.shift_id:
                    shift_route = cache_manager.get_shift_with_cache(db, tenant_id, route.shift_id)
                    if shift_route:
                        shift_details = shift_route

                route_info = {
                    "route_id": route.route_id,
                    "route_code": route.route_code,
                    "status": route.status.value,
                    "shift_details": shift_details,
                    "vehicle_details": vehicle_details,
                    "driver_details": driver_details,
                    "vendor_details": vendor_details,
                    "escort_required": route.escort_required,
                    "estimated_total_time": route.estimated_total_time,
                    "estimated_total_distance": route.estimated_total_distance,
                    "actual_total_time": route.actual_total_time,
                    "actual_total_distance": route.actual_total_distance,
                    "passengers": passengers,
                }
                booking_dict["route_details"] = route_info
            else:
                booking_dict["route_details"] = None
        else:
            booking_dict["route_details"] = None

        return ResponseWrapper.success(
            data=booking_dict,
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

@router.put("/{booking_id}", status_code=status.HTTP_200_OK)
async def update_booking(
    booking_id: int,
    request: UpdateBookingRequest,
    db: Session = Depends(get_db),
    user_data=Depends(BookingUpdatePermission),
):
    """
    Update booking - allows changing shift and re-booking cancelled bookings.
    Only bookings with status 'Request' or 'Cancelled' can be updated.
    - For 'Request' status: allows changing shift.
    - For 'Cancelled' status: allows changing shift and re-booking (changes status to 'Request').
    - Validation: Employee can have only one booking per shift per date.
    
    Permission logic:
    - app-employee.update: Employee can update only their own bookings
    - booking.update: Employee can update any booking in their tenant
    """
    try:
        user_type = user_data.get("user_type")
        tenant_id = user_data.get("tenant_id")
        employee_id = user_data.get("user_id")
        
        # Only employees can use this endpoint
        if user_type != "employee":
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=ResponseWrapper.error(
                    message="Only employees can update bookings through this endpoint",
                    error_code="FORBIDDEN",
                ),
            )

        # Check which permission the user has
        user_permissions = user_data.get("permissions", [])
        has_app_employee_update = any(
            (isinstance(p, dict) and p.get("module") == "app-employee" and "update" in p.get("action", [])) or
            (isinstance(p, str) and p == "app-employee.update")
            for p in user_permissions
        )
        has_booking_update = any(
            (isinstance(p, dict) and p.get("module") == "booking" and "update" in p.get("action", [])) or
            (isinstance(p, str) and p == "booking.update")
            for p in user_permissions
        )

        logger.info(f"[booking.update] tenant={tenant_id}, employee={employee_id}, booking={booking_id}, has_app_employee_update={has_app_employee_update}, has_booking_update={has_booking_update}")

        # Fetch booking with appropriate filter based on permission
        if has_booking_update:
            # Can update any booking in their tenant
            logger.info(f"[booking.update] User has booking.update - querying with filters: booking_id={booking_id}, tenant_id={tenant_id}")
            booking = db.query(Booking).filter(
                Booking.booking_id == booking_id,
                Booking.tenant_id == tenant_id,
            ).first()
            logger.info(f"[booking.update] Query result: {'Found' if booking else 'Not Found'}")
            
            # Additional debug: Check if booking exists at all
            if not booking:
                any_booking = db.query(Booking).filter(Booking.booking_id == booking_id).first()
                if any_booking:
                    logger.warning(f"[booking.update] Booking {booking_id} exists but in different tenant: booking.tenant_id={any_booking.tenant_id}, user.tenant_id={tenant_id}, booking.employee_id={any_booking.employee_id}")
                else:
                    logger.warning(f"[booking.update] Booking {booking_id} does not exist in database at all")
        else:
            # Can only update their own bookings (app-employee.update)
            logger.info(f"[booking.update] User has app-employee.update only - querying with filters: booking_id={booking_id}, employee_id={employee_id}, tenant_id={tenant_id}")
            booking = db.query(Booking).filter(
                Booking.booking_id == booking_id,
                Booking.employee_id == employee_id,
                Booking.tenant_id == tenant_id,
            ).first()
            logger.info(f"[booking.update] Query result: {'Found' if booking else 'Not Found'}")
            
            # Additional debug: Check if booking exists but belongs to different employee
            if not booking:
                any_booking = db.query(Booking).filter(
                    Booking.booking_id == booking_id,
                    Booking.tenant_id == tenant_id
                ).first()
                if any_booking:
                    logger.warning(f"[booking.update] Booking {booking_id} exists in tenant {tenant_id} but belongs to different employee: booking.employee_id={any_booking.employee_id}, user.employee_id={employee_id}")
                else:
                    logger.warning(f"[booking.update] Booking {booking_id} does not exist in tenant {tenant_id}")

        if not booking:
            logger.error(f"[booking.update] FAILED - Booking not found. booking_id={booking_id}, tenant_id={tenant_id}, employee_id={employee_id}, has_booking_update={has_booking_update}")
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=ResponseWrapper.error(
                    message="Booking not found",
                    error_code="BOOKING_NOT_FOUND",
                    details={
                        "booking_id": booking_id,
                        "tenant_id": tenant_id,
                        "employee_id": employee_id,
                        "permission_type": "booking.update" if has_booking_update else "app-employee.update"
                    }
                ),
            )

        logger.info(f"[booking.update] Found booking: booking_id={booking.booking_id}, employee_id={booking.employee_id}, tenant_id={booking.tenant_id}, status={booking.status.value}, booking_date={booking.booking_date}, shift_id={booking.shift_id}")

        if booking.status not in [BookingStatusEnum.REQUEST, BookingStatusEnum.CANCELLED]:
            logger.warning(f"[booking.update] FAILED - Invalid status. Current status: {booking.status.value}, Allowed: [REQUEST, CANCELLED]")
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=ResponseWrapper.error(
                    message="Booking can only be updated if status is Request or Cancelled",
                    error_code="INVALID_BOOKING_STATUS",
                    details={
                        "current_status": booking.status.value,
                        "allowed_statuses": ["REQUEST", "CANCELLED"]
                    }
                ),
            )

        updated = False

        if request.shift_id is not None:
            # Validate shift exists
            logger.info(f"[booking.update] Validating shift_id={request.shift_id}")
            shift = cache_manager.get_shift_with_cache(db, tenant_id, request.shift_id)
            if not shift:
                logger.error(f"[booking.update] FAILED - Shift not found: shift_id={request.shift_id}")
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail=ResponseWrapper.error(
                        message="Shift not found",
                        error_code="SHIFT_NOT_FOUND",
                        details={"shift_id": request.shift_id}
                    ),
                )
            # Get shift details
            shift_time = get_shift_time(shift)
            shift_log_type = get_shift_log_type(shift)
            logger.info(f"[booking.update] Shift found: shift_id={shift.get('shift_id') if isinstance(shift, dict) else shift.shift_id}, shift_time={shift_time}, log_type={shift_log_type}")
            # Cutoff validation for the new shift
            cutoff = cache_manager.get_cutoff_with_cache(db, tenant_id)
            cutoff_interval = None
            if cutoff:
                if booking.booking_type == "adhoc":
                    if not cutoff.allow_adhoc_booking:
                        raise HTTPException(
                            status_code=status.HTTP_400_BAD_REQUEST,
                            detail=ResponseWrapper.error(
                                "Ad-hoc booking is not enabled for this tenant",
                                "ADHOC_BOOKING_DISABLED",
                            ),
                        )
                    cutoff_interval = cutoff.adhoc_booking_cutoff
                elif booking.booking_type == "medical_emergency":
                    if not cutoff.allow_medical_emergency_booking:
                        raise HTTPException(
                            status_code=status.HTTP_400_BAD_REQUEST,
                            detail=ResponseWrapper.error(
                                "Medical emergency booking is not enabled for this tenant",
                                "MEDICAL_EMERGENCY_BOOKING_DISABLED",
                            ),
                        )
                    cutoff_interval = cutoff.medical_emergency_booking_cutoff
                else:
                    if shift.log_type == "IN":
                        cutoff_interval = cutoff.booking_login_cutoff
                    elif shift.log_type == "OUT":
                        cutoff_interval = cutoff.booking_logout_cutoff

            shift_datetime = datetime.combine(booking.booking_date, shift.shift_time).replace(tzinfo=timezone(timedelta(hours=5, minutes=30)))
            now = get_current_ist_time()
            time_until_shift = shift_datetime - now

            if cutoff and shift and cutoff_interval and cutoff_interval.total_seconds() > 0:
                if time_until_shift < cutoff_interval:
                    booking_type_name = "ad-hoc" if booking.booking_type == "adhoc" else ("medical emergency" if booking.booking_type == "medical_emergency" else ("login" if shift.log_type == "IN" else "logout"))
                    raise HTTPException(
                        status_code=status.HTTP_400_BAD_REQUEST,
                        detail=ResponseWrapper.error(
                            f"Booking cutoff time has passed for this {booking_type_name} shift (cutoff: {cutoff_interval})",
                            "BOOKING_CUTOFF",
                        ),
                    )

            # Prevent updating to a shift that has already passed today
            if booking.booking_date == date.today() and now >= shift_datetime:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=ResponseWrapper.error(
                        message=f"Cannot update to a shift that has already started or passed (Shift time: {shift.shift_time})",
                        error_code="PAST_SHIFT_TIME",
                    ),
                )

            # Validate no duplicate booking for same date and shift
            # Use the actual employee_id from the booking for validation
            existing_booking = db.query(Booking).filter(
                Booking.employee_id == booking.employee_id,
                Booking.tenant_id == tenant_id,
                Booking.booking_date == booking.booking_date,
                Booking.shift_id == request.shift_id,
                Booking.booking_id != booking_id,
            ).first()
            if existing_booking:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=ResponseWrapper.error(
                        message="Employee already has a booking for this shift on the same date",
                        error_code="DUPLICATE_BOOKING",
                    ),
                )
            booking.shift_id = request.shift_id
            updated = True

        if booking.status == BookingStatusEnum.CANCELLED:
            booking.status = BookingStatusEnum.REQUEST
            updated = True

        if updated:
            booking.updated_at = func.now()
            db.commit()
            db.refresh(booking)

        return ResponseWrapper.success(
            data={
                "booking_id": booking.booking_id,
                "status": booking.status.value,
                "shift_id": booking.shift_id,
                "updated_at": booking.updated_at.isoformat() if booking.updated_at else None,
            },
            message="Booking updated successfully",
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.exception("Error updating booking")
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

        # --- Cancellation cutoff validation ---
        cutoff = cache_manager.get_cutoff_with_cache(db, tenant_id)
        cancel_cutoff_interval = None
        if booking.shift and booking.shift.log_type == "IN":
            cancel_cutoff_interval = cutoff.cancel_login_cutoff if cutoff else None
        elif booking.shift and booking.shift.log_type == "OUT":
            cancel_cutoff_interval = cutoff.cancel_logout_cutoff if cutoff else None
        
        if cancel_cutoff_interval and cancel_cutoff_interval.total_seconds() > 0:
            shift_datetime = datetime.combine(booking.booking_date, booking.shift.shift_time).replace(tzinfo=timezone(timedelta(hours=5, minutes=30)))
            now = get_current_ist_time()
            time_until_shift = shift_datetime - now
            
            if time_until_shift < cancel_cutoff_interval:
                shift_type_name = "login" if booking.shift.log_type == "IN" else "logout"
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=ResponseWrapper.error(
                        f"Cancellation cutoff time has passed for this {shift_type_name} shift (cutoff: {cancel_cutoff_interval})",
                        "CANCEL_CUTOFF",
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

        booking_dict = BookingResponse.model_validate(booking, from_attributes=True).model_dump()
        if booking.shift:
            booking_dict["shift_time"] = booking.shift.shift_time

        return ResponseWrapper.success(
            data=booking_dict,
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

