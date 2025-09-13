# Import the path setup module first to configure Python's path
import sys
import os
import shutil  # Add this import to check for executable availability
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Now continue with the rest of your imports
from fastapi import FastAPI, Depends, HTTPException, status, Query, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from typing import List, Optional, Dict, Any
import uvicorn
import psycopg2
import traceback  # For detailed error info
from sqlalchemy.sql import text
from app.database.session import get_db

from sqlalchemy.orm import Session
from app.routes import (
    employee_router, 
    driver_router, 
    booking_router, 
    tenant_router,
    vendor_router,
    vehicle_type_router,
    vehicle_router,
    vendor_user_router,
    team_router,
    shift_router,
    route_router,
    route_booking_router,
    weekoff_config_router
)

app = FastAPI(
    title="Fleet Manager API",
    description="API for Fleet Management System",
    version="1.0.0",
)

# Set up CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include routers
app.include_router(employee_router.router, prefix="/api/v1")
app.include_router(driver_router.router, prefix="/api/v1")
app.include_router(booking_router.router, prefix="/api/v1")
app.include_router(tenant_router.router, prefix="/api/v1")
app.include_router(vendor_router.router, prefix="/api/v1")
app.include_router(vehicle_type_router.router, prefix="/api/v1")
app.include_router(vehicle_router.router, prefix="/api/v1")
app.include_router(vendor_user_router.router, prefix="/api/v1")
app.include_router(team_router.router, prefix="/api/v1")
app.include_router(shift_router.router, prefix="/api/v1")
app.include_router(route_router.router, prefix="/api/v1")
app.include_router(route_booking_router.router, prefix="/api/v1")
app.include_router(weekoff_config_router.router, prefix="/api/v1")

# Direct PostgreSQL connection for seeding database
def get_psql_connection():
    host = os.environ.get("POSTGRES_HOST", "localhost")
    port = os.environ.get("POSTGRES_PORT", "5434")  # Use the correct port 5434 instead of default 5432
    database = os.environ.get("POSTGRES_DB", "fleet_db")
    user = os.environ.get("POSTGRES_USER", "fleetadmin")
    password = os.environ.get("POSTGRES_PASSWORD", "fleetpass")
    
    try:
        return psycopg2.connect(
            host=host,
            port=port,
            database=database,
            user=user,
            password=password
        )
    except psycopg2.OperationalError as e:
        print(f"Connection parameters: host={host}, port={port}, database={database}, user={user}")
        print(f"Connection error: {str(e)}")
        raise e


@app.get("/")
async def root():
    return {"message": "Welcome to Fleet Manager API"}


@app.get("/health")
async def health_check():
    return {"message": "I Am Alive!!"}


@app.get("/db-tables")
async def get_db_tables(db: Session = Depends(get_db)):
    """Get information about tables in the database"""
    try:
        # Query table information
        result = db.execute(text("""
            SELECT 
                table_name,
                (SELECT COUNT(*) FROM information_schema.columns WHERE table_name=t.table_name) AS column_count
            FROM 
                information_schema.tables t
            WHERE 
                table_schema='public'
            ORDER BY 
                table_name
        """))
        
        tables = [{"name": row[0], "column_count": row[1]} for row in result]
        
        # Get row counts for each table
        for table in tables:
            try:
                count_result = db.execute(text(f"SELECT COUNT(*) FROM {table['name']}"))
                table['row_count'] = count_result.scalar()
            except Exception:
                table['row_count'] = "Error counting rows"
        
        return {
            "total_tables": len(tables),
            "tables": tables
        }
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to retrieve table information: {str(e)}"
        )


@app.post("/seed")
async def seed_database(
    force: bool = Query(False, description="Force reinitialization of database"),
    use_models: bool = Query(False, description="Use SQLAlchemy models instead of SQL files"),
) -> Dict[str, Any]:
    try:
        # Get connection parameters for logging
        host = os.environ.get("POSTGRES_HOST", "localhost")
        port = os.environ.get("POSTGRES_PORT", "5434")
        database = os.environ.get("POSTGRES_DB", "fleet_db")
        user = os.environ.get("POSTGRES_USER", "fleetadmin")
        password = os.environ.get("POSTGRES_PASSWORD", "fleetpass")
        
        # Get base directory for SQL files
        base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        sql_dir = os.path.join(base_dir, "sql")
        init_script_path = os.path.join(sql_dir, "01_init.sql")
        sample_script_path = os.path.join(sql_dir, "02_sample_data.sql")
        
        print(f"Attempting to connect to database: host={host}, port={port}, db={database}, user={user}")
        print(f"SQL scripts located at: {sql_dir}")
        
        try:
            conn = get_psql_connection()
            cursor = conn.cursor()
            
            # Check if database already has tables
            cursor.execute("SELECT COUNT(*) FROM information_schema.tables WHERE table_schema = 'public'")
            table_count = cursor.fetchone()[0]
            
            if table_count == 0 or force:
                if use_models:
                    cursor.close()
                    conn.close()
                    print("Creating tables from SQLAlchemy models...")
                    create_tables_from_models()
                    
                    return {
                        "message": "Database initialized successfully using SQLAlchemy models",
                    }
                
                # Check if psql is available
                psql_available = shutil.which('psql') is not None
                
            else:
                cursor.close()
                conn.close()
                return {"message": "Database already initialized, use force=true to reinitialize"}
                
        except psycopg2.OperationalError as e:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Database connection failed: {str(e)}"
            )
    except Exception as e:
        traceback.print_exc()  # Print full traceback for debugging
        raise HTTPException(status_code=500, detail=f"Failed to seed database: {str(e)}")


@app.post("/create-tables")
async def create_tables_endpoint():
    """Create tables using SQLAlchemy models"""
    try:
        
        from app.database.create_tables import create_tables

        create_tables()


        return {
            "message": "Table creation process completed",
        }
    except Exception as e:
        traceback.print_exc()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to create tables: {str(e)}"
        )

if __name__ == "__main__":
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
