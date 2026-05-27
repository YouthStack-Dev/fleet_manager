"""
Firebase service for managing driver location data in hierarchical structure:
tenant_id -> vendor_id -> driver_id -> {latitude, longitude}
"""
from firebase_admin import db
from app.firebase.config import init_firebase
from app.core.logging_config import get_logger

from datetime import datetime
import firebase_admin
logger = get_logger(__name__)
init_firebase()

def push_driver_location_to_firebase(
    tenant_id: str,
    vendor_id: int,
    driver_id: int,
    latitude: float = None,
    longitude: float = None,
    driver_code: str = None
):
    """
    Initialize or update driver location data in Firebase.
    Safe-checks: ensures firebase_admin is initialized before using db.reference.
    """

    ref_path = f"drivers/{tenant_id}/{vendor_id}/{driver_id}"

    try:
        # Ensure firebase app exists (avoid ValueError)
        try:
            firebase_admin.get_app()
        except ValueError:
            # Not initialized — log and fail-safe: do not crash entire request flow
            logger.error(
                "Firebase Admin SDK not initialized. Skipping Firebase push for %s/%s/%s",
                tenant_id, vendor_id, driver_id
            )
            return

        ref = db.reference(ref_path)

        # BUG-1 fixed: use the actual latitude/longitude params instead of hardcoded coords
        # BUG-2 fixed: always overwrite lat/lng/updated_at so live location stays current
        location_data = {
            "driver_id": driver_id,
            "latitude": latitude,
            "longitude": longitude,
            "updated_at": datetime.utcnow().isoformat()
        }

        existing = ref.get()
        if existing is None:
            logger.info("Creating driver node at %s", ref_path)
            ref.set(location_data)
        else:
            # Always update coordinates and timestamp — never skip if keys already exist
            ref.update(location_data)

        logger.info(
            "Driver location updated at %s — lat=%.6f, lng=%.6f",
            ref_path, latitude, longitude
        )

    except Exception as exc:
        logger.exception("Error pushing driver location to Firebase for %s: %s", ref_path, exc)
        # depending on business need, choose whether to raise or swallow
        # raising will kill the caller stack; swallowing will let the process continue
        # raise


def clear_driver_location_from_firebase(
    tenant_id: str,
    vendor_id: int,
    driver_id: int,
):
    """
    IMP-11 — Mark driver as offline in Firebase RTDB when duty ends.

    Sets `is_active=False` and `cleared_at` on the driver node rather than
    deleting it.  This allows any client currently subscribed to the node to
    receive the update and hide the marker, without losing the last-known
    position for audit purposes.

    If the node does not exist, this is a no-op.
    All exceptions are swallowed — a Firebase failure must never prevent
    a successful duty-end response.
    """
    ref_path = f"drivers/{tenant_id}/{vendor_id}/{driver_id}"
    try:
        try:
            firebase_admin.get_app()
        except ValueError:
            logger.error(
                "Firebase Admin SDK not initialized. Skipping Firebase clear for %s/%s/%s",
                tenant_id, vendor_id, driver_id,
            )
            return

        ref = db.reference(ref_path)
        existing = ref.get()
        if existing is None:
            logger.info(
                "[firebase.clear] Driver node %s not found — nothing to clear",
                ref_path,
            )
            return

        ref.update({
            "is_active": False,
            "cleared_at": datetime.utcnow().isoformat(),
        })
        logger.info(
            "[firebase.clear] Driver node marked offline at %s",
            ref_path,
        )

    except Exception as exc:
        logger.exception(
            "[firebase.clear] Error clearing Firebase node for %s: %s",
            ref_path, exc,
        )
