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
    try:
        q = db.query(ReviewTag).filter(ReviewTag.is_active == True)  # noqa: E712
        if tenant_id:
            q = q.filter(
                or_(ReviewTag.tenant_id.is_(None), ReviewTag.tenant_id == tenant_id)
            )
        else:
            q = q.filter(ReviewTag.tenant_id.is_(None))
        tags = q.order_by(ReviewTag.display_order, ReviewTag.tag_name).all()
        return ResponseWrapper.success(
            data={
                "driver_tags": [t.tag_name for t in tags if t.tag_type == ReviewTagTypeEnum.DRIVER],
                "vehicle_tags": [t.tag_name for t in tags if t.tag_type == ReviewTagTypeEnum.VEHICLE],
            },
            message="Review tags fetched successfully",
        )
    except Exception as e:
        logger.exception("Error fetching review tags")
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
            f"[review_tag.create] tenant={ctx['tenant_id']} "
            f"tag='{tag.tag_name}' type={tag.tag_type}"
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
        logger.exception("Error creating review tag")
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
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=ResponseWrapper.error("Tag not found or access denied", "TAG_NOT_FOUND"),
            )
        tag.is_active = False
        db.commit()
        logger.info(f"[review_tag.delete] tenant={ctx['tenant_id']} tag_id={tag_id}")
        return ResponseWrapper.success(message="Tag deactivated successfully")
    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        logger.exception("Error deactivating review tag")
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
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=ResponseWrapper.error("Booking not found or access denied", "BOOKING_NOT_FOUND"),
            )

        if booking.status != BookingStatusEnum.COMPLETED:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=ResponseWrapper.error(
                    f"Only completed bookings can be reviewed. Current status: {booking.status.value}",
                    "BOOKING_NOT_COMPLETED",
                ),
            )

        if db.query(RideReview).filter(RideReview.booking_id == booking_id).first():
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=ResponseWrapper.error("You have already reviewed this ride", "REVIEW_ALREADY_EXISTS"),
            )

        participants = _resolve_trip_participants(db, booking_id)

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
            f"[review.submit_booking] tenant={tenant_id} employee={employee_id} "
            f"booking={booking_id} review={review.review_id}"
        )
        return ResponseWrapper.success(
            data=_enrich_review(db, review),
            message="Review submitted successfully",
        )
    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        logger.exception("Error submitting review by booking")
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
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=ResponseWrapper.error(
                    "No booking found for you on this route",
                    "BOOKING_NOT_FOUND_ON_ROUTE",
                ),
            )

        if employee_booking.status != BookingStatusEnum.COMPLETED:
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
            f"[review.submit_route] tenant={tenant_id} employee={employee_id} "
            f"route={route_id} booking={employee_booking.booking_id} review={review.review_id}"
        )
        return ResponseWrapper.success(
            data=_enrich_review(db, review),
            message="Review submitted successfully",
        )
    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        logger.exception("Error submitting review by route")
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
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=ResponseWrapper.error("No review found for this booking", "REVIEW_NOT_FOUND"),
            )

        return ResponseWrapper.success(
            data=_enrich_review(db, review),
            message="Review fetched successfully",
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("Error fetching employee review")
        raise handle_http_error(e)


# ================================================================
# ADMIN -- READ ANY BOOKING'S REVIEW
# ================================================================

@router.get(
    "/bookings/{booking_id}/review",
    status_code=status.HTTP_200_OK,
    summary="Get review for any booking (admin/manager)",
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
    try:
        tenant_id = ctx["tenant_id"]

        booking = (
            db.query(Booking)
            .filter(Booking.booking_id == booking_id, Booking.tenant_id == tenant_id)
            .first()
        )
        if not booking:
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
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=ResponseWrapper.error("No review found for this booking", "REVIEW_NOT_FOUND"),
            )

        return ResponseWrapper.success(
            data=_enrich_review(db, review),
            message="Review fetched successfully",
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("Error fetching booking review")
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
    try:
        tenant_id = ctx["tenant_id"]

        driver = (
            db.query(Driver)
            .filter(Driver.driver_id == driver_id, Driver.tenant_id == tenant_id)
            .first()
        )
        if not driver:
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
        logger.exception("Error fetching driver reviews")
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
    try:
        tenant_id = ctx["tenant_id"]

        vehicle = db.query(Vehicle).filter(Vehicle.vehicle_id == vehicle_id).first()
        if not vehicle:
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
        logger.exception("Error fetching vehicle reviews")
        raise handle_http_error(e)
