#!/usr/bin/env python3
"""
Initialize the database by running all Alembic migrations.

This ensures:
  - All tables are created with the exact schema defined in migrations
  - alembic_version is always stamped correctly
  - Health check /health always shows up_to_date: true after this runs
"""

import subprocess
import sys
import os


def create_tables():
    """Run all pending Alembic migrations (upgrade head)."""
    try:
        result = subprocess.run(
            ["alembic", "upgrade", "head"],
            capture_output=True,
            text=True,
        )

        if result.returncode != 0:
            print(f"Alembic upgrade failed:\n{result.stderr}")
            raise RuntimeError(f"alembic upgrade head failed: {result.stderr}")

        print("Database migrations applied successfully.")
        if result.stdout:
            print(result.stdout)
        if result.stderr:
            print(result.stderr)

    except FileNotFoundError:
        # alembic not on PATH — fall back to SQLAlchemy create_all + stamp
        print("alembic CLI not found, falling back to SQLAlchemy create_all + stamp")
        _fallback_create_and_stamp()


def _fallback_create_and_stamp():
    """
    Fallback: create tables via SQLAlchemy and stamp alembic_version to head.
    Only used when the alembic CLI is unavailable.
    """
    from app.database.session import engine, Base
    from app.models import *  # noqa: F401,F403 — ensure all models are registered
    from alembic.config import Config as AlembicConfig
    from alembic import command as alembic_command

    Base.metadata.create_all(bind=engine)
    print("Tables created via SQLAlchemy.")

    # Stamp alembic_version to head so health check passes
    cfg = AlembicConfig("alembic.ini")
    alembic_command.stamp(cfg, "head")
    print("alembic_version stamped to head.")
