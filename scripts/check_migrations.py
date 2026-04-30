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

    # Regex-based function detection — tolerates `-> None` type annotations and
    # any amount of whitespace that Alembic / Black may generate, e.g.:
    #   def upgrade():
    #   def upgrade() -> None:
    #   def upgrade()  ->  None :
    _upgrade_re   = re.compile(r'^\s*def\s+upgrade\s*\(\s*\)\s*(?:->\s*\w+\s*)?:', re.M)
    _downgrade_re = re.compile(r'^\s*def\s+downgrade\s*\(\s*\)\s*(?:->\s*\w+\s*)?:', re.M)

    # Detect a merge migration: down_revision is a tuple (two or more parents).
    # Merge migrations intentionally have empty (pass-only) bodies.
    _merge_re = re.compile(r'^down_revision\s*=\s*\(', re.M)

    issues = []

    for migration_file in migration_files:
        with open(migration_file, 'r', encoding='utf-8') as f:
            content = f.read()

        is_merge = bool(_merge_re.search(content))

        # ── 1. Required function signatures ───────────────────────────────────
        if not _upgrade_re.search(content):
            issues.append(f"❌ {migration_file.name}: Missing upgrade() function")

        if not _downgrade_re.search(content):
            issues.append(f"❌ {migration_file.name}: Missing downgrade() function")

        # ── 2. Warn when both bodies are pass-only (skip for merge migrations) ─
        # Use regex to extract the body of each function so we don't get tripped
        # up by `-> None` annotations in the split delimiter.
        if not is_merge and _upgrade_re.search(content) and _downgrade_re.search(content):
            # Split on the upgrade signature, grab everything after it
            after_upgrade   = _upgrade_re.split(content, maxsplit=1)[-1]
            # The upgrade body is everything up to the next top-level def
            upgrade_body    = re.split(r'\ndef\s+\w', after_upgrade, maxsplit=1)[0]
            after_downgrade = _downgrade_re.split(content, maxsplit=1)[-1]
            downgrade_body  = re.split(r'\ndef\s+\w', after_downgrade, maxsplit=1)[0]

            upgrade_is_empty   = re.fullmatch(r'\s*(pass\s*)?', upgrade_body) is not None
            downgrade_is_empty = re.fullmatch(r'\s*(pass\s*)?', downgrade_body) is not None

            if upgrade_is_empty and downgrade_is_empty:
                issues.append(
                    f"⚠️  {migration_file.name}: Both upgrade() and downgrade() are empty. "
                    f"If this is intentional (e.g. a no-op migration), add a comment explaining why."
                )

        # ── 3. revision must not be None (except the very first migration) ────
        if re.search(r'^revision\s*=\s*None', content, re.M):
            if not re.search(r'^down_revision\s*=\s*None', content, re.M):
                # down_revision = None only appears in the root migration; if it's
                # absent and revision is None, the file was left in a broken state.
                issues.append(f"❌ {migration_file.name}: revision = None (did Alembic fail to generate the ID?)")

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

    # Settings() requires SECRET_KEY at instantiation time.  This script only
    # validates that model metadata is importable — it never uses the secret
    # key.  Set a dummy value so BaseSettings doesn't raise when no .env file
    # is present (CI pre-install step, local pre-commit hook, etc.).
    os.environ.setdefault("SECRET_KEY", "check-migrations-dummy-not-used")

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
