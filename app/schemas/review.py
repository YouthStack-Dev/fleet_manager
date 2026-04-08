# app/schemas/review.py
"""
Pydantic schemas for the ride review system.

All review fields are optional — employees are never forced to submit anything.
"""

from __future__ import annotations

from datetime import datetime
from typing import List, Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


# ──────────────────────────────────────────────────────────────
# Helpers
# ──────────────────────────────────────────────────────────────

def _validate_star(v: Optional[int], field_name: str) -> Optional[int]:
    if v is not None and v not in range(1, 6):
        raise ValueError(f"{field_name} must be between 1 and 5")
    return v


# ──────────────────────────────────────────────────────────────
# Tag reference  (returned by GET /reviews/tags)
# ──────────────────────────────────────────────────────────────

class ReviewTagsResponse(BaseModel):
    driver_tags: List[str]
    vehicle_tags: List[str]


# ──────────────────────────────────────────────────────────────
# Tag management schemas  (admin POST/DELETE /reviews/tags)
# ──────────────────────────────────────────────────────────────

class ReviewTagCreate(BaseModel):
    """Admin creates a new tag in the driver or vehicle suggestion bank."""
    tag_type: str = Field(..., description="'driver' or 'vehicle'")
    tag_name: str = Field(..., min_length=1, max_length=100, description="Word or phrase shown in the app")
    display_order: int = Field(default=0, ge=0, description="Lower numbers appear first in the picker")

    @field_validator("tag_type")
    @classmethod
    def validate_tag_type(cls, v: str) -> str:
        if v not in ("driver", "vehicle"):
            raise ValueError("tag_type must be 'driver' or 'vehicle'")
        return v

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "tag_type": "driver",
                "tag_name": "Punctual",
                "display_order": 1
            }
        }
    )


class ReviewTagResponse(BaseModel):
    tag_id: int
    tag_type: str
    tag_name: str
    tenant_id: Optional[str] = None
    display_order: int
    is_active: bool
    created_at: datetime

    class Config:
        from_attributes = True


# ──────────────────────────────────────────────────────────────
# Create / Update request body
# ──────────────────────────────────────────────────────────────

class RideReviewCreate(BaseModel):
    """
    Body for  POST /employee/bookings/{booking_id}/review
    Everything is optional — submit only what the employee cares about.
    """

    # Overall trip impression
    overall_rating: Optional[int] = Field(
        default=None, ge=1, le=5, description="Overall trip rating 1-5 stars"
    )

    # Driver sub-review
    driver_rating: Optional[int] = Field(
        default=None, ge=1, le=5, description="Driver rating 1-5 stars"
    )
    driver_tags: Optional[List[str]] = Field(
        default=None,
        description="Word-tags for the driver — pick from suggestions OR add your own custom words",
    )
    driver_comment: Optional[str] = Field(
        default=None, max_length=500, description="Free-text comment about the driver"
    )

    # Vehicle sub-review
    vehicle_rating: Optional[int] = Field(
        default=None, ge=1, le=5, description="Vehicle rating 1-5 stars"
    )
    vehicle_tags: Optional[List[str]] = Field(
        default=None,
        description="Word-tags for the vehicle — pick from suggestions OR add your own custom words",
    )
    vehicle_comment: Optional[str] = Field(
        default=None, max_length=500, description="Free-text comment about the vehicle"
    )

    @model_validator(mode="after")
    def at_least_one_field(self) -> "RideReviewCreate":
        """Ensure the payload contains at least one reviewable field."""
        fields = [
            self.overall_rating,
            self.driver_rating,
            self.driver_tags,
            self.driver_comment,
            self.vehicle_rating,
            self.vehicle_tags,
            self.vehicle_comment,
        ]
        if all(f is None or f == [] for f in fields):
            raise ValueError("Review must contain at least one rating, tag, or comment")
        return self

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "overall_rating": 4,
                "driver_rating": 5,
                "driver_tags": ["Punctual", "Polite"],
                "driver_comment": "Driver arrived on time and was very courteous.",
                "vehicle_rating": 4,
                "vehicle_tags": ["Clean", "Comfortable"],
                "vehicle_comment": "Vehicle was clean and AC was working well."
            }
        }
    )


# ──────────────────────────────────────────────────────────────
# Response schemas
# ──────────────────────────────────────────────────────────────

class DriverReviewSummary(BaseModel):
    """Aggregated driver review statistics shown on driver/trip details."""
    driver_id: int
    driver_name: Optional[str] = None
    total_reviews: int
    average_rating: Optional[float] = None
    tag_counts: dict  # {"Punctual": 12, "Polite": 8, ...}
    recent_comments: List[str]  # last 5 non-empty comments


class VehicleReviewSummary(BaseModel):
    """Aggregated vehicle review statistics shown on vehicle/trip details."""
    vehicle_id: int
    vehicle_number: Optional[str] = None
    total_reviews: int
    average_rating: Optional[float] = None
    tag_counts: dict
    recent_comments: List[str]


class RideReviewResponse(BaseModel):
    """Full review record returned to the frontend."""
    review_id: int
    booking_id: int
    employee_id: int
    tenant_id: str
    driver_id: Optional[int] = None
    vehicle_id: Optional[int] = None
    route_id: Optional[int] = None

    overall_rating: Optional[int] = None

    driver_rating: Optional[int] = None
    driver_tags: Optional[List[str]] = None
    driver_comment: Optional[str] = None

    vehicle_rating: Optional[int] = None
    vehicle_tags: Optional[List[str]] = None
    vehicle_comment: Optional[str] = None

    is_active: bool
    created_at: datetime
    updated_at: datetime

    # Enriched snapshot shown to employees on booking detail page
    driver_name: Optional[str] = None
    driver_phone: Optional[str] = None
    vehicle_number: Optional[str] = None

    class Config:
        from_attributes = True
