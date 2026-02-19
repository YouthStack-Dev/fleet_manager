"""
Core / utility endpoints that live outside any domain-specific router.

Routes exposed:
    GET  /              – welcome message
    GET  /health        – liveness probe
    GET  /db-tables     – list all public DB tables with column & row counts
    POST /seed-database – seed initial data (supports ?force=true)
    POST /create-tables – create all tables via SQLAlchemy models
    POST /drop-tables   – drop all tables (⚠ destructive)
"""

import traceback

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session
from sqlalchemy.sql import text

from app.core.logging_config import get_logger
from app.database.session import get_db
from app.models.tenant import Tenant
from app.seed.seed_data import (
    seed_admins,
    seed_employees,
    seed_iam,
    seed_shifts,
    seed_teams,
    seed_tenants,
    seed_vehicle_types,
    seed_vehicles,
    seed_vendor_users,
    seed_weekoffs,
    seed_vendors,
)

logger = get_logger(__name__)

router = APIRouter(tags=["Core"])


# ──────────────────────────────────────────────────────────────
# Liveness & welcome
# ──────────────────────────────────────────────────────────────

@router.get("/")
async def root():
    return {"message": "Welcome to Fleet Manager API"}


@router.get("/health")
async def health_check():
    return {"status": "ok", "message": "I Am Alive!!"}


# ──────────────────────────────────────────────────────────────
# Database inspection
# ──────────────────────────────────────────────────────────────

@router.get("/db-tables")
async def get_db_tables(db: Session = Depends(get_db)):
    """Return all public tables with column and row counts."""
    try:
        result = db.execute(text("""
            SELECT
                table_name,
                (SELECT COUNT(*) FROM information_schema.columns
                 WHERE table_name = t.table_name) AS column_count
            FROM information_schema.tables t
            WHERE table_schema = 'public'
            ORDER BY table_name
        """))
        tables = [{"name": row[0], "column_count": row[1]} for row in result]

        for table in tables:
            try:
                table["row_count"] = db.execute(
                    text(f'SELECT COUNT(*) FROM "{table["name"]}"')
                ).scalar()
            except Exception:
                table["row_count"] = "error"

        return {"total_tables": len(tables), "tables": tables}
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to retrieve table information: {e}",
        )


# ──────────────────────────────────────────────────────────────
# Database management  (admin / internal use only)
# ──────────────────────────────────────────────────────────────

@router.post("/seed-database")
def seed_database(
    force: bool = Query(False, description="Force reseed (delete + insert)"),
    db: Session = Depends(get_db),
):
    """Seed the database with initial data."""
    logger.info("Starting database seeding…")
    try:
        if force:
            logger.warning("Force reseed: deleting all tenants…")
            deleted = db.query(Tenant).delete()
            db.commit()
            logger.info("Deleted %d tenants.", deleted)

        seed_tenants(db)
        seed_iam(db)
        seed_admins(db)
        seed_teams(db)
        seed_employees(db)
        seed_shifts(db)
        seed_weekoffs(db)
        seed_vendors(db)
        seed_vendor_users(db)
        seed_vehicle_types(db)
        seed_vehicles(db)
        logger.info("Database seeding completed.")
        return {"message": "Database seeded successfully."}

    except Exception as e:
        logger.error("Seeding failed: %s\n%s", e, traceback.format_exc())
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Database seeding failed. Check server logs for details.",
        ) from e


@router.post("/create-tables")
async def create_tables_endpoint():
    """Create all database tables via SQLAlchemy models."""
    try:
        from app.database.create_tables import create_tables
        create_tables()
        return {"message": "Table creation process completed"}
    except Exception as e:
        traceback.print_exc()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to create tables: {e}",
        )


@router.post("/drop-tables")
async def drop_tables_endpoint(db: Session = Depends(get_db)):
    """Drop all tables from the public schema (⚠ destructive)."""
    try:
        logger.warning("Dropping all tables…")
        db.execute(text("SET session_replication_role = 'replica';"))
        tables = db.execute(
            text("SELECT tablename FROM pg_tables WHERE schemaname = 'public';")
        ).fetchall()

        if not tables:
            return {"message": "No tables found to drop"}

        db.execute(text(
            "DROP TABLE IF EXISTS " +
            ", ".join(f'"{t[0]}"' for t in tables) +
            " CASCADE;"
        ))
        db.execute(text("SET session_replication_role = 'origin';"))
        db.commit()

        return {
            "message": f"Successfully dropped {len(tables)} tables",
            "tables_dropped": [t[0] for t in tables],
        }
    except Exception as e:
        traceback.print_exc()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to drop tables: {e}",
        )
