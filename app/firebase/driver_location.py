"""
Firebase service for managing driver location data in hierarchical structure:
tenant_id -> vendor_id -> driver_id -> {latitude, longitude, metadata}

Enhanced with:
- Node initialization on duty start
- Auto-recovery for missing/deleted nodes
- Complete metadata (driver name, route info, status)
"""
from firebase_admin import db
from app.firebase.config import init_firebase
from app.core.logging_config import get_logger

from datetime import datetime
from typing import Optional
import firebase_admin
logger = get_logger(__name__)
init_firebase()

def push_driver_location_to_firebase(
    tenant_id: str,
    vendor_id: int,
    driver_id: int,
    latitude: float = None,
    longitude: float = None,
    speed: Optional[float] = None,
    driver_code: str = None,
    driver_name: str = None,
    route_id: int = None,
):
    """
    Update driver location data in Firebase with auto-recovery.
    
    Enhanced features:
    - Automatically recovers missing/deleted nodes
    - Updates complete metadata (location + speed + driver info)
    - Safe-checks: ensures firebase_admin is initialized
    
    Args:
        tenant_id: Tenant identifier
        vendor_id: Vendor ID
        driver_id: Driver ID (stored as int in Firebase)
        latitude: Current latitude
        longitude: Current longitude
        speed: Current speed in km/h (optional)
        driver_code: Driver code (for recovery)
        driver_name: Driver name (for recovery)
        route_id: Current route ID (for recovery)
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
        existing = ref.get()

        # Auto-recovery: If node doesn't exist, initialize it
        if existing is None:
            logger.warning(
                "[firebase.push] Node missing at %s — initializing before update",
                ref_path
            )
            if driver_name and driver_code and route_id:
                initialize_driver_node_on_duty_start(
                    tenant_id=tenant_id,
                    vendor_id=vendor_id,
                    driver_id=driver_id,
                    driver_name=driver_name,
                    driver_code=driver_code,
                    route_id=route_id,
                    initial_latitude=latitude,
                    initial_longitude=longitude,
                )
                # Add speed if available
                if speed is not None:
                    ref.update({"speed": speed})
                return
            else:
                # Missing recovery metadata - create minimal node
                logger.warning(
                    "[firebase.push] Missing recovery metadata for %s — creating minimal node",
                    ref_path
                )
        
        # Prepare location update data
        # driver_id cast to int: JWT encodes all claims as strings, we always want int in Firebase
        location_data = {
            "driver_id": int(driver_id),
            "latitude": latitude,
            "longitude": longitude,
            "updated_at": datetime.utcnow().isoformat()
        }
        
        # Add speed if available
        if speed is not None:
            location_data["speed"] = speed
        
        # Add recovery metadata if available
        if driver_name:
            location_data["driver_name"] = driver_name
        if driver_code:
            location_data["driver_code"] = driver_code
        if route_id:
            location_data["route_id"] = route_id
        
        # Ensure is_active flag is set
        location_data["is_active"] = True

        # Update node (creates if doesn't exist due to above recovery)
        if existing is None:
            logger.info("Creating driver node at %s", ref_path)
            ref.set(location_data)
        else:
            # Always update coordinates and timestamp
            ref.update(location_data)

        logger.debug(
            "Driver location updated at %s — lat=%.6f, lng=%.6f, speed=%s",
            ref_path, latitude, longitude, speed
        )

    except Exception as exc:
        logger.exception("Error pushing driver location to Firebase for %s: %s", ref_path, exc)
        # Swallow exception - Firebase failure must never block location tracking


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


def initialize_driver_node_on_duty_start(
    tenant_id: str,
    vendor_id: int,
    driver_id: int,
    driver_name: str,
    driver_code: str,
    route_id: int,
    initial_latitude: Optional[float] = None,
    initial_longitude: Optional[float] = None,
):
    """
    Initialize Firebase node when driver starts duty.
    
    Creates a complete driver node with all metadata:
    - Driver info (id, name, code)
    - Route info (id)
    - Initial location (if available)
    - Status flags (is_active, created_at)
    
    This ensures every active driver has a Firebase node, even before
    the first GPS ping arrives.
    
    Args:
        tenant_id: Tenant identifier
        vendor_id: Vendor ID
        driver_id: Driver ID (stored as int in Firebase)
        driver_name: Driver full name
        driver_code: Driver unique code
        route_id: Assigned route ID
        initial_latitude: Optional initial latitude
        initial_longitude: Optional initial longitude
    """
    ref_path = f"drivers/{tenant_id}/{vendor_id}/{driver_id}"
    
    try:
        try:
            firebase_admin.get_app()
        except ValueError:
            logger.error(
                "Firebase Admin SDK not initialized. Skipping node initialization for %s/%s/%s",
                tenant_id, vendor_id, driver_id
            )
            return
        
        ref = db.reference(ref_path)
        now = datetime.utcnow().isoformat()
        
        # Complete node structure with all metadata
        # driver_id cast to int: JWT encodes all claims as strings, we always want int in Firebase
        node_data = {
            "driver_id": int(driver_id),
            "driver_name": driver_name,
            "driver_code": driver_code,
            "route_id": route_id,
            "is_active": True,
            "created_at": now,
            "updated_at": now,
        }
        
        # Add initial location if available
        if initial_latitude is not None and initial_longitude is not None:
            node_data["latitude"] = initial_latitude
            node_data["longitude"] = initial_longitude
        
        # Check if node exists
        existing = ref.get()
        
        if existing is None:
            # Create new node
            ref.set(node_data)
            logger.info(
                "[firebase.init] Created driver node at %s for route %s",
                ref_path, route_id
            )
        else:
            # Update existing node (recovery from stale/partial data)
            ref.update(node_data)
            logger.info(
                "[firebase.init] Updated existing driver node at %s for route %s",
                ref_path, route_id
            )
    
    except Exception as exc:
        logger.exception(
            "[firebase.init] Error initializing driver node for %s: %s",
            ref_path, exc
        )


def ensure_driver_node_exists(
    tenant_id: str,
    vendor_id: int,
    driver_id: int,
    driver_name: str,
    driver_code: str,
    route_id: int,
) -> bool:
    """
    Auto-recovery: Ensures driver node exists in Firebase.
    
    Called before location updates to handle edge cases:
    - Manually deleted nodes
    - Failed duty start initialization
    - Missing nodes for any reason
    
    Returns:
        bool: True if node exists/created, False if initialization failed
    """
    ref_path = f"drivers/{tenant_id}/{vendor_id}/{driver_id}"
    
    try:
        try:
            firebase_admin.get_app()
        except ValueError:
            logger.error(
                "Firebase Admin SDK not initialized. Cannot check node existence for %s/%s/%s",
                tenant_id, vendor_id, driver_id
            )
            return False
        
        ref = db.reference(ref_path)
        existing = ref.get()
        
        if existing is None:
            logger.warning(
                "[firebase.recovery] Node missing at %s — auto-recovering",
                ref_path
            )
            # Initialize node without location (will be updated on next ping)
            initialize_driver_node_on_duty_start(
                tenant_id=tenant_id,
                vendor_id=vendor_id,
                driver_id=driver_id,
                driver_name=driver_name,
                driver_code=driver_code,
                route_id=route_id,
            )
            return True
        
        # Node exists - check if it needs metadata recovery
        if not existing.get("driver_name") or not existing.get("route_id"):
            logger.warning(
                "[firebase.recovery] Node at %s has incomplete metadata — recovering",
                ref_path
            )
            ref.update({
                "driver_name": driver_name,
                "driver_code": driver_code,
                "route_id": route_id,
                "is_active": True,
                "updated_at": datetime.utcnow().isoformat(),
            })
        
        return True
    
    except Exception as exc:
        logger.exception(
            "[firebase.recovery] Error ensuring node exists for %s: %s",
            ref_path, exc
        )
        return False


def sync_all_active_drivers_to_firebase(db_session):
    """
    Sync all active drivers with ongoing routes to Firebase.
    
    This is a maintenance/recovery function that:
    1. Queries all ONGOING routes from PostgreSQL
    2. Ensures each driver has a Firebase node
    3. Recovers missing or deleted nodes
    
    Should be called:
    - On server startup (to recover from crashes)
    - Periodically via scheduler (every 5 minutes)
    - Manually via admin API endpoint
    
    Args:
        db_session: SQLAlchemy database session
    """
    try:
        from app.models.route_management import RouteManagement, RouteManagementStatusEnum
        from app.models.driver import Driver
        from sqlalchemy.orm import joinedload
        
        # Query all ongoing routes with driver info
        ongoing_routes = (
            db_session.query(RouteManagement)
            .join(Driver, RouteManagement.assigned_driver_id == Driver.driver_id)
            .filter(RouteManagement.status == RouteManagementStatusEnum.ONGOING)
            .options(joinedload(RouteManagement.driver))
            .all()
        )
        
        logger.info(
            "[firebase.sync] Starting sync for %d ongoing routes",
            len(ongoing_routes)
        )
        
        success_count = 0
        error_count = 0
        
        for route in ongoing_routes:
            try:
                driver = route.driver
                
                # Get vendor_id from driver
                vendor_id = driver.vendor_id
                
                # Get latest location from PostgreSQL if available
                from app.models.driver_location_history import DriverLocationHistory
                latest_location = (
                    db_session.query(DriverLocationHistory)
                    .filter(DriverLocationHistory.route_id == route.route_id)
                    .order_by(DriverLocationHistory.recorded_at.desc())
                    .first()
                )
                
                # Initialize/update node
                initialize_driver_node_on_duty_start(
                    tenant_id=route.tenant_id,
                    vendor_id=vendor_id,
                    driver_id=driver.driver_id,
                    driver_name=driver.name,
                    driver_code=driver.code,
                    route_id=route.route_id,
                    initial_latitude=latest_location.latitude if latest_location else None,
                    initial_longitude=latest_location.longitude if latest_location else None,
                )
                
                success_count += 1
            
            except Exception as route_exc:
                logger.error(
                    "[firebase.sync] Failed to sync route %s: %s",
                    route.route_id, route_exc
                )
                error_count += 1
        
        logger.info(
            "[firebase.sync] Sync completed — success: %d, errors: %d",
            success_count, error_count
        )
        
        return {"success": success_count, "errors": error_count}
    
    except Exception as exc:
        logger.exception("[firebase.sync] Sync operation failed: %s", exc)
        return {"success": 0, "errors": -1}


def clean_old_mobile_app_fields(tenant_id: Optional[str] = None, dry_run: bool = False) -> dict:
    """
    Remove old fields added by Flutter mobile app: accuracy, heading, provider.
    
    These fields were written by an older version of the mobile app that
    wrote directly to Firebase. The current app sends all location data
    via REST API to the backend.
    
    Args:
        tenant_id: Specific tenant to clean (None = all tenants)
        dry_run: If True, only log what would be changed
    
    Returns:
        dict: {"cleaned": int, "errors": int}
    """
    try:
        firebase_admin.get_app()
    except ValueError:
        logger.error("Firebase not initialized")
        return {"error": "Firebase not initialized", "cleaned": 0, "errors": 1}
    
    logger.info("=" * 80)
    logger.info("FIREBASE NODE CLEANUP - Removing Old Mobile App Fields")
    logger.info("=" * 80)
    
    # Get root reference
    root_ref = db.reference("drivers")
    all_tenants = root_ref.get()
    
    if not all_tenants:
        logger.warning("No driver nodes found in Firebase")
        return {"cleaned": 0, "errors": 0}
    
    cleaned_count = 0
    error_count = 0
    
    # Filter to specific tenant if provided
    tenants_to_process = (
        {tenant_id: all_tenants[tenant_id]} 
        if tenant_id and tenant_id in all_tenants 
        else all_tenants
    )
    
    for tid, vendors in tenants_to_process.items():
        logger.info(f"\n📋 Processing Tenant: {tid}")
        
        if not isinstance(vendors, dict):
            continue
        
        for vendor_id, drivers in vendors.items():
            if not isinstance(drivers, dict):
                continue
            
            for driver_id, driver_data in drivers.items():
                if not isinstance(driver_data, dict):
                    continue
                
                # Check for old fields
                old_fields = []
                if "accuracy" in driver_data:
                    old_fields.append("accuracy")
                if "heading" in driver_data:
                    old_fields.append("heading")
                if "provider" in driver_data:
                    old_fields.append("provider")
                
                if old_fields:
                    node_path = f"drivers/{tid}/{vendor_id}/{driver_id}"
                    logger.info(
                        f"  🧹 {node_path}: Found old fields: {', '.join(old_fields)}"
                    )
                    
                    if not dry_run:
                        try:
                            node_ref = db.reference(node_path)
                            # Remove old fields
                            for field in old_fields:
                                node_ref.child(field).delete()
                            cleaned_count += 1
                            logger.info(f"    ✅ Cleaned")
                        except Exception as e:
                            logger.error(f"    ❌ Error: {e}")
                            error_count += 1
                    else:
                        logger.info(
                            f"    🔍 DRY RUN - Would remove: {', '.join(old_fields)}"
                        )
                        cleaned_count += 1
    
    logger.info("\n" + "=" * 80)
    logger.info(f"CLEANUP SUMMARY:")
    logger.info(f"  Nodes cleaned: {cleaned_count}")
    logger.info(f"  Errors: {error_count}")
    logger.info(f"  Mode: {'DRY RUN' if dry_run else 'LIVE'}")
    logger.info("=" * 80)
    
    return {"cleaned": cleaned_count, "errors": error_count}
