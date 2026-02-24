"""
Background task manager for Fleet Manager
Handles async operations like email sending, route optimization, and Firebase updates
"""
import asyncio
from typing import Any, Dict, Optional
import uuid
from datetime import datetime, time
from app.utils.cache_manager import cache
from app.core.logging_config import get_logger
from common_utils import datetime_to_minutes

logger = get_logger(__name__)

class TaskManager:
    """Manages background tasks with status tracking"""

    def __init__(self):
        self.tasks = {}

    def create_task(self, task_func: callable, *args, **kwargs) -> str:
        """Create a background task and return task ID"""
        task_id = str(uuid.uuid4())

        # Store task metadata
        task_info = {
            "task_id": task_id,
            "status": "queued",
            "created_at": datetime.utcnow().isoformat(),
            "function": task_func.__name__,
            "args": args,
            "kwargs": kwargs
        }

        cache.set(f"task:{task_id}", task_info, ttl=3600)  # 1 hour TTL

        # Submit to background
        asyncio.create_task(self._execute_task(task_id, task_func, *args, **kwargs))

        return task_id

    async def _execute_task(self, task_id: str, task_func: callable, *args, **kwargs):
        """Execute task and update status"""
        try:
            # Update status to running
            task_info = cache.get(f"task:{task_id}")
            if task_info:
                task_info["status"] = "running"
                task_info["started_at"] = datetime.utcnow().isoformat()
                cache.set(f"task:{task_id}", task_info, ttl=3600)

            # Execute the task
            logger.info(f"Starting background task {task_id}: {task_func.__name__}")
            result = await task_func(*args, **kwargs)

            # Update status to completed
            task_info["status"] = "completed"
            task_info["completed_at"] = datetime.utcnow().isoformat()
            task_info["result"] = result
            cache.set(f"task:{task_id}", task_info, ttl=3600)

            logger.info(f"Completed background task {task_id}")

        except Exception as e:
            logger.error(f"Background task {task_id} failed: {e}")

            # Update status to failed
            task_info = cache.get(f"task:{task_id}")
            if task_info:
                task_info["status"] = "failed"
                task_info["error"] = str(e)
                task_info["failed_at"] = datetime.utcnow().isoformat()
                cache.set(f"task:{task_id}", task_info, ttl=3600)

    def get_task_status(self, task_id: str) -> Optional[Dict[str, Any]]:
        """Get task status and metadata"""
        return cache.get(f"task:{task_id}")

# Global task manager instance
task_manager = TaskManager()

# Convenience functions for common background tasks

async def send_email_async(recipient: str, subject: str, body: str, **kwargs):
    """Send email asynchronously"""
    from app.core.email_service import EmailService

    email_service = EmailService()
    await email_service.send_email(
        to_emails=recipient,
        subject=subject,
        html_content=body,
        **kwargs
    )

async def optimize_routes_async(job_id: str, route_data: dict):
    """Run route optimization asynchronously"""
    from app.database.session import get_db
    from app.models.booking import Booking, BookingStatusEnum
    from app.models.route_management import RouteManagement, RouteManagementBooking
    from app.models.shift import Shift
    from app.services.geodesic import group_rides
    from app.services.optimal_roiute_generation import generate_optimal_route, generate_drop_route
    from sqlalchemy import func
    import random

    try:
        # Extract parameters
        booking_date = route_data["booking_date"]
        shift_id = route_data["shift_id"]
        radius = route_data["radius"]
        group_size = route_data["group_size"]
        strict_grouping = route_data["strict_grouping"]
        tenant_id = route_data["tenant_id"]
        user_data = route_data["user_data"]

        db = next(get_db())

        # Get shift info
        shift = db.query(Shift).filter(Shift.shift_id == shift_id, Shift.tenant_id == tenant_id).first()
        if not shift:
            raise Exception(f"Shift {shift_id} not found")

        # Determine coordinate columns
        shift_type = shift.log_type or "Unknown"
        lat_col = "pickup_latitude" if shift_type == "IN" else "drop_latitude"
        lon_col = "pickup_longitude" if shift_type == "IN" else "drop_longitude"

        # Fetch already routed booking IDs
        routed_booking_ids = (
            db.query(RouteManagementBooking.booking_id)
            .join(RouteManagement, RouteManagement.route_id == RouteManagementBooking.route_id)
            .filter(RouteManagement.tenant_id == tenant_id)
            .distinct()
            .all()
        )
        routed_booking_ids = [b.booking_id for b in routed_booking_ids]

        # Fetch unrouted bookings
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
            result = {"clusters": [], "total_bookings": 0, "total_clusters": 0}
            cache.set(f"route_result:{job_id}", result, ttl=3600)
            return result

        # Prepare rides for clustering
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
            result = {"clusters": [], "total_bookings": len(bookings), "total_clusters": 0}
            cache.set(f"route_result:{job_id}", result, ttl=3600)
            return result

        # Generate clusters
        clusters = group_rides(valid_rides, radius, group_size, strict_grouping)

        cluster_data = []
        for idx, cluster in enumerate(clusters, start=1):
            for booking in cluster:
                booking.pop("lat", None)
                booking.pop("lon", None)
            cluster_data.append({"cluster_id": idx, "bookings": cluster})

        # Generate optimal route for each cluster
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
                    db.flush()

                    for idx, booking in enumerate(optimized_route[0]["pickup_order"]):
                        otp_code = random.randint(1000, 9999)
                        est_pickup = booking["estimated_pickup_time_formatted"]
                        if isinstance(est_pickup, time):
                            est_pickup = est_pickup.strftime("%H:%M:%S")
                        
                        est_drop = booking.get("estimated_drop_time_formatted")
                        if isinstance(est_drop, time):
                            est_drop = est_drop.strftime("%H:%M:%S")
                        
                        route_booking = RouteManagementBooking(
                            route_id=route.route_id,
                            booking_id=booking["booking_id"],
                            order_id=idx + 1,
                            estimated_pick_up_time=est_pickup,
                            estimated_drop_time=est_drop,
                            estimated_distance=booking["estimated_distance_km"],
                        )
                        db.add(route_booking)

                        # Update booking status to SCHEDULED
                        db.query(Booking).filter(
                            Booking.booking_id == booking["booking_id"],
                            Booking.status == BookingStatusEnum.REQUEST
                        ).update(
                            {
                                Booking.status: BookingStatusEnum.SCHEDULED,
                                Booking.OTP: otp_code,
                                Booking.updated_at: func.now(),
                            },
                            synchronize_session=False
                        )

                    db.commit()
                    cluster["optimized_route"] = optimized_route

                except Exception as e:
                    logger.error(f"Failed to save route to database: {e}")
                    db.rollback()
                    continue

        # Prepare result
        result = {
            "job_id": job_id,
            "clusters": cluster_data,
            "total_bookings": len(bookings),
            "total_clusters": len(clusters),
            "shift": {
                "shift_id": shift.shift_id,
                "shift_code": shift.shift_code,
                "shift_time": shift.shift_time.strftime("%H:%M:%S"),
                "log_type": shift.log_type.value if shift.log_type else None
            }
        }

        cache.set(f"route_result:{job_id}", result, ttl=3600)
        return result

    except Exception as e:
        logger.error(f"Route optimization failed for job {job_id}: {e}")
        raise

async def update_firebase_async(location_data: dict):
    """Update Firebase asynchronously"""
    from app.firebase.driver_location import push_driver_location_to_firebase

    try:
        await asyncio.get_event_loop().run_in_executor(
            None,
            lambda: push_driver_location_to_firebase(
                tenant_id=location_data["tenant_id"],
                vendor_id=location_data["vendor_id"],
                driver_id=location_data["driver_id"],
                latitude=location_data.get("latitude"),
                longitude=location_data.get("longitude"),
                driver_code=location_data.get("driver_code")
            )
        )
    except Exception as e:
        logger.error(f"Firebase update failed: {e}")

async def generate_report_async(job_id: str, report_params: dict):
    """Generate report asynchronously"""
    try:
        from app.routes.reports_router import generate_booking_report

        # Generate the report
        report_data = await asyncio.get_event_loop().run_in_executor(
            None,
            lambda: generate_booking_report(**report_params)
        )

        # Store report data
        cache.set(f"report:{job_id}", report_data, ttl=3600)  # 1 hour

    except Exception as e:
        logger.error(f"Report generation failed for job {job_id}: {e}")
        raise

# FastAPI integration helpers
def run_background_task(task_func: callable, *args, **kwargs) -> str:
    """Helper to run background task from FastAPI endpoint"""
    return task_manager.create_task(task_func, *args, **kwargs)

def get_task_status(task_id: str) -> Optional[Dict[str, Any]]:
    """Get background task status"""
    return task_manager.get_task_status(task_id)