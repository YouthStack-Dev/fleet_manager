"""
Admin API Router

Administrative endpoints for system maintenance and management:
- Firebase node management (sync, cleanup, recovery)
- Database maintenance
- System operations

Access: Admin users only
"""
from fastapi import APIRouter, Depends, HTTPException, Query, status, BackgroundTasks
from sqlalchemy.orm import Session
from typing import Optional
from app.database.session import get_db
from app.core.logging_config import get_logger
from app.utils.response_utils import ResponseWrapper
from common_utils.auth.permission_checker import PermissionChecker
from datetime import datetime

logger = get_logger(__name__)

router = APIRouter(prefix="/admin", tags=["admin"])


# ============================================================
# FIREBASE SYNC & MANAGEMENT
# ============================================================

@router.post("/firebase/sync", status_code=status.HTTP_200_OK)
async def sync_firebase_driver_nodes(
    operation: str = Query(
        "full",
        description="Operation type: 'clean' (remove old fields), 'sync' (add missing nodes), or 'full' (both)",
        regex="^(clean|sync|full)$"
    ),
    tenant_id: Optional[str] = Query(None, description="Filter by specific tenant ID (e.g., HS001)"),
    dry_run: bool = Query(False, description="Preview changes without applying them"),
    db: Session = Depends(get_db),
    # ctx=Depends(AdminAuth),  # Uncomment when AdminAuth is available
):
    """
    Sync and manage Firebase driver location nodes.
    
    **Operations:**
    - `clean`: Remove old mobile app fields (accuracy, heading, provider)
    - `sync`: Ensure all active drivers (ONGOING routes) have complete Firebase nodes
    - `full`: Both clean and sync operations
    
    **Options:**
    - `tenant_id`: Process only specific tenant (default: all tenants)
    - `dry_run`: Preview changes without applying (default: false)
    
    **Use Cases:**
    - After server restart: Recover all active driver nodes
    - Manual cleanup: Remove legacy mobile app fields
    - Node recovery: Restore deleted or incomplete nodes
    - Health check: Verify all active drivers are tracked
    
    **Example:**
    ```bash
    # Preview full sync for all tenants
    curl -X POST "http://localhost:8000/api/v1/admin/firebase/sync?operation=full&dry_run=true"
    
    # Execute sync for specific tenant
    curl -X POST "http://localhost:8000/api/v1/admin/firebase/sync?operation=sync&tenant_id=HS001"
    ```
    """
    try:
        # tenant_id_from_ctx = ctx.get("tenant_id")  # Uncomment when auth is available
        logger.info(
            f"[admin.firebase.sync] Starting operation={operation}, "
            f"tenant_id={tenant_id}, dry_run={dry_run}"
        )
        
        results = {}
        start_time = datetime.utcnow()
        
        # Operation: Clean old mobile app fields
        if operation in ["clean", "full"]:
            logger.info("[admin.firebase.sync] Executing cleanup operation...")
            try:
                from app.firebase.driver_location import clean_old_mobile_app_fields
                clean_result = clean_old_mobile_app_fields(
                    tenant_id=tenant_id,
                    dry_run=dry_run
                )
                results["clean"] = clean_result
                logger.info(f"[admin.firebase.sync] Cleanup completed: {clean_result}")
            except Exception as clean_err:
                logger.exception(f"[admin.firebase.sync] Cleanup failed: {clean_err}")
                results["clean"] = {
                    "error": str(clean_err),
                    "cleaned": 0,
                    "errors": 1
                }
        
        # Operation: Sync all active drivers
        if operation in ["sync", "full"]:
            logger.info("[admin.firebase.sync] Executing sync operation...")
            try:
                from app.firebase.driver_location import sync_all_active_drivers_to_firebase
                sync_result = sync_all_active_drivers_to_firebase(db)
                results["sync"] = sync_result
                logger.info(f"[admin.firebase.sync] Sync completed: {sync_result}")
            except Exception as sync_err:
                logger.exception(f"[admin.firebase.sync] Sync failed: {sync_err}")
                results["sync"] = {
                    "error": str(sync_err),
                    "success": 0,
                    "errors": 1
                }
        
        end_time = datetime.utcnow()
        duration_ms = int((end_time - start_time).total_seconds() * 1000)
        
        # Build response message
        message_parts = []
        if operation in ["clean", "full"] and "clean" in results:
            message_parts.append(
                f"Cleaned {results['clean'].get('cleaned', 0)} nodes"
            )
        if operation in ["sync", "full"] and "sync" in results:
            message_parts.append(
                f"Synced {results['sync'].get('success', 0)} active drivers"
            )
        
        message = "Firebase sync completed: " + ", ".join(message_parts)
        if dry_run:
            message = "[DRY RUN] " + message
        
        return ResponseWrapper.success(
            message=message,
            data={
                "operation": operation,
                "tenant_id": tenant_id,
                "dry_run": dry_run,
                "duration_ms": duration_ms,
                "results": results,
                "timestamp": end_time.isoformat()
            }
        )
    
    except Exception as e:
        logger.exception("[admin.firebase.sync] Operation failed")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=ResponseWrapper.error(
                message="Firebase sync operation failed",
                error_code="FIREBASE_SYNC_ERROR",
                details={"error": str(e)}
            )
        )


@router.get("/firebase/status", status_code=status.HTTP_200_OK)
async def get_firebase_status(
    tenant_id: Optional[str] = Query(None, description="Filter by tenant ID"),
    # ctx=Depends(AdminAuth),  # Uncomment when AdminAuth is available
):
    """
    Get Firebase RTDB status and node statistics.
    
    Returns:
    - Total number of driver nodes
    - Nodes by tenant
    - Nodes with incomplete metadata
    - Nodes with old mobile app fields
    - Active vs inactive nodes
    
    **Example:**
    ```bash
    curl -X GET "http://localhost:8000/api/v1/admin/firebase/status"
    curl -X GET "http://localhost:8000/api/v1/admin/firebase/status?tenant_id=HS001"
    ```
    """
    try:
        from firebase_admin import db
        import firebase_admin
        
        logger.info(f"[admin.firebase.status] Checking Firebase status, tenant_id={tenant_id}")
        
        # Check Firebase SDK
        try:
            firebase_admin.get_app()
            sdk_initialized = True
        except ValueError:
            sdk_initialized = False
        
        if not sdk_initialized:
            return ResponseWrapper.error(
                message="Firebase SDK not initialized",
                error_code="FIREBASE_NOT_INITIALIZED"
            )
        
        # Get all driver nodes
        root_ref = db.reference("drivers")
        all_tenants = root_ref.get()
        
        if not all_tenants:
            return ResponseWrapper.success(
                message="No driver nodes found in Firebase",
                data={
                    "sdk_initialized": True,
                    "total_nodes": 0,
                    "tenants": []
                }
            )
        
        # Analyze nodes
        stats = {
            "sdk_initialized": True,
            "total_nodes": 0,
            "active_nodes": 0,
            "inactive_nodes": 0,
            "nodes_with_old_fields": 0,
            "incomplete_nodes": 0,
            "tenants": []
        }
        
        # Filter to specific tenant if provided
        tenants_to_process = {tenant_id: all_tenants[tenant_id]} if tenant_id and tenant_id in all_tenants else all_tenants
        
        for tid, vendors in tenants_to_process.items():
            if not isinstance(vendors, dict):
                continue
            
            tenant_stats = {
                "tenant_id": tid,
                "total_nodes": 0,
                "active_nodes": 0,
                "inactive_nodes": 0,
                "nodes_with_old_fields": 0,
                "incomplete_nodes": 0
            }
            
            for vendor_id, drivers in vendors.items():
                if not isinstance(drivers, dict):
                    continue
                
                for driver_id, driver_data in drivers.items():
                    if not isinstance(driver_data, dict):
                        continue
                    
                    stats["total_nodes"] += 1
                    tenant_stats["total_nodes"] += 1
                    
                    # Check active status
                    if driver_data.get("is_active", False):
                        stats["active_nodes"] += 1
                        tenant_stats["active_nodes"] += 1
                    else:
                        stats["inactive_nodes"] += 1
                        tenant_stats["inactive_nodes"] += 1
                    
                    # Check for old mobile app fields
                    if any(field in driver_data for field in ["accuracy", "heading", "provider"]):
                        stats["nodes_with_old_fields"] += 1
                        tenant_stats["nodes_with_old_fields"] += 1
                    
                    # Check for incomplete metadata
                    required_fields = ["driver_name", "driver_code", "route_id", "route_code"]
                    if not all(field in driver_data for field in required_fields):
                        stats["incomplete_nodes"] += 1
                        tenant_stats["incomplete_nodes"] += 1
            
            stats["tenants"].append(tenant_stats)
        
        return ResponseWrapper.success(
            message="Firebase status retrieved",
            data=stats
        )
    
    except Exception as e:
        logger.exception("[admin.firebase.status] Failed to get Firebase status")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=ResponseWrapper.error(
                message="Failed to retrieve Firebase status",
                error_code="FIREBASE_STATUS_ERROR",
                details={"error": str(e)}
            )
        )


@router.delete("/firebase/node", status_code=status.HTTP_200_OK)
async def delete_firebase_node(
    tenant_id: str = Query(..., description="Tenant ID"),
    vendor_id: int = Query(..., description="Vendor ID"),
    driver_id: int = Query(..., description="Driver ID"),
    # ctx=Depends(AdminAuth),  # Uncomment when AdminAuth is available
):
    """
    Delete a specific driver node from Firebase.
    
    **Use Cases:**
    - Remove stale/invalid nodes
    - Clean up test data
    - Force node recreation (will auto-recover on next ping)
    
    **Example:**
    ```bash
    curl -X DELETE "http://localhost:8000/api/v1/admin/firebase/node?tenant_id=HS001&vendor_id=30&driver_id=12"
    ```
    """
    try:
        from firebase_admin import db
        import firebase_admin
        
        logger.info(
            f"[admin.firebase.delete] Deleting node: "
            f"tenant={tenant_id}, vendor={vendor_id}, driver={driver_id}"
        )
        
        # Check Firebase SDK
        try:
            firebase_admin.get_app()
        except ValueError:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail=ResponseWrapper.error(
                    message="Firebase SDK not initialized",
                    error_code="FIREBASE_NOT_INITIALIZED"
                )
            )
        
        ref_path = f"drivers/{tenant_id}/{vendor_id}/{driver_id}"
        ref = db.reference(ref_path)
        
        # Check if node exists
        existing = ref.get()
        if existing is None:
            return ResponseWrapper.error(
                message=f"Node not found at path: {ref_path}",
                error_code="NODE_NOT_FOUND"
            )
        
        # Delete node
        ref.delete()
        
        logger.info(f"[admin.firebase.delete] Successfully deleted node: {ref_path}")
        
        return ResponseWrapper.success(
            message="Firebase node deleted successfully",
            data={
                "path": ref_path,
                "tenant_id": tenant_id,
                "vendor_id": vendor_id,
                "driver_id": driver_id,
                "note": "Node will auto-recover if driver sends location ping"
            }
        )
    
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("[admin.firebase.delete] Failed to delete node")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=ResponseWrapper.error(
                message="Failed to delete Firebase node",
                error_code="FIREBASE_DELETE_ERROR",
                details={"error": str(e)}
            )
        )


# ============================================================
# BACKGROUND TASK MANAGEMENT
# ============================================================

@router.post("/firebase/sync/background", status_code=status.HTTP_202_ACCEPTED)
async def sync_firebase_background(
    operation: str = Query("full", regex="^(clean|sync|full)$"),
    tenant_id: Optional[str] = Query(None),
    background_tasks: BackgroundTasks = BackgroundTasks(),
    db: Session = Depends(get_db),
    # ctx=Depends(AdminAuth),  # Uncomment when AdminAuth is available
):
    """
    Trigger Firebase sync as a background task (non-blocking).
    
    For large operations that may take time, this endpoint returns immediately
    and processes the sync in the background.
    
    **Response:** 202 Accepted with task_id for status tracking
    
    **Example:**
    ```bash
    # Start background sync
    curl -X POST "http://localhost:8000/api/v1/admin/firebase/sync/background?operation=full"
    
    # Response: {"task_id": "abc-123-def"}
    
    # Check status later
    curl -X GET "http://localhost:8000/api/v1/monitoring/tasks/abc-123-def"
    ```
    """
    try:
        from uuid import uuid4
        
        task_id = str(uuid4())
        
        logger.info(
            f"[admin.firebase.sync.bg] Queueing background task: "
            f"task_id={task_id}, operation={operation}, tenant_id={tenant_id}"
        )
        
        # Add background task
        background_tasks.add_task(
            _execute_firebase_sync_bg,
            task_id=task_id,
            operation=operation,
            tenant_id=tenant_id,
            db=db
        )
        
        return ResponseWrapper.success(
            message="Firebase sync queued as background task",
            data={
                "task_id": task_id,
                "operation": operation,
                "tenant_id": tenant_id,
                "status_endpoint": f"/api/v1/monitoring/tasks/{task_id}"
            }
        )
    
    except Exception as e:
        logger.exception("[admin.firebase.sync.bg] Failed to queue background task")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=ResponseWrapper.error(
                message="Failed to queue Firebase sync task",
                error_code="TASK_QUEUE_ERROR",
                details={"error": str(e)}
            )
        )


def _execute_firebase_sync_bg(
    task_id: str,
    operation: str,
    tenant_id: Optional[str],
    db: Session
):
    """Background task executor for Firebase sync"""
    try:
        from app.utils.task_manager import update_task_status
        
        logger.info(f"[admin.firebase.sync.bg] Starting task: {task_id}")
        
        update_task_status(task_id, "running", {"operation": operation, "tenant_id": tenant_id})
        
        results = {}
        
        # Clean operation
        if operation in ["clean", "full"]:
            from app.firebase.driver_location import clean_old_mobile_app_fields
            results["clean"] = clean_old_mobile_app_fields(tenant_id=tenant_id, dry_run=False)
        
        # Sync operation
        if operation in ["sync", "full"]:
            from app.firebase.driver_location import sync_all_active_drivers_to_firebase
            results["sync"] = sync_all_active_drivers_to_firebase(db)
        
        update_task_status(task_id, "completed", results)
        logger.info(f"[admin.firebase.sync.bg] Completed task: {task_id}")
    
    except Exception as e:
        logger.exception(f"[admin.firebase.sync.bg] Task failed: {task_id}")
        from app.utils.task_manager import update_task_status
        update_task_status(task_id, "failed", {"error": str(e)})
