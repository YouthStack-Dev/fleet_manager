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

        # Build explicit structure (use None to create nulls in RTDB)
        location_data = {
            "driver_id": driver_id,
            "latitude": 12.9734,
            "longitude": 77.6140,
            "updated_at": datetime.utcnow().isoformat()
        }

        existing = ref.get()
        if existing is None:
            logger.info("Creating driver node at %s", ref_path)
            ref.set(location_data)
        else:
            # ensure keys exist without overwriting other keys
            # only set keys that are missing (so we keep existing data intact)
            missing = {k: v for k, v in location_data.items() if k not in existing}
            if missing:
                logger.info("Updating missing keys for %s: %s", ref_path, missing.keys())
                ref.update(missing)
            else:
                logger.info("Driver node exists and keys present for %s", ref_path)

        logger.info("Driver node ensured at %s", ref_path)

    except Exception as exc:
        logger.exception("Error pushing driver location to Firebase for %s: %s", ref_path, exc)
        # depending on business need, choose whether to raise or swallow
        # raising will kill the caller stack; swallowing will let the process continue
        # raise
