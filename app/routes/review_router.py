# app/routes/review_router.py
"""
Ride Review Router
==================
Single flat router -- all endpoints registered directly on `router` so they
are visible to FastAPI the moment the module is imported.

Root cause of the old bug: the previous version called
    router.include_router(tags_router)
    router.include_router(employee_review_router)
    router.include_router(admin_review_router)
at module-import time, BEFORE any @tags_router.get(...) decorators had run.
FastAPI copies routes at include_router() call-time, so router ended up with
zero routes. Fixed by using a single flat router with explicit full paths.

Endpoints (all under /api/v1 via api.py)
-----------------------------------------
GET    /reviews/tags                              -> tag picker (global + tenant, no auth)
POST   /reviews/tags                              -> admin adds a new tag
DELETE /reviews/tags/{tag_id}                     -> admin soft-deletes a tag

POST   /employee/bookings/{booking_id}/review     -> employee submits review by booking
GET    /employee/bookings/{booking_id}/review     -> employee reads their own review
POST   /employee/routes/{route_id}/review         -> employee submits review by route

GET    /bookings/{booking_id}/review              -> admin/manager reads any booking review
GET    /drivers/{driver_id}/reviews               -> driver aggregate + paginated list
GET    /vehicles/{vehicle_id}/reviews             -> vehicle aggregate + paginated list
"""

from __future__ import annotations

from collections import Counter
from datetime import date, datetime, time as dt_time
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import or_
from sqlalchemy.orm import Session

from app.core.logging_config import get_logger
from app.database.session import get_db
from app.models.booking import Booking, BookingStatusEnum
from app.models.driver import Driver
from app.models.review import RideReview, ReviewTag, ReviewTagTypeEnum
from app.models.route_management import RouteManagement, RouteManagementBooking
from app.models.vehicle import Vehicle
from app.schemas.review import (
    DriverReviewSummary,
    RideReviewCreate,
    RideReviewResponse,
    ReviewTagCreate,
    ReviewTagResponse,
    ReviewTagsResponse,
    VehicleReviewSummary,
)
from app.utils.response_utils import ResponseWrapper, handle_http_error
from common_utils.auth.permission_checker import PermissionChecker

logger = get_logger(__name__)

# ----------------------------------------------------------------
# Single flat router -- api.py registers this with prefix=/api/v1
# ----------------------------------------------------------------
router = APIRouter(tags=["Ride Reviews"])


# ----------------------------------------------------------------
# Auth dependency factories
# ----------------------------------------------------------------

def EmployeeAuth(
    user_data=Depends(PermissionChecker(["app-employee.read", "app-employee.write"]))
):
    if user_data.get("user_type") != "employee":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Employee access only",
        )
    tenant_id = user_data.get("tenant_id")
    employee_id = user_data.get("user_id")
    if not tenant_id or not employee_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Employee or tenant not resolved from token",
        )
    return {"tenant_id": tenant_id, "employee_id": employee_id}


def AdminAuth(
    user_data=Depends(PermissionChecker(["booking.read"]))
):
    tenant_id = user_data.get("tenant_id")
    if not tenant_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Tenant not resolved from token",
        )
    return {"tenant_id": tenant_id, "user_id": user_data.get("user_id")}


# ----------------------------------------------------------------
# Helpers
# ----------------------------------------------------------------

def _resolve_trip_participants(db: Session, booking_id: int) -> dict:
    """Walk booking -> route_management_bookings -> route_management."""
    route_booking = (
        db.query(RouteManagementBooking)
        .filter(RouteManagementBooking.booking_id == booking_id)
        .first()
    )
    if not route_booking:
        return {"driver_id": None, "vehicle_id": None, "route_id": None}

    route = (
        db.query(RouteManagement)
        .filter(RouteManagement.route_id == route_booking.route_id)
        .first()
    )
    if not route:
        return {"driver_id": None, "vehicle_id": None, "route_id": None}

    return {
        "driver_id": route.assigned_driver_id,
        "vehicle_id": route.assigned_vehicle_id,
        "route_id": route.route_id,
    }


def _enrich_review(db: Session, review: RideReview) -> dict:
    """ORM -> dict with snapshot of driver name/phone and vehicle number."""
    data = {
        "review_id": review.review_id,
        "booking_id": review.booking_id,
        "employee_id": review.employee_id,
        "tenant_id": review.tenant_id,
        "driver_id": review.driver_id,
        "vehicle_id": review.vehicle_id,
        "route_id": review.route_id,
        "overall_rating": review.overall_rating,
        "driver_rating": review.driver_rating,
        "driver_tags": review.driver_tags or [],
        "driver_comment": review.driver_comment,
        "vehicle_rating": review.vehicle_rating,
        "vehicle_tags": review.vehicle_tags or [],
        "vehicle_comment": review.vehicle_comment,
        "is_active": review.is_active,
        "created_at": review.created_at.isoformat() if review.created_at else None,
        "updated_at": review.updated_at.isoformat() if review.updated_at else None,
        "driver_name": None,
        "driver_phone": None,
        "vehicle_number": None,
    }
    if review.driver_id:
        driver = db.query(Driver).filter(Driver.driver_id == review.driver_id).first()
        if driver:
            data["driver_name"] = driver.name
            data["driver_phone"] = driver.phone
    if review.vehicle_id:
        vehicle = db.query(Vehicle).filter(Vehicle.vehicle_id == review.vehicle_id).first()
        if vehicle:
            data["vehicle_number"] = vehicle.rc_number
    return data


def _build_aggregate(reviews: list, rating_field: str, tags_field: str, comment_field: str) -> dict:
    """Compute avg rating, tag frequency map, and last 5 comments."""
    ratings = [getattr(r, rating_field) for r in reviews if getattr(r, rating_field)]
    all_tags = [
        tag
        for r in reviews
        if getattr(r, tags_field)
        for tag in getattr(r, tags_field)
    ]
    comments = [getattr(r, comment_field) for r in reviews if getattr(r, comment_field)]
    return {
        "total_reviews": len(reviews),
        "average_rating": round(sum(ratings) / len(ratings), 2) if ratings else None,
        "tag_counts": dict(Counter(all_tags)),
        "recent_comments": comments[:5],
    }


# ================================================================
# TAG MANAGEMENT
# ================================================================

@router.get(
    "/reviews/tags",
    status_code=status.HTTP_200_OK,
    summary="Get available review tags (driver + vehicle)",
)
async def get_review_tags(
    tenant_id: Optional[str] = Query(
        default=None,
        description="Pass your tenant_id to include tenant-specific tags alongside global ones",
    ),
    db: Session = Depends(get_db),
):
    """
    Returns word-tags employees can pick from in the review UI.
    Pass ?tenant_id=X to also include tags your admin created for your tenant.
    No authentication required -- used by the tag picker before login.
    Employees can always send any free-form custom word; no server-side enforcement.
    """
    logger.info(f"[review_tags.get] tenant_id={tenant_id}")
    try:
        q = db.query(ReviewTag).filter(ReviewTag.is_active == True)  # noqa: E712
        if tenant_id:
            q = q.filter(
                or_(ReviewTag.tenant_id.is_(None), ReviewTag.tenant_id == tenant_id)
            )
        else:
            q = q.filter(ReviewTag.tenant_id.is_(None))
        tags = q.order_by(ReviewTag.display_order, ReviewTag.tag_name).all()
        logger.info(f"[review_tags.get] OK tenant_id={tenant_id} driver_tags={sum(1 for t in tags if t.tag_type == ReviewTagTypeEnum.DRIVER)} vehicle_tags={sum(1 for t in tags if t.tag_type == ReviewTagTypeEnum.VEHICLE)}")
        return ResponseWrapper.success(
            data={
                "driver_tags": [t.tag_name for t in tags if t.tag_type == ReviewTagTypeEnum.DRIVER],
                "vehicle_tags": [t.tag_name for t in tags if t.tag_type == ReviewTagTypeEnum.VEHICLE],
            },
            message="Review tags fetched successfully",
        )
    except Exception as e:
        logger.exception(f"[review_tags.get] CRASH tenant_id={tenant_id} error={e}")
        raise handle_http_error(e)


@router.post(
    "/reviews/tags",
    status_code=status.HTTP_201_CREATED,
    summary="Add a new review tag (admin)",
)
async def create_review_tag(
    payload: ReviewTagCreate,
    db: Session = Depends(get_db),
    ctx=Depends(AdminAuth),
):
    """
    Admin adds a new word to the suggestion bank shown in the app.
    tag_type: "driver" or "vehicle"
    Tags are scoped to the caller's tenant and appear immediately in the app.
    """
    logger.info(f"[review_tag.create] START tenant={ctx['tenant_id']} tag_name='{payload.tag_name}' tag_type={payload.tag_type}")
    try:
        tag = ReviewTag(
            tenant_id=ctx["tenant_id"],
            tag_type=ReviewTagTypeEnum(payload.tag_type),
            tag_name=payload.tag_name.strip(),
            display_order=payload.display_order,
        )
        db.add(tag)
        db.commit()
        db.refresh(tag)
        logger.info(
            f"[review_tag.create] OK tenant={ctx['tenant_id']} "
            f"tag_id={tag.tag_id} tag='{tag.tag_name}' type={tag.tag_type}"
        )
        return ResponseWrapper.success(
            data={
                "tag_id": tag.tag_id,
                "tag_name": tag.tag_name,
                "tag_type": tag.tag_type,
                "tenant_id": tag.tenant_id,
                "display_order": tag.display_order,
                "is_active": tag.is_active,
                "created_at": tag.created_at.isoformat() if tag.created_at else None,
            },
            message="Tag created successfully",
        )
    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        logger.exception(f"[review_tag.create] CRASH tenant={ctx['tenant_id']} tag_name='{payload.tag_name}' error={e}")
        raise handle_http_error(e)


@router.delete(
    "/reviews/tags/{tag_id}",
    status_code=status.HTTP_200_OK,
    summary="Deactivate a review tag (admin)",
)
async def delete_review_tag(
    tag_id: int,
    db: Session = Depends(get_db),
    ctx=Depends(AdminAuth),
):
    """
    Soft-deletes (deactivates) a tag -- disappears from the picker immediately.
    Only tags owned by the caller's tenant can be deactivated.
    Global (tenant_id=NULL) tags cannot be deactivated this way.
    """
    logger.info(f"[review_tag.delete] START tenant={ctx['tenant_id']} tag_id={tag_id}")
    try:
        tag = (
            db.query(ReviewTag)
            .filter(
                ReviewTag.tag_id == tag_id,
                ReviewTag.tenant_id == ctx["tenant_id"],
            )
            .first()
        )
        if not tag:
            logger.warning(f"[review_tag.delete] 404 NOT_FOUND tenant={ctx['tenant_id']} tag_id={tag_id}")
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=ResponseWrapper.error("Tag not found or access denied", "TAG_NOT_FOUND"),
            )
        tag.is_active = False
        db.commit()
        logger.info(f"[review_tag.delete] OK tenant={ctx['tenant_id']} tag_id={tag_id} tag_name='{tag.tag_name}'")
        return ResponseWrapper.success(message="Tag deactivated successfully")
    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        logger.exception(f"[review_tag.delete] CRASH tenant={ctx['tenant_id']} tag_id={tag_id} error={e}")
        raise handle_http_error(e)


# ================================================================
# EMPLOYEE -- SUBMIT REVIEW
# ================================================================

@router.post(
    "/employee/bookings/{booking_id}/review",
    status_code=status.HTTP_201_CREATED,
    summary="Submit a ride review by booking ID (employee)",
)
async def submit_review_by_booking(
    booking_id: int,
    payload: RideReviewCreate,
    db: Session = Depends(get_db),
    ctx=Depends(EmployeeAuth),
):
    """
    Employee submits an optional review after a Completed ride.
    Rules:
    - Booking must belong to this employee.
    - Booking status must be Completed.
    - One review per booking -- a second call returns 409.
    - Every field is optional: send only what you care about.
    - Tags can be predefined suggestions OR any free-form word.
    Edge cases:
    - Wrong employee: 404 | Not completed: 400 | Already reviewed: 409
    - No route assignment: driver_id / vehicle_id saved as null
    """
    logger.info(f"[review.submit_booking] START tenant={ctx['tenant_id']} employee={ctx['employee_id']} booking_id={booking_id} overall_rating={payload.overall_rating}")
    try:
        tenant_id = ctx["tenant_id"]
        employee_id = ctx["employee_id"]

        booking = (
            db.query(Booking)
            .filter(
                Booking.booking_id == booking_id,
                Booking.employee_id == employee_id,
                Booking.tenant_id == tenant_id,
            )
            .first()
        )
        if not booking:
            logger.warning(f"[review.submit_booking] 404 BOOKING_NOT_FOUND tenant={tenant_id} employee={employee_id} booking_id={booking_id}")
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=ResponseWrapper.error("Booking not found or access denied", "BOOKING_NOT_FOUND"),
            )

        if booking.status != BookingStatusEnum.COMPLETED:
            logger.warning(f"[review.submit_booking] 400 NOT_COMPLETED tenant={tenant_id} employee={employee_id} booking_id={booking_id} status={booking.status.value}")
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=ResponseWrapper.error(
                    f"Only completed bookings can be reviewed. Current status: {booking.status.value}",
                    "BOOKING_NOT_COMPLETED",
                ),
            )

        if db.query(RideReview).filter(RideReview.booking_id == booking_id).first():
            logger.warning(f"[review.submit_booking] 409 ALREADY_EXISTS tenant={tenant_id} employee={employee_id} booking_id={booking_id}")
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=ResponseWrapper.error("You have already reviewed this ride", "REVIEW_ALREADY_EXISTS"),
            )

        participants = _resolve_trip_participants(db, booking_id)
        logger.info(f"[review.submit_booking] participants resolved driver_id={participants['driver_id']} vehicle_id={participants['vehicle_id']} route_id={participants['route_id']}")

        review = RideReview(
            tenant_id=tenant_id,
            booking_id=booking_id,
            employee_id=employee_id,
            driver_id=participants["driver_id"],
            vehicle_id=participants["vehicle_id"],
            route_id=participants["route_id"],
            overall_rating=payload.overall_rating,
            driver_rating=payload.driver_rating,
            driver_tags=payload.driver_tags,
            driver_comment=payload.driver_comment,
            vehicle_rating=payload.vehicle_rating,
            vehicle_tags=payload.vehicle_tags,
            vehicle_comment=payload.vehicle_comment,
        )
        db.add(review)
        db.commit()
        db.refresh(review)

        logger.info(
            f"[review.submit_booking] OK tenant={tenant_id} employee={employee_id} "
            f"booking={booking_id} review_id={review.review_id} overall_rating={review.overall_rating}"
        )
        return ResponseWrapper.success(
            data=_enrich_review(db, review),
            message="Review submitted successfully",
        )
    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        logger.exception(f"[review.submit_booking] CRASH tenant={ctx['tenant_id']} employee={ctx['employee_id']} booking_id={booking_id} error={e}")
        raise handle_http_error(e)


@router.post(
    "/employee/routes/{route_id}/review",
    status_code=status.HTTP_201_CREATED,
    summary="Submit a ride review by route ID (employee)",
)
async def submit_review_by_route(
    route_id: int,
    payload: RideReviewCreate,
    db: Session = Depends(get_db),
    ctx=Depends(EmployeeAuth),
):
    """
    Alternative: employee references the route instead of the booking.
    The system auto-finds their booking on that route.
    Edge cases:
    - Route not in this tenant: 404 | Employee not on this route: 404
    - Ride not completed: 400 | Already reviewed: 409
    """
    logger.info(f"[review.submit_route] START tenant={ctx['tenant_id']} employee={ctx['employee_id']} route_id={route_id} overall_rating={payload.overall_rating}")
    try:
        tenant_id = ctx["tenant_id"]
        employee_id = ctx["employee_id"]

        route = (
            db.query(RouteManagement)
            .filter(
                RouteManagement.route_id == route_id,
                RouteManagement.tenant_id == tenant_id,
            )
            .first()
        )
        if not route:
            logger.warning(f"[review.submit_route] 404 ROUTE_NOT_FOUND tenant={tenant_id} employee={employee_id} route_id={route_id}")
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=ResponseWrapper.error("Route not found", "ROUTE_NOT_FOUND"),
            )

        employee_booking = None
        for rb in (
            db.query(RouteManagementBooking)
            .filter(RouteManagementBooking.route_id == route_id)
            .all()
        ):
            bk = (
                db.query(Booking)
                .filter(
                    Booking.booking_id == rb.booking_id,
                    Booking.employee_id == employee_id,
                    Booking.tenant_id == tenant_id,
                )
                .first()
            )
            if bk:
                employee_booking = bk
                break

        if not employee_booking:
            logger.warning(f"[review.submit_route] 404 BOOKING_NOT_FOUND_ON_ROUTE tenant={tenant_id} employee={employee_id} route_id={route_id}")
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=ResponseWrapper.error(
                    "No booking found for you on this route",
                    "BOOKING_NOT_FOUND_ON_ROUTE",
                ),
            )

        if employee_booking.status != BookingStatusEnum.COMPLETED:
            logger.warning(f"[review.submit_route] 400 NOT_COMPLETED tenant={tenant_id} employee={employee_id} route_id={route_id} booking_id={employee_booking.booking_id} status={employee_booking.status.value}")
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=ResponseWrapper.error(
                    f"Only completed bookings can be reviewed. Current status: {employee_booking.status.value}",
                    "BOOKING_NOT_COMPLETED",
                ),
            )

        if (
            db.query(RideReview)
            .filter(RideReview.booking_id == employee_booking.booking_id)
            .first()
        ):
            logger.warning(f"[review.submit_route] 409 ALREADY_EXISTS tenant={tenant_id} employee={employee_id} route_id={route_id} booking_id={employee_booking.booking_id}")
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=ResponseWrapper.error("You have already reviewed this ride", "REVIEW_ALREADY_EXISTS"),
            )

        review = RideReview(
            tenant_id=tenant_id,
            booking_id=employee_booking.booking_id,
            employee_id=employee_id,
            driver_id=route.assigned_driver_id,
            vehicle_id=route.assigned_vehicle_id,
            route_id=route_id,
            overall_rating=payload.overall_rating,
            driver_rating=payload.driver_rating,
            driver_tags=payload.driver_tags,
            driver_comment=payload.driver_comment,
            vehicle_rating=payload.vehicle_rating,
            vehicle_tags=payload.vehicle_tags,
            vehicle_comment=payload.vehicle_comment,
        )
        db.add(review)
        db.commit()
        db.refresh(review)

        logger.info(
            f"[review.submit_route] OK tenant={tenant_id} employee={employee_id} "
            f"route_id={route_id} booking_id={employee_booking.booking_id} review_id={review.review_id} overall_rating={review.overall_rating}"
        )
        return ResponseWrapper.success(
            data=_enrich_review(db, review),
            message="Review submitted successfully",
        )
    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        logger.exception(f"[review.submit_route] CRASH tenant={ctx['tenant_id']} employee={ctx['employee_id']} route_id={route_id} error={e}")
        raise handle_http_error(e)


# ================================================================
# EMPLOYEE -- READ OWN REVIEW
# ================================================================

@router.get(
    "/employee/bookings/{booking_id}/review",
    status_code=status.HTTP_200_OK,
    summary="Get your own review for a booking (employee)",
)
async def get_my_review(
    booking_id: int,
    db: Session = Depends(get_db),
    ctx=Depends(EmployeeAuth),
):
    """
    Employee reads the review they previously submitted.
    Edge cases:
    - Booking doesn't belong to this employee: 404
    - Review not yet submitted: 404
    """
    logger.info(f"[review.get_my] START tenant={ctx['tenant_id']} employee={ctx['employee_id']} booking_id={booking_id}")
    try:
        tenant_id = ctx["tenant_id"]
        employee_id = ctx["employee_id"]

        booking = (
            db.query(Booking)
            .filter(
                Booking.booking_id == booking_id,
                Booking.employee_id == employee_id,
                Booking.tenant_id == tenant_id,
            )
            .first()
        )
        if not booking:
            logger.warning(f"[review.get_my] 404 BOOKING_NOT_FOUND tenant={tenant_id} employee={employee_id} booking_id={booking_id}")
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=ResponseWrapper.error("Booking not found or access denied", "BOOKING_NOT_FOUND"),
            )

        review = (
            db.query(RideReview)
            .filter(
                RideReview.booking_id == booking_id,
                RideReview.employee_id == employee_id,
            )
            .first()
        )
        if not review:
            logger.warning(f"[review.get_my] 404 REVIEW_NOT_FOUND tenant={tenant_id} employee={employee_id} booking_id={booking_id}")
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=ResponseWrapper.error("No review found for this booking", "REVIEW_NOT_FOUND"),
            )

        logger.info(f"[review.get_my] OK tenant={tenant_id} employee={employee_id} booking_id={booking_id} review_id={review.review_id}")
        return ResponseWrapper.success(
            data=_enrich_review(db, review),
            message="Review fetched successfully",
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.exception(f"[review.get_my] CRASH tenant={ctx['tenant_id']} employee={ctx['employee_id']} booking_id={booking_id} error={e}")
        raise handle_http_error(e)


# ================================================================
# ADMIN -- LIST / SEARCH ALL REVIEWS
# ================================================================

@router.get(
    "/reviews",
    status_code=status.HTTP_200_OK,
    summary="List and search reviews (admin/manager)",
)
async def list_reviews(
    page: int = Query(default=1, ge=1),
    per_page: int = Query(default=20, ge=1, le=100),
    from_date: Optional[date] = Query(
        default=None,
        description="Return reviews created on or after this date (YYYY-MM-DD)",
    ),
    to_date: Optional[date] = Query(
        default=None,
        description="Return reviews created on or before this date (YYYY-MM-DD, inclusive)",
    ),
    driver_id: Optional[int] = Query(default=None, description="Filter by driver"),
    employee_id: Optional[int] = Query(default=None, description="Filter by employee"),
    route_id: Optional[int] = Query(default=None, description="Filter by route"),
    min_rating: Optional[float] = Query(
        default=None, ge=1, le=5, description="Minimum overall_rating (inclusive)"
    ),
    max_rating: Optional[float] = Query(
        default=None, ge=1, le=5, description="Maximum overall_rating (inclusive)"
    ),
    db: Session = Depends(get_db),
    ctx=Depends(AdminAuth),
):
    """
    Browse all reviews for the tenant with flexible filters — no booking ID needed.

    Filters
    -------
    from_date / to_date  → date range on created_at
    driver_id            → reviews about a specific driver
    employee_id          → reviews submitted by a specific employee
    route_id             → reviews tied to a specific route
    min_rating / max_rating → filter by overall_rating (1-5)
    """
    logger.info(
        f"[review.list] START tenant={ctx['tenant_id']} page={page} per_page={per_page} "
        f"from_date={from_date} to_date={to_date} driver_id={driver_id} "
        f"employee_id={employee_id} route_id={route_id} min_rating={min_rating} max_rating={max_rating}"
    )
    try:
        tenant_id = ctx["tenant_id"]

        q = db.query(RideReview).filter(
            RideReview.tenant_id == tenant_id,
            RideReview.is_active.is_(True),
        )
        if from_date:
            q = q.filter(RideReview.created_at >= datetime.combine(from_date, dt_time.min))
        if to_date:
            q = q.filter(RideReview.created_at <= datetime.combine(to_date, dt_time.max))
        if driver_id:
            q = q.filter(RideReview.driver_id == driver_id)
        if employee_id:
            q = q.filter(RideReview.employee_id == employee_id)
        if route_id:
            q = q.filter(RideReview.route_id == route_id)
        if min_rating is not None:
            q = q.filter(RideReview.overall_rating >= min_rating)
        if max_rating is not None:
            q = q.filter(RideReview.overall_rating <= max_rating)

        total = q.count()
        reviews = (
            q.order_by(RideReview.created_at.desc())
            .offset((page - 1) * per_page)
            .limit(per_page)
            .all()
        )

        logger.info(f"[review.list] OK tenant={tenant_id} total={total} page={page} returning={len(reviews)}")
        return ResponseWrapper.paginated(
            items=[_enrich_review(db, r) for r in reviews],
            total=total,
            page=page,
            per_page=per_page,
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.exception(f"[review.list] CRASH tenant={ctx['tenant_id']} error={e}")
        raise handle_http_error(e)


# ================================================================
# ADMIN -- READ ANY BOOKING'S REVIEW
# ================================================================

@router.get(
    "/bookings/{booking_id}/review",
    status_code=status.HTTP_200_OK,
    summary="Get review for a specific booking (admin/manager)",
)
async def get_booking_review(
    booking_id: int,
    db: Session = Depends(get_db),
    ctx=Depends(AdminAuth),
):
    """
    Admin or manager fetches the review for any booking in their tenant.
    Edge cases:
    - Booking from a different tenant: 404
    - Review not yet submitted: 404
    """
    logger.info(f"[review.get_booking] START tenant={ctx['tenant_id']} booking_id={booking_id}")
    try:
        tenant_id = ctx["tenant_id"]

        booking = (
            db.query(Booking)
            .filter(Booking.booking_id == booking_id, Booking.tenant_id == tenant_id)
            .first()
        )
        if not booking:
            logger.warning(f"[review.get_booking] 404 BOOKING_NOT_FOUND tenant={tenant_id} booking_id={booking_id}")
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=ResponseWrapper.error("Booking not found", "BOOKING_NOT_FOUND"),
            )

        review = (
            db.query(RideReview)
            .filter(RideReview.booking_id == booking_id)
            .first()
        )
        if not review:
            logger.warning(f"[review.get_booking] 404 REVIEW_NOT_FOUND tenant={tenant_id} booking_id={booking_id}")
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=ResponseWrapper.error("No review found for this booking", "REVIEW_NOT_FOUND"),
            )

        logger.info(f"[review.get_booking] OK tenant={tenant_id} booking_id={booking_id} review_id={review.review_id}")
        return ResponseWrapper.success(
            data=_enrich_review(db, review),
            message="Review fetched successfully",
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.exception(f"[review.get_booking] CRASH tenant={ctx['tenant_id']} booking_id={booking_id} error={e}")
        raise handle_http_error(e)


# ================================================================
# ADMIN -- DRIVER REVIEW SUMMARY
# ================================================================

@router.get(
    "/drivers/{driver_id}/reviews",
    status_code=status.HTTP_200_OK,
    summary="Get aggregated reviews for a driver (admin/manager)",
)
async def get_driver_reviews(
    driver_id: int,
    page: int = Query(default=1, ge=1),
    per_page: int = Query(default=20, ge=1, le=100),
    start_date: Optional[date] = Query(default=None, description="Reviews from date (YYYY-MM-DD)"),
    end_date: Optional[date] = Query(default=None, description="Reviews up to date (YYYY-MM-DD)"),
    route_id: Optional[int] = Query(default=None, description="Filter to a specific route"),
    db: Session = Depends(get_db),
    ctx=Depends(AdminAuth),
):
    """
    Returns: summary (avg rating, tag frequency, last 5 comments) + paginated reviews.
    Filters: ?start_date=2026-01-01&end_date=2026-03-04&route_id=42
    Edge cases:
    - Driver not in this tenant: 404 | No reviews yet: empty list, null avg
    - date range start > end: empty list (DB handles naturally)
    """
    logger.info(f"[review.driver_summary] START tenant={ctx['tenant_id']} driver_id={driver_id} page={page} per_page={per_page} start_date={start_date} end_date={end_date} route_id={route_id}")
    try:
        tenant_id = ctx["tenant_id"]

        driver = (
            db.query(Driver)
            .filter(Driver.driver_id == driver_id, Driver.tenant_id == tenant_id)
            .first()
        )
        if not driver:
            logger.warning(f"[review.driver_summary] 404 DRIVER_NOT_FOUND tenant={tenant_id} driver_id={driver_id}")
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=ResponseWrapper.error("Driver not found", "DRIVER_NOT_FOUND"),
            )

        q = db.query(RideReview).filter(
            RideReview.driver_id == driver_id,
            RideReview.tenant_id == tenant_id,
            RideReview.driver_rating.isnot(None),
        )
        if start_date:
            q = q.filter(RideReview.created_at >= datetime.combine(start_date, dt_time.min))
        if end_date:
            q = q.filter(RideReview.created_at <= datetime.combine(end_date, dt_time.max))
        if route_id:
            q = q.filter(RideReview.route_id == route_id)
        all_reviews = q.order_by(RideReview.created_at.desc()).all()

        agg = _build_aggregate(all_reviews, "driver_rating", "driver_tags", "driver_comment")
        total = agg["total_reviews"]
        offset = (page - 1) * per_page
        page_reviews = all_reviews[offset: offset + per_page]

        logger.info(f"[review.driver_summary] OK tenant={tenant_id} driver_id={driver_id} driver_name='{driver.name}' total_reviews={total} avg_rating={agg['average_rating']}")
        return ResponseWrapper.success(
            data={
                "summary": {
                    "driver_id": driver_id,
                    "driver_name": driver.name,
                    **agg,
                },
                "reviews": [_enrich_review(db, r) for r in page_reviews],
                "pagination": {
                    "total": total,
                    "page": page,
                    "per_page": per_page,
                    "pages": max(1, (total + per_page - 1) // per_page),
                },
            },
            message="Driver reviews fetched successfully",
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.exception(f"[review.driver_summary] CRASH tenant={ctx['tenant_id']} driver_id={driver_id} error={e}")
        raise handle_http_error(e)


# ================================================================
# ADMIN -- VEHICLE REVIEW SUMMARY
# ================================================================

@router.get(
    "/vehicles/{vehicle_id}/reviews",
    status_code=status.HTTP_200_OK,
    summary="Get aggregated reviews for a vehicle (admin/manager)",
)
async def get_vehicle_reviews(
    vehicle_id: int,
    page: int = Query(default=1, ge=1),
    per_page: int = Query(default=20, ge=1, le=100),
    start_date: Optional[date] = Query(default=None, description="Reviews from date (YYYY-MM-DD)"),
    end_date: Optional[date] = Query(default=None, description="Reviews up to date (YYYY-MM-DD)"),
    route_id: Optional[int] = Query(default=None, description="Filter to a specific route"),
    db: Session = Depends(get_db),
    ctx=Depends(AdminAuth),
):
    """
    Returns: summary (avg rating, tag frequency, last 5 comments) + paginated reviews.
    Filters: ?start_date=2026-01-01&end_date=2026-03-04&route_id=42
    Edge cases:
    - Vehicle not found in tenant: 404 | No reviews yet: empty list, null avg
    """
    logger.info(f"[review.vehicle_summary] START tenant={ctx['tenant_id']} vehicle_id={vehicle_id} page={page} per_page={per_page} start_date={start_date} end_date={end_date} route_id={route_id}")
    try:
        tenant_id = ctx["tenant_id"]

        vehicle = db.query(Vehicle).filter(Vehicle.vehicle_id == vehicle_id).first()
        if not vehicle:
            logger.warning(f"[review.vehicle_summary] 404 VEHICLE_NOT_FOUND tenant={tenant_id} vehicle_id={vehicle_id}")
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=ResponseWrapper.error("Vehicle not found", "VEHICLE_NOT_FOUND"),
            )

        q = db.query(RideReview).filter(
            RideReview.vehicle_id == vehicle_id,
            RideReview.tenant_id == tenant_id,
            RideReview.vehicle_rating.isnot(None),
        )
        if start_date:
            q = q.filter(RideReview.created_at >= datetime.combine(start_date, dt_time.min))
        if end_date:
            q = q.filter(RideReview.created_at <= datetime.combine(end_date, dt_time.max))
        if route_id:
            q = q.filter(RideReview.route_id == route_id)
        all_reviews = q.order_by(RideReview.created_at.desc()).all()

        agg = _build_aggregate(all_reviews, "vehicle_rating", "vehicle_tags", "vehicle_comment")
        total = agg["total_reviews"]
        offset = (page - 1) * per_page
        page_reviews = all_reviews[offset: offset + per_page]

        logger.info(f"[review.vehicle_summary] OK tenant={tenant_id} vehicle_id={vehicle_id} rc_number='{vehicle.rc_number}' total_reviews={total} avg_rating={agg['average_rating']}")
        return ResponseWrapper.success(
            data={
                "summary": {
                    "vehicle_id": vehicle_id,
                    "vehicle_number": vehicle.rc_number,
                    **agg,
                },
                "reviews": [_enrich_review(db, r) for r in page_reviews],
                "pagination": {
                    "total": total,
                    "page": page,
                    "per_page": per_page,
                    "pages": max(1, (total + per_page - 1) // per_page),
                },
            },
            message="Vehicle reviews fetched successfully",
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.exception(f"[review.vehicle_summary] CRASH tenant={ctx['tenant_id']} vehicle_id={vehicle_id} error={e}")
        raise handle_http_error(e)
