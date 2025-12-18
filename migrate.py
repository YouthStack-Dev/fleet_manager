#!/usr/bin/env python3
"""
Migration Management Script for Fleet Manager
Provides easy commands for database migrations
"""

import sys
import os
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

def main():
    """Main entry point for migration commands."""
    if len(sys.argv) < 2:
        print_help()
        sys.exit(1)
    
    command = sys.argv[1].lower()
    
    if command == "init":
        init_migrations()
    elif command == "create":
        create_migration()
    elif command == "upgrade":
        upgrade_database()
    elif command == "downgrade":
        downgrade_database()
    elif command == "current":
        show_current()
    elif command == "history":
        show_history()
    elif command == "heads":
        show_heads()
    elif command == "help":
        print_help()
    else:
        print(f"Unknown command: {command}")
        print_help()
        sys.exit(1)


def init_migrations():
    """Initialize the database with all migrations."""
    print("🚀 Initializing database...")
    os.system("alembic upgrade head")
    print("✅ Database initialized successfully!")


def create_migration():
    """Create a new migration."""
    if len(sys.argv) < 3:
        print("❌ Error: Please provide a message for the migration")
        print("Usage: python migrate.py create 'add new column to users'")
        sys.exit(1)
    
    message = " ".join(sys.argv[2:])
    print(f"📝 Creating new migration: {message}")
    os.system(f'alembic revision --autogenerate -m "{message}"')
    print("✅ Migration created successfully!")
    print("⚠️  Please review the generated migration file before applying it")


def upgrade_database():
    """Upgrade database to a specific revision or head."""
    revision = sys.argv[2] if len(sys.argv) > 2 else "head"
    print(f"⬆️  Upgrading database to: {revision}")
    os.system(f"alembic upgrade {revision}")
    print("✅ Database upgraded successfully!")


def downgrade_database():
    """Downgrade database to a specific revision."""
    revision = sys.argv[2] if len(sys.argv) > 2 else "-1"
    print(f"⬇️  Downgrading database to: {revision}")
    os.system(f"alembic downgrade {revision}")
    print("✅ Database downgraded successfully!")


def show_current():
    """Show current revision."""
    print("📊 Current database revision:")
    os.system("alembic current")


def show_history():
    """Show migration history."""
    print("📜 Migration history:")
    os.system("alembic history --verbose")


def show_heads():
    """Show head revisions."""
    print("🎯 Head revisions:")
    os.system("alembic heads --verbose")


def print_help():
    """Print help message."""
    help_text = """
🗄️  Fleet Manager Migration Tool

Usage: python migrate.py <command> [options]

Commands:
  init              Initialize database with all migrations (upgrade to head)
  create <message>  Create a new migration with autogenerate
  upgrade [rev]     Upgrade to a specific revision (default: head)
  downgrade [rev]   Downgrade to a specific revision (default: -1)
  current           Show current database revision
  history           Show all migration history
  heads             Show head revisions
  help              Show this help message

Examples:
  python migrate.py init
  python migrate.py create "add user email column"
  python migrate.py upgrade
  python migrate.py upgrade +2
  python migrate.py downgrade -1
  python migrate.py current
  python migrate.py history

For more information, see: docs/MIGRATION_GUIDE.md
"""
    print(help_text)


if __name__ == "__main__":
    main()
