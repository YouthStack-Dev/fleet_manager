# app/routes/announcement_router.py
"""
Announcement / Broadcast Router
================================
Single flat router — all 11 endpoints registered directly on `router` so
FastAPI sees them the moment the module is imported (no include_router at
definition-time anti-pattern).

Admin endpoints  (booking.read permission required — tenant_id from JWT)
──────────────────────────────────────────────────────────────────────────
  POST   /announcements                      → create draft
  GET    /announcements                      → list (paginated, filterable by status)
  GET    /announcements/{id}                 → get one
  PUT    /announcements/{id}                 → update draft (DRAFT only)
  POST   /announcements/{id}/publish         → publish + push notifications
  DELETE /announcements/{id}                 → soft-delete
  GET    /announcements/{id}/recipients      → per-user delivery tracking

Employee app endpoints  (app-employee.read OR app-employee.write)
──────────────────────────────────────────────────────────────────
  GET    /employee/announcements             → list announcements I received
  POST   /employee/announcements/{id}/read   → mark as read

Driver app endpoints  (app-driver.read OR app-driver.write)
──────────────────────────────────────────────────────────────────
  GET    /driver/announcements               → list announcements I received
  POST   /driver/announcements/{id}/read     → mark as read
"""

from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.core.logging_config import get_logger
from app.crud.announcement import (
    create_announcement,
    delete_announcement,
    get_announcement,
    get_announcements_for_user,
    list_announcements,
    list_recipients,
    mark_announcement_read,
    publish_announcement,
    update_announcement,
)
from app.database.session import get_db
from app.models.announcement import Announcement
from app.schemas.announcement import AnnouncementCreate, AnnouncementUpdate
from app.utils.response_utils import ResponseWrapper
from common_utils.auth.permission_checker import PermissionChecker

logger = get_logger(__name__)

# ─────────────────────────────────────────────────────────────────────────────
# Single flat router — api.py registers with prefix=/api/v1
# ─────────────────────────────────────────────────────────────────────────────
router = APIRouter(tags=["Announcements"])


# ─────────────────────────────────────────────────────────────────────────────
# Auth dependency factories
# ─────────────────────────────────────────────────────────────────────────────

def AdminAuth(user_data=Depends(PermissionChecker(["booking.read"]))):
    """Require booking.read; returns {tenant_id, user_id}."""
    tenant_id = user_data.get("tenant_id")
    if not tenant_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Tenant not resolved from token",
        )
    return {"tenant_id": tenant_id, "user_id": user_data.get("user_id")}


def EmployeeAuth(
    user_data=Depends(PermissionChecker(["app-employee.read", "app-employee.write"]))
):
    """Require app-employee read/write; rejects non-employee callers."""
    if user_data.get("user_type") not in ("employee", "admin"):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Employee access only",
        )
    tenant_id = user_data.get("tenant_id")
    user_id   = user_data.get("user_id")
    if not tenant_id or not user_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="User or tenant not resolved from token",
        )
    return {"tenant_id": tenant_id, "user_id": int(user_id)}


def DriverAuth(
    user_data=Depends(PermissionChecker(["app-driver.read", "app-driver.write"]))
):
    """Require app-driver read/write; rejects non-driver callers."""
    if user_data.get("user_type") not in ("driver", "admin"):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Driver access only",
        )
    tenant_id = user_data.get("tenant_id")
    user_id   = user_data.get("user_id")
    if not tenant_id or not user_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="User or tenant not resolved from token",
        )
    return {"tenant_id": tenant_id, "user_id": int(user_id)}


# ─────────────────────────────────────────────────────────────────────────────
# Serialisation helpers
# ─────────────────────────────────────────────────────────────────────────────

def _enum_val(v) -> str:
    return v.value if hasattr(v, "value") else str(v)


def _ann_to_dict(ann: Announcement) -> dict:
    return {
        "announcement_id":  ann.announcement_id,
        "tenant_id":        ann.tenant_id,
        "title":            ann.title,
        "body":             ann.body,
        "content_type":     _enum_val(ann.content_type),
        "media_url":        ann.media_url,
        "media_filename":   ann.media_filename,
        "media_size_bytes": ann.media_size_bytes,
        "target_type":      _enum_val(ann.target_type),
        "target_ids":       ann.target_ids,
        "channels":         ann.channels or ["push", "in_app"],
        "status":           _enum_val(ann.status),
        "is_active":        ann.is_active,
        "total_recipients": ann.total_recipients,
        "success_count":    ann.success_count,
        "failure_count":    ann.failure_count,
        "no_device_count":  ann.no_device_count,
        "sms_sent_count":   ann.sms_sent_count   if hasattr(ann, "sms_sent_count")   else 0,
        "email_sent_count": ann.email_sent_count if hasattr(ann, "email_sent_count") else 0,
        "created_by":       ann.created_by,
        "published_at":     ann.published_at.isoformat() if ann.published_at else None,
        "created_at":       ann.created_at.isoformat() if ann.created_at else None,
        "updated_at":       ann.updated_at.isoformat() if ann.updated_at else None,
    }


def _rec_to_dict(rec) -> dict:
    return {
        "recipient_id":      rec.recipient_id,
        "announcement_id":   rec.announcement_id,
        "recipient_type":    rec.recipient_type,
        "recipient_user_id": rec.recipient_user_id,
        "delivery_status":   _enum_val(rec.delivery_status),
        "push_sent_at":      rec.push_sent_at.isoformat()  if rec.push_sent_at  else None,
        "sms_sent_at":       rec.sms_sent_at.isoformat()   if rec.sms_sent_at   else None,
        "email_sent_at":     rec.email_sent_at.isoformat() if rec.email_sent_at else None,
        "read_at":           rec.read_at.isoformat()       if rec.read_at       else None,
        "created_at":        rec.created_at.isoformat()    if rec.created_at    else None,
    }


def _get_or_404(db: Session, announcement_id: int, tenant_id: str) -> Announcement:
    ann = get_announcement(db, announcement_id, tenant_id)
    if not ann:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Announcement {announcement_id} not found",
        )
    return ann


# ─────────────────────────────────────────────────────────────────────────────
# Admin: Create
# ─────────────────────────────────────────────────────────────────────────────

@router.post("/announcements", status_code=status.HTTP_201_CREATED)
def create_announcement_endpoint(
    payload: AnnouncementCreate,
    auth: dict = Depends(AdminAuth),
    db: Session = Depends(get_db),
):
    """Create a new announcement in DRAFT status. Use /publish to broadcast it."""
    ann = create_announcement(
        db=db,
        tenant_id=auth["tenant_id"],
        created_by=auth.get("user_id"),
        payload=payload,
    )
    return ResponseWrapper.created(
        data=_ann_to_dict(ann),
        message="Announcement created successfully",
    )


# ─────────────────────────────────────────────────────────────────────────────
# Admin: List
# ─────────────────────────────────────────────────────────────────────────────

@router.get("/announcements")
def list_announcements_endpoint(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    status_filter: Optional[str] = Query(
        None, alias="status",
        description="Filter by status: draft | published | cancelled",
    ),
    content_type: Optional[str] = Query(
        None,
        description="Filter by content type: text | image | video | audio | pdf | link",
    ),
    target_type: Optional[str] = Query(
        None,
        description="Filter by target: all_employees | specific_employees | teams | all_drivers | vendor_drivers | specific_drivers",
    ),
    from_date: Optional[str] = Query(
        None,
        description="Start of date range — ISO date e.g. 2026-03-01  (applied to date_field)",
    ),
    to_date: Optional[str] = Query(
        None,
        description="End of date range — ISO date e.g. 2026-03-31  (inclusive, end-of-day)",
    ),
    date_field: str = Query(
        "created_at",
        description="Which date to filter on: created_at (default) | published_at",
    ),
    auth: dict = Depends(AdminAuth),
    db: Session = Depends(get_db),
):
    """
    List announcements for the tenant, newest first.

    Filters available
    -----------------
    status       → draft / published / cancelled
    content_type → text / image / video / audio / pdf / link
    target_type  → all_employees / specific_employees / teams /
                   all_drivers / vendor_drivers / specific_drivers
    from_date    → ISO date string, e.g. 2026-03-01
    to_date      → ISO date string, e.g. 2026-03-31  (inclusive)
    date_field   → created_at (default) or published_at
    """
    from datetime import datetime as dt

    def _parse_date(s: Optional[str]) -> Optional[dt]:
        if not s:
            return None
        try:
            return dt.fromisoformat(s)   # accepts "2026-03-01" or "2026-03-01T00:00:00"
        except ValueError:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=f"Invalid date format '{s}'. Use ISO format: YYYY-MM-DD",
            )

    if date_field not in ("created_at", "published_at"):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="date_field must be 'created_at' or 'published_at'",
        )

    items, total = list_announcements(
        db=db,
        tenant_id=auth["tenant_id"],
        page=page,
        page_size=page_size,
        status_filter=status_filter,
        content_type_filter=content_type,
        target_type_filter=target_type,
        from_date=_parse_date(from_date),
        to_date=_parse_date(to_date),
        date_field=date_field,
    )
    return ResponseWrapper.paginated(
        items=[_ann_to_dict(a) for a in items],
        total=total,
        page=page,
        per_page=page_size,
    )


# ─────────────────────────────────────────────────────────────────────────────
# Admin: Get one
# ─────────────────────────────────────────────────────────────────────────────

@router.get("/announcements/{announcement_id}")
def get_announcement_endpoint(
    announcement_id: int,
    auth: dict = Depends(AdminAuth),
    db: Session = Depends(get_db),
):
    """Get full details for one announcement."""
    ann = _get_or_404(db, announcement_id, auth["tenant_id"])
    return ResponseWrapper.success(data=_ann_to_dict(ann))


# ─────────────────────────────────────────────────────────────────────────────
# Admin: Update (DRAFT only)
# ─────────────────────────────────────────────────────────────────────────────

@router.put("/announcements/{announcement_id}")
def update_announcement_endpoint(
    announcement_id: int,
    payload: AnnouncementUpdate,
    auth: dict = Depends(AdminAuth),
    db: Session = Depends(get_db),
):
    """Update a DRAFT announcement. Returns 400 if already published."""
    ann = _get_or_404(db, announcement_id, auth["tenant_id"])
    try:
        ann = update_announcement(db=db, ann=ann, payload=payload)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))
    return ResponseWrapper.updated(
        data=_ann_to_dict(ann),
        message="Announcement updated successfully",
    )


# ─────────────────────────────────────────────────────────────────────────────
# Admin: Publish
# ─────────────────────────────────────────────────────────────────────────────

@router.post("/announcements/{announcement_id}/publish")
def publish_announcement_endpoint(
    announcement_id: int,
    auth: dict = Depends(AdminAuth),
    db: Session = Depends(get_db),
):
    """
    Publish a DRAFT announcement.

    Atomically:
      - Resolves target audience from DB
      - Creates AnnouncementRecipient rows
      - Sends batch push notifications
      - Updates delivery counters
    """
    ann = _get_or_404(db, announcement_id, auth["tenant_id"])
    try:
        ann = publish_announcement(db=db, ann=ann)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))
    return ResponseWrapper.success(
        data=_ann_to_dict(ann),
        message=f"Announcement published to {ann.total_recipients} recipient(s)",
    )


# ─────────────────────────────────────────────────────────────────────────────
# Admin: Soft-delete
# ─────────────────────────────────────────────────────────────────────────────

@router.delete("/announcements/{announcement_id}")
def delete_announcement_endpoint(
    announcement_id: int,
    auth: dict = Depends(AdminAuth),
    db: Session = Depends(get_db),
):
    """Soft-delete an announcement (is_active=False). DRAFT → CANCELLED."""
    ann = _get_or_404(db, announcement_id, auth["tenant_id"])
    delete_announcement(db=db, ann=ann)
    return ResponseWrapper.deleted(message="Announcement deleted successfully")


# ─────────────────────────────────────────────────────────────────────────────
# Admin: Delivery tracking
# ─────────────────────────────────────────────────────────────────────────────

@router.get("/announcements/{announcement_id}/recipients")
def list_announcement_recipients_endpoint(
    announcement_id: int,
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
    auth: dict = Depends(AdminAuth),
    db: Session = Depends(get_db),
):
    """List per-user delivery status for a published announcement."""
    ann = _get_or_404(db, announcement_id, auth["tenant_id"])
    items, total = list_recipients(
        db=db,
        announcement_id=ann.announcement_id,
        page=page,
        page_size=page_size,
    )
    return ResponseWrapper.paginated(
        items=[_rec_to_dict(r) for r in items],
        total=total,
        page=page,
        per_page=page_size,
    )


# ─────────────────────────────────────────────────────────────────────────────
# Employee app: List received announcements
# ─────────────────────────────────────────────────────────────────────────────

@router.get("/employee/announcements")
def employee_list_announcements(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    from_date: Optional[str] = Query(
        None, description="ISO date e.g. 2026-03-01 — filter by published_at"
    ),
    to_date: Optional[str] = Query(
        None, description="ISO date e.g. 2026-03-31 — inclusive end of range"
    ),
    unread_only: bool = Query(
        False, description="When true, return only unread announcements"
    ),
    content_type: Optional[str] = Query(
        None, description="Filter by content type: text | image | video | audio | pdf | link"
    ),
    auth: dict = Depends(EmployeeAuth),
    db: Session = Depends(get_db),
):
    """
    List announcements targeted to the authenticated employee.

    Filters available
    -----------------
    from_date    → ISO date string, e.g. 2026-03-01
    to_date      → ISO date string, e.g. 2026-03-31  (inclusive)
    unread_only  → true returns only unread items (great for badge counts)
    content_type → text / image / video / audio / pdf / link
    """
    from datetime import datetime as dt

    def _parse_date(s: Optional[str]):
        if not s:
            return None
        try:
            return dt.fromisoformat(s)
        except ValueError:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=f"Invalid date format '{s}'. Use ISO format: YYYY-MM-DD",
            )

    items, total = get_announcements_for_user(
        db=db,
        tenant_id=auth["tenant_id"],
        recipient_type="employee",
        recipient_user_id=auth["user_id"],
        page=page,
        page_size=page_size,
        from_date=_parse_date(from_date),
        to_date=_parse_date(to_date),
        unread_only=unread_only,
        content_type_filter=content_type,
    )
    return ResponseWrapper.paginated(
        items=items,
        total=total,
        page=page,
        per_page=page_size,
    )


# ─────────────────────────────────────────────────────────────────────────────
# Employee app: Mark read
# ─────────────────────────────────────────────────────────────────────────────

@router.post("/employee/announcements/{announcement_id}/read")
def employee_mark_announcement_read(
    announcement_id: int,
    auth: dict = Depends(EmployeeAuth),
    db: Session = Depends(get_db),
):
    """Mark an announcement as read for the authenticated employee."""
    rec = mark_announcement_read(
        db=db,
        announcement_id=announcement_id,
        recipient_type="employee",
        recipient_user_id=auth["user_id"],
    )
    if not rec:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Announcement not found for this user",
        )
    return ResponseWrapper.success(
        data={"read_at": rec.read_at.isoformat() if rec.read_at else None},
        message="Marked as read",
    )


# ─────────────────────────────────────────────────────────────────────────────
# Driver app: List received announcements
# ─────────────────────────────────────────────────────────────────────────────

@router.get("/driver/announcements")
def driver_list_announcements(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    from_date: Optional[str] = Query(
        None, description="ISO date e.g. 2026-03-01 — filter by published_at"
    ),
    to_date: Optional[str] = Query(
        None, description="ISO date e.g. 2026-03-31 — inclusive end of range"
    ),
    unread_only: bool = Query(
        False, description="When true, return only unread announcements"
    ),
    content_type: Optional[str] = Query(
        None, description="Filter by content type: text | image | video | audio | pdf | link"
    ),
    auth: dict = Depends(DriverAuth),
    db: Session = Depends(get_db),
):
    """
    List announcements targeted to the authenticated driver.

    Filters available
    -----------------
    from_date    → ISO date string, e.g. 2026-03-01
    to_date      → ISO date string, e.g. 2026-03-31  (inclusive)
    unread_only  → true returns only unread items
    content_type → text / image / video / audio / pdf / link
    """
    from datetime import datetime as dt

    def _parse_date(s: Optional[str]):
        if not s:
            return None
        try:
            return dt.fromisoformat(s)
        except ValueError:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=f"Invalid date format '{s}'. Use ISO format: YYYY-MM-DD",
            )

    items, total = get_announcements_for_user(
        db=db,
        tenant_id=auth["tenant_id"],
        recipient_type="driver",
        recipient_user_id=auth["user_id"],
        page=page,
        page_size=page_size,
        from_date=_parse_date(from_date),
        to_date=_parse_date(to_date),
        unread_only=unread_only,
        content_type_filter=content_type,
    )
    return ResponseWrapper.paginated(
        items=items,
        total=total,
        page=page,
        per_page=page_size,
    )


# ─────────────────────────────────────────────────────────────────────────────
# Driver app: Mark read
# ─────────────────────────────────────────────────────────────────────────────

@router.post("/driver/announcements/{announcement_id}/read")
def driver_mark_announcement_read(
    announcement_id: int,
    auth: dict = Depends(DriverAuth),
    db: Session = Depends(get_db),
):
    """Mark an announcement as read for the authenticated driver."""
    rec = mark_announcement_read(
        db=db,
        announcement_id=announcement_id,
        recipient_type="driver",
        recipient_user_id=auth["user_id"],
    )
    if not rec:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Announcement not found for this user",
        )
    return ResponseWrapper.success(
        data={"read_at": rec.read_at.isoformat() if rec.read_at else None},
        message="Marked as read",
    )
