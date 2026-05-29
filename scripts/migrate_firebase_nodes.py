#!/usr/bin/env python3
"""
Firebase Node Migration Script

Purpose:
- Standardize all driver location nodes in Firebase
- Remove old fields from mobile app (accuracy, heading, provider)
- Add new backend fields (driver_name, driver_code, route_id, route_code)
- Ensure all active drivers have complete metadata

Usage:
    python scripts/migrate_firebase_nodes.py [--dry-run] [--tenant-id HS001]
"""
import sys
import os
import argparse
from datetime import datetime

# Add parent directory to path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from app.database.session import get_db
from app.firebase.driver_location import sync_all_active_drivers_to_firebase
from app.core.logging_config import get_logger
from firebase_admin import db
import firebase_admin

logger = get_logger(__name__)


def clean_old_mobile_app_fields(tenant_id: str = None, dry_run: bool = False):
    """
    Remove old fields added by Flutter app: accuracy, heading, provider
    
    Args:
        tenant_id: Specific tenant to clean (None = all tenants)
        dry_run: If True, only log what would be changed
    """
    try:
        firebase_admin.get_app()
    except ValueError:
        logger.error("Firebase not initialized")
        return {"error": "Firebase not initialized"}
    
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
    tenants_to_process = {tenant_id: all_tenants[tenant_id]} if tenant_id and tenant_id in all_tenants else all_tenants
    
    for tenant_id, vendors in tenants_to_process.items():
        logger.info(f"\n📋 Processing Tenant: {tenant_id}")
        
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
                    node_path = f"drivers/{tenant_id}/{vendor_id}/{driver_id}"
                    logger.info(f"  🧹 {node_path}: Found old fields: {', '.join(old_fields)}")
                    
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
                        logger.info(f"    🔍 DRY RUN - Would remove: {', '.join(old_fields)}")
                        cleaned_count += 1
    
    logger.info("\n" + "=" * 80)
    logger.info(f"CLEANUP SUMMARY:")
    logger.info(f"  Nodes cleaned: {cleaned_count}")
    logger.info(f"  Errors: {error_count}")
    logger.info(f"  Mode: {'DRY RUN' if dry_run else 'LIVE'}")
    logger.info("=" * 80)
    
    return {"cleaned": cleaned_count, "errors": error_count}


def sync_active_drivers(dry_run: bool = False):
    """
    Sync all active drivers from PostgreSQL to Firebase
    Ensures all ONGOING routes have complete Firebase nodes
    """
    logger.info("\n" + "=" * 80)
    logger.info("FIREBASE NODE SYNC - Adding Missing Nodes for Active Drivers")
    logger.info("=" * 80)
    
    if dry_run:
        logger.info("🔍 DRY RUN MODE - No actual changes will be made")
        # In dry run, we'd need to query DB and log what would be synced
        from app.models.route_management import RouteManagement, RouteManagementStatusEnum
        db_session = next(get_db())
        
        ongoing_routes = (
            db_session.query(RouteManagement)
            .filter(RouteManagement.status == RouteManagementStatusEnum.ONGOING)
            .all()
        )
        
        logger.info(f"  Found {len(ongoing_routes)} ongoing routes")
        for route in ongoing_routes:
            logger.info(f"  🔍 Would sync: Route {route.route_id} - Driver {route.assigned_driver_id}")
        
        db_session.close()
        return {"success": len(ongoing_routes), "errors": 0, "dry_run": True}
    else:
        db_session = next(get_db())
        result = sync_all_active_drivers_to_firebase(db_session)
        db_session.close()
        
        logger.info("\n" + "=" * 80)
        logger.info(f"SYNC SUMMARY:")
        logger.info(f"  Success: {result['success']}")
        logger.info(f"  Errors: {result['errors']}")
        logger.info("=" * 80)
        
        return result


def main():
    parser = argparse.ArgumentParser(
        description="Migrate and clean Firebase driver location nodes"
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show what would be changed without making actual changes"
    )
    parser.add_argument(
        "--tenant-id",
        type=str,
        help="Only process specific tenant (e.g., HS001)"
    )
    parser.add_argument(
        "--clean-only",
        action="store_true",
        help="Only clean old fields, don't sync active drivers"
    )
    parser.add_argument(
        "--sync-only",
        action="store_true",
        help="Only sync active drivers, don't clean old fields"
    )
    
    args = parser.parse_args()
    
    logger.info("\n" + "🚀 " * 20)
    logger.info("FIREBASE NODE MIGRATION SCRIPT")
    logger.info("🚀 " * 20 + "\n")
    
    if args.dry_run:
        logger.warning("⚠️  DRY RUN MODE - No changes will be made")
    
    # Step 1: Clean old mobile app fields
    if not args.sync_only:
        clean_result = clean_old_mobile_app_fields(
            tenant_id=args.tenant_id,
            dry_run=args.dry_run
        )
    
    # Step 2: Sync all active drivers
    if not args.clean_only:
        sync_result = sync_active_drivers(dry_run=args.dry_run)
    
    logger.info("\n" + "✅ " * 20)
    logger.info("MIGRATION COMPLETE")
    logger.info("✅ " * 20 + "\n")


if __name__ == "__main__":
    main()
