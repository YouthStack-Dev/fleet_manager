"""
Test script for database migrations
This script verifies that migrations are working correctly
"""

import sys
import os
from pathlib import Path
import subprocess

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

def run_command(command, description):
    """Run a command and return success status."""
    print(f"\n{'='*60}")
    print(f"🧪 Test: {description}")
    print(f"{'='*60}")
    print(f"Running: {command}\n")
    
    result = subprocess.run(
        command,
        shell=True,
        capture_output=True,
        text=True
    )
    
    print(result.stdout)
    if result.stderr:
        print("STDERR:", result.stderr)
    
    success = result.returncode == 0
    status = "✅ PASSED" if success else "❌ FAILED"
    print(f"\n{status}")
    
    return success


def test_alembic_config():
    """Test 1: Verify Alembic configuration."""
    return run_command(
        "alembic --version",
        "Verify Alembic is installed and accessible"
    )


def test_migration_env():
    """Test 2: Test migration environment."""
    return run_command(
        "alembic current",
        "Check current migration state"
    )


def test_migration_creation():
    """Test 3: Test creating a migration."""
    return run_command(
        'alembic revision --autogenerate -m "initial migration"',
        "Generate initial migration"
    )


def test_migration_upgrade():
    """Test 4: Test upgrading database."""
    return run_command(
        "alembic upgrade head",
        "Apply all migrations"
    )


def test_migration_current():
    """Test 5: Verify current state."""
    return run_command(
        "alembic current",
        "Check migration applied successfully"
    )


def test_migration_history():
    """Test 6: Check migration history."""
    return run_command(
        "alembic history",
        "Display migration history"
    )


def test_python_migrate_script():
    """Test 7: Test Python migration script."""
    return run_command(
        "python migrate.py help",
        "Test migration helper script"
    )


def test_database_connection():
    """Test 8: Verify database connection."""
    try:
        from app.config import settings
        from app.database.session import engine
        
        print("\n" + "="*60)
        print("🧪 Test: Verify database connection")
        print("="*60)
        
        print(f"\nDatabase URL: {settings.DATABASE_URL}")
        
        # Test connection
        with engine.connect() as conn:
            result = conn.execute("SELECT version()")
            version = result.fetchone()[0]
            print(f"PostgreSQL Version: {version}")
            
        print("\n✅ PASSED")
        return True
        
    except Exception as e:
        print(f"\n❌ FAILED: {str(e)}")
        return False


def test_models_import():
    """Test 9: Verify all models can be imported."""
    try:
        print("\n" + "="*60)
        print("🧪 Test: Import all models")
        print("="*60)
        
        from app.models.admin import Admin
        from app.models.audit_log import AuditLog
        from app.models.booking import Booking
        from app.models.cutoff import CutoffTime
        from app.models.driver import Driver
        from app.models.employee import Employee
        from app.models.escort import Escort
        from app.models.shift import Shift
        from app.models.team import Team
        from app.models.tenant_config import TenantConfig
        from app.models.tenant import Tenant
        from app.models.vehicle_type import VehicleType
        from app.models.vehicle import Vehicle
        from app.models.vendor_user import VendorUser
        from app.models.vendor import Vendor
        from app.models.weekoff_config import WeekOffConfig
        
        print("✅ All models imported successfully")
        print("\n✅ PASSED")
        return True
        
    except Exception as e:
        print(f"\n❌ FAILED: {str(e)}")
        return False


def main():
    """Run all tests."""
    print("\n" + "="*60)
    print("🚀 Fleet Manager Migration Test Suite")
    print("="*60)
    
    tests = [
        ("Alembic Configuration", test_alembic_config),
        ("Database Connection", test_database_connection),
        ("Model Imports", test_models_import),
        ("Migration Environment", test_migration_env),
        ("Migration Creation", test_migration_creation),
        ("Migration Upgrade", test_migration_upgrade),
        ("Current State", test_migration_current),
        ("Migration History", test_migration_history),
        ("Python Script", test_python_migrate_script),
    ]
    
    results = []
    for name, test_func in tests:
        try:
            success = test_func()
            results.append((name, success))
        except Exception as e:
            print(f"\n❌ Test '{name}' crashed: {str(e)}")
            results.append((name, False))
    
    # Print summary
    print("\n\n" + "="*60)
    print("📊 Test Summary")
    print("="*60)
    
    passed = sum(1 for _, success in results if success)
    total = len(results)
    
    for name, success in results:
        status = "✅ PASSED" if success else "❌ FAILED"
        print(f"{status}: {name}")
    
    print(f"\n{'='*60}")
    print(f"Results: {passed}/{total} tests passed")
    print(f"{'='*60}\n")
    
    # Exit with appropriate code
    sys.exit(0 if passed == total else 1)


if __name__ == "__main__":
    main()
