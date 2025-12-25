"""
Quick migration validation script
Run this to quickly verify migration setup
"""

import sys
import os
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

def check_files():
    """Check if all required files exist."""
    print("🔍 Checking migration files...")
    
    required_files = [
        "alembic.ini",
        "migrate.py",
        "migrate.sh",
        "migrations/env.py",
        "migrations/script.py.mako",
        "migrations/versions",
    ]
    
    all_exist = True
    for file_path in required_files:
        full_path = project_root / file_path
        exists = full_path.exists()
        status = "✅" if exists else "❌"
        print(f"{status} {file_path}")
        if not exists:
            all_exist = False
    
    return all_exist


def check_imports():
    """Check if models can be imported."""
    print("\n🔍 Checking model imports...")
    
    try:
        from app.database.session import Base
        from app.models.admin import Admin
        from app.models.tenant import Tenant
        print("✅ Core models can be imported")
        return True
    except Exception as e:
        print(f"❌ Error importing models: {e}")
        return False


def check_config():
    """Check database configuration."""
    print("\n🔍 Checking database configuration...")
    
    try:
        from app.config import settings
        print(f"✅ Database URL configured: {settings.DATABASE_URL[:30]}...")
        return True
    except Exception as e:
        print(f"❌ Error reading configuration: {e}")
        return False


def main():
    """Run validation checks."""
    print("\n" + "="*60)
    print("🚀 Migration Setup Validation")
    print("="*60 + "\n")
    
    checks = [
        ("Files", check_files),
        ("Imports", check_imports),
        ("Config", check_config),
    ]
    
    results = []
    for name, check_func in checks:
        try:
            success = check_func()
            results.append((name, success))
        except Exception as e:
            print(f"❌ Check '{name}' failed: {e}")
            results.append((name, False))
    
    # Summary
    print("\n" + "="*60)
    print("📊 Validation Summary")
    print("="*60)
    
    all_passed = all(success for _, success in results)
    
    for name, success in results:
        status = "✅" if success else "❌"
        print(f"{status} {name}")
    
    if all_passed:
        print("\n✅ Migration setup is ready!")
        print("\nNext steps:")
        print("  1. Run: python migrate.py create 'initial migration'")
        print("  2. Review the generated migration file")
        print("  3. Run: python migrate.py upgrade")
    else:
        print("\n❌ Some checks failed. Please fix the issues above.")
    
    print("="*60 + "\n")


if __name__ == "__main__":
    main()
