from fastapi import APIRouter, Depends, HTTPException, Query, status as http_status
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session
from sqlalchemy import and_, or_, func
from typing import Optional, List
from datetime import date, datetime
from io import BytesIO
import openpyxl
from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
from openpyxl.utils import get_column_letter

from app.database.session import get_db
from app.models.booking import Booking, BookingStatusEnum
from app.models.route_management import RouteManagement, RouteManagementBooking, RouteManagementStatusEnum
from app.models.route_delay_event import RouteDelayEvent
from app.models.driver import Driver
from app.models.vehicle import Vehicle
from app.models.vendor import Vendor
from app.models.employee import Employee
from app.models.shift import Shift
from app.models.tenant import Tenant
from app.utils.response_utils import ResponseWrapper, handle_db_error
from common_utils.auth.permission_checker import PermissionChecker
from common_utils import get_current_ist_time
from app.core.logging_config import get_logger
from app.utils.cache_manager import cached

logger = get_logger(__name__)

router = APIRouter(prefix="/reports", tags=["reports"])


def validate_date_range(start_date: date, end_date: date):
    """Validate that date range is valid and not too large"""
    if start_date > end_date:
        raise HTTPException(
            status_code=http_status.HTTP_400_BAD_REQUEST,
            detail=ResponseWrapper.error(
                message="start_date cannot be after end_date",
                error_code="INVALID_DATE_RANGE"
            )
        )
    
    # Limit to 90 days to prevent performance issues
    date_diff = (end_date - start_date).days
    if date_diff > 90:
        raise HTTPException(
            status_code=http_status.HTTP_400_BAD_REQUEST,
            detail=ResponseWrapper.error(
                message="Date range cannot exceed 90 days",
                error_code="DATE_RANGE_TOO_LARGE"
            )
        )


def style_excel_report(ws, headers):
    """Apply professional styling to Excel worksheet"""
    # Header styling
    header_fill = PatternFill(start_color="366092", end_color="366092", fill_type="solid")
    header_font = Font(bold=True, color="FFFFFF", size=11)
    border = Border(
        left=Side(style='thin'),
        right=Side(style='thin'),
        top=Side(style='thin'),
        bottom=Side(style='thin')
    )
    
    # Style header row
    for col_num, header in enumerate(headers, 1):
        cell = ws.cell(row=1, column=col_num)
        cell.value = header
        cell.fill = header_fill
        cell.font = header_font
        cell.alignment = Alignment(horizontal='center', vertical='center', wrap_text=True)
        cell.border = border
        
        # Auto-adjust column width
        ws.column_dimensions[get_column_letter(col_num)].width = max(len(str(header)) + 5, 15)
    
    # Freeze header row
    ws.freeze_panes = 'A2'
    
    return ws


@router.get("/bookings/export", status_code=http_status.HTTP_200_OK)
async def export_bookings_report(
    start_date: date = Query(..., description="Start date for the report (YYYY-MM-DD)"),
    end_date: date = Query(..., description="End date for the report (YYYY-MM-DD)"),
    tenant_id: Optional[str] = Query(None, description="Tenant ID"),
    shift_id: Optional[int] = Query(None, description="Filter by shift ID"),
    booking_status: Optional[List[BookingStatusEnum]] = Query(None, description="Filter by booking status (can select multiple)"),
    route_status: Optional[List[RouteManagementStatusEnum]] = Query(None, description="Filter by route status (can select multiple)"),
    vendor_id: Optional[int] = Query(None, description="Filter by vendor ID"),
    include_unrouted: Optional[bool] = Query(True, description="Include bookings without routes"),
    db: Session = Depends(get_db),
    user_data=Depends(PermissionChecker(["report.read"], check_tenant=True)),
):
    """
    Generate comprehensive Excel report for bookings with route and assignment details.
    
    Filters:
    - Date range (required, max 90 days)
    - Shift ID
    - Booking status (REQUEST, SCHEDULED, ONGOING, COMPLETED, CANCELLED, NO_SHOW, EXPIRED)
    - Route status (PLANNED, VENDOR_ASSIGNED, DRIVER_ASSIGNED, ONGOING, COMPLETED, CANCELLED)
    - Vendor ID
    - Include/exclude unrouted bookings
    
    Returns: Excel file with detailed booking information
    """
    try:
        user_type = user_data.get("user_type")
        token_tenant_id = user_data.get("tenant_id")
        token_vendor_id = user_data.get("vendor_id")
        user_id = user_data.get("user_id")

        logger.info(
            f"[export_bookings_report] user_id={user_id}, user_type={user_type}, "
            f"date_range={start_date} to {end_date}, shift={shift_id}, status={booking_status}"
        )

        # --- Tenant Resolution ---
        if user_type == "employee":
            tenant_id = token_tenant_id
        elif user_type == "vendor":
            tenant_id = token_tenant_id
            vendor_id = token_vendor_id  # Force vendor to only see their data
        elif user_type == "admin":
            if not tenant_id:
                raise HTTPException(
                    status_code=http_status.HTTP_400_BAD_REQUEST,
                    detail=ResponseWrapper.error(
                        message="tenant_id is required for admin users",
                        error_code="TENANT_ID_REQUIRED"
                    )
                )
        else:
            raise HTTPException(
                status_code=http_status.HTTP_403_FORBIDDEN,
                detail=ResponseWrapper.error(
                    message="Insufficient permissions to generate reports",
                    error_code="FORBIDDEN"
                )
            )

        if not tenant_id:
            raise HTTPException(
                status_code=http_status.HTTP_403_FORBIDDEN,
                detail=ResponseWrapper.error(
                    message="Tenant context not available",
                    error_code="TENANT_ID_REQUIRED"
                )
            )

        # --- Validate Date Range ---
        validate_date_range(start_date, end_date)

        # --- Validate Tenant (use cache) ---
        from app.utils.cache_manager import get_tenant_with_cache, get_shift_with_cache
        tenant = get_tenant_with_cache(db, tenant_id)
        if not tenant:
            raise HTTPException(
                status_code=http_status.HTTP_404_NOT_FOUND,
                detail=ResponseWrapper.error(
                    message=f"Tenant {tenant_id} not found",
                    error_code="TENANT_NOT_FOUND"
                )
            )

        # --- Validate Shift if provided (use cache) ---
        if shift_id:
            shift = get_shift_with_cache(db, tenant_id, shift_id)
            if not shift:
                raise HTTPException(
                    status_code=http_status.HTTP_404_NOT_FOUND,
                    detail=ResponseWrapper.error(
                        message=f"Shift {shift_id} not found for this tenant",
                        error_code="SHIFT_NOT_FOUND"
                    )
                )

        # --- Build Query ---
        query = (
            db.query(
                Booking.booking_id,
                Booking.booking_date,
                Booking.status.label('booking_status'),
                Booking.pickup_location,
                Booking.drop_location,
                Booking.pickup_latitude,
                Booking.pickup_longitude,
                Booking.drop_latitude,
                Booking.drop_longitude,
                Booking.reason,
                Booking.employee_id,
                Booking.employee_code,
                Employee.name.label('employee_name'),
                Employee.phone.label('employee_phone'),
                Employee.gender.label('employee_gender'),
                Shift.shift_id,
                Shift.shift_code,
                Shift.shift_time,
                Shift.log_type.label('shift_type'),
                RouteManagement.route_id,
                RouteManagement.route_code,
                RouteManagement.status.label('route_status'),
                RouteManagementBooking.order_id,
                RouteManagementBooking.estimated_pick_up_time,
                RouteManagementBooking.estimated_drop_time,
                RouteManagementBooking.actual_pick_up_time,
                RouteManagementBooking.actual_drop_time,
                RouteManagementBooking.estimated_distance,
                Driver.driver_id,
                Driver.name.label('driver_name'),
                Driver.phone.label('driver_phone'),
                Driver.license_number,
                Vehicle.vehicle_id,
                Vehicle.rc_number,
                Vendor.vendor_id,
                Vendor.name.label('vendor_name'),
                Vendor.phone.label('vendor_phone')
            )
            .outerjoin(Employee, Booking.employee_id == Employee.employee_id)
            .join(Shift, Booking.shift_id == Shift.shift_id)
            .outerjoin(RouteManagementBooking, Booking.booking_id == RouteManagementBooking.booking_id)
            .outerjoin(RouteManagement, RouteManagementBooking.route_id == RouteManagement.route_id)
            .outerjoin(Driver, RouteManagement.assigned_driver_id == Driver.driver_id)
            .outerjoin(Vehicle, RouteManagement.assigned_vehicle_id == Vehicle.vehicle_id)
            .outerjoin(Vendor, RouteManagement.assigned_vendor_id == Vendor.vendor_id)
            .filter(
                Booking.tenant_id == tenant_id,
                Booking.booking_date >= start_date,
                Booking.booking_date <= end_date
            )
        )

        # --- Apply Filters ---
        if shift_id:
            query = query.filter(Booking.shift_id == shift_id)

        if booking_status:
            query = query.filter(Booking.status.in_(booking_status))

        if route_status:
            query = query.filter(RouteManagement.status.in_(route_status))

        if vendor_id:
            query = query.filter(RouteManagement.assigned_vendor_id == vendor_id)

        if not include_unrouted:
            # Only include bookings that have routes
            query = query.filter(RouteManagement.route_id.isnot(None))

        # Order by date, shift, and route
        query = query.order_by(
            Booking.booking_date.desc(),
            Shift.shift_id,
            RouteManagement.route_id,
            RouteManagementBooking.order_id
        )

        # --- Execute Query ---
        results = query.all()

        if not results:
            raise HTTPException(
                status_code=http_status.HTTP_404_NOT_FOUND,
                detail=ResponseWrapper.error(
                    message="No bookings found matching the specified filters",
                    error_code="NO_DATA_FOUND"
                )
            )

        logger.info(f"[export_bookings_report] Found {len(results)} records")

        # --- Create Excel Workbook ---
        wb = openpyxl.Workbook()
        ws = wb.active
        ws.title = "Bookings Report"

        # Define headers
        headers = [
            "Booking ID",
            "Booking Date",
            "Booking Status",
            "Employee ID",
            "Employee Code",
            "Employee Name",
            "Employee Phone",
            "Employee Gender",
            "Shift ID",
            "Shift Code",
            "Shift Time",
            "Shift Type",
            "Pickup Location",
            "Pickup Latitude",
            "Pickup Longitude",
            "Drop Location",
            "Drop Latitude",
            "Drop Longitude",
            "Route ID",
            "Route Code",
            "Route Status",
            "Stop Order",
            "Estimated Pickup Time",
            "Estimated Drop Time",
            "Actual Pickup Time",
            "Actual Drop Time",
            "Distance (km)",
            "Driver ID",
            "Driver Name",
            "Driver Phone",
            "Driver License",
            "Vehicle ID",
            "Vehicle Number",
            "Vendor ID",
            "Vendor Name",
            "Vendor Phone",
            "Reason"
        ]

        # Apply styling
        ws = style_excel_report(ws, headers)

        # --- Populate Data ---
        for row_num, record in enumerate(results, 2):
            ws.cell(row=row_num, column=1, value=record.booking_id)
            ws.cell(row=row_num, column=2, value=record.booking_date.strftime('%Y-%m-%d') if record.booking_date else '')
            ws.cell(row=row_num, column=3, value=record.booking_status.value if record.booking_status else '')
            ws.cell(row=row_num, column=4, value=record.employee_id)
            ws.cell(row=row_num, column=5, value=record.employee_code or '')
            ws.cell(row=row_num, column=6, value=record.employee_name or '')
            ws.cell(row=row_num, column=7, value=record.employee_phone or '')
            ws.cell(row=row_num, column=8, value=record.employee_gender or '')
            ws.cell(row=row_num, column=9, value=record.shift_id)
            ws.cell(row=row_num, column=10, value=record.shift_code or '')
            ws.cell(row=row_num, column=11, value=str(record.shift_time) if record.shift_time else '')
            ws.cell(row=row_num, column=12, value=record.shift_type.value if record.shift_type else '')
            ws.cell(row=row_num, column=13, value=record.pickup_location or '')
            ws.cell(row=row_num, column=14, value=record.pickup_latitude)
            ws.cell(row=row_num, column=15, value=record.pickup_longitude)
            ws.cell(row=row_num, column=16, value=record.drop_location or '')
            ws.cell(row=row_num, column=17, value=record.drop_latitude)
            ws.cell(row=row_num, column=18, value=record.drop_longitude)
            ws.cell(row=row_num, column=19, value=record.route_id or '')
            ws.cell(row=row_num, column=20, value=record.route_code or '')
            ws.cell(row=row_num, column=21, value=record.route_status.value if record.route_status else '')
            ws.cell(row=row_num, column=22, value=record.order_id if record.order_id is not None else '')
            ws.cell(row=row_num, column=23, value=str(record.estimated_pick_up_time) if record.estimated_pick_up_time else '')
            ws.cell(row=row_num, column=24, value=str(record.estimated_drop_time) if record.estimated_drop_time else '')
            ws.cell(row=row_num, column=25, value=str(record.actual_pick_up_time) if record.actual_pick_up_time else '')
            ws.cell(row=row_num, column=26, value=str(record.actual_drop_time) if record.actual_drop_time else '')
            ws.cell(row=row_num, column=27, value=record.estimated_distance)
            ws.cell(row=row_num, column=28, value=record.driver_id or '')
            ws.cell(row=row_num, column=29, value=record.driver_name or '')
            ws.cell(row=row_num, column=30, value=record.driver_phone or '')
            ws.cell(row=row_num, column=31, value=record.license_number or '')
            ws.cell(row=row_num, column=32, value=record.vehicle_id or '')
            ws.cell(row=row_num, column=33, value=record.rc_number or '')
            ws.cell(row=row_num, column=34, value=record.vendor_id or '')
            ws.cell(row=row_num, column=35, value=record.vendor_name or '')
            ws.cell(row=row_num, column=36, value=record.vendor_phone or '')
            ws.cell(row=row_num, column=37, value=record.reason or '')

        # --- Create Summary Sheet ---
        summary_ws = wb.create_sheet(title="Summary")
        
        # Summary statistics
        total_bookings = len(results)
        status_counts = {}
        for record in results:
            status = record.booking_status.value if record.booking_status else 'UNKNOWN'
            status_counts[status] = status_counts.get(status, 0) + 1

        routed_bookings = sum(1 for r in results if r.route_id is not None)
        unrouted_bookings = total_bookings - routed_bookings

        summary_data = [
            ["Report Summary", ""],
            ["Generated On", get_current_ist_time().strftime('%Y-%m-%d %H:%M:%S')],
            ["Generated By", f"User ID: {user_id}"],
            ["Tenant ID", tenant_id],
            ["Tenant Name", tenant.name],
            ["Date Range", f"{start_date} to {end_date}"],
            ["", ""],
            ["Total Bookings", total_bookings],
            ["Routed Bookings", routed_bookings],
            ["Unrouted Bookings", unrouted_bookings],
            ["", ""],
            ["Booking Status Breakdown", "Count"]
        ]

        for status, count in sorted(status_counts.items()):
            summary_data.append([status, count])

        for row_num, row_data in enumerate(summary_data, 1):
            for col_num, value in enumerate(row_data, 1):
                cell = summary_ws.cell(row=row_num, column=col_num, value=value)
                if row_num == 1 or (row_num == 12 and col_num <= 2):
                    cell.font = Font(bold=True, size=12)

        # Adjust column widths
        summary_ws.column_dimensions['A'].width = 30
        summary_ws.column_dimensions['B'].width = 30

        # --- Save to BytesIO ---
        output = BytesIO()
        wb.save(output)
        output.seek(0)

        # --- Generate filename ---
        filename = f"bookings_report_{tenant_id}_{start_date}_to_{end_date}.xlsx"

        logger.info(f"[export_bookings_report] Generated report with {len(results)} records for user {user_id}")

        # --- Return as StreamingResponse ---
        return StreamingResponse(
            output,
            media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            headers={
                "Content-Disposition": f'attachment; filename="{filename}"',
                "Content-Type": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                "Access-Control-Expose-Headers": "Content-Disposition"
            }
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.exception(f"[export_bookings_report] Error generating report: {e}")
        raise handle_db_error(e)


@router.get("/bookings/analytics", status_code=http_status.HTTP_200_OK)
@cached(ttl_seconds=300, key_prefix="analytics")  # Cache for 5 minutes
async def get_bookings_analytics(
    start_date: date = Query(..., description="Start date for analytics (YYYY-MM-DD)"),
    end_date: date = Query(..., description="End date for analytics (YYYY-MM-DD)"),
    tenant_id: Optional[str] = Query(None, description="Tenant ID"),
    shift_id: Optional[int] = Query(None, description="Filter by shift ID"),
    db: Session = Depends(get_db),
    user_data=Depends(PermissionChecker(["report.read"], check_tenant=True)),
):
    """
    Get analytics summary for bookings within a date range.
    
    Returns JSON with:
    - Total bookings by status
    - Routed vs unrouted breakdown
    - Route status distribution
    - Completion rates
    - Daily breakdown
    """
    try:
        user_type = user_data.get("user_type")
        token_tenant_id = user_data.get("tenant_id")
        user_id = user_data.get("user_id")

        logger.info(
            f"[get_bookings_analytics] user_id={user_id}, date_range={start_date} to {end_date}"
        )

        # --- Tenant Resolution ---
        if user_type == "employee":
            tenant_id = token_tenant_id
        elif user_type == "vendor":
            tenant_id = token_tenant_id
        elif user_type == "admin":
            if not tenant_id:
                raise HTTPException(
                    status_code=http_status.HTTP_400_BAD_REQUEST,
                    detail=ResponseWrapper.error(
                        message="tenant_id is required for admin users",
                        error_code="TENANT_ID_REQUIRED"
                    )
                )
        else:
            raise HTTPException(
                status_code=http_status.HTTP_403_FORBIDDEN,
                detail=ResponseWrapper.error(
                    message="Insufficient permissions",
                    error_code="FORBIDDEN"
                )
            )

        if not tenant_id:
            raise HTTPException(
                status_code=http_status.HTTP_403_FORBIDDEN,
                detail=ResponseWrapper.error(
                    message="Tenant context not available",
                    error_code="TENANT_ID_REQUIRED"
                )
            )

        # --- Validate Date Range ---
        validate_date_range(start_date, end_date)

        # --- Base Query ---
        base_query = db.query(Booking).filter(
            Booking.tenant_id == tenant_id,
            Booking.booking_date >= start_date,
            Booking.booking_date <= end_date
        )

        if shift_id:
            base_query = base_query.filter(Booking.shift_id == shift_id)

        # --- Booking Status Breakdown ---
        status_breakdown = (
            base_query
            .with_entities(
                Booking.status,
                func.count(Booking.booking_id).label('count')
            )
            .group_by(Booking.status)
            .all()
        )

        status_counts = {
            status.value if status else 'UNKNOWN': count
            for status, count in status_breakdown
        }

        # --- Routed vs Unrouted ---
        total_bookings = base_query.count()
        
        routed_count = (
            base_query
            .join(RouteManagementBooking, Booking.booking_id == RouteManagementBooking.booking_id)
            .join(RouteManagement, RouteManagementBooking.route_id == RouteManagement.route_id)
            .filter(RouteManagement.tenant_id == tenant_id)
            .distinct()
            .count()
        )
        
        unrouted_count = total_bookings - routed_count

        # --- Route Status Breakdown (for routed bookings) ---
        route_status_breakdown = (
            db.query(
                RouteManagement.status,
                func.count(func.distinct(Booking.booking_id)).label('booking_count')
            )
            .join(RouteManagementBooking, RouteManagement.route_id == RouteManagementBooking.route_id)
            .join(Booking, RouteManagementBooking.booking_id == Booking.booking_id)
            .filter(
                RouteManagement.tenant_id == tenant_id,
                Booking.booking_date >= start_date,
                Booking.booking_date <= end_date
            )
            .group_by(RouteManagement.status)
            .all()
        )

        route_status_counts = {
            status.value if status else 'UNKNOWN': count
            for status, count in route_status_breakdown
        }

        # --- Daily Breakdown ---
        daily_breakdown = (
            base_query
            .with_entities(
                Booking.booking_date,
                Booking.status,
                func.count(Booking.booking_id).label('count')
            )
            .group_by(Booking.booking_date, Booking.status)
            .order_by(Booking.booking_date)
            .all()
        )

        daily_data = {}
        for booking_date, status, count in daily_breakdown:
            date_str = booking_date.strftime('%Y-%m-%d')
            if date_str not in daily_data:
                daily_data[date_str] = {
                    "booking_status": {},
                    "vendor_assigned": 0,
                    "driver_assigned": 0
                }
            status_str = status.value if status else 'UNKNOWN'
            daily_data[date_str]["booking_status"][status_str] = count

        # --- Daily Vendor and Driver Assignment Breakdown ---
        assignment_daily_breakdown = (
            db.query(
                Booking.booking_date,
                func.count(
                    func.distinct(
                        Booking.booking_id
                    ).filter(RouteManagement.assigned_vendor_id.isnot(None))
                ).label("vendor_assigned_count"),
                func.count(
                    func.distinct(
                        Booking.booking_id
                    ).filter(RouteManagement.assigned_driver_id.isnot(None))
                ).label("driver_assigned_count"),
            )
            .join(RouteManagementBooking, Booking.booking_id == RouteManagementBooking.booking_id)
            .join(RouteManagement, RouteManagementBooking.route_id == RouteManagement.route_id)
            .filter(
                RouteManagement.tenant_id == tenant_id,
                Booking.booking_date >= start_date,
                Booking.booking_date <= end_date,
            )
            .group_by(Booking.booking_date)
            .all()
        )
        for booking_date, vendor_count, driver_count in assignment_daily_breakdown:
            date_str = booking_date.strftime('%Y-%m-%d')
            if date_str not in daily_data:
                daily_data[date_str] = {
                    "booking_status": {},
                    "vendor_assigned": 0,
                    "driver_assigned": 0,
                }
            daily_data[date_str]["vendor_assigned"] = vendor_count or 0
            daily_data[date_str]["driver_assigned"] = driver_count or 0

        # --- Completion Rate ---
        completed_count = status_counts.get('Completed', 0)
        completion_rate = (completed_count / total_bookings * 100) if total_bookings > 0 else 0

        # --- Vendor Assignment Count ---
        vendor_assigned_count = (
            db.query(func.count(func.distinct(Booking.booking_id)))
            .join(RouteManagementBooking, Booking.booking_id == RouteManagementBooking.booking_id)
            .join(RouteManagement, RouteManagementBooking.route_id == RouteManagement.route_id)
            .filter(
                RouteManagement.tenant_id == tenant_id,
                RouteManagement.assigned_vendor_id.isnot(None),
                Booking.booking_date >= start_date,
                Booking.booking_date <= end_date
            )
            .scalar() or 0
        )

        # --- Driver Assignment Count ---
        driver_assigned_count = (
            db.query(func.count(func.distinct(Booking.booking_id)))
            .join(RouteManagementBooking, Booking.booking_id == RouteManagementBooking.booking_id)
            .join(RouteManagement, RouteManagementBooking.route_id == RouteManagement.route_id)
            .filter(
                RouteManagement.tenant_id == tenant_id,
                RouteManagement.assigned_driver_id.isnot(None),
                Booking.booking_date >= start_date,
                Booking.booking_date <= end_date
            )
            .scalar() or 0
        )

        # --- Total Unique Shifts ---
        total_shifts = (
            base_query
            .with_entities(func.count(func.distinct(Booking.shift_id)))
            .scalar() or 0
        )

        # --- Response ---
        analytics = {
            "date_range": {
                "start_date": start_date.strftime('%Y-%m-%d'),
                "end_date": end_date.strftime('%Y-%m-%d')
            },
            "total_bookings": total_bookings,
            "total_shifts": total_shifts,
            "booking_status_breakdown": status_counts,
            "routing_summary": {
                "routed": routed_count,
                "unrouted": unrouted_count,
                "routing_percentage": (routed_count / total_bookings * 100) if total_bookings > 0 else 0
            },
            "assignment_summary": {
                "vendor_assigned": vendor_assigned_count,
                "driver_assigned": driver_assigned_count,
                "vendor_assignment_percentage": (vendor_assigned_count / total_bookings * 100) if total_bookings > 0 else 0,
                "driver_assignment_percentage": (driver_assigned_count / total_bookings * 100) if total_bookings > 0 else 0
            },
            "route_status_breakdown": route_status_counts,
            "completion_rate": round(completion_rate, 2),
            "daily_breakdown": daily_data
        }

        return ResponseWrapper.success(
            data=analytics,
            message="Analytics generated successfully"
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.exception(f"[get_bookings_analytics] Error: {e}")
        raise handle_db_error(e)


# ---------------------------------------------------------------------------
# Feature 6: OTA / OTD Delay Reports
# ---------------------------------------------------------------------------

@router.get("/delays", status_code=http_status.HTTP_200_OK)
async def get_delay_report(
    start_date: date = Query(..., description="Start date (YYYY-MM-DD)"),
    end_date: date = Query(..., description="End date (YYYY-MM-DD)"),
    delay_type: Optional[str] = Query(None, description="Filter: LATE | EARLY | ON_TIME"),
    tenant_id: Optional[str] = Query(None, description="Tenant ID (admin only; employees use token)"),
    db: Session = Depends(get_db),
    ctx=Depends(PermissionChecker(["report.read"], check_tenant=True)),
):
    """
    Return a summary of OTD delay-tagged routes for the given date range.

    Each row includes route metadata and the latest delay tag.
    Results are ordered by route creation date descending.

    Query params
    ------------
    start_date  – inclusive lower bound on route.created_at date
    end_date    – inclusive upper bound
    delay_type  – optional filter (LATE | EARLY | ON_TIME)
    tenant_id   – admin-only override; otherwise resolved from token
    """
    try:
        user_data = ctx
        token_tenant_id = user_data.get("tenant_id")

        # Resolve tenant
        resolved_tenant_id = tenant_id or token_tenant_id
        if not resolved_tenant_id:
            raise HTTPException(
                status_code=http_status.HTTP_403_FORBIDDEN,
                detail=ResponseWrapper.error(
                    message="Tenant context not available",
                    error_code="TENANT_ID_MISSING",
                ),
            )

        validate_date_range(start_date, end_date)

        start_dt = datetime.combine(start_date, datetime.min.time())
        end_dt = datetime.combine(end_date, datetime.max.time().replace(microsecond=0))

        query = (
            db.query(RouteManagement)
            .filter(
                RouteManagement.tenant_id == resolved_tenant_id,
                RouteManagement.delay_tagged_at.isnot(None),
                RouteManagement.delay_tagged_at >= start_dt,
                RouteManagement.delay_tagged_at <= end_dt,
            )
        )

        if delay_type:
            query = query.filter(RouteManagement.delay_type == delay_type.upper())

        routes = query.order_by(RouteManagement.delay_tagged_at.desc()).all()

        rows = []
        for r in routes:
            rows.append({
                "route_id": r.route_id,
                "route_code": r.route_code,
                "shift_id": r.shift_id,
                "status": r.status.value if r.status else None,
                "assigned_driver_id": r.assigned_driver_id,
                "actual_start_time": r.actual_start_time.isoformat() if r.actual_start_time else None,
                "actual_end_time": r.actual_end_time.isoformat() if r.actual_end_time else None,
                "estimated_total_time_min": r.estimated_total_time,
                "delay_type": r.delay_type,
                "delay_minutes": r.delay_minutes,
                "delay_tagged_at": r.delay_tagged_at.isoformat() if r.delay_tagged_at else None,
                "ota_grace_minutes": r.ota_grace_minutes,
            })

        # Aggregate summary
        total = len(rows)
        late_count = sum(1 for row in rows if row["delay_type"] == "LATE")
        early_count = sum(1 for row in rows if row["delay_type"] == "EARLY")
        on_time_count = sum(1 for row in rows if row["delay_type"] == "ON_TIME")
        avg_delay = (
            round(sum(row["delay_minutes"] for row in rows if row["delay_minutes"] is not None) / total, 1)
            if total else 0
        )

        return ResponseWrapper.success(
            data={
                "summary": {
                    "total_routes_tagged": total,
                    "late": late_count,
                    "early": early_count,
                    "on_time": on_time_count,
                    "average_delay_minutes": avg_delay,
                },
                "routes": rows,
            },
            message="Delay report generated successfully",
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.exception("[get_delay_report] Error: %s", e)
        raise handle_db_error(e)


@router.get("/delays/{route_id}", status_code=http_status.HTTP_200_OK)
async def get_route_delay_detail(
    route_id: int,
    tenant_id: Optional[str] = Query(None, description="Tenant ID (admin only)"),
    db: Session = Depends(get_db),
    ctx=Depends(PermissionChecker(["report.read"], check_tenant=True)),
):
    """
    Return the full delay event history for a specific route.

    Each row in `events` corresponds to one RouteDelayEvent (OTA or OTD).
    Also returns the summary delay fields from the route itself.
    """
    try:
        user_data = ctx
        token_tenant_id = user_data.get("tenant_id")
        resolved_tenant_id = tenant_id or token_tenant_id

        if not resolved_tenant_id:
            raise HTTPException(
                status_code=http_status.HTTP_403_FORBIDDEN,
                detail=ResponseWrapper.error(
                    message="Tenant context not available",
                    error_code="TENANT_ID_MISSING",
                ),
            )

        route = (
            db.query(RouteManagement)
            .filter(
                RouteManagement.route_id == route_id,
                RouteManagement.tenant_id == resolved_tenant_id,
            )
            .first()
        )
        if not route:
            raise HTTPException(
                status_code=http_status.HTTP_404_NOT_FOUND,
                detail=ResponseWrapper.error(
                    message=f"Route {route_id} not found",
                    error_code="ROUTE_NOT_FOUND",
                ),
            )

        events = (
            db.query(RouteDelayEvent)
            .filter(RouteDelayEvent.route_id == route_id)
            .order_by(RouteDelayEvent.tagged_at.asc())
            .all()
        )

        event_list = [
            {
                "id": ev.id,
                "event_kind": ev.event_kind,
                "delay_type": ev.delay_type,
                "delay_minutes": ev.delay_minutes,
                "notes": ev.notes,
                "tagged_at": ev.tagged_at.isoformat() if ev.tagged_at else None,
            }
            for ev in events
        ]

        return ResponseWrapper.success(
            data={
                "route_id": route.route_id,
                "route_code": route.route_code,
                "shift_id": route.shift_id,
                "status": route.status.value if route.status else None,
                "actual_start_time": route.actual_start_time.isoformat() if route.actual_start_time else None,
                "actual_end_time": route.actual_end_time.isoformat() if route.actual_end_time else None,
                "estimated_total_time_min": route.estimated_total_time,
                "delay_summary": {
                    "delay_type": route.delay_type,
                    "delay_minutes": route.delay_minutes,
                    "delay_tagged_at": route.delay_tagged_at.isoformat() if route.delay_tagged_at else None,
                    "ota_grace_minutes": route.ota_grace_minutes,
                },
                "events": event_list,
            },
            message="Route delay detail fetched successfully",
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.exception("[get_route_delay_detail] Error: %s", e)
        raise handle_db_error(e)
