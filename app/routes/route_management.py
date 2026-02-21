import random as random
from fastapi import APIRouter, Depends, HTTPException, Path, Query, Request, status, BackgroundTasks
from sqlalchemy import func
from sqlalchemy.orm import Session
from typing import List, Optional, Dict
from pydantic import BaseModel, Field
from datetime import date , datetime, time
from enum import Enum

from app.database.session import get_db
from app.models.booking import Booking, BookingStatusEnum
from app.models.cutoff import Cutoff
from app.models.driver import Driver
from app.models.escort import Escort
from app.models.route_management import RouteManagement, RouteManagementBooking, RouteManagementStatusEnum
from app.models.shift import Shift  # Add shift model import
from app.models.tenant import Tenant  # Add tenant model import
from app.models.tenant_config import TenantConfig
from app.models.vehicle import Vehicle
from app.models.vendor import Vendor
from app.schemas.route import RouteWithEstimations, RouteEstimations, RouteManagementBookingResponse  # Add import for response schema
from app.schemas.shift import ShiftResponse
from app.services.clustering_algorithm import group_rides
from common_utils.auth.permission_checker import PermissionChecker
from app.core.logging_config import get_logger, setup_logging
from app.utils.response_utils import ResponseWrapper, handle_db_error
from app.utils.audit_helper import log_audit
from app.utils.cache_manager import cached, cache_manager, get_tenant_with_cache, get_shift_with_cache, get_cutoff_with_cache, get_tenant_config_with_cache
from app.utils.task_manager import run_background_task
from common_utils import datetime_to_minutes, get_current_ist_time

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session
from sqlalchemy.exc import SQLAlchemyError
from typing import Any

from app.utils.otp_utils import get_required_otp_count

# Configure logging immediately at module level
setup_logging(
    log_level="DEBUG",
    force_configure=True,
    use_colors=True
)

# Create module logger with explicit name
logger = get_logger("route_management")

# Test logger immediately
logger.info("🚀 Route Management module initialized")

# Helper functions for shift data extraction (from cached format)
def safe_get_enum_value(obj, attr_name):
    """
    Safely get enum value from either SQLAlchemy object or dict.
    Handles both cached (dict with string values) and fresh DB objects (with Enum attributes).
    
    Args:
        obj: Either a dict or SQLAlchemy model instance
        attr_name: The attribute name (e.g., 'log_type', 'status')
    
    Returns:
        String value of the enum or None
    """
    if obj is None:
        return None
    
    if isinstance(obj, dict):
        # Already a dict (from cache), value is already a string
        return obj.get(attr_name)
    
    # It's an object, get the attribute
    attr = getattr(obj, attr_name, None)
    if attr is None:
        return None
    
    # Check if it has .value (is an Enum) or is already a string
    if hasattr(attr, 'value'):
        return attr.value
    
    # Already a string or other primitive
    return str(attr) if attr else None


def get_shift_time(shift):
    """Extract shift_time from shift dict (cached format) or Shift object"""
    if isinstance(shift, dict):
        time_str = shift.get("shift_time")
        if time_str:
            from datetime import time as dt_time
            h, m, s = map(int, time_str.split(":"))
            return dt_time(h, m, s)
        return None
    return shift.shift_time if hasattr(shift, "shift_time") else None

def get_shift_log_type(shift):
    """Extract log_type from shift dict (cached format) or Shift object"""
    return safe_get_enum_value(shift, "log_type")

logger.debug("📝 Debug logging is active")

router = APIRouter(
    prefix="/routes",
    tags=["route-management"]
)


# Background task for sending notifications
async def send_assignment_notifications_background(
    booking_data: List[Dict],
    route_code: str,
    driver_name: str,
    driver_phone: str,
    vehicle_rc_number: str,
    route_id: int,
):
    """
    Send notifications (Email, SMS, Push) to employees in the background.
    This prevents blocking the main API response.
    """
    from app.core.email_service import EmailService
    from app.services.unified_notification_service import UnifiedNotificationService
    from app.services.session_cache import SessionCache
    from app.services.sms_service import SMSService
    from app.database.session import SessionLocal
    
    db = SessionLocal()
    
    try:
        email_service = EmailService()
        push_service = UnifiedNotificationService(db, SessionCache())
        sms_service = SMSService()
        
        logger.info(f"[BACKGROUND] Starting notification dispatch for {len(booking_data)} bookings")
        
        for data in booking_data:
            employee_email = data.get("employee_email")
            employee_phone = data.get("employee_phone")
            employee_name = data.get("employee_name")
            employee_id = data.get("employee_id")
            booking_id = data.get("booking_id")
            shift_type = data.get("shift_type")
            shift_time = data.get("shift_time")
            booking_date = data.get("booking_date")
            estimated_pickup = data.get("estimated_pickup")
            boarding_otp = data.get("boarding_otp")
            deboarding_otp = data.get("deboarding_otp")
            escort_otp = data.get("escort_otp")
            
            otp_details = []
            if boarding_otp:
                otp_details.append(f"Boarding OTP: {boarding_otp}")
            if deboarding_otp:
                otp_details.append(f"Deboarding OTP: {deboarding_otp}")
            if escort_otp:
                otp_details.append(f"Escort OTP: {escort_otp}")
            
            otp_message = "\n".join(otp_details) if otp_details else "No OTP required"
            
            subject = f"Driver Assigned - Route {route_code}"
            message_body = f"""
Hello {employee_name},

Your driver has been assigned for your {shift_type} shift on {booking_date}.

Route Details:
- Route Code: {route_code}
- Shift Time: {shift_time}
- Driver: {driver_name} ({driver_phone})
- Vehicle: {vehicle_rc_number}

Your OTP Codes:
{otp_message}

Please share these OTPs with the driver at the designated times.

Estimated Pickup: {estimated_pickup or 'TBD'}

Thank you,
Fleet Management Team
            """.strip()
            
            # 1. Send Email
            try:
                if employee_email:
                    email_html = f"""
                    <html>
                        <body style="font-family: Arial, sans-serif;">
                            <h2 style="color: #2c5aa0;">🚗 Driver Assigned</h2>
                            <p>Hello <strong>{employee_name}</strong>,</p>
                            <p>Your driver has been assigned for your <strong>{shift_type}</strong> shift on <strong>{booking_date}</strong>.</p>
                            
                            <div style="background-color: #f0f8ff; padding: 15px; border-left: 4px solid #2c5aa0; margin: 20px 0;">
                                <h3 style="margin-top: 0;">Route Details</h3>
                                <ul style="list-style: none; padding-left: 0;">
                                    <li>📍 <strong>Route Code:</strong> {route_code}</li>
                                    <li>🕐 <strong>Shift Time:</strong> {shift_time}</li>
                                    <li>👤 <strong>Driver:</strong> {driver_name} ({driver_phone})</li>
                                    <li>🚙 <strong>Vehicle:</strong> {vehicle_rc_number}</li>
                                    <li>⏰ <strong>Estimated Pickup:</strong> {estimated_pickup or 'TBD'}</li>
                                </ul>
                            </div>
                            
                            <div style="background-color: #fff3cd; padding: 15px; border-left: 4px solid #ffc107; margin: 20px 0;">
                                <h3 style="margin-top: 0;">🔐 Your OTP Codes</h3>
                                <p style="font-size: 16px; line-height: 1.8;">
                                    {'<br>'.join(otp_details) if otp_details else 'No OTP required'}
                                </p>
                                <p style="color: #856404; font-size: 14px;">
                                    <em>Please share these OTPs with the driver at the designated times.</em>
                                </p>
                            </div>
                            
                            <p>Thank you,<br><strong>Fleet Management Team</strong></p>
                        </body>
                    </html>
                    """
                    
                    email_sent = await email_service.send_email(
                        to_emails=[employee_email],
                        subject=subject,
                        html_content=email_html,
                        text_content=message_body
                    )
                    
                    if email_sent:
                        logger.info(f"[BACKGROUND] Email sent to {employee_email} for booking {booking_id}")
                    else:
                        logger.warning(f"[BACKGROUND] Failed to send email to {employee_email}")
                else:
                    logger.warning(f"[BACKGROUND] No email found for employee {employee_id}")
            except Exception as e:
                logger.error(f"[BACKGROUND] Error sending email: {e}")
            
            # 2. Send SMS
            try:
                if employee_phone:
                    sms_message = f"Driver Assigned! Route: {route_code}, Driver: {driver_name} ({driver_phone}), Vehicle: {vehicle_rc_number}. "
                    
                    if otp_details:
                        sms_message += f"OTPs: {' | '.join(otp_details)}. "
                    
                    sms_message += f"Pickup: {estimated_pickup or 'TBD'}. Check email for details."
                    
                    sms_sent = sms_service.send_sms(
                        to_phone=employee_phone,
                        message=sms_message
                    )
                    
                    if sms_sent:
                        logger.info(f"[BACKGROUND] SMS sent to {employee_phone} for booking {booking_id}")
                    else:
                        logger.warning(f"[BACKGROUND] Failed to send SMS to {employee_phone}")
                else:
                    logger.warning(f"[BACKGROUND] No phone found for employee {employee_id}")
            except Exception as e:
                logger.error(f"[BACKGROUND] Error sending SMS: {e}")
            
            # 3. Send Push Notification
            try:
                push_result = push_service.send_to_user(
                    user_type="employee",
                    user_id=employee_id,
                    title=subject,
                    body=f"Driver {driver_name} assigned. Vehicle: {vehicle_rc_number}. Check your OTPs.",
                    data={
                        "type": "driver_assignment",
                        "route_id": str(route_id),
                        "route_code": route_code,
                        "booking_id": str(booking_id),
                        "driver_name": driver_name,
                        "driver_phone": driver_phone,
                        "vehicle_number": vehicle_rc_number,
                        "estimated_pickup": estimated_pickup or "",
                        "boarding_otp": str(boarding_otp) if boarding_otp else "",
                        "deboarding_otp": str(deboarding_otp) if deboarding_otp else "",
                        "escort_otp": str(escort_otp) if escort_otp else "",
                    },
                    priority="high"
                )
                
                if push_result.get("success"):
                    logger.info(f"[BACKGROUND] Push notification sent to employee {employee_id}")
                else:
                    logger.warning(f"[BACKGROUND] Push notification failed: {push_result.get('error', 'Unknown')}")
            except Exception as e:
                logger.error(f"[BACKGROUND] Error sending push notification: {e}")
        
        logger.info(f"[BACKGROUND] Notification dispatch completed for route {route_id}")
        
    except Exception as e:
        logger.error(f"[BACKGROUND] Error in notification background task: {e}")
    finally:
        db.close()


class RequestItem(BaseModel):
    booking_ids: List[int]  # Changed from bookings to booking_ids

class CreateRoutesRequest(BaseModel):
    groups: List[RequestItem]

class MergeRoutesRequest(BaseModel):
    route_ids: List[int]  # Already int, no change needed

class SplitRouteRequest(BaseModel):
    groups: List[RequestItem]  # Changed from List[str] to List[int] for booking IDs

class RouteOperationEnum(str, Enum):
    ADD = "add"
    REMOVE = "remove"

class UpdateRouteRequest(BaseModel):
    operation: RouteOperationEnum  # Add operation field
    booking_ids: List[int]  # Changed from bookings to booking_ids for consistency

class RouteUpdate(BaseModel):
    booking_id: int
    new_order_id: int
    estimated_pickup_time: str
    estimated_drop_time: str

# New unified models for route operations
class CreateRouteFromBookingsRequest(BaseModel):
    booking_ids: List[int] = Field(..., description="List of booking IDs from any routes to create new route")
    optimize: bool = Field(True, description="If true, optimize route; if false, use current order")

class RouteBookingUpdate(BaseModel):
    booking_id: int
    order_id: int
    estimated_pick_up_time: Optional[str] = Field(None, description="Time in HH:MM:SS format (required if optimize=false)")
    estimated_drop_time: Optional[str] = Field(None, description="Time in HH:MM:SS format (required if optimize=false)")

class UpdateRouteBookingsRequest(BaseModel):
    bookings: List[RouteBookingUpdate]
    optimize: bool = Field(True, description="If true, auto-optimize route; if false, use provided times")

def get_bookings_by_ids(booking_ids: List[int], db: Session) -> List[Dict]:
    """
    Retrieve bookings by their IDs and convert to dictionary format.
    Adds detailed logs for traceability.
    """
    logger.info(f"[get_bookings_by_ids] Raw booking_ids input: {booking_ids}")

    if not booking_ids:
        logger.warning("[get_bookings_by_ids] Empty booking_ids list received.")
        return []

    # ---- Flatten nested IDs if needed ----
    if isinstance(booking_ids[0], (tuple, list)):
        flat_booking_ids = []
        for item in booking_ids:
            if isinstance(item, (tuple, list)):
                flat_booking_ids.extend(
                    [int(x) for x in item if isinstance(x, (int, str)) and str(x).isdigit()]
                )
            else:
                flat_booking_ids.append(int(item))
        booking_ids = flat_booking_ids
        logger.debug(f"[get_bookings_by_ids] Flattened booking_ids: {booking_ids}")

    # ---- Normalize all IDs to integers ----
    booking_ids = [
        int(bid) for bid in booking_ids if isinstance(bid, (int, str)) and str(bid).isdigit()
    ]

    if not booking_ids:
        logger.warning("[get_bookings_by_ids] No valid integer booking_ids after cleanup.")
        raise HTTPException(status_code=400, detail="No valid booking IDs provided.")

    logger.info(f"[get_bookings_by_ids] Final booking_ids to query: {booking_ids}")

    # ---- Query bookings ----
    bookings = db.query(Booking).filter(Booking.booking_id.in_(booking_ids)).all()
    logger.info(f"[get_bookings_by_ids] Retrieved {len(bookings)} bookings from DB")

    # ---- Log detailed booking info ----
    for b in bookings:
        logger.debug(
            f"[get_bookings_by_ids] Booking fetched → "
            f"id={b.booking_id}, tenant={b.tenant_id}, shift={b.shift_id}, date={b.booking_date}, "
            f"employee={b.employee_code or b.employee_id}, status={b.status.name if b.status else None}"
        )

    # ---- Convert to dictionaries ----
    bookings_dicts = [
        {
            "booking_id": booking.booking_id,
            "tenant_id": booking.tenant_id,
            "employee_id": booking.employee_id,
            "employee_code": booking.employee_code,
            "shift_id": booking.shift_id,
            "team_id": booking.team_id,
            "booking_date": booking.booking_date,
            "pickup_latitude": booking.pickup_latitude,
            "pickup_longitude": booking.pickup_longitude,
            "pickup_location": booking.pickup_location,
            "drop_latitude": booking.drop_latitude,
            "drop_longitude": booking.drop_longitude,
            "drop_location": booking.drop_location,
            "status": safe_get_enum_value(booking, "status"),
            "reason": booking.reason,
            "is_active": getattr(booking, 'is_active', True),
            "created_at": booking.created_at,
            "updated_at": booking.updated_at
        }
        for booking in bookings
    ]

    if not bookings_dicts:
        logger.warning(f"[get_bookings_by_ids] No matching bookings found for IDs {booking_ids}")

    return bookings_dicts

def get_booking_by_id(booking_id: int, db: Session) -> Optional[Dict]:
    """
    Retrieve a single booking by its ID and convert to dictionary format.
    """
    booking = db.query(Booking).filter(Booking.booking_id == booking_id).first()
    if not booking:
        logger.warning(f"[get_booking_by_id] No booking found with ID {booking_id}")
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND,
            detail=ResponseWrapper.error(
                message="Booking not found.",
                error_code="BOOKING_NOT_FOUND",
            )
        )

    logger.debug(
        f"[get_booking_by_id] Booking fetched → "
        f"id={booking.booking_id}, tenant={booking.tenant_id}, shift={booking.shift_id}, date={booking.booking_date}, "
        f"employee={booking.employee_code or booking.employee_id}, status={booking.status.name if booking.status else None}"
    )

    booking_dict = {
        "booking_id": booking.booking_id,
        "tenant_id": booking.tenant_id,
        "employee_id": booking.employee_id,
        "employee_code": booking.employee_code,
        "shift_id": booking.shift_id,
        "team_id": booking.team_id,
        "booking_date": booking.booking_date,
        "pickup_latitude": booking.pickup_latitude,
        "pickup_longitude": booking.pickup_longitude,
        "pickup_location": booking.pickup_location,
        "drop_latitude": booking.drop_latitude,
        "drop_longitude": booking.drop_longitude,
        "drop_location": booking.drop_location,
        "status": safe_get_enum_value(booking, "status"),
        "reason": booking.reason,
        "is_active": getattr(booking, 'is_active', True),
        "created_at": booking.created_at,
        "updated_at": booking.updated_at
    }

    return booking_dict



@router.post("/" , status_code=status.HTTP_200_OK)
async def create_routes(
    booking_date: date = Query(..., description="Date for the bookings (YYYY-MM-DD)"),
    shift_id: int = Query(..., description="Shift ID to filter bookings"),
    radius: float = Query(1.0, description="Radius in km for clustering"),
    group_size: int = Query(2, description="Number of route clusters to generate"),
    strict_grouping: bool = Query(False, description="Whether to enforce strict grouping by group size or not"),
    tenant_id: Optional[str] = Query(None, description="Tenant ID for multi-tenant setups"),
    db: Session = Depends(get_db),
    user_data=Depends(PermissionChecker(["route.create"], check_tenant=True)),
):

    """
    Generate route clusters (suggestions) for a given shift and date.
    Only includes bookings NOT already assigned to any route.

    Parameters:
    - booking_date: Date for the bookings (YYYY-MM-DD)
    - shift_id: Shift ID to filter bookings
    - radius: Radius in km for clustering
    - group_size: Number of route clusters to generate
    - strict_grouping: Whether to enforce strict grouping by group size or not
    - tenant_id: Tenant ID for multi-tenant setups

    Returns:
    - A list of route clusters, each containing unrouted bookings
    - A dictionary containing the total number of unrouted bookings and total number of route clusters generated
    """
    try:
        logger.info(
            f"Clustering request for date={booking_date}, shift={shift_id}, user={user_data.get('user_id', 'unknown')}"
        )

        user_type = user_data.get("user_type")
        token_tenant_id = user_data.get("tenant_id")

        # ---- Tenant Resolution ----
        if user_type == "employee":
            tenant_id = token_tenant_id
        elif user_type == "admin" and not tenant_id:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=ResponseWrapper.error(
                    message="tenant_id is required for admin users",
                    error_code="TENANT_ID_REQUIRED",
                ),
            )
        else:
            tenant_id = tenant_id or token_tenant_id

        if not tenant_id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=ResponseWrapper.error(
                    message="Tenant context not available",
                    error_code="TENANT_ID_REQUIRED",
                ),
            )

        # ---- Validate Shift ----
        shift = (
            db.query(Shift)
            .filter(Shift.shift_id == shift_id, Shift.tenant_id == tenant_id)
            .first()
        )

        if not shift:
            logger.warning(f"Shift not found: {shift_id}")
            raise HTTPException(
                status_code=404,
                detail=ResponseWrapper.error(
                    message=f"Shift {shift_id} not found or doesn't belong to this tenant",
                    error_code="SHIFT_NOT_FOUND_OR_UNAUTHORIZED"
                ),
            )

        # ---- Determine Coordinate Columns ----
        shift_type = shift.log_type or "Unknown"
        lat_col = "pickup_latitude" if shift_type == "IN" else "drop_latitude"
        lon_col = "pickup_longitude" if shift_type == "IN" else "drop_longitude"
        
        # ---- Fetch Already Routed Booking IDs ----
        routed_booking_ids = (
            db.query(RouteManagementBooking.booking_id)
            .join(RouteManagement, RouteManagement.route_id == RouteManagementBooking.route_id)
            .filter(RouteManagement.tenant_id == tenant_id)
            .distinct()
            .all()
        )
        routed_booking_ids = [b.booking_id for b in routed_booking_ids]

        # ---- Fetch Only Unrouted Bookings ----
        bookings_query = db.query(Booking).filter(
            Booking.booking_date == booking_date,
            Booking.shift_id == shift_id,
            Booking.tenant_id == tenant_id,
            Booking.status == BookingStatusEnum.REQUEST
        )
        if routed_booking_ids:
            bookings_query = bookings_query.filter(~Booking.booking_id.in_(routed_booking_ids))

        bookings = bookings_query.all()

        if not bookings:
            logger.info(f"No unrouted bookings found for tenant={tenant_id}, shift={shift_id} on {booking_date}")
            return ResponseWrapper.success(
                data={"clusters": [], "total_bookings": 0, "total_clusters": 0},
                message=f"No unrouted bookings found for shift {shift_id} on {booking_date}"
            )

        # ---- Prepare Rides for Clustering ----
        rides = []
        for booking in bookings:
            ride = {
                "lat": getattr(booking, lat_col),
                "lon": getattr(booking, lon_col),
            }
            ride.update(booking.__dict__)
            rides.append(ride)

        valid_rides = [r for r in rides if r["lat"] is not None and r["lon"] is not None]

        if not valid_rides:
            logger.warning(f"No valid coordinates found for {len(bookings)} unrouted bookings")
            return ResponseWrapper.success(
                data={"clusters": [], "total_bookings": len(bookings), "total_clusters": 0},
                message="No bookings with valid coordinates found for clustering"
            )

        # ---- Generate Clusters ----
        clusters = group_rides(valid_rides, radius, group_size, strict_grouping)

        cluster_data = []
        for idx, cluster in enumerate(clusters, start=1):
            for booking in cluster:
                booking.pop("lat", None)
                booking.pop("lon", None)
            cluster_data.append({"cluster_id": idx, "bookings": cluster})

        logger.info(f"Generated {len(cluster_data)} clusters from {len(bookings)} unrouted bookings")

        # ---- Generate optimal route for each cluster ----
        from app.services.optimal_roiute_generation import generate_optimal_route, generate_drop_route

        for cluster in cluster_data:
            if shift_type == "IN":
                optimized_route = generate_optimal_route(
                    deadline_minutes=540,
                    shift_time=shift.shift_time,
                    group=cluster["bookings"],
                    drop_lat=cluster["bookings"][-1]["drop_latitude"],
                    drop_lng=cluster["bookings"][-1]["drop_longitude"],
                    drop_address=cluster["bookings"][-1]["drop_location"]
                )
            else:
                optimized_route = generate_drop_route(
                    group=cluster["bookings"],
                    start_time_minutes=datetime_to_minutes(shift.shift_time),
                    office_lat=cluster["bookings"][0]["pickup_latitude"],
                    office_lng=cluster["bookings"][0]["pickup_longitude"],
                    office_address=cluster["bookings"][0]["pickup_location"]
                )

            # Save the optimized route to the database
            if optimized_route:
                try:
                    route = RouteManagement(
                        tenant_id=tenant_id,
                        shift_id=shift_id,
                        route_code=f"Route-{cluster['cluster_id']}",
                        estimated_total_time=optimized_route[0]["estimated_time"].split()[0],
                        estimated_total_distance=optimized_route[0]["estimated_distance"].split()[0],
                        buffer_time=float(optimized_route[0]["buffer_time"].split()[0]),
                        status="PLANNED",
                    )
                    db.add(route)
                    db.flush()  # Get the route_id

                    # Check if route requires escort for safety
                    from app.utils.otp_utils import update_route_escort_requirement
                    update_route_escort_requirement(db, route.route_id, tenant_id)

                    # Escort requirement flag is set; manual assignment will be done later if needed

                    for idx, booking in enumerate(optimized_route[0]["pickup_order"]):
                        otp_code = random.randint(1000, 9999)
                        # Convert datetime.time to string for SQLite
                        est_pickup = booking["estimated_pickup_time_formatted"]
                        if isinstance(est_pickup, time):
                            est_pickup = est_pickup.strftime("%H:%M:%S")
                        
                        route_booking = RouteManagementBooking(
                            route_id=route.route_id,
                            booking_id=booking["booking_id"],
                            order_id=idx + 1,
                            estimated_pick_up_time=est_pickup,
                            estimated_distance=booking["estimated_distance_km"],
                        )
                        db.add(route_booking)

                        # Update booking status to SCHEDULED (only if still in REQUEST)
                        db.query(Booking).filter(
                            Booking.booking_id == booking["booking_id"],
                            Booking.status == BookingStatusEnum.REQUEST
                        ).update(
                            {
                                Booking.status: BookingStatusEnum.SCHEDULED,
                                Booking.updated_at: func.now(),
                            },
                            synchronize_session=False
                        )

                    db.commit()
                except SQLAlchemyError as e:
                    db.rollback()
                    logger.error(f"Failed to save route to database: {e}")
                    continue

                cluster["optimized_route"] = optimized_route

        # ---- Final Response ----
        shift_response = ShiftResponse.model_validate(shift, from_attributes=True)
        return ResponseWrapper.success(
            data={
                "shift": shift_response,
                "clusters": cluster_data,
                "total_bookings": len(bookings),
                "total_clusters": len(clusters),
            },
            message="Successfully generated route suggestions for unrouted bookings"
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error generating route suggestions: {e}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail=ResponseWrapper.error(
                message="Error generating route suggestions",
                error_code="ROUTE_SUGGESTION_ERROR",
                details={"error": str(e)},
            ),
        )

@router.get("/", status_code=status.HTTP_200_OK)
# @cached(ttl_seconds=180, key_prefix="routes")  # Cache for 3 minutes
async def get_all_routes(
    tenant_id: Optional[str] = Query(None, description="Tenant ID"),
    shift_id: Optional[int] = Query(None, description="Filter by shift ID"),
    booking_date: Optional[date] = Query(None, description="Filter by booking date"),
    status: Optional[RouteManagementStatusEnum] = Query(None, description="Filter by route status (e.g. PLANNED,VENDOR_ASSIGNED,DRIVER_ASSIGNED)"),
    db: Session = Depends(get_db),
    user_data=Depends(PermissionChecker(["route.read"], check_tenant=True)),
):
    """
    Get all active routes with their details, optionally filtered by shift and booking date.
    """

    try:
        user_type = user_data.get("user_type")
        token_tenant_id = user_data.get("tenant_id")

        logger.info(
            f"[get_all_routes] user={user_data.get('user_id')} "
            f"user_type={user_type}, query_tenant={tenant_id}, token_tenant={token_tenant_id}"
        )

        # ---------- Tenant Resolution ----------
        if user_type == "employee":
            # Employees always locked to their tenant
            tenant_id = token_tenant_id

        elif user_type == "admin":
            if token_tenant_id:
                # Normal admin with tenant in token
                tenant_id = token_tenant_id
            else:
                # SuperAdmin must provide tenant_id explicitly
                if not tenant_id:
                    raise HTTPException(
                        status_code=status.HTTP_400_BAD_REQUEST,
                        detail=ResponseWrapper.error(
                            message="tenant_id is required for admin users",
                            error_code="TENANT_ID_REQUIRED",
                        ),
                    )
                # tenant_id from query param stays

        else:
            # fallback
            tenant_id = token_tenant_id

        # final safety check
        if not tenant_id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=ResponseWrapper.error(
                    message="Tenant context not available",
                    error_code="TENANT_ID_REQUIRED",
                ),
            )
        # ---------- Vendor-Specific Access Control ----------
        vendor_id = user_data.get("vendor_id")
        if user_type == "vendor":
            if not vendor_id:
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail=ResponseWrapper.error(
                        message="Vendor ID missing in token",
                        error_code="VENDOR_ID_MISSING",
                    ),
                )

            # Vendor can only see their own routes
            logger.info(f"[get_all_routes] Restricting to vendor_id={vendor_id}")


        logger.info(f"[get_all_routes] resolved tenant: {tenant_id}")

        # ---------- Validate Tenant ----------
        tenant = get_tenant_with_cache(db, tenant_id)
        if not tenant:
            raise HTTPException(
                status_code=404,
                detail=ResponseWrapper.error(
                    message=f"Tenant {tenant_id} not found",
                    error_code="TENANT_NOT_FOUND",
                ),
            )
        tenant_details = {
            "tenant_id": tenant.tenant_id,
            "name": tenant.name,
            "address": tenant.address,
            "latitude": tenant.latitude,
            "longitude": tenant.longitude,
        }
        logger.info(f"Fetching all routes for tenant: {tenant_id}, shift_id: {shift_id}, booking_date: {booking_date}, user: {user_data.get('user_id', 'unknown')}")
        


        # --- Query routes ---
        routes_q = db.query(RouteManagement).filter(RouteManagement.tenant_id == tenant_id)

        if user_type == "vendor":
            logger.info(f"[get_all_routes] Applying vendor filter: {vendor_id}")
            routes_q = routes_q.filter(RouteManagement.assigned_vendor_id == vendor_id)

        # Apply status filter if provided
        if status:
            logger.info(f"[get_all_routes] Applying status filter: {status}")
            routes_q = routes_q.filter(RouteManagement.status == status)

        if shift_id or booking_date:
            routes_q = (
                routes_q
                .join(RouteManagementBooking, RouteManagement.route_id == RouteManagementBooking.route_id)
                .join(Booking, RouteManagementBooking.booking_id == Booking.booking_id)
            )
            if shift_id:
                routes_q = routes_q.filter(Booking.shift_id == shift_id)
            if booking_date:
                routes_q = routes_q.filter(Booking.booking_date == booking_date)

        routes = routes_q.distinct().all()

        if not routes:
            return ResponseWrapper.success(
                {"shifts": [], "total_shifts": 0, "total_routes": 0},
                "No routes found"
            )

        # --- DATA INTEGRITY CHECK: Validate all shifts exist before processing ---
        logger.info(f"[get_all_routes] Validating data integrity for {len(routes)} routes...")
        unique_shift_ids = {r.shift_id for r in routes}
        existing_shifts = db.query(Shift.shift_id).filter(
            Shift.shift_id.in_(unique_shift_ids),
            Shift.tenant_id == tenant_id
        ).all()
        existing_shift_ids = {s.shift_id for s in existing_shifts}
        missing_shift_ids = unique_shift_ids - existing_shift_ids
        
        if missing_shift_ids:
            # Data integrity violation - routes reference non-existent shifts
            routes_with_missing_shifts = [
                f"route_id={r.route_id}(shift_id={r.shift_id})" 
                for r in routes if r.shift_id in missing_shift_ids
            ]
            error_msg = (
                f"Data integrity error: Found {len(routes_with_missing_shifts)} route(s) "
                f"referencing non-existent shift(s) {sorted(missing_shift_ids)}. "
                f"This indicates database corruption or incomplete data migration. "
                f"Affected routes: {', '.join(routes_with_missing_shifts[:5])}"
                f"{' and more...' if len(routes_with_missing_shifts) > 5 else ''}"
            )
            logger.error(f"❌ [DATA INTEGRITY ERROR] {error_msg}")
            logger.error(
                f"   [ROOT CAUSE] Shifts {missing_shift_ids} do not exist in 'shifts' table "
                f"for tenant_id={tenant_id} but are referenced by routes in 'route_management' table."
            )
            logger.error(
                f"   [SOLUTION REQUIRED] Run data cleanup: "
                f"1) Check if shifts were deleted, 2) Re-create missing shifts, "
                f"3) Or delete orphaned routes. See docs/ROUTES_ERROR_DEBUG.md"
            )
            
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=ResponseWrapper.error(
                    message="Data integrity error: Routes reference non-existent shifts",
                    error_code="DATA_INTEGRITY_VIOLATION",
                    details={
                        "missing_shift_ids": sorted(missing_shift_ids),
                        "affected_routes_count": len(routes_with_missing_shifts),
                        "affected_routes_sample": routes_with_missing_shifts[:5],
                        "solution": "Contact administrator to fix database integrity. See logs for details.",
                        "documentation": "docs/ROUTES_ERROR_DEBUG.md"
                    }
                )
            )
        
        logger.info(f"✅ [get_all_routes] Data integrity check passed - all shifts exist")

        # --- Collect IDs ---
        driver_ids = {r.assigned_driver_id for r in routes if r.assigned_driver_id}
        vehicle_ids = {r.assigned_vehicle_id for r in routes if r.assigned_vehicle_id}
        vendor_ids = {r.assigned_vendor_id for r in routes if r.assigned_vendor_id}
        escort_ids = {r.assigned_escort_id for r in routes if r.assigned_escort_id}

        # --- Bulk Load related data ---
        drivers = (
            db.query(Driver.driver_id, Driver.name, Driver.phone)
            .filter(Driver.driver_id.in_(driver_ids | escort_ids))  # Include escorts
            .all() if (driver_ids | escort_ids) else []
        )
        escorts = (
            db.query(Escort.escort_id, Escort.name, Escort.phone)
            .filter(Escort.escort_id.in_(escort_ids))
            .all() if escort_ids else []
        )
        escort_map = {e.escort_id: {"id": e.escort_id, "name": e.name, "phone": e.phone} for e in escorts}
        vehicles = (
            db.query(Vehicle.vehicle_id, Vehicle.rc_number)
            .filter(Vehicle.vehicle_id.in_(vehicle_ids))
            .all() if vehicle_ids else []
        )
        vendors = (
            db.query(Vendor.vendor_id, Vendor.name)
            .filter(Vendor.vendor_id.in_(vendor_ids))
            .all() if vendor_ids else []
        )

        driver_map = {d.driver_id: {"id": d.driver_id, "name": d.name, "phone": d.phone} for d in drivers}
        vehicle_map = {v.vehicle_id: {"id": v.vehicle_id, "rc_number": v.rc_number} for v in vehicles}
        vendor_map = {v.vendor_id: {"id": v.vendor_id, "name": v.name} for v in vendors}

        shifts = {}

        for route in routes:
            rbs = db.query(RouteManagementBooking).filter(
                RouteManagementBooking.route_id == route.route_id
            ).order_by(RouteManagementBooking.order_id).all()

            booking_ids = [rb.booking_id for rb in rbs]
            bookings = get_bookings_by_ids(booking_ids, db) if booking_ids else []

            stops = []
            for rb in rbs:
                b = next((x for x in bookings if x["booking_id"] == rb.booking_id), None)
                if not b: continue

                stops.append({
                    **b,
                    "order_id": rb.order_id,
                    "estimated_pick_up_time": rb.estimated_pick_up_time,
                    "estimated_drop_time": rb.estimated_drop_time,
                    "estimated_distance": rb.estimated_distance,
                    "actual_pick_up_time": rb.actual_pick_up_time,
                    "actual_drop_time": rb.actual_drop_time,
                    "actual_distance": rb.actual_distance,
                })

            shift_id_key = route.shift_id
            if shift_id_key not in shifts:
                # Get shift from cache/DB - should ALWAYS succeed due to integrity check above
                s = get_shift_with_cache(db, tenant_id, shift_id_key)
                if s:
                    # Safe extraction: handle both dict (from cache) and object (from DB)
                    if isinstance(s, dict):
                        # Already a dict from cache
                        shifts[shift_id_key] = {
                            "shift_id": s.get("shift_id"),
                            "log_type": s.get("log_type"),
                            "shift_time": s.get("shift_time"),
                            "routes": []
                        }
                    else:
                        # SQLAlchemy object from DB
                        shifts[shift_id_key] = {
                            "shift_id": s.shift_id,
                            "log_type": safe_get_enum_value(s, "log_type"),
                            "shift_time": s.shift_time.strftime("%H:%M:%S") if s.shift_time else None,
                            "routes": []
                        }
                else:
                    # This should NEVER happen due to integrity check, but fail explicitly if it does
                    logger.critical(
                        f"❌ [CRITICAL ERROR] Shift {shift_id_key} passed integrity check but "
                        f"get_shift_with_cache returned None! This indicates a race condition or "
                        f"concurrent deletion. tenant_id={tenant_id}, shift_id={shift_id_key}"
                    )
                    raise HTTPException(
                        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                        detail=ResponseWrapper.error(
                            message=f"Critical: Shift {shift_id_key} disappeared during processing",
                            error_code="SHIFT_RACE_CONDITION",
                            details={
                                "shift_id": shift_id_key,
                                "tenant_id": tenant_id,
                                "cause": "Shift existed during validation but not during retrieval",
                                "solution": "Retry the request. If persists, check for concurrent deletions."
                            }
                        )
                    )

            shifts[shift_id_key]["routes"].append({
                "tenant": tenant_details,
                "route_id": route.route_id,
                "route_code": route.route_code,
                "status": safe_get_enum_value(route, "status"),
                "escort_required": route.escort_required,
                "driver": driver_map.get(route.assigned_driver_id),
                "vehicle": vehicle_map.get(route.assigned_vehicle_id),
                "vendor": vendor_map.get(route.assigned_vendor_id),
                "escort": escort_map.get(route.assigned_escort_id),  # Escort info from escort_map
                "stops": stops,
                "summary": {
                    "total_distance_km": route.actual_total_distance or route.estimated_total_distance or 0,
                    "total_time_minutes": route.actual_total_time or route.estimated_total_time or 0,
                },
            })

        shifts_list = list(shifts.values())

        return ResponseWrapper.success(
            {
                "shifts": shifts_list,
                "total_shifts": len(shifts_list),
                "total_routes": sum(len(s["routes"]) for s in shifts_list)
            },
            "Routes fetched successfully"
        )

    except HTTPException:
        raise
    except Exception as e:
        # Comprehensive error logging with diagnostic context
        logger.error("="*80)
        logger.error(f"❌ [ROUTES ENDPOINT FAILURE] Unexpected exception occurred")
        logger.error("="*80)
        logger.error(f"Error Type: {type(e).__name__}")
        logger.error(f"Error Message: {str(e)}")
        logger.error(f"Request Context:")
        logger.error(f"  - tenant_id: {tenant_id}")
        logger.error(f"  - shift_id: {shift_id}")
        logger.error(f"  - booking_date: {booking_date}")
        logger.error(f"  - status_filter: {status}")
        logger.error(f"  - user_type: {user_data.get('user_type')}")
        logger.error(f"  - user_id: {user_data.get('user_id')}")
        logger.error(f"Stack Trace:", exc_info=True)
        logger.error("="*80)
        
        # Provide diagnostic hints based on error type
        if "shift" in str(e).lower():
            logger.error("[DIAGNOSTIC] Error involves 'shift' - check shift table integrity")
        if "booking" in str(e).lower():
            logger.error("[DIAGNOSTIC] Error involves 'booking' - check booking relationships")
        if "foreign key" in str(e).lower():
            logger.error("[DIAGNOSTIC] Foreign key violation - check referential integrity")
        
        logger.error("[SOLUTION] See docs/ROUTES_ERROR_DEBUG.md for troubleshooting steps")
        logger.error("="*80)
        
        return handle_db_error(e)

@router.get("/unrouted", status_code=status.HTTP_200_OK)
# @cached(ttl_seconds=120, key_prefix="unrouted")  # Cache for 2 minutes
async def get_unrouted_bookings(
    tenant_id: Optional[str] = Query(None, description="Tenant ID"),
    shift_id: int = Query(..., description="Filter by shift ID"),
    booking_date: date = Query(..., description="Filter by booking date (YYYY-MM-DD)"),
    db: Session = Depends(get_db),
    user_data=Depends(PermissionChecker(["route.read"], check_tenant=True)),
):
    """
    Get all bookings for a specific shift and date that are NOT assigned to any route.
    """
    try:
        user_type = user_data.get("user_type")
        token_tenant_id = user_data.get("tenant_id")

        # ---- Tenant Resolution ----
        if user_type == "admin" and not tenant_id:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=ResponseWrapper.error(
                    message="tenant_id is required for admin users",
                    error_code="TENANT_ID_REQUIRED",
                ),
            )
        elif user_type != "admin":
            tenant_id = token_tenant_id

        if not tenant_id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=ResponseWrapper.error(
                    message="Tenant context not available",
                    error_code="TENANT_ID_REQUIRED",
                ),
            )

        logger.info(f"[unrouted_bookings] Effective tenant resolved: {tenant_id}")

        # ---- Validate tenant exists (use cache) ----
        tenant = get_tenant_with_cache(db, tenant_id)
        if not tenant:
            raise HTTPException(
                status_code=404,
                detail=ResponseWrapper.error(
                    message=f"Tenant {tenant_id} not found",
                    error_code="TENANT_NOT_FOUND",
                ),
            )

        logger.info(
            f"Fetching unrouted bookings for tenant {tenant_id}, shift_id: {shift_id}, booking_date: {booking_date}"
        )

        # ---- Fetch all bookings with REQUEST status ----
        unrouted_bookings = (
            db.query(Booking)
            .filter(
                Booking.tenant_id == tenant_id,
                Booking.shift_id == shift_id,
                Booking.booking_date == booking_date,
                Booking.status == BookingStatusEnum.REQUEST
            )
            .all()
        )

        logger.info(f"[unrouted_bookings] Found {len(unrouted_bookings)} bookings with REQUEST status")

        if not unrouted_bookings:
            logger.info(f"No unrouted bookings found for tenant {tenant_id}, shift {shift_id} on {booking_date}")
            return ResponseWrapper.success(
                data={"bookings": [], "total_unrouted": 0},
                message=f"No unrouted bookings found for tenant {tenant_id}, shift {shift_id}, date {booking_date}",
            )

        bookings_data = get_bookings_by_ids([b.booking_id for b in unrouted_bookings], db)

        logger.info(f"Found {len(bookings_data)} unrouted bookings for tenant {tenant_id}")

        return ResponseWrapper.success(
            data={
                "bookings": bookings_data,
                "total_unrouted": len(bookings_data)
            },
            message=f"Successfully retrieved {len(bookings_data)} unrouted bookings for shift {shift_id} on {booking_date}"
        )

    except HTTPException:
        raise
    except Exception as e:
        return handle_db_error(e)

@router.put("/assign-vendor", status_code=status.HTTP_200_OK)
async def assign_vendor_to_route(
    request: Request,
    route_id: int = Query(..., description="Route ID"),
    vendor_id: int = Query(..., description="Vendor ID to assign"),
    tenant_id: Optional[str] = Query(None, description="Tenant ID"),
    db: Session = Depends(get_db),
    user_data=Depends(PermissionChecker(["route_vendor_assignment.update", "route_vendor_assignment.create", "route_vendor_assignment.delete", "route_vendor_assignment.read"], check_tenant=True))
):
    """
    Assign a vendor to a specific route.
    Ensures both the route and vendor belong to the same tenant.
    """
    try:

        user_id = user_data.get("user_id")
        user_type = user_data.get("user_type")
        token_tenant_id = user_data.get("tenant_id")
        
        # Resolve tenant_id
        if user_type == "employee":
            tenant_id = token_tenant_id
        elif user_type == "admin":
            # Use token tenant if no explicit tenant_id provided
            if not tenant_id:
                tenant_id = token_tenant_id
            # Super admin must provide tenant_id if token has none
            if not tenant_id:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=ResponseWrapper.error(
                        message="tenant_id is required for admin users",
                        error_code="TENANT_ID_REQUIRED",
                    ),
                )
        else:
            tenant_id = token_tenant_id

        if not tenant_id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=ResponseWrapper.error(
                    message="Tenant context not available",
                    error_code="TENANT_ID_REQUIRED",
                ),
            )
        logger.info(f"[assign_vendor_to_route] User={user_id} | Tenant={tenant_id} | Route={route_id} | Vendor={vendor_id}")

        # ---- Validate route ----
        route = (
            db.query(RouteManagement)
            .filter(RouteManagement.route_id == route_id, RouteManagement.tenant_id == tenant_id)
            .first()
        )
        if not route:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=ResponseWrapper.error(
                    message="Route not found for this tenant",
                    error_code="ROUTE_NOT_FOUND",
                    details={"route_id": route_id, "tenant_id": tenant_id},
                ),
            )

        # ---- Validate vendor belongs to the same tenant ----
        vendor = (
            db.query(Vendor)
            .filter(Vendor.vendor_id == vendor_id, Vendor.tenant_id == tenant_id)
            .first()
        )
        if not vendor:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=ResponseWrapper.error(
                    message="Vendor not found under this tenant",
                    error_code="VENDOR_NOT_FOUND_OR_MISMATCH",
                    details={"vendor_id": vendor_id, "tenant_id": tenant_id},
                ),
            )

        # ---- Assign vendor ----
        route.assigned_vendor_id = vendor_id

        if route.status == RouteManagementStatusEnum.PLANNED:
            route.status = RouteManagementStatusEnum.VENDOR_ASSIGNED

        db.commit()
        db.refresh(route)

        # 🔍 Audit Log: Vendor Assignment
        try:
            log_audit(
                db=db,
                tenant_id=tenant_id,
                module="route_management",
                action="UPDATE",
                user_data=user_data,
                description=f"Assigned vendor '{vendor.name}' (ID: {vendor_id}) to route '{route.route_code}' (ID: {route_id})",
                new_values={
                    "route_id": route_id,
                    "route_code": route.route_code,
                    "assigned_vendor_id": vendor_id,
                    "vendor_name": vendor.name,
                    "status": safe_get_enum_value(route, "status")
                },
                request=request
            )
        except Exception as audit_error:
            logger.error(f"Failed to create audit log for vendor assignment: {str(audit_error)}")

        logger.info(
            f"[assign_vendor_to_route] Vendor={vendor_id} assigned successfully to Route={route_id} (Tenant={tenant_id})"
        )

        return ResponseWrapper.success(
            data={
                "route_id": route_id,
                "assigned_vendor_id": vendor_id,
                "status": route.status,
            },
            message="Vendor assigned successfully",
        )

    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        logger.exception("[assign_vendor_to_route] Unexpected error")
        return handle_db_error(e)

@router.put("/assign-vehicle", status_code=status.HTTP_200_OK)
async def assign_vehicle_to_route(
    request: Request,
    background_tasks: BackgroundTasks,
    route_id: int = Query(..., description="Route ID"),
    vehicle_id: int = Query(..., description="Vehicle ID to assign"),
    db: Session = Depends(get_db),
    user_data=Depends(PermissionChecker(["route_vehicle_assignment.update", "route_vehicle_assignment.create", "route_vehicle_assignment.delete", "route_vehicle_assignment.read"], check_tenant=True)),
):
    """
    Assign a vehicle (and implicitly driver) to a route.

    Validation:
      - Vendor must be assigned to route before assigning a vehicle.
      - Route and Vehicle must belong to the same tenant.
      - Vehicle.vendor_id must match Route.assigned_vendor_id.
      - Vehicle must have a mapped driver.
      - Driver.vendor_id must match Route.assigned_vendor_id.
    """
    try:
        tenant_id = user_data.get("tenant_id")
        user_id = user_data.get("user_id")

        logger.info(
            f"[assign_vehicle_to_route] User={user_id} | Tenant={tenant_id} | Route={route_id} | Vehicle={vehicle_id}"
        )

        # ---- Validate Route ----
        route = (
            db.query(RouteManagement)
            .filter(RouteManagement.route_id == route_id, RouteManagement.tenant_id == tenant_id)
            .with_for_update()
            .first()
        )
        if not route:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=ResponseWrapper.error(
                    message="Route not found for this tenant",
                    error_code="ROUTE_NOT_FOUND",
                ),
            )

        # ✅ Enforce vendor assignment first
        if not route.assigned_vendor_id:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=ResponseWrapper.error(
                    message="Assign a vendor to the route before assigning a vehicle/driver",
                    error_code="VENDOR_NOT_ASSIGNED",
                    details={"route_id": route_id},
                ),
            )
        # ---- Vendor-level access validation ----
        user_vendor_id = user_data.get("vendor_id")  # Comes from token if vendor persona
        if user_vendor_id:
            # Ensure vendor trying to assign belongs to the same route
            if route.assigned_vendor_id != int(user_vendor_id):
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail=ResponseWrapper.error(
                        message="You can only assign vehicles to routes owned by your vendor",
                        error_code="VENDOR_ROUTE_MISMATCH",
                        details={
                            "user_vendor_id": user_vendor_id,
                            "route_vendor_id": route.assigned_vendor_id,
                        },
                    ),
                )

        # ---- Validate Vehicle ----
        vehicle = (
            db.query(Vehicle)
            .join(Vendor, Vendor.vendor_id == Vehicle.vendor_id)
            .filter(Vehicle.vehicle_id == vehicle_id, Vendor.tenant_id == tenant_id)
            .with_for_update()
            .first()
        )
        if not vehicle:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=ResponseWrapper.error(
                    message="Vehicle not found under this tenant",
                    error_code="VEHICLE_NOT_FOUND",
                    details={"vehicle_id": vehicle_id, "tenant_id": tenant_id},
                ),
            )

        # ✅ Vehicle’s vendor must match route’s vendor
        if vehicle.vendor_id != route.assigned_vendor_id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=ResponseWrapper.error(
                    message="Vehicle vendor does not match the vendor assigned to the route",
                    error_code="ROUTE_VEHICLE_VENDOR_MISMATCH",
                    details={
                        "route_vendor_id": route.assigned_vendor_id,
                        "vehicle_vendor_id": vehicle.vendor_id,
                    },
                ),
            )

        # ✅ Check if vehicle is active
        if not vehicle.is_active:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=ResponseWrapper.error(
                    message="Cannot assign inactive vehicle to route",
                    error_code="VEHICLE_INACTIVE",
                    details={"vehicle_id": vehicle.vehicle_id, "rc_number": vehicle.rc_number},
                ),
            )

        # ✅ Check if vehicle has a driver assigned
        if not vehicle.driver_id:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=ResponseWrapper.error(
                    message="Vehicle does not have a driver assigned. Please assign a driver to the vehicle first.",
                    error_code="VEHICLE_NO_DRIVER",
                    details={"vehicle_id": vehicle.vehicle_id, "rc_number": vehicle.rc_number},
                ),
            )

        # ---- Resolve Driver from Vehicle ----
        driver = (
            db.query(Driver)
            .join(Vendor, Vendor.vendor_id == Driver.vendor_id)
            .filter(
                Driver.driver_id == vehicle.driver_id,
                Driver.vendor_id == vehicle.vendor_id,
                Vendor.tenant_id == tenant_id,
            )
            .first()
        )
        if not driver:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=ResponseWrapper.error(
                    message="No driver mapped to this vehicle",
                    error_code="DRIVER_NOT_LINKED_TO_VEHICLE",
                    details={"vehicle_id": vehicle.vehicle_id},
                ),
            )

        # ✅ Driver’s vendor must match route’s vendor too
        if driver.vendor_id != route.assigned_vendor_id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=ResponseWrapper.error(
                    message="Driver vendor mismatch with route vendor",
                    error_code="DRIVER_VENDOR_MISMATCH",
                    details={
                        "route_vendor_id": route.assigned_vendor_id,
                        "driver_vendor_id": driver.vendor_id,
                    },
                ),
            )

        # ✅ Check if driver is active
        if not driver.is_active:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=ResponseWrapper.error(
                    message="Cannot assign inactive driver to route",
                    error_code="DRIVER_INACTIVE",
                    details={"driver_id": driver.driver_id, "driver_name": driver.name},
                ),
            )

        # ✅ Verify bidirectional connection between vehicle and driver
        if vehicle.driver_id != driver.driver_id:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=ResponseWrapper.error(
                    message="Vehicle and driver are not properly connected",
                    error_code="VEHICLE_DRIVER_MISMATCH",
                    details={
                        "vehicle_id": vehicle.vehicle_id,
                        "vehicle_driver_id": vehicle.driver_id,
                        "driver_id": driver.driver_id,
                    },
                ),
            )

        # --- Normalize gender (optional safeguard) ---
        if hasattr(driver, "gender") and driver.gender:
            valid_enums = {"MALE", "FEMALE", "OTHER"}
            if driver.gender.upper() not in valid_enums:
                driver.gender = driver.gender.upper()

        # ---- Check if same vehicle/driver already assigned ----
        is_same_assignment = (
            route.assigned_vehicle_id == vehicle.vehicle_id and
            route.assigned_driver_id == driver.driver_id
        )

        if is_same_assignment:
            logger.info(
                f"[assign_vehicle_to_route] Same vehicle/driver already assigned to route {route_id}. Skipping OTP generation and notifications."
            )
            return ResponseWrapper.success(
                data={
                    "route_id": route.route_id,
                    "assigned_vendor_id": route.assigned_vendor_id,
                    "assigned_vehicle_id": route.assigned_vehicle_id,
                    "assigned_driver_id": route.assigned_driver_id,
                    "status": safe_get_enum_value(route, "status"),
                },
                message="Vehicle and driver are already assigned to this route. No changes made.",
            )

        # ---- Apply assignment ----
        route.assigned_vehicle_id = vehicle.vehicle_id
        route.assigned_driver_id = driver.driver_id

        # Progress status only if vendor already assigned
        if route.status == RouteManagementStatusEnum.VENDOR_ASSIGNED:
            route.status = RouteManagementStatusEnum.DRIVER_ASSIGNED

        db.commit()
        db.refresh(route)

        # 🔍 Audit Log: Vehicle/Driver Assignment
        try:
            log_audit(
                db=db,
                tenant_id=tenant_id,
                module="route_management",
                action="UPDATE",
                user_data=user_data,
                description=f"Assigned vehicle '{vehicle.rc_number}' and driver '{driver.name}' to route '{route.route_code}' (ID: {route_id})",
                new_values={
                    "route_id": route_id,
                    "route_code": route.route_code,
                    "assigned_vehicle_id": vehicle.vehicle_id,
                    "vehicle_rc_number": vehicle.rc_number,
                    "assigned_driver_id": driver.driver_id,
                    "driver_name": driver.name,
                    "status": safe_get_enum_value(route, "status")
                },
                request=request
            )
        except Exception as audit_error:
            logger.error(f"Failed to create audit log for vehicle/driver assignment: {str(audit_error)}")

        # Generate OTPs and send notifications for all bookings in the route
        from app.utils.otp_utils import generate_otp_codes
        from app.utils import cache_manager
        from app.models.employee import Employee
        
        cutoff = get_cutoff_with_cache(db, tenant_id)
        
        # Get tenant_config using cache-first helper
        tenant_config = get_tenant_config_with_cache(db, tenant_id)
        
        # Check if escort is assigned to this route AND route requires escort
        escort_enabled = route.assigned_escort_id
        
        # ✅ OPTIMIZATION: Fetch all route bookings with related data in one query using eager loading
        route_bookings = (
            db.query(RouteManagementBooking)
            .join(Booking, Booking.booking_id == RouteManagementBooking.booking_id)
            .join(Employee, Employee.employee_id == Booking.employee_id)
            .filter(RouteManagementBooking.route_id == route.route_id)
            .all()
        )

        if not route_bookings:
            logger.info(f"[assign_vehicle_to_route] No bookings found for route {route_id}")
            return ResponseWrapper.success(
                data={
                    "route_id": route.route_id,
                    "assigned_vendor_id": route.assigned_vendor_id,
                    "assigned_vehicle_id": route.assigned_vehicle_id,
                    "assigned_driver_id": route.assigned_driver_id,
                    "status": safe_get_enum_value(route, "status"),
                },
                message="Vehicle and driver assigned successfully. No bookings to notify.",
            )

        # ✅ OPTIMIZATION: Fetch all bookings and employees at once (batch query)
        booking_ids = [rb.booking_id for rb in route_bookings]
        bookings_dict = {b.booking_id: b for b in db.query(Booking).filter(Booking.booking_id.in_(booking_ids)).all()}
        employee_ids = [bookings_dict[bid].employee_id for bid in booking_ids if bid in bookings_dict]
        employees_dict = {e.employee_id: e for e in db.query(Employee).filter(Employee.employee_id.in_(employee_ids)).all()}

        logger.info(f"[assign_vehicle_to_route] Starting OTP generation for route {route_id} with {len(route_bookings)} bookings")

        # Prepare batch updates for OTPs
        otp_updates = []
        
        for rb in route_bookings:
            booking = bookings_dict.get(rb.booking_id)
            if not booking:
                logger.warning(f"[assign_vehicle_to_route] Booking {rb.booking_id} not found in batch")
                continue
                
            # Recalculate OTP count and purposes at assignment time
            shift = get_shift_with_cache(db, booking.tenant_id, booking.shift_id)
            shift_log_type = safe_get_enum_value(shift, "log_type") if shift else "IN"
            required_otp_count = get_required_otp_count(booking.booking_type, shift_log_type, tenant_config, escort_enabled)

            # Generate OTPs based on required count
            otp_codes = generate_otp_codes(required_otp_count)

            # Determine which OTP fields to assign based on configuration
            required_otps = []

            # Check shift type and add required OTPs
            if shift_log_type == "IN":  # Login shift
                if tenant_config and tenant_config.login_boarding_otp:
                    required_otps.append('boarding')
                if tenant_config and tenant_config.login_deboarding_otp:
                    required_otps.append('deboarding')
            elif shift_log_type == "OUT":  # Logout shift
                if tenant_config and tenant_config.logout_boarding_otp:
                    required_otps.append('boarding')
                if tenant_config and tenant_config.logout_deboarding_otp:
                    required_otps.append('deboarding')

            # Add escort if enabled
            if escort_enabled:
                required_otps.append('escort')

            # Assign OTP codes to required fields in order
            assignments = {}
            for i, otp_type in enumerate(required_otps):
                if i < len(otp_codes):
                    assignments[otp_type] = otp_codes[i]
                else:
                    assignments[otp_type] = None

            # Update booking OTPs
            booking.boarding_otp = assignments.get('boarding')
            booking.deboarding_otp = assignments.get('deboarding')
            booking.escort_otp = assignments.get('escort')

        # ✅ OPTIMIZATION: Commit all OTP updates at once
        db.commit()

        logger.info(f"[assign_vehicle_to_route] OTP generation completed for route {route_id}")

        # ✅ OPTIMIZATION: Prepare notification data for background task
        notification_data = []
        
        for rb in route_bookings:
            booking = bookings_dict.get(rb.booking_id)
            employee = employees_dict.get(booking.employee_id) if booking else None
            
            if not booking or not employee:
                logger.warning(f"[assign_vehicle_to_route] Booking or employee not found for route booking {rb.route_booking_id}")
                continue
            
            # Prepare shift data
            shift = get_shift_with_cache(db, booking.tenant_id, booking.shift_id)
            shift_time = get_shift_time(shift) if shift else None
            shift_time_str = shift_time.strftime('%H:%M') if shift_time else 'N/A'
            shift_type = get_shift_log_type(shift) if shift else 'IN'
            
            notification_data.append({
                "employee_email": employee.email,
                "employee_phone": employee.phone,
                "employee_name": employee.name,
                "employee_id": employee.employee_id,
                "booking_id": booking.booking_id,
                "shift_type": shift_type,
                "shift_time": shift_time_str,
                "booking_date": str(booking.booking_date),
                "estimated_pickup": rb.estimated_pick_up_time,
                "boarding_otp": booking.boarding_otp,
                "deboarding_otp": booking.deboarding_otp,
                "escort_otp": booking.escort_otp,
            })
        
        # ✅ OPTIMIZATION: Add notification sending to background tasks
        if notification_data:
            background_tasks.add_task(
                send_assignment_notifications_background,
                booking_data=notification_data,
                route_code=route.route_code,
                driver_name=driver.name,
                driver_phone=driver.phone,
                vehicle_rc_number=vehicle.rc_number,
                route_id=route.route_id,
            )
            logger.info(f"[assign_vehicle_to_route] {len(notification_data)} notifications queued for background processing")
        
        logger.info(
            f"[assign_vehicle_to_route] Vehicle={vehicle_id} (Driver={driver.driver_id}) assigned to Route={route_id} (Tenant={tenant_id})"
        )

        return ResponseWrapper.success(
            data={
                "route_id": route.route_id,
                "assigned_vendor_id": route.assigned_vendor_id,
                "assigned_vehicle_id": route.assigned_vehicle_id,
                "assigned_driver_id": route.assigned_driver_id,
                "status": safe_get_enum_value(route, "status"),
            },
            message="Vehicle and driver assigned successfully",
        )

    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        logger.exception("[assign_vehicle_to_route] Unexpected error")
        raise handle_db_error(e)


@router.get("/{route_id}")
async def get_route_by_id(
    route_id: int,
    tenant_id: Optional[str] = Query(None, description="Tenant ID"),
    db: Session = Depends(get_db),
    user_data=Depends(PermissionChecker(["route.read"], check_tenant=True)),
):
    """
    Get details of a specific route by its ID.
    """
    try:
        user_type = user_data.get("user_type")
        token_tenant_id = user_data.get("tenant_id")

        # --- Tenant Resolution ---
        if user_type == "employee":
            tenant_id = token_tenant_id
        elif user_type == "admin":
            if token_tenant_id:
                tenant_id = token_tenant_id  # normal admin with tenant scope
            else:
                if not tenant_id:  # superadmin case, must pass tenant
                    raise HTTPException(
                        status_code=400,
                        detail=ResponseWrapper.error(
                            message="tenant_id is required for admin users",
                            error_code="TENANT_ID_REQUIRED",
                        ),
                    )
        else:
            tenant_id = token_tenant_id

        if not tenant_id:
            raise HTTPException(
                status_code=403,
                detail=ResponseWrapper.error(
                    message="Tenant context not available",
                    error_code="TENANT_ID_REQUIRED",
                )
            )

        logger.info(f"[get_route_by_id] tenant={tenant_id}, route_id={route_id}")

        # Validate tenant exists (use cache)
        tenant = get_tenant_with_cache(db, tenant_id)
        if not tenant:
            raise HTTPException(
                status_code=404,
                detail=ResponseWrapper.error(
                    message=f"Tenant {tenant_id} not found",
                    error_code="TENANT_NOT_FOUND"
                )
            )
        tenant_details = {
            "tenant_id": tenant.tenant_id,
            "name": tenant.name,
            "address": tenant.address,
            "latitude": tenant.latitude,
            "longitude": tenant.longitude,
        }
        # Fetch route
        route = db.query(RouteManagement).filter(
            RouteManagement.route_id == route_id,
            RouteManagement.tenant_id == tenant_id
        ).first()

        if not route:
            raise HTTPException(
                status_code=404,
                detail=ResponseWrapper.error("Route not found", "ROUTE_NOT_FOUND")
            )
        # ✅ Restrict vendor access to only their own routes
        vendor_id = user_data.get("vendor_id")
        if user_type == "vendor":
            if not vendor_id:
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail=ResponseWrapper.error(
                        message="Vendor ID missing in token",
                        error_code="VENDOR_ID_MISSING",
                    ),
                )

            if route.assigned_vendor_id != int(vendor_id):
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail=ResponseWrapper.error(
                        message="You are not authorized to access this route",
                        error_code="ROUTE_ACCESS_DENIED",
                        details={
                            "requested_route_vendor": route.assigned_vendor_id,
                            "your_vendor_id": vendor_id,
                        },
                    ),
                )


        # Get bookings
        rbs = db.query(RouteManagementBooking).filter(
            RouteManagementBooking.route_id == route_id
        ).order_by(RouteManagementBooking.order_id).all()

        booking_ids = [rb.booking_id for rb in rbs]
        bookings = get_bookings_by_ids(booking_ids, db) if booking_ids else []

        # ---- Fetch Driver / Vehicle / Vendor ----
        driver = None
        vehicle = None
        vendor = None
        escort = None

        if route.assigned_driver_id:
            driver = db.query(Driver.driver_id, Driver.name, Driver.phone).filter(
                Driver.driver_id == route.assigned_driver_id
            ).first()

        if route.assigned_vehicle_id:
            vehicle = db.query(Vehicle.vehicle_id, Vehicle.rc_number).filter(
                Vehicle.vehicle_id == route.assigned_vehicle_id
            ).first()

        if route.assigned_vendor_id:
            vendor = db.query(Vendor.vendor_id, Vendor.name).filter(
                Vendor.vendor_id == route.assigned_vendor_id
            ).first()

        if route.assigned_escort_id:
            escort = db.query(Escort.escort_id, Escort.name, Escort.phone).filter(
                Escort.escort_id == route.assigned_escort_id
            ).first()

        # Build stops list
        stops = []
        for rb in rbs:
            b = next((x for x in bookings if x["booking_id"] == rb.booking_id), None)
            if not b: 
                continue

            stops.append({
                **b,
                "order_id": rb.order_id,
                "estimated_pick_up_time": rb.estimated_pick_up_time,
                "estimated_drop_time": rb.estimated_drop_time,
                "estimated_distance": rb.estimated_distance,
                "actual_pick_up_time": rb.actual_pick_up_time,
                "actual_drop_time": rb.actual_drop_time,
                "actual_distance": rb.actual_distance,
            })

        # Same response structure as list API ✅
        response = {
            "tenant": tenant_details,
            "route_id": route.route_id,
            "shift_id": route.shift_id,
            "route_code": route.route_code,
            "status": safe_get_enum_value(route, "status"),
            "escort_required": route.escort_required,
            "driver": {"id": driver.driver_id, "name": driver.name, "phone": driver.phone} if driver else None,
            "vehicle": {"id": vehicle.vehicle_id, "rc_number": vehicle.rc_number} if vehicle else None,
            "vendor": {"id": vendor.vendor_id, "name": vendor.name} if vendor else None,
            "escort": {"id": escort.escort_id, "name": escort.name, "phone": escort.phone} if escort else None,
            "stops": stops,
            "summary": {
                "total_distance_km": route.actual_total_distance or route.estimated_total_distance or 0,
                "total_time_minutes": route.actual_total_time or route.estimated_total_time or 0
            }
        }

        return ResponseWrapper.success(response, "Route fetched successfully")

    except HTTPException:
        raise
    except Exception as e:
        return handle_db_error(e)

@router.post("/merge")
async def merge_routes(
    merge_request: MergeRoutesRequest,
    request: Request,
    tenant_id: Optional[str] = Query(None, description="Tenant ID"),
    db: Session = Depends(get_db),
    user_data=Depends(PermissionChecker(["route_merge.create", "route_merge.read", "route_merge.update", "route_merge.delete"], check_tenant=True)),
):
    """
    Merge multiple routes into a single optimized route.
    """
    try:
        user_type = user_data.get("user_type")
        token_tenant_id = user_data.get("tenant_id")
        user_id = user_data.get("user_id", "unknown")

        # --- Tenant Resolution ---
        if user_type == "employee":
            tenant_id = token_tenant_id
        elif user_type == "admin":
            if not tenant_id:
                tenant_id = token_tenant_id  # Use token tenant for admin
            if not tenant_id:  # Still none? Super admin needs explicit tenant
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=ResponseWrapper.error(
                        message="tenant_id is required for super admin users",
                        error_code="TENANT_ID_REQUIRED",
                    ),
                )
        else:
            tenant_id = tenant_id or token_tenant_id

        if not tenant_id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=ResponseWrapper.error(
                    message="Tenant context not available",
                    error_code="TENANT_ID_MISSING",
                ),
            )

        logger.info(f"[MERGE] ============ ROUTE MERGE STARTED ============")
        logger.info(f"[MERGE] Tenant: {tenant_id} | User: {user_id} | Route IDs: {merge_request.route_ids}")

        # --- Step 1: Validate Input ---
        if not merge_request.route_ids:
            logger.error(f"[MERGE] ❌ FAILED: No route IDs provided")
            raise HTTPException(
                400,
                ResponseWrapper.error("No route ids provided", "NO_ROUTE_IDS")
            )

        if len(merge_request.route_ids) < 2:
            logger.warning(f"[MERGE] ⚠️ Only {len(merge_request.route_ids)} route provided - merge requires at least 2 routes")

        logger.info(f"[MERGE] ✓ Step 1: Input validated - {len(merge_request.route_ids)} routes to merge")

        # --- Step 2: Load routes from database ---
        logger.info(f"[MERGE] Step 2: Loading routes from database...")
        routes = db.query(RouteManagement).filter(
            RouteManagement.route_id.in_(merge_request.route_ids),
            RouteManagement.tenant_id == tenant_id
        ).all()

        logger.info(f"[MERGE] Found {len(routes)} routes in database")
        
        if not routes:
            logger.error(f"[MERGE] ❌ FAILED: No routes found for IDs {merge_request.route_ids} in tenant {tenant_id}")
            raise HTTPException(
                404,
                ResponseWrapper.error("Routes not found", "ROUTE_NOT_FOUND")
            )

        if len(routes) != len(merge_request.route_ids):
            missing_routes = set(merge_request.route_ids) - {r.route_id for r in routes}
            logger.warning(f"[MERGE] ⚠️ Some routes not found: {missing_routes}")

        logger.info(f"[MERGE] ✓ Step 2: Loaded routes: {[r.route_id for r in routes]}")

        # --- Step 3: Collect bookings from all routes ---
        logger.info(f"[MERGE] Step 3: Collecting bookings from routes...")
        all_booking_ids = []
        shift_id = None

        for idx, r in enumerate(routes):
            logger.debug(f"[MERGE]   Route {idx+1}/{len(routes)}: ID={r.route_id}, Shift={r.shift_id}, Status={r.status}")
            
            if shift_id and r.shift_id != shift_id:
                logger.error(f"[MERGE] ❌ FAILED: Shift mismatch - Route {r.route_id} has shift {r.shift_id}, expected {shift_id}")
                raise HTTPException(
                    400,
                    ResponseWrapper.error(
                        "All routes must belong to same shift",
                        "SHIFT_MISMATCH"
                    )
                )
            shift_id = r.shift_id

            rbs = db.query(RouteManagementBooking).filter(
                RouteManagementBooking.route_id == r.route_id
            ).all()

            route_booking_ids = [b.booking_id for b in rbs]
            all_booking_ids.extend(route_booking_ids)
            logger.info(f"[MERGE]   Route {r.route_id}: {len(route_booking_ids)} bookings - {route_booking_ids}")

        all_booking_ids = list(dict.fromkeys(all_booking_ids))  # unique preserve order
        logger.info(f"[MERGE] ✓ Step 3: Collected {len(all_booking_ids)} unique bookings from {len(routes)} routes")
        logger.debug(f"[MERGE] Booking IDs: {all_booking_ids}")

        if not all_booking_ids:
            logger.error(f"[MERGE] ❌ FAILED: No bookings found in selected routes")
            raise HTTPException(
                400,
                ResponseWrapper.error("No bookings in selected routes", "EMPTY_ROUTE_LIST")
            )

        # --- Step 4: Load full booking objects ---
        logger.info(f"[MERGE] Step 4: Loading full booking details...")
        try:
            bookings = get_bookings_by_ids(all_booking_ids, db)
            logger.info(f"[MERGE] ✓ Step 4: Loaded {len(bookings)} booking objects")
        except Exception as e:
            logger.error(f"[MERGE] ❌ FAILED: Error loading bookings - {str(e)}", exc_info=True)
            raise

        # --- Step 5: Load and validate shift ---
        logger.info(f"[MERGE] Step 5: Loading shift {shift_id} for tenant {tenant_id}...")
        shift = get_shift_with_cache(db, tenant_id, shift_id)
        if not shift:
            logger.error(f"[MERGE] ❌ FAILED: Shift {shift_id} not found")
            raise HTTPException(
                404, ResponseWrapper.error("Shift not found", "SHIFT_NOT_FOUND")
            )
        
        shift_type = safe_get_enum_value(shift, "log_type")
        logger.info(f"[MERGE] ✓ Step 5: Shift loaded - Type: {shift_type}, Time: {shift.shift_time}")

        # --- Step 6: Validate office location consistency ---
        logger.info(f"[MERGE] Step 6: Validating office location consistency...")
        
        if shift_type == "IN":
            # For IN shift (LOGIN): All employees go TO office - drop location must be same
            logger.info(f"[MERGE]   Checking IN shift - all bookings must have same DROP location (office)")
            office_locations = set()
            office_details = []
            
            for idx, booking in enumerate(bookings):
                office_key = (
                    round(booking["drop_latitude"], 6),
                    round(booking["drop_longitude"], 6),
                    booking["drop_location"]
                )
                office_locations.add(office_key)
                office_details.append({
                    "booking_id": booking["booking_id"],
                    "drop_lat": booking["drop_latitude"],
                    "drop_lng": booking["drop_longitude"],
                    "drop_location": booking["drop_location"]
                })
                logger.debug(f"[MERGE]     Booking {booking['booking_id']}: Drop={booking['drop_location']} ({booking['drop_latitude']}, {booking['drop_longitude']})")
            
            if len(office_locations) > 1:
                logger.error(f"[MERGE] ❌ FAILED: IN shift has {len(office_locations)} different office drop locations:")
                for loc in office_details:
                    logger.error(f"[MERGE]   - Booking {loc['booking_id']}: {loc['drop_location']} ({loc['drop_lat']}, {loc['drop_lng']})")
                raise HTTPException(
                    400,
                    ResponseWrapper.error(
                        "Cannot merge routes: All bookings must have the same office drop location for IN shift",
                        "OFFICE_LOCATION_MISMATCH",
                        {"shift_type": "IN", "unique_locations": len(office_locations), "details": office_details}
                    )
                )
            
            # Use validated office location
            office_location = bookings[0]
            office_lat = office_location["drop_latitude"]
            office_lng = office_location["drop_longitude"]
            office_address = office_location["drop_location"]
            logger.info(f"[MERGE] ✓ Step 6: All bookings have same office DROP location: {office_address}")
            
        else:
            # For OUT shift (LOGOUT): All employees start FROM office - pickup location must be same
            logger.info(f"[MERGE]   Checking OUT shift - all bookings must have same PICKUP location (office)")
            office_locations = set()
            office_details = []
            
            for idx, booking in enumerate(bookings):
                office_key = (
                    round(booking["pickup_latitude"], 6),
                    round(booking["pickup_longitude"], 6),
                    booking["pickup_location"]
                )
                office_locations.add(office_key)
                office_details.append({
                    "booking_id": booking["booking_id"],
                    "pickup_lat": booking["pickup_latitude"],
                    "pickup_lng": booking["pickup_longitude"],
                    "pickup_location": booking["pickup_location"]
                })
                logger.debug(f"[MERGE]     Booking {booking['booking_id']}: Pickup={booking['pickup_location']} ({booking['pickup_latitude']}, {booking['pickup_longitude']})")
            
            if len(office_locations) > 1:
                logger.error(f"[MERGE] ❌ FAILED: OUT shift has {len(office_locations)} different office pickup locations:")
                for loc in office_details:
                    logger.error(f"[MERGE]   - Booking {loc['booking_id']}: {loc['pickup_location']} ({loc['pickup_lat']}, {loc['pickup_lng']})")
                raise HTTPException(
                    400,
                    ResponseWrapper.error(
                        "Cannot merge routes: All bookings must have the same office pickup location for OUT shift",
                        "OFFICE_LOCATION_MISMATCH",
                        {"shift_type": "OUT", "unique_locations": len(office_locations), "details": office_details}
                    )
                )
            
            # Use validated office location
            office_location = bookings[0]
            office_lat = office_location["pickup_latitude"]
            office_lng = office_location["pickup_longitude"]
            office_address = office_location["pickup_location"]
            logger.info(f"[MERGE] ✓ Step 6: All bookings have same office PICKUP location: {office_address}")

        logger.info(f"[MERGE] Office coordinates: ({office_lat}, {office_lng})")

        # --- Step 7: Generate optimized route ---
        logger.info(f"[MERGE] Step 7: Generating optimized route for {len(bookings)} bookings...")
        from app.services.optimal_roiute_generation import generate_optimal_route, generate_drop_route

        try:
            if shift_type == "IN":
                logger.info(f"[MERGE]   Calling generate_optimal_route (IN shift)")
                logger.debug(f"[MERGE]   Params: shift_time={shift.shift_time}, bookings={len(bookings)}, office=({office_lat}, {office_lng})")
                optimized = generate_optimal_route(
                    shift_time=shift.shift_time,
                    group=bookings,
                    drop_lat=office_lat,
                    drop_lng=office_lng,
                    drop_address=office_address
                )
            else:
                start_time_min = datetime_to_minutes(shift.shift_time)
                logger.info(f"[MERGE]   Calling generate_drop_route (OUT shift)")
                logger.debug(f"[MERGE]   Params: start_time={start_time_min}min, bookings={len(bookings)}, office=({office_lat}, {office_lng})")
                optimized = generate_drop_route(
                    group=bookings,
                    start_time_minutes=start_time_min,
                    office_lat=office_lat,
                    office_lng=office_lng,
                    office_address=office_address
                )
            
            if not optimized:
                logger.error(f"[MERGE] ❌ FAILED: Route optimization returned empty result")
                raise HTTPException(
                    500,
                    ResponseWrapper.error("Route optimization failed", "OPT_FAIL")
                )

            optimized = optimized[0]  # first candidate
            logger.info(f"[MERGE] ✓ Step 7: Route optimized successfully")
            logger.info(f"[MERGE]   - Estimated time: {optimized.get('estimated_time')}")
            logger.info(f"[MERGE]   - Estimated distance: {optimized.get('estimated_distance')}")
            logger.info(f"[MERGE]   - Stops: {len(optimized.get('pickup_order', []))}")
            
        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"[MERGE] ❌ FAILED: Route optimization error - {str(e)}", exc_info=True)
            raise HTTPException(
                500,
                ResponseWrapper.error("Route optimization failed", "OPT_FAIL", {"error": str(e)})
            )

        # --- Step 8: Create new merged route ---
        logger.info(f"[MERGE] Step 8: Creating new merged route in database...")
        try:
            route = RouteManagement(
                tenant_id=tenant_id,
                shift_id=shift_id,
                # route_code=f"M-{tenant_id}-{shift_id}",
                estimated_total_time=float(optimized["estimated_time"].split()[0]),
                estimated_total_distance=float(optimized["estimated_distance"].split()[0]),
                buffer_time=float(optimized["buffer_time"].split()[0]),
                status="PLANNED"
            )

            db.add(route)
            db.flush()
            logger.info(f"[MERGE] ✓ Step 8: Created route ID: {route.route_id}")
        except Exception as e:
            logger.error(f"[MERGE] ❌ FAILED: Error creating route - {str(e)}", exc_info=True)
            raise

        # --- Step 9: Insert route stops ---
        logger.info(f"[MERGE] Step 9: Inserting {len(optimized['pickup_order'])} stops into route...")
        try:
            for idx, b in enumerate(optimized["pickup_order"]):
                # Convert datetime.time to string for SQLite
                est_pickup = b["estimated_pickup_time_formatted"]
                if isinstance(est_pickup, time):
                    est_pickup = est_pickup.strftime("%H:%M:%S")
                
                db.add(RouteManagementBooking(
                    route_id=route.route_id,
                    booking_id=b["booking_id"],
                    order_id=idx + 1,
                    estimated_pick_up_time=est_pickup,
                    estimated_distance=b["estimated_distance_km"]
                ))
                logger.debug(f"[MERGE]   Stop {idx+1}: Booking {b['booking_id']} at {est_pickup}")
            
            logger.info(f"[MERGE] ✓ Step 9: Inserted all stops")
        except Exception as e:
            logger.error(f"[MERGE] ❌ FAILED: Error inserting stops - {str(e)}", exc_info=True)
            raise

        # --- Step 10: Update booking statuses ---
        logger.info(f"[MERGE] Step 10: Updating booking statuses to SCHEDULED...")
        try:
            request_bookings = db.query(Booking).filter(
                Booking.booking_id.in_(all_booking_ids),
                Booking.status == BookingStatusEnum.REQUEST
            ).all()
            
            request_booking_ids = [b.booking_id for b in request_bookings]
            logger.info(f"[MERGE]   Found {len(request_booking_ids)} bookings in REQUEST status: {request_booking_ids}")
            
            if request_booking_ids:
                update_count = db.query(Booking).filter(
                    Booking.booking_id.in_(all_booking_ids),
                    Booking.status == BookingStatusEnum.REQUEST
                ).update(
                    {
                        Booking.status: BookingStatusEnum.SCHEDULED,
                        Booking.updated_at: func.now(),
                    },
                    synchronize_session=False
                )
                logger.info(f"[MERGE] ✓ Step 10: Updated {update_count} bookings to SCHEDULED")
            else:
                logger.info(f"[MERGE] ✓ Step 10: No bookings in REQUEST status, skipping update")
        except Exception as e:
            logger.error(f"[MERGE] ❌ FAILED: Error updating booking statuses - {str(e)}", exc_info=True)
            raise

        # --- Step 11: Delete old routes ---
        logger.info(f"[MERGE] Step 11: Deleting old routes {merge_request.route_ids}...")
        try:
            # Delete route bookings
            deleted_bookings = db.query(RouteManagementBooking).filter(
                RouteManagementBooking.route_id.in_(merge_request.route_ids)
            ).delete(synchronize_session=False)
            logger.info(f"[MERGE]   Deleted {deleted_bookings} route-booking associations")

            # Delete routes
            deleted_routes = db.query(RouteManagement).filter(
                RouteManagement.route_id.in_(merge_request.route_ids)
            ).delete(synchronize_session=False)
            logger.info(f"[MERGE]   Deleted {deleted_routes} routes")
            
            logger.info(f"[MERGE] ✓ Step 11: Cleaned up old routes")
        except Exception as e:
            logger.error(f"[MERGE] ❌ FAILED: Error deleting old routes - {str(e)}", exc_info=True)
            raise

        # --- Step 12: Commit transaction ---
        logger.info(f"[MERGE] Step 12: Committing database transaction...")
        try:
            db.commit()
            logger.info(f"[MERGE] ✓ Step 12: Transaction committed successfully")
        except Exception as e:
            logger.error(f"[MERGE] ❌ FAILED: Database commit error - {str(e)}", exc_info=True)
            raise

        # --- Step 13: Create audit log ---
        logger.info(f"[MERGE] Step 13: Creating audit log...")
        try:
            log_audit(
                db=db,
                tenant_id=tenant_id,
                module="route_management",
                action="CREATE",
                user_data=user_data,
                description=f"Merged {len(merge_request.route_ids)} routes into new route '{route.route_code}' (ID: {route.route_id})",
                new_values={
                    "new_route_id": route.route_id,
                    "new_route_code": route.route_code,
                    "merged_route_ids": merge_request.route_ids,
                    "total_bookings": len(all_booking_ids),
                    "shift_id": shift_id,
                    "estimated_distance_km": route.estimated_total_distance,
                    "estimated_time_min": route.estimated_total_time
                },
                request=request
            )
            logger.info(f"[MERGE] ✓ Step 13: Audit log created")
        except Exception as audit_error:
            logger.warning(f"[MERGE] ⚠️ Audit log creation failed (non-critical): {str(audit_error)}")

        logger.info(f"[MERGE] ============ ROUTE MERGE COMPLETED SUCCESSFULLY ============")
        logger.info(f"[MERGE] New Route ID: {route.route_id} | Bookings: {len(all_booking_ids)} | Distance: {route.estimated_total_distance}km | Time: {route.estimated_total_time}min")
        
        return ResponseWrapper.success(
            {"route_id": route.route_id},
            f"Merged routes into {route.route_id}"
        )

    except HTTPException as he:
        db.rollback()
        logger.error(f"[MERGE] ============ MERGE FAILED (HTTPException) ============")
        logger.error(f"[MERGE] Status: {he.status_code} | Detail: {he.detail}")
        raise
    except Exception as e:
        db.rollback()
        logger.error(f"[MERGE] ============ MERGE FAILED (Exception) ============")
        logger.error(f"[MERGE] Error Type: {type(e).__name__}")
        logger.error(f"[MERGE] Error Message: {str(e)}", exc_info=True)
        raise HTTPException(
            500,
            ResponseWrapper.error("Error merging routes", "ROUTE_MERGE_ERROR", {"error": str(e), "error_type": type(e).__name__})
        )


@router.put("/{route_id}")
async def update_route(
    route_id: int,
    update_request: UpdateRouteRequest,
    request: Request,
    tenant_id: Optional[str] = Query(None, description="Tenant ID"),
    db: Session = Depends(get_db),
    user_data=Depends(PermissionChecker(["route.update"], check_tenant=True)),
):
    """
    Update a route by adding or removing bookings, then regenerate the optimal route.
    """
    try:
        logger.debug(f"UpdateRouteRequest received: {request}")
        logger.debug(f"User data: {user_data}")
        user_type = user_data.get("user_type")
        token_tenant_id = user_data.get("tenant_id")

        user_type = user_data.get("user_type")
        token_tenant_id = user_data.get("tenant_id")

        if user_type == "employee":
            tenant_id = token_tenant_id

        elif user_type == "vendor":
            if not tenant_id:
                raise HTTPException(
                    status_code=400,
                    detail=ResponseWrapper.error(
                        message="tenant_id is required for vendor users",
                        error_code="TENANT_ID_REQUIRED",
                    ),
                )

        elif user_type == "admin":
            # Use token tenant if no explicit tenant_id provided
            if not tenant_id:
                tenant_id = token_tenant_id
            # Super admin must provide tenant_id if token has none
            if not tenant_id:
                raise HTTPException(
                    status_code=400,
                    detail=ResponseWrapper.error(
                        message="tenant_id is required for admin users",
                        error_code="TENANT_ID_REQUIRED",
                    ),
                )

        if not tenant_id:
            raise HTTPException(
                status_code=403,
                detail=ResponseWrapper.error(
                    message="Tenant context not available",
                    error_code="TENANT_ID_MISSING",
                ),
            )

        logger.info(f"Updating route {route_id} with operation '{update_request.operation}' for {len(update_request.booking_ids)} bookings, user: {user_data.get('user_id', 'unknown')}")

        # Validate tenant exists (use cache)
        tenant = get_tenant_with_cache(db, tenant_id)
        if not tenant:
            logger.warning(f"Tenant {tenant_id} not found")
            raise HTTPException(
                status_code=404,
                detail=ResponseWrapper.error(
                    message=f"Tenant {tenant_id} not found",
                    error_code="TENANT_NOT_FOUND",
                    details={"tenant_id": tenant_id}
                )
            )
    
        if not update_request.booking_ids:
            raise HTTPException(
                status_code=400,
                detail=ResponseWrapper.error(
                    message="No booking IDs provided for update",
                    error_code="NO_BOOKINGS_PROVIDED",
                )
            )

        logger.info(f"Fetching route {route_id} for tenant {tenant_id}")
        # Check if route exists
        route = db.query(RouteManagement).filter(
            RouteManagement.route_id == route_id,
            RouteManagement.tenant_id == tenant_id
        ).first()

        logger.debug(f"Fetched route: {route}")
        if not route:
            raise HTTPException(
                status_code=404,
                detail=ResponseWrapper.error(
                    message=f"Route {route_id} not found",
                    error_code="ROUTE_NOT_FOUND",
                )
            )

        # Fetch current bookings in the route
        current_rbs = db.query(RouteManagementBooking).filter(
            RouteManagementBooking.route_id == route_id
        ).all()
        logger.debug(f"Current route bookings: {current_rbs}")

        current_booking_ids = {rb.booking_id for rb in current_rbs}
        request_booking_ids = set(update_request.booking_ids)  
        logger.debug(f"Current booking IDs: {current_booking_ids}, Requested booking IDs: {request_booking_ids}")

        request_bookings = []
        for booking in request_booking_ids:
            booking_details = get_booking_by_id(booking, db)
            request_bookings.append(booking_details)

        # --- Remove booking from any other active route before adding ---
        if update_request.operation == "add":
            for booking_id in request_booking_ids:
                existing_links = db.query(RouteManagementBooking).join(RouteManagement).filter(
                    RouteManagementBooking.booking_id == booking_id,
                    RouteManagementBooking.route_id != route_id,
                    RouteManagement.tenant_id == tenant_id
                ).all()

                for link in existing_links:
                    logger.info(
                        f"Removing booking {booking_id} from route {link.route_id} "
                        f"because it is being moved to route {route_id}"
                    )
                    db.delete(link)

            db.flush()  # ensure removal is persisted before adding in new route

        
        logger.debug(f"Fetched request bookings: {request_bookings}")
        
        # figure out the shift type (use cache)
        shift = get_shift_with_cache(db, route.tenant_id, route.shift_id)
        shift_type = safe_get_enum_value(shift, "log_type")
        logger.debug(f"Shift type for route {route_id} is {shift_type}")

        all_booking_ids = []
        if update_request.operation == "add":
            all_booking_ids = list(current_booking_ids.union(request_booking_ids))
        else:
            all_booking_ids = list(current_booking_ids.difference(request_booking_ids))
        logger.debug(f"All booking IDs after '{update_request.operation}': {all_booking_ids}")

        # Handle empty route (all bookings removed)
        if not all_booking_ids:
            # Delete all route-booking mappings
            db.query(RouteManagementBooking).filter(
                RouteManagementBooking.route_id == route_id
            ).delete(synchronize_session=False)
            
            # Revert removed bookings to REQUEST status
            db.query(Booking).filter(
                Booking.booking_id.in_(request_booking_ids),
                Booking.status == BookingStatusEnum.SCHEDULED
            ).update(
                {
                    Booking.status: BookingStatusEnum.REQUEST,
                    Booking.updated_at: func.now(),
                },
                synchronize_session=False
            )
            
            # Reset route estimations
            route.estimated_total_time = 0.0
            route.estimated_total_distance = 0.0
            route.buffer_time = 0.0
            
            db.commit()
            
            return ResponseWrapper.success(
                data={
                    "route_id": route_id,
                    "message": "All bookings removed from route"
                },
                message=f"Successfully removed all bookings from route {route.route_code}"
            )

        all_bookings = []
        for booking_id in all_booking_ids:
            booking_details = get_booking_by_id(booking_id, db)
            all_bookings.append(booking_details)

        # generate route based on shift type
        logger.info("="*80)
        logger.info(f"🛣️  ROUTE OPTIMIZATION REQUEST - Route ID: {route_id}")
        logger.info(f"📍 Shift Type: {shift_type}, Shift Time: {shift.shift_time}")
        logger.info(f"📦 Total bookings to process: {len(all_bookings)}")
        
        from app.services.optimal_roiute_generation import generate_optimal_route, generate_drop_route
        if shift_type == "IN":
            logger.info(f"🏢 PICKUP Route (IN): Optimizing pickups → Office")
            logger.info(f"   Drop point: ({all_bookings[-1]['drop_latitude']}, {all_bookings[-1]['drop_longitude']})")
            logger.info(f"   Drop address: {all_bookings[-1]['drop_location']}")
            
            optimized = generate_optimal_route(
                shift_time=shift.shift_time,
                group=all_bookings,
                drop_lat=all_bookings[-1]["drop_latitude"],
                drop_lng=all_bookings[-1]["drop_longitude"],
                drop_address=all_bookings[-1]["drop_location"]
            )
        else:
            logger.info(f"🏠 DROP Route (OUT): Optimizing Office → Drop locations")
            logger.info(f"   Pickup point: ({all_bookings[0]['pickup_latitude']}, {all_bookings[0]['pickup_longitude']})")
            logger.info(f"   Pickup address: {all_bookings[0]['pickup_location']}")
            
            optimized = generate_drop_route(
                group=all_bookings,
                start_time_minutes=datetime_to_minutes(shift.shift_time),
                office_lat=all_bookings[0]["pickup_latitude"],
                office_lng=all_bookings[0]["pickup_longitude"],
                office_address=all_bookings[0]["pickup_location"]
            )
        
        logger.info(f"📊 Optimization result: {len(optimized) if optimized else 0} route(s) generated")
        if optimized:
            logger.debug(f"Optimized route data: {optimized}")
        
        # Validate route optimization results
        if not optimized or len(optimized) == 0:
            logger.error("❌ ROUTE OPTIMIZATION FAILED - Empty result returned")
            logger.error(f"Route ID: {route_id}, Shift Type: {shift_type}, Bookings: {len(all_bookings)}")
            
            # Collect problematic bookings for error message
            problematic_bookings = []
            office_lat = all_bookings[0]["pickup_latitude"] if shift_type != "IN" else all_bookings[-1]["drop_latitude"]
            office_lng = all_bookings[0]["pickup_longitude"] if shift_type != "IN" else all_bookings[-1]["drop_longitude"]
            
            logger.error(f"Reference coordinates: ({office_lat}, {office_lng})")
            
            for booking in all_bookings:
                lat = booking["drop_latitude"] if shift_type != "IN" else booking["pickup_latitude"]
                lng = booking["drop_longitude"] if shift_type != "IN" else booking["pickup_longitude"]
                location_str = f"{lat},{lng}"
                logger.error(
                    f"  Problematic Booking #{booking['booking_id']}: "
                    f"Employee={booking['employee_code']}, Coords={location_str}, "
                    f"Location={booking.get('drop_location' if shift_type != 'IN' else 'pickup_location', 'Unknown')}"
                )
                problematic_bookings.append({
                    "booking_id": booking["booking_id"],
                    "employee_code": booking["employee_code"],
                    "coordinates": location_str,
                    "location": booking.get("drop_location" if shift_type != "IN" else "pickup_location", "Unknown")
                })
            
            logger.error(
                f"Route optimization failed for route {route_id}. "
                f"Cannot generate route with the given coordinates. "
                f"Office/Destination: ({office_lat}, {office_lng}), "
                f"Problematic bookings: {problematic_bookings}"
            )
            
            raise HTTPException(
                status_code=400,
                detail=ResponseWrapper.error(
                    message="Cannot generate route: Invalid or unreachable locations",
                    error_code="ROUTE_OPTIMIZATION_FAILED",
                    details={
                        "reason": "Route optimization service returned no valid routes. This usually happens when:",
                        "possible_causes": [
                            "One or more locations are too far apart (e.g., different countries/continents)",
                            "Invalid or unreachable coordinates",
                            "Locations not connected by drivable roads"
                        ],
                        "action_required": "Please verify all booking locations are within the same city/region and have valid coordinates",
                        "problematic_bookings": problematic_bookings
                    }
                )
            )
        
        logger.info("✅ Route optimization successful - Processing results...")
        # now we generated routes, lets update our route and route_bookings
        optimized = optimized[0]  # first candidate
        
        logger.info(f"📊 Updating route metrics:")
        logger.info(f"   Total time: {optimized['estimated_time']}")
        logger.info(f"   Total distance: {optimized['estimated_distance']}")
        logger.info(f"   Buffer time: {optimized['buffer_time']}")
        
        route.estimated_total_time = float(optimized["estimated_time"].split()[0])
        route.estimated_total_distance = float(optimized["estimated_distance"].split()[0])
        route.buffer_time = float(optimized["buffer_time"].split()[0])
        # calculate the estimations to return
        estimations = {
            "start_time": str(optimized.get("start_time", "")),
            "total_distance_km": optimized.get("estimated_distance", "0"),
            "total_time_minutes": optimized.get("total_route_duration", "0")
        }


        # --- Safely replace stops without deleting the route row (avoid StaleDataError) ---
        logger.info(f"🔄 Updating route-booking mappings...")
        # Get bookings that will be removed from this route
        removed_booking_ids = current_booking_ids - set(all_booking_ids)
        added_booking_ids = set(all_booking_ids) - current_booking_ids
        
        logger.info(f"   Removed bookings: {list(removed_booking_ids) if removed_booking_ids else 'None'}")
        logger.info(f"   Added bookings: {list(added_booking_ids) if added_booking_ids else 'None'}")
        logger.info(f"   Total stops in new route: {len(optimized['pickup_order'])}")
        
        # Delete existing route-booking mappings for this route_id
        deleted_count = db.query(RouteManagementBooking).filter(
            RouteManagementBooking.route_id == route_id
        ).delete(synchronize_session=False)
        logger.info(f"   Deleted {deleted_count} old route-booking mappings")

        # Add new route-booking mappings based on optimized pickup_order
        logger.info(f"   Creating {len(optimized['pickup_order'])} new route-booking mappings...")
        for idx, b in enumerate(optimized["pickup_order"]):
            # Convert datetime.time objects to strings for SQLite compatibility
            est_pickup = b.get("estimated_pickup_time_formatted")
            if isinstance(est_pickup, time):
                est_pickup = est_pickup.strftime("%H:%M:%S")
            
            est_drop = b.get("estimated_drop_time_formatted")
            if isinstance(est_drop, time):
                est_drop = est_drop.strftime("%H:%M:%S")
            
            db.add(RouteManagementBooking(
                route_id=route.route_id,
                booking_id=b["booking_id"],
                order_id=idx + 1,
                estimated_pick_up_time=est_pickup,
                estimated_distance=b.get("estimated_distance_km"),
                estimated_drop_time=est_drop,
            ))

        logger.info(f"✅ Created {len(optimized['pickup_order'])} new route-booking mappings")
        
        # Update booking statuses
        logger.info(f"🔄 Updating booking statuses...")
        # 1. Set removed bookings back to REQUEST (if they were SCHEDULED)
        if removed_booking_ids:
            updated_removed = db.query(Booking).filter(
                Booking.booking_id.in_(removed_booking_ids),
                Booking.status == BookingStatusEnum.SCHEDULED
            ).update(
                {
                    Booking.status: BookingStatusEnum.REQUEST,
                    Booking.updated_at: func.now(),
                },
                synchronize_session=False
            )
            logger.info(f"   Reverted {updated_removed} removed bookings to REQUEST status")

        # 2. Set added bookings to SCHEDULED (if they are in REQUEST)
        if added_booking_ids:
            updated_added = db.query(Booking).filter(
                Booking.booking_id.in_(added_booking_ids),
                Booking.status == BookingStatusEnum.REQUEST
            ).update(
                {
                    Booking.status: BookingStatusEnum.SCHEDULED,
                    Booking.updated_at: func.now(),
                },
                synchronize_session=False
            )
            logger.info(f"   Updated {updated_added} added bookings to SCHEDULED status")

        # Commit once so both route updates and new mappings are persisted together
        logger.info("💾 Committing changes to database...")
        db.commit()
        logger.info("✅ Database commit successful")

        # 🔍 Audit Log: Route Update
        logger.info("📝 Creating audit log entry...")
        try:
            log_audit(
                db=db,
                tenant_id=tenant_id,
                module="route_management",
                action="UPDATE",
                user_data=user_data,
                description=f"{update_request.operation.upper()} bookings in route '{route.route_code}' (ID: {route_id}) - {len(update_request.booking_ids)} bookings affected",
                new_values={
                    "route_id": route_id,
                    "route_code": route.route_code,
                    "operation": update_request.operation,
                    "booking_ids_affected": update_request.booking_ids,
                    "total_bookings_in_route": len(all_booking_ids),
                    "added_count": len(added_booking_ids) if added_booking_ids else 0,
                    "removed_count": len(removed_booking_ids) if removed_booking_ids else 0
                },
                request=request
            )
            logger.info("✅ Audit log created successfully")
        except Exception as audit_error:
            logger.error(f"❌ Failed to create audit log for route update: {str(audit_error)}")

        logger.info("="*80)
        logger.info(f"🎉 ROUTE UPDATE COMPLETED SUCCESSFULLY")
        logger.info(f"   Route ID: {route_id}, Route Code: {route.route_code}")
        logger.info(f"   Total bookings: {len(all_booking_ids)}")
        logger.info(f"   Estimated time: {route.estimated_total_time} mins")
        logger.info(f"   Estimated distance: {route.estimated_total_distance} km")
        logger.info("="*80)

        return ResponseWrapper.success(
            data=RouteWithEstimations(
                route_id=route_id,
                bookings=all_bookings,
                estimations=estimations
            ),
            message=f"Route {route_id} updated successfully"
        )

    except HTTPException:
        logger.error(f"❌ HTTP Exception during route update - rolling back transaction")
        db.rollback()
        raise
    except Exception as e:
        logger.error(f"❌ Unexpected error updating route {route_id} - rolling back transaction")
        db.rollback()
        logger.error(f"Error details: {e}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail=ResponseWrapper.error(
                message="Error updating route",
                error_code="ROUTE_UPDATE_ERROR",
                details={"error": str(e)},
            ),
        )

@router.patch("/{route_id}/update", status_code=status.HTTP_200_OK)
async def update_route_bookings(
    route_id: int,
    update_request: UpdateRouteBookingsRequest,
    request: Request,
    tenant_id: Optional[str] = Query(None, description="Tenant ID"),
    db: Session = Depends(get_db),
    user_data=Depends(PermissionChecker(["route.update"], check_tenant=True)),
    ):
    """
    Update bookings in a route - either with auto-optimization or manual times.
    If optimize=true: reorders and optimizes route automatically.
    If optimize=false: uses provided manual pickup/drop times.
    """
    try:
        user_type = user_data.get("user_type")
        token_tenant_id = user_data.get("tenant_id")

        # Tenant Resolution
        if user_type == "employee":
            tenant_id = token_tenant_id
        elif user_type == "admin":
            if not tenant_id:
                tenant_id = token_tenant_id
            if not tenant_id:
                raise HTTPException(
                    status_code=400,
                    detail=ResponseWrapper.error(
                        message="tenant_id is required for admin users",
                        error_code="TENANT_ID_REQUIRED",
                    ),
                )
        else:
            tenant_id = tenant_id or token_tenant_id

        if not tenant_id:
            raise HTTPException(
                status_code=403,
                detail=ResponseWrapper.error(
                    message="Tenant context not available",
                    error_code="TENANT_ID_MISSING",
                ),
            )

        logger.info(f"[UPDATE_BOOKINGS] Updating route {route_id}, optimize={update_request.optimize}, user={user_data.get('user_id', 'unknown')}")

        if not update_request.bookings:
            raise HTTPException(
                status_code=400,
                detail=ResponseWrapper.error(
                    message="No bookings provided",
                    error_code="NO_BOOKINGS_PROVIDED",
                ),
            )

        # Validate route exists and get shift info
        route_with_shift = (
            db.query(RouteManagement)
            .join(RouteManagementBooking, RouteManagementBooking.route_id == RouteManagement.route_id)
            .join(Booking, RouteManagementBooking.booking_id == Booking.booking_id)
            .join(Shift, Shift.shift_id == Booking.shift_id)
            .filter(
                RouteManagement.route_id == route_id,
                RouteManagement.tenant_id == tenant_id,
            )
            .with_entities(
                RouteManagement,
                Shift.shift_time,
                Shift.log_type
            )
            .first()
        )

        if not route_with_shift:
            raise HTTPException(
                status_code=404,
                detail=ResponseWrapper.error(
                    message=f"Route {route_id} not found",
                    error_code="ROUTE_NOT_FOUND",
                ),
            )

        route, shift_time, shift_type = route_with_shift

        # Validate all bookings belong to this route
        booking_ids = [b.booking_id for b in update_request.bookings]
        existing_bookings = db.query(RouteManagementBooking).filter(
            RouteManagementBooking.route_id == route_id,
            RouteManagementBooking.booking_id.in_(booking_ids)
        ).all()

        if len(existing_bookings) != len(booking_ids):
            raise HTTPException(
                status_code=400,
                detail=ResponseWrapper.error(
                    message="Some bookings do not belong to this route",
                    error_code="INVALID_BOOKINGS",
                ),
            )

        # Delete existing route-booking mappings
        db.query(RouteManagementBooking).filter(
            RouteManagementBooking.route_id == route_id
        ).delete(synchronize_session=False)

        new_mappings = []

        if update_request.optimize:
            # AUTO-OPTIMIZE MODE
            logger.info(f"[UPDATE_BOOKINGS] Auto-optimizing route {route_id}")
            
            # Sort bookings by order
            ordered_bookings = sorted(update_request.bookings, key=lambda x: x.order_id)
            
            # Fetch full booking details
            bookings = []
            for booking_req in ordered_bookings:
                booking_details = get_booking_by_id(booking_req.booking_id, db)
                bookings.append(booking_details)

            # Generate optimal route based on shift type
            from app.services.optimal_roiute_generation import generate_optimal_route, generate_drop_route

            if shift_type == "IN":
                optimized = generate_optimal_route(
                    shift_time=shift_time,
                    group=bookings,
                    drop_lat=bookings[-1]["drop_latitude"],
                    drop_lng=bookings[-1]["drop_longitude"],
                    drop_address=bookings[-1]["drop_location"],
                    use_centroid=False
                )
            else:
                optimized = generate_drop_route(
                    group=bookings,
                    start_time_minutes=datetime_to_minutes(shift_time),
                    office_lat=bookings[0]["pickup_latitude"],
                    office_lng=bookings[0]["pickup_longitude"],
                    office_address=bookings[0]["pickup_location"],
                    optimize_route="false"
                )

            if not optimized:
                raise HTTPException(
                    status_code=500,
                    detail=ResponseWrapper.error(
                        message="Route optimization failed",
                        error_code="OPTIMIZATION_FAILED",
                    ),
                )

            optimized = optimized[0]

            # Update route metrics
            route.estimated_total_time = float(optimized["estimated_time"].split()[0])
            route.estimated_total_distance = float(optimized["estimated_distance"].split()[0])
            route.buffer_time = float(optimized["buffer_time"].split()[0])

            # Create new mappings from optimized data
            for idx, booking in enumerate(optimized["pickup_order"]):
                est_pickup = booking["estimated_pickup_time_formatted"]
                if isinstance(est_pickup, time):
                    est_pickup = est_pickup.strftime("%H:%M:%S")
                
                est_drop = booking.get("estimated_drop_time_formatted")
                if isinstance(est_drop, time):
                    est_drop = est_drop.strftime("%H:%M:%S")
                
                new_mappings.append(RouteManagementBooking(
                    route_id=route_id,
                    booking_id=booking["booking_id"],
                    order_id=idx + 1,
                    estimated_pick_up_time=est_pickup,
                    estimated_drop_time=est_drop,
                    estimated_distance=booking["estimated_distance_km"],
                ))

        else:
            # MANUAL MODE
            logger.info(f"[UPDATE_BOOKINGS] Using manual times for route {route_id}")
            
            # Validate time format
            from datetime import datetime
            for booking in update_request.bookings:
                if not booking.estimated_pick_up_time or not booking.estimated_drop_time:
                    raise HTTPException(
                        status_code=400,
                        detail=ResponseWrapper.error(
                            message=f"Manual times required for booking {booking.booking_id} when optimize=false",
                            error_code="MANUAL_TIMES_REQUIRED",
                        ),
                    )
                try:
                    datetime.strptime(booking.estimated_pick_up_time, "%H:%M:%S")
                    datetime.strptime(booking.estimated_drop_time, "%H:%M:%S")
                except ValueError:
                    raise HTTPException(
                        status_code=400,
                        detail=ResponseWrapper.error(
                            message=f"Invalid time format for booking {booking.booking_id}. Use HH:MM:SS",
                            error_code="INVALID_TIME_FORMAT",
                        ),
                    )

            # Create mappings with manual times
            for booking in update_request.bookings:
                new_mappings.append(RouteManagementBooking(
                    route_id=route_id,
                    booking_id=booking.booking_id,
                    order_id=booking.order_id,
                    estimated_pick_up_time=booking.estimated_pick_up_time,
                    estimated_drop_time=booking.estimated_drop_time,
                    estimated_distance=None  # No calculation for manual times
                ))

        # Add all new mappings
        db.add_all(new_mappings)
        
        # Update booking statuses to SCHEDULED
        db.query(Booking).filter(
            Booking.booking_id.in_(booking_ids),
            Booking.status == BookingStatusEnum.REQUEST
        ).update(
            {
                Booking.status: BookingStatusEnum.SCHEDULED,
                Booking.updated_at: func.now(),
            },
            synchronize_session=False
        )
        
        db.commit()

        # Audit log
        try:
            log_audit(
                db=db,
                tenant_id=tenant_id,
                module="route_management",
                action="UPDATE",
                user_data=user_data,
                description=f"Updated route '{route.route_code}' (ID: {route_id}) - {len(update_request.bookings)} bookings, optimize={update_request.optimize}",
                new_values={
                    "route_id": route_id,
                    "route_code": route.route_code,
                    "bookings_count": len(update_request.bookings),
                    "optimize": update_request.optimize,
                    "booking_updates": [{"booking_id": b.booking_id, "order": b.order_id} for b in update_request.bookings]
                },
                request=request
            )
        except Exception as audit_error:
            logger.error(f"Failed to create audit log: {str(audit_error)}")

        logger.info(f"[UPDATE_BOOKINGS] Successfully updated route {route_id}")

        response_data = [
            {
                "booking_id": rb.booking_id,
                "order_id": rb.order_id,
                "estimated_pick_up_time": rb.estimated_pick_up_time,
                "estimated_drop_time": rb.estimated_drop_time,
                "estimated_distance": rb.estimated_distance,
            }
            for rb in new_mappings
        ]

        return ResponseWrapper.success(
            data=response_data,
            message=f"Route {route_id} updated successfully ({('optimized' if update_request.optimize else 'manual times')})",
        )

    except HTTPException:
        db.rollback()
        raise
    except Exception as e:
        db.rollback()
        logger.error(f"[UPDATE_BOOKINGS] Error updating route {route_id}: {e}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail=ResponseWrapper.error(
                message="Error updating route bookings",
                error_code="UPDATE_BOOKINGS_ERROR",
                details={"error": str(e)},
            ),
        )

@router.post("/new-route", status_code=status.HTTP_201_CREATED)
async def create_route_from_bookings(
    create_request: CreateRouteFromBookingsRequest,
    request: Request,
    tenant_id: Optional[str] = Query(None, description="Tenant ID"),
    db: Session = Depends(get_db),
    user_data=Depends(PermissionChecker(["route.create"], check_tenant=True)),
):
    """
    Create a new route from bookings selected from any existing routes.
    The bookings will remain in their original routes and also be added to the new route.
    """
    try:
        user_type = user_data.get("user_type")
        token_tenant_id = user_data.get("tenant_id")

        # Tenant Resolution
        if user_type == "employee":
            tenant_id = token_tenant_id
        elif user_type == "admin":
            if not tenant_id:
                tenant_id = token_tenant_id
            if not tenant_id:
                raise HTTPException(
                    status_code=400,
                    detail=ResponseWrapper.error(
                        message="tenant_id is required for admin users",
                        error_code="TENANT_ID_REQUIRED",
                    ),
                )
        else:
            tenant_id = tenant_id or token_tenant_id

        if not tenant_id:
            raise HTTPException(
                status_code=403,
                detail=ResponseWrapper.error(
                    message="Tenant context not available",
                    error_code="TENANT_ID_MISSING",
                ),
            )

        logger.info(f"[CREATE_FROM_BOOKINGS] Creating route from {len(create_request.booking_ids)} bookings, user={user_data.get('user_id', 'unknown')}")

        if not create_request.booking_ids:
            raise HTTPException(
                status_code=400,
                detail=ResponseWrapper.error(
                    message="No booking IDs provided",
                    error_code="NO_BOOKINGS_PROVIDED",
                ),
            )

        # Fetch booking details
        bookings = db.query(Booking).filter(
            Booking.booking_id.in_(create_request.booking_ids),
            Booking.tenant_id == tenant_id
        ).all()

        if len(bookings) != len(create_request.booking_ids):
            raise HTTPException(
                status_code=404,
                detail=ResponseWrapper.error(
                    message="Some bookings not found or don't belong to this tenant",
                    error_code="BOOKINGS_NOT_FOUND",
                ),
            )

        # Validate all bookings belong to same shift and date
        shift_ids = set(b.shift_id for b in bookings)
        booking_dates = set(b.booking_date for b in bookings)
        
        if len(shift_ids) > 1:
            raise HTTPException(
                status_code=400,
                detail=ResponseWrapper.error(
                    message="All bookings must belong to the same shift",
                    error_code="MIXED_SHIFTS",
                ),
            )
        
        if len(booking_dates) > 1:
            raise HTTPException(
                status_code=400,
                detail=ResponseWrapper.error(
                    message="All bookings must be for the same date",
                    error_code="MIXED_DATES",
                ),
            )

        shift_id = bookings[0].shift_id
        booking_date = bookings[0].booking_date

        # Get shift info
        shift = get_shift_with_cache(db, shift_id)
        if not shift:
            raise HTTPException(
                status_code=404,
                detail=ResponseWrapper.error(
                    message=f"Shift {shift_id} not found",
                    error_code="SHIFT_NOT_FOUND",
                ),
            )

        logger.info(f"[CREATE_FROM_BOOKINGS] Shift {shift_id}, Date {booking_date}, Type {shift.log_type}")

        # Generate route code
        existing_routes_count = db.query(RouteManagement).filter(
            RouteManagement.tenant_id == tenant_id
        ).count()
        route_code = f"ROUTE-{tenant_id[:4].upper()}-{existing_routes_count + 1:04d}"

        # Prepare booking data for optimization
        booking_data = []
        for booking in bookings:
            booking_data.append({
                "booking_id": booking.booking_id,
                "pickup_latitude": booking.pickup_latitude,
                "pickup_longitude": booking.pickup_longitude,
                "pickup_location": booking.pickup_location,
                "drop_latitude": booking.drop_latitude,
                "drop_longitude": booking.drop_longitude,
                "drop_location": booking.drop_location,
            })

        # Optimize route if requested
        if create_request.optimize:
            logger.info(f"[CREATE_FROM_BOOKINGS] Optimizing new route")
            from app.services.optimal_roiute_generation import generate_optimal_route, generate_drop_route

            if shift.log_type == "IN":
                optimized = generate_optimal_route(
                    shift_time=shift.shift_time,
                    group=booking_data,
                    drop_lat=booking_data[-1]["drop_latitude"],
                    drop_lng=booking_data[-1]["drop_longitude"],
                    drop_address=booking_data[-1]["drop_location"],
                    use_centroid=False
                )
            else:
                optimized = generate_drop_route(
                    group=booking_data,
                    start_time_minutes=datetime_to_minutes(shift.shift_time),
                    office_lat=booking_data[0]["pickup_latitude"],
                    office_lng=booking_data[0]["pickup_longitude"],
                    office_address=booking_data[0]["pickup_location"],
                    optimize_route="true"
                )

            if not optimized:
                raise HTTPException(
                    status_code=500,
                    detail=ResponseWrapper.error(
                        message="Route optimization failed",
                        error_code="OPTIMIZATION_FAILED",
                    ),
                )

            optimized = optimized[0]
            estimated_time = float(optimized["estimated_time"].split()[0])
            estimated_distance = float(optimized["estimated_distance"].split()[0])
            buffer_time = float(optimized["buffer_time"].split()[0])
            optimized_order = optimized["pickup_order"]
        else:
            # No optimization - use provided order
            logger.info(f"[CREATE_FROM_BOOKINGS] Using booking order without optimization")
            estimated_time = 0.0
            estimated_distance = 0.0
            buffer_time = 0.0
            optimized_order = [{"booking_id": b["booking_id"]} for b in booking_data]

        # Create new route
        new_route = RouteManagement(
            route_code=route_code,
            tenant_id=tenant_id,
            estimated_total_time=estimated_time,
            estimated_total_distance=estimated_distance,
            buffer_time=buffer_time,
        )
        db.add(new_route)
        db.flush()

        # Create route-booking mappings
        for idx, booking_info in enumerate(optimized_order):
            booking_id = booking_info["booking_id"]
            
            if create_request.optimize:
                est_pickup = booking_info.get("estimated_pickup_time_formatted")
                if isinstance(est_pickup, time):
                    est_pickup = est_pickup.strftime("%H:%M:%S")
                
                est_drop = booking_info.get("estimated_drop_time_formatted")
                if isinstance(est_drop, time):
                    est_drop = est_drop.strftime("%H:%M:%S")
                
                est_distance = booking_info.get("estimated_distance_km")
            else:
                est_pickup = None
                est_drop = None
                est_distance = None

            db.add(RouteManagementBooking(
                route_id=new_route.route_id,
                booking_id=booking_id,
                order_id=idx + 1,
                estimated_pick_up_time=est_pickup,
                estimated_drop_time=est_drop,
                estimated_distance=est_distance,
            ))

        # Update booking statuses to SCHEDULED
        db.query(Booking).filter(
            Booking.booking_id.in_(create_request.booking_ids),
            Booking.status == BookingStatusEnum.REQUEST
        ).update(
            {
                Booking.status: BookingStatusEnum.SCHEDULED,
                Booking.updated_at: func.now(),
            },
            synchronize_session=False
        )

        db.commit()

        # Audit log
        try:
            log_audit(
                db=db,
                tenant_id=tenant_id,
                module="route_management",
                action="CREATE",
                user_data=user_data,
                description=f"Created route '{route_code}' (ID: {new_route.route_id}) from {len(create_request.booking_ids)} selected bookings",
                new_values={
                    "route_id": new_route.route_id,
                    "route_code": route_code,
                    "booking_ids": create_request.booking_ids,
                    "optimized": create_request.optimize,
                },
                request=request
            )
        except Exception as audit_error:
            logger.error(f"Failed to create audit log: {str(audit_error)}")

        logger.info(f"[CREATE_FROM_BOOKINGS] Successfully created route {new_route.route_id}")

        return ResponseWrapper.success(
            data={
                "route_id": new_route.route_id,
                "route_code": route_code,
                "bookings_count": len(create_request.booking_ids),
                "optimized": create_request.optimize,
            },
            message=f"Route '{route_code}' created successfully from {len(create_request.booking_ids)} bookings",
        )

    except HTTPException:
        db.rollback()
        raise
    except Exception as e:
        db.rollback()
        logger.error(f"[CREATE_FROM_BOOKINGS] Error creating route: {e}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail=ResponseWrapper.error(
                message="Error creating route from bookings",
                error_code="CREATE_ROUTE_ERROR",
                details={"error": str(e)},
            ),
        )


@router.delete("/bulk")
async def bulk_delete_routes(
    request: Request,
    shift_id: int = Query(..., description="Shift ID"),
    route_date: date = Query(..., description="Booking date (YYYY-MM-DD)"),
    tenant_id: Optional[str] = Query(None, description="Tenant ID"),
    db: Session = Depends(get_db),
    user_data=Depends(PermissionChecker(["route.delete"], check_tenant=True)),
):
    """
    Permanently delete all routes and their associated route-booking records
    for a given shift and date, and revert bookings back to 'REQUEST'.
    """
    try:
        logger.info("="*80)
        logger.info("🗑️  BULK ROUTE HARD DELETE INITIATED")
        logger.info(f"📋 Request Parameters:")
        logger.info(f"   Shift ID: {shift_id}")
        logger.info(f"   Route Date: {route_date}")
        logger.info(f"   Tenant Query: {tenant_id}")

        user_type = user_data.get("user_type")
        token_tenant_id = user_data.get("tenant_id")
        user_id = user_data.get("user_id", "unknown")
        
        logger.info(f"👤 User Context: user_id={user_id}, user_type={user_type}, token_tenant={token_tenant_id}")

        # --- Tenant Resolution ---
        logger.info("🔍 Step 1: Resolving tenant context...")
        if user_type == "employee":
            tenant_id = token_tenant_id
            logger.info(f"   Employee user - using token tenant: {tenant_id}")
        elif user_type == "admin":
            if not tenant_id:
                tenant_id = token_tenant_id  # Use token tenant for admin
                logger.info(f"   Admin user - using token tenant: {tenant_id}")
            else:
                logger.info(f"   Admin user - using query tenant: {tenant_id}")
            if not tenant_id:  # Still none? Super admin needs explicit tenant
                logger.error("❌ Super admin must provide explicit tenant_id")
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=ResponseWrapper.error(
                        message="tenant_id is required for super admin users",
                        error_code="TENANT_ID_REQUIRED",
                    ),
                )
        else:
            tenant_id = tenant_id or token_tenant_id
            logger.info(f"   Other user type - resolved tenant: {tenant_id}")

        if not tenant_id:
            logger.error("❌ Tenant context not available")
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=ResponseWrapper.error(
                    message="Tenant context not available",
                    error_code="TENANT_ID_MISSING",
                ),
            )
        
        logger.info(f"✅ Tenant resolved: {tenant_id}")

        # --- Validate Tenant (use cache) ---
        logger.info("🔍 Step 2: Validating tenant...")
        tenant = get_tenant_with_cache(db, tenant_id)
        if not tenant:
            logger.error(f"❌ Tenant {tenant_id} not found in database")
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=ResponseWrapper.error(
                    message=f"Tenant {tenant_id} not found",
                    error_code="TENANT_NOT_FOUND",
                ),
            )
        logger.info(f"✅ Tenant validated: {tenant.tenant_id}")

        logger.info("🔍 Step 3: Querying routes for deletion...")
        logger.info(f"   Tenant: {tenant_id}, Shift: {shift_id}, Date: {route_date}")

        # --- Fetch route IDs ---
        route_query = (
            db.query(RouteManagement.route_id)
            .join(RouteManagementBooking, RouteManagementBooking.route_id == RouteManagement.route_id)
            .join(Booking, RouteManagementBooking.booking_id == Booking.booking_id)
            .filter(
                RouteManagement.tenant_id == tenant_id,
                Booking.shift_id == shift_id,
                Booking.booking_date == route_date,
            )
            .distinct()
        )

        route_ids = [r.route_id for r in route_query.all()]
        logger.info(f"📊 Found {len(route_ids)} route(s) for hard deletion")
        if route_ids:
            logger.info(f"   Route IDs: {route_ids}")

        if not route_ids:
            logger.info("ℹ️  No routes found - nothing to delete")
            logger.info(f"   Shift: {shift_id}, Date: {route_date}")
            logger.info("="*80)
            return ResponseWrapper.success(
                {
                    "deleted_routes_count": 0,
                    "reverted_bookings_count": 0,
                    "shift_id": shift_id,
                    "route_date": str(route_date)
                },
                f"No routes found for shift {shift_id} on {route_date}"
            )

        # --- Fetch affected booking IDs ---
        logger.info("🔍 Step 4: Fetching affected bookings...")
        booking_ids = [
            b.booking_id
            for b in db.query(RouteManagementBooking.booking_id)
            .filter(RouteManagementBooking.route_id.in_(route_ids))
            .distinct()
            .all()
        ]
        logger.info(f"📦 Found {len(booking_ids)} booking(s) affected")
        if booking_ids:
            logger.info(f"   Booking IDs: {booking_ids}")

        # --- Delete child route-booking links ---
        logger.info("🗑️  Step 5: Deleting route-booking mappings...")
        deleted_bookings_count = (
            db.query(RouteManagementBooking)
            .filter(RouteManagementBooking.route_id.in_(route_ids))
            .delete(synchronize_session=False)
        )
        logger.info(f"✅ Deleted {deleted_bookings_count} route-booking mapping(s)")

        # --- Revert booking statuses ---
        logger.info("🔄 Step 6: Reverting booking statuses to REQUEST...")
        reverted_count = 0
        if booking_ids:
            reverted_count = db.query(Booking).filter(
                Booking.booking_id.in_(booking_ids),
                Booking.status == BookingStatusEnum.SCHEDULED,
            ).update(
                {
                    Booking.status: BookingStatusEnum.REQUEST,
                    Booking.boarding_otp: None,
                    Booking.deboarding_otp: None,
                    Booking.escort_otp: None,
                    Booking.updated_at: func.now(),
                    Booking.reason: "Route deleted - reverted to request",
                },
                synchronize_session=False,
            )
            logger.info(f"✅ Reverted {reverted_count} booking(s) to REQUEST status")
            logger.info(f"   Reset boarding_otp, deboarding_otp, escort_otp to NULL")
        else:
            logger.info("ℹ️  No bookings to revert")

        # --- Hard delete routes ---
        logger.info("🗑️  Step 7: Deleting route records...")
        deleted_routes_count = (
            db.query(RouteManagement)
            .filter(RouteManagement.route_id.in_(route_ids))
            .delete(synchronize_session=False)
        )
        logger.info(f"✅ Deleted {deleted_routes_count} route record(s)")

        logger.info("💾 Step 8: Committing transaction to database...")
        db.commit()
        logger.info("✅ Database commit successful")

        # 🔍 Audit Log: Bulk Route Deletion
        logger.info("📝 Step 9: Creating audit log entry...")
        try:
            log_audit(
                db=db,
                tenant_id=tenant_id,
                module="route_management",
                action="HARD_DELETE",
                user_data=user_data,
                description=f"Bulk deleted {deleted_routes_count} routes for shift {shift_id} on {route_date}",
                new_values={
                    "shift_id": shift_id,
                    "route_date": str(route_date),
                    "deleted_route_ids": route_ids,
                    "deleted_routes_count": deleted_routes_count,
                    "reverted_bookings_count": len(booking_ids)
                },
                request=request
            )
            logger.info("✅ Audit log created successfully")
        except Exception as audit_error:
            logger.error(f"❌ Failed to create audit log: {str(audit_error)}")

        logger.info("="*80)
        logger.info("🎉 BULK DELETE COMPLETED SUCCESSFULLY")
        logger.info(f"📊 Summary:")
        logger.info(f"   Routes deleted: {deleted_routes_count}")
        logger.info(f"   Route IDs: {route_ids}")
        logger.info(f"   Route-booking mappings deleted: {deleted_bookings_count}")
        logger.info(f"   Bookings reverted to REQUEST: {len(booking_ids)}")
        logger.info(f"   Shift ID: {shift_id}")
        logger.info(f"   Date: {route_date}")
        logger.info(f"   Tenant: {tenant_id}")
        logger.info("="*80)

        return ResponseWrapper.success(
            data={
                "deleted_route_ids": route_ids,
                "deleted_routes_count": deleted_routes_count,
                "deleted_bookings_count": deleted_bookings_count,
            },
            message=f"Successfully deleted {deleted_routes_count} routes and related records for shift {shift_id} on {route_date}",
        )

    except HTTPException:
        logger.error("❌ HTTP Exception during bulk delete - rolling back transaction")
        db.rollback()
        raise
    except Exception as e:
        logger.error("❌ Unexpected error during bulk hard delete - rolling back transaction")
        logger.error(f"   Tenant: {tenant_id if 'tenant_id' in locals() else 'unknown'}")
        logger.error(f"   Shift: {shift_id}, Date: {route_date}")
        logger.error(f"   User: {user_id if 'user_id' in locals() else 'unknown'}")
        logger.error(f"   Error: {e}", exc_info=True)
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=ResponseWrapper.error(
                message="Error while deleting routes",
                error_code="BULK_ROUTE_DELETE_ERROR",
                details={
                    "tenant_id": tenant_id,
                    "shift_id": shift_id,
                    "date": str(route_date),
                    "error": str(e),
                },
            ),
        )


@router.delete("/{route_id}")
async def delete_route(
    route_id: int,
    request: Request,
    tenant_id: Optional[str] = Query(None, description="Tenant ID"),
    db: Session = Depends(get_db),
    user_data=Depends(PermissionChecker(["route.delete"], check_tenant=True)),
):
    """
    Permanently delete a route and all its associated route-booking links,
    reverting affected bookings back to 'REQUEST'.
    """
    try:
        user_type = user_data.get("user_type")
        token_tenant_id = user_data.get("tenant_id")
        user_id = user_data.get("user_id", "unknown")

        # ---- Determine tenant context ----
        if user_type == "employee":
            tenant_id = token_tenant_id
        elif user_type == "admin":
            if not tenant_id:
                tenant_id = token_tenant_id  # Use token tenant for admin
            if not tenant_id:  # Still none? Super admin needs explicit tenant
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=ResponseWrapper.error(
                        message="tenant_id is required for super admin users",
                        error_code="TENANT_ID_REQUIRED",
                    ),
                )
        else:
            tenant_id = tenant_id or token_tenant_id

        if not tenant_id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=ResponseWrapper.error(
                    message="Tenant context not available",
                    error_code="TENANT_ID_MISSING",
                ),
            )

        logger.info(f"[delete_route] User={user_id} | Tenant={tenant_id} | Route={route_id}")

        # ---- Validate tenant ----
        tenant_exists = (
            db.query(Tenant.tenant_id)
            .filter(Tenant.tenant_id == tenant_id)
            .first()
        )
        if not tenant_exists:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=ResponseWrapper.error(
                    message=f"Tenant {tenant_id} not found",
                    error_code="TENANT_NOT_FOUND",
                ),
            )

        # ---- Fetch route ----
        route = (
            db.query(RouteManagement)
            .filter(RouteManagement.route_id == route_id, RouteManagement.tenant_id == tenant_id)
            .first()
        )

        if not route:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=ResponseWrapper.error(
                    message=f"Route {route_id} not found for tenant {tenant_id}",
                    error_code="ROUTE_NOT_FOUND",
                ),
            )


        # --- Get linked bookings ---
        booking_ids = [
            b.booking_id
            for b in db.query(RouteManagementBooking.booking_id)
            .filter(RouteManagementBooking.route_id == route_id)
            .distinct()
            .all()
        ]

        # --- Delete route-booking mappings ---
        deleted_bookings_count = (
            db.query(RouteManagementBooking)
            .filter(RouteManagementBooking.route_id == route_id)
            .delete(synchronize_session=False)
        )

        # --- Revert bookings ---
        if booking_ids:
            db.query(Booking).filter(
                Booking.booking_id.in_(booking_ids),
                Booking.status == BookingStatusEnum.SCHEDULED,
            ).update(
                {
                    Booking.status: BookingStatusEnum.REQUEST,
                    Booking.boarding_otp: None,
                    Booking.deboarding_otp: None,
                    Booking.escort_otp: None,
                    Booking.updated_at: func.now(),
                    Booking.reason: "Route deleted - reverted to request",
                },
                synchronize_session=False,
            )

        # --- Delete route itself ---
        route_code = route.route_code
        db.delete(route)
        db.commit()

        # 🔍 Audit Log: Route Deletion
        try:
            log_audit(
                db=db,
                tenant_id=tenant_id,
                module="route_management",
                action="DELETE",
                user_data=user_data,
                description=f"Deleted route '{route_code}' (ID: {route_id}) - {len(booking_ids)} bookings reverted to REQUEST",
                new_values={
                    "route_id": route_id,
                    "route_code": route_code,
                    "reverted_bookings_count": len(booking_ids),
                    "reverted_booking_ids": booking_ids
                },
                request=request
            )
        except Exception as audit_error:
            logger.error(f"Failed to create audit log for route deletion: {str(audit_error)}")

        logger.info(
            f"✅ Route {route_id} deleted. {len(booking_ids)} bookings reverted to REQUEST."
        )

        return ResponseWrapper.success(
            data={
                "deleted_route_id": route_id,
                "reverted_bookings_count": len(booking_ids),
            },
            message=f"Route {route_id} deleted successfully, reverted {len(booking_ids)} bookings to REQUEST",
        )

    except HTTPException:
        db.rollback()
        raise
    except Exception as e:
        db.rollback()
        logger.exception(f"[delete_route] Unexpected error deleting route {route_id}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=ResponseWrapper.error(
                message=f"Error deleting route {route_id}",
                error_code="ROUTE_DELETE_ERROR",
                details={"error": str(e)},
            ),
        )


@router.put("/{route_id}/assign-escort")
async def assign_escort_to_route(
    route_id: int = Path(..., description="Route ID to assign escort to"),
    escort_id: int = Query(..., description="Escort ID to assign"),
    tenant_id: Optional[str] = Query(None, description="Tenant ID for multi-tenant setups"),
    db: Session = Depends(get_db),
    user_data=Depends(PermissionChecker(["route.update"], check_tenant=True)),
    request: Request = None,
):
    """
    Assign an escort to a route.
    """
    try:
        logger.info(f"Assigning escort {escort_id} to route {route_id}")

        user_type = user_data.get("user_type")
        token_tenant_id = user_data.get("tenant_id")

        # ---- Tenant Resolution ----
        if user_type == "employee":
            tenant_id = token_tenant_id
        elif user_type == "admin" and not tenant_id:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=ResponseWrapper.error(
                    message="tenant_id is required for admin users",
                    error_code="TENANT_ID_REQUIRED",
                ),
            )
        else:
            tenant_id = tenant_id or token_tenant_id

        if not tenant_id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=ResponseWrapper.error(
                    message="Tenant context not available",
                    error_code="TENANT_ID_REQUIRED",
                ),
            )

        # ---- Validate Route ----
        route = (
            db.query(RouteManagement)
            .filter(RouteManagement.route_id == route_id, RouteManagement.tenant_id == tenant_id)
            .first()
        )
        if not route:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=ResponseWrapper.error(
                    message="Route not found for this tenant",
                    error_code="ROUTE_NOT_FOUND",
                ),
            )

        # ---- Validate Escort ----
        from app.models.escort import Escort
        escort = (
            db.query(Escort)
            .join(Vendor, Vendor.vendor_id == Escort.vendor_id)
            .filter(
                Escort.escort_id == escort_id,
                Vendor.tenant_id == tenant_id,
            )
            .first()
        )
        if not escort:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=ResponseWrapper.error(
                    message="Escort not found for this tenant",
                    error_code="ESCORT_NOT_FOUND",
                ),
            )

        # ---- Check if escort is available ----
        if not escort.is_available:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=ResponseWrapper.error(
                    message="Escort is not available",
                    error_code="ESCORT_NOT_AVAILABLE",
                ),
            )

        # ---- Assign escort to route ----
        old_escort_id = route.assigned_escort_id
        route.assigned_escort_id = escort_id
        route.updated_at = get_current_ist_time()

        db.commit()

        # 🔍 Audit Log: Escort Assignment
        try:
            log_audit(
                db=db,
                tenant_id=tenant_id,
                module="route_management",
                action="UPDATE",
                user_data=user_data,
                description=f"Assigned escort {escort_id} to route {route_id}",
                old_values={"assigned_escort_id": old_escort_id},
                new_values={
                    "assigned_escort_id": escort_id,
                    "route_id": route_id,
                },
                request=request
            )
        except Exception as audit_error:
            logger.error(f"Failed to create audit log for escort assignment: {str(audit_error)}")

        logger.info(
            f"✅ Escort {escort_id} assigned to route {route_id}."
        )

        return ResponseWrapper.success(
            data={
                "route_id": route_id,
                "assigned_escort_id": escort_id,
            },
            message=f"Escort assigned to route successfully.",
        )

    except HTTPException:
        db.rollback()
        raise
    except Exception as e:
        db.rollback()
        logger.exception(f"[assign_escort_to_route] Unexpected error assigning escort {escort_id} to route {route_id}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=ResponseWrapper.error(
                message=f"Error assigning escort to route",
                error_code="ESCORT_ASSIGNMENT_ERROR",
                details={"error": str(e)},
            ),
        )


