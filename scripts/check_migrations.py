#!/usr/bin/env python3
"""
Pre-commit migration check
Run this before committing migration files
"""

import sys
import os
from pathlib import Path
import re

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))


def check_migration_files():
    """Check for common issues in migration files."""
    print("🔍 Checking migration files...")
    
    migrations_dir = project_root / "migrations" / "versions"
    migration_files = list(migrations_dir.glob("*.py"))
    
    if not migration_files:
        print("⚠️  No migration files found")
        return True
    
    issues = []
    
    for migration_file in migration_files:
        with open(migration_file, 'r', encoding='utf-8') as f:
            content = f.read()
        
        # Check for required functions
        if 'def upgrade()' not in content:
            issues.append(f"❌ {migration_file.name}: Missing upgrade() function")
        
        if 'def downgrade()' not in content:
            issues.append(f"❌ {migration_file.name}: Missing downgrade() function")
        
        # Check for common mistakes
        if 'def upgrade()' in content and 'pass' in content:
            # Only warn if BOTH upgrade and downgrade are just 'pass'
            upgrade_section = content.split('def upgrade()')[1].split('def downgrade()')[0]
            downgrade_section = content.split('def downgrade()')[1] if 'def downgrade()' in content else ''
            
            if upgrade_section.strip().endswith('pass') and 'pass' in downgrade_section:
                issues.append(f"⚠️  {migration_file.name}: Both upgrade and downgrade are empty (just 'pass')")
        
        # Check revision is set
        if "revision = None" in content and "down_revision = None" in content:
            pass  # This is OK for first migration
        elif "revision = None" in content:
            issues.append(f"❌ {migration_file.name}: revision is None")
    
    if issues:
        print("\n".join(issues))
        return False
    else:
        print(f"✅ All {len(migration_files)} migration files look good")
        return True


def check_env_py():
    """Check migrations/env.py for common issues."""
    print("\n🔍 Checking migrations/env.py...")
    
    env_file = project_root / "migrations" / "env.py"
    
    with open(env_file, 'r', encoding='utf-8') as f:
        content = f.read()
    
    issues = []
    
    # Check for critical imports
    if 'from app.database.session import Base' not in content:
        issues.append("❌ Missing import: app.database.session.Base")
    
    if 'target_metadata = Base.metadata' not in content:
        issues.append("❌ target_metadata not set to Base.metadata")
    
    # Check for model imports (at least a few core ones)
    critical_models = ['Tenant', 'Admin', 'Driver', 'Booking']
    for model in critical_models:
        if f'import {model}' not in content and f'from app.models' not in content:
            issues.append(f"⚠️  Model {model} might not be imported")
            break  # Only warn once
    
    if issues:
        print("\n".join(issues))
        return False
    else:
        print("✅ migrations/env.py looks good")
        return True


def check_alembic_ini():
    """Check alembic.ini configuration."""
    print("\n🔍 Checking alembic.ini...")
    
    alembic_file = project_root / "alembic.ini"
    
    with open(alembic_file, 'r', encoding='utf-8') as f:
        content = f.read()
    
    issues = []
    
    if 'script_location = migrations' not in content:
        issues.append("❌ script_location should be 'migrations'")
    
    # Check that sqlalchemy.url is empty (set dynamically in env.py)
    if re.search(r'sqlalchemy\.url\s*=\s*postgresql://', content):
        issues.append("⚠️  sqlalchemy.url should be empty (configured in env.py)")
    
    if issues:
        print("\n".join(issues))
        return False
    else:
        print("✅ alembic.ini looks good")
        return True


def check_models():
    """Quick check that models can be imported."""
    print("\n🔍 Checking models can be imported...")
    
    try:
        from app.database.session import Base
        from app.models.tenant import Tenant
        from app.models.admin import Admin
        print("✅ Core models import successfully")
        return True
    except Exception as e:
        print(f"❌ Error importing models: {e}")
        return False


def main():
    """Run all checks."""
    print("\n" + "="*60)
    print("🚀 Migration Pre-Commit Check")
    print("="*60 + "\n")
    
    checks = [
        ("Alembic Config", check_alembic_ini),
        ("Environment File", check_env_py),
        ("Migration Files", check_migration_files),
        ("Model Imports", check_models),
    ]
    
    results = []
    for name, check_func in checks:
        try:
            success = check_func()
            results.append((name, success))
        except Exception as e:
            print(f"❌ Check '{name}' failed with error: {e}")
            results.append((name, False))
    
    # Summary
    print("\n" + "="*60)
    print("📊 Check Summary")
    print("="*60)
    
    all_passed = all(success for _, success in results)
    
    for name, success in results:
        status = "✅" if success else "❌"
        print(f"{status} {name}")
    
    if all_passed:
        print("\n✅ All checks passed! Safe to commit.")
        print("="*60 + "\n")
        return 0
    else:
        print("\n❌ Some checks failed. Please fix before committing.")
        print("="*60 + "\n")
        return 1


if __name__ == "__main__":
    sys.exit(main())
