# Import the path setup module first to configure Python's path
import sys
import os
import shutil  # Add this import to check for executable availability
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Now continue with the rest of your imports
from fastapi import FastAPI, Depends, HTTPException, status, Query
from fastapi.middleware.cors import CORSMiddleware
from typing import List, Optional, Dict, Any
import uvicorn
import subprocess
import psycopg2

from database.session import get_db
from sqlalchemy.orm import Session
from routes import (
    admin_router, 
    employee_router, 
    driver_router, 
    booking_router, 
    tenant_router,
    auth_router,
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
app.include_router(admin_router.router, prefix="/api/v1")
app.include_router(employee_router.router, prefix="/api/v1")
app.include_router(driver_router.router, prefix="/api/v1")
app.include_router(booking_router.router, prefix="/api/v1")
app.include_router(tenant_router.router, prefix="/api/v1")
app.include_router(auth_router.router, prefix="/api/v1")
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
async def health_check(db: Session = Depends(get_db)):
    try:
        # Try to execute a simple query to check DB connection
        db.execute("SELECT 1")
        return {"status": "healthy", "database": "connected"}
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"Database connection failed: {str(e)}"
        )


@app.post("/seed")
async def seed_database(force: bool = Query(False, description="Force reinitialization of database")) -> Dict[str, Any]:
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
                # Check if psql is available
                psql_available = shutil.which('psql') is not None
                
                if psql_available:
                    # Close the connection before running SQL scripts
                    cursor.close()
                    conn.close()
                    
                    # Create environment with password for psql
                    env_with_password = dict(os.environ)
                    env_with_password["PGPASSWORD"] = password
                    
                    # Execute initialization scripts
                    result_init = subprocess.run([
                        'psql', 
                        f"-h{host}",
                        f"-p{port}",
                        f"-U{user}", 
                        f"-d{database}", 
                        '-f', init_script_path
                    ], env=env_with_password, capture_output=True, text=True)
                    
                    if result_init.returncode != 0:
                        raise Exception(f"Init script failed: {result_init.stderr}")
                    
                    # Execute sample data scripts
                    result_sample = subprocess.run([
                        'psql', 
                        f"-h{host}",
                        f"-p{port}",
                        f"-U{user}", 
                        f"-d{database}", 
                        '-f', sample_script_path
                    ], env=env_with_password, capture_output=True, text=True)
                    
                    if result_sample.returncode != 0:
                        raise Exception(f"Sample data script failed: {result_sample.stderr}")
                    
                    return {
                        "message": "Database initialized successfully using psql", 
                        "init_output": result_init.stdout,
                        "sample_output": result_sample.stdout
                    }
                else:
                    print("psql command not found. Falling back to direct SQL execution.")
                    # Fallback to direct SQL file execution via psycopg2
                    
                    # Function to execute SQL from file
                    def execute_sql_file(file_path, conn):
                        try:
                            print(f"Reading SQL file: {file_path}")
                            with open(file_path, 'r') as f:
                                sql_content = f.read()
                            
                            # Split SQL by semicolons to execute statements individually
                            # But be careful with PL/pgSQL blocks that contain semicolons
                            sql_statements = []
                            in_plpgsql_block = False
                            current_statement = ""
                            
                            for line in sql_content.split('\n'):
                                # Skip comments
                                if line.strip().startswith('--'):
                                    continue
                                
                                # Check for PL/pgSQL block start
                                if "DO $$" in line or "do $$" in line:
                                    in_plpgsql_block = True
                                
                                current_statement += line + "\n"
                                
                                # Check for PL/pgSQL block end
                                if "END $$" in line or "end $$" in line:
                                    in_plpgsql_block = False
                                
                                # Check if this line contains a statement end
                                if ";" in line and not in_plpgsql_block:
                                    idx = line.rindex(";") + 1
                                    current_statement = current_statement[:-len(line) + idx]
                                    sql_statements.append(current_statement.strip())
                                    current_statement = line[idx:] + "\n" if idx < len(line) else ""
                            
                            # Create a new cursor for execution
                            cur = conn.cursor()
                            
                            # Execute statements one by one
                            for i, statement in enumerate(sql_statements):
                                if statement.strip():
                                    try:
                                        print(f"Executing statement {i+1}/{len(sql_statements)}")
                                        cur.execute(statement)
                                        conn.commit()
                                    except Exception as e:
                                        conn.rollback()
                                        print(f"Error executing statement: {statement[:100]}...")
                                        print(f"Error: {str(e)}")
                                        # Continue with next statement instead of failing
                                        continue
                            
                            cur.close()
                            return True
                        except Exception as e:
                            conn.rollback()
                            print(f"Error executing SQL file {file_path}: {str(e)}")
                            raise e
                    
                    # Use the combined initialization file that doesn't rely on servicemgr_user
                    combined_script_path = os.path.join(sql_dir, "init-db.sql")
                    if os.path.exists(combined_script_path):
                        print(f"Using combined initialization script: {combined_script_path}")
                        execute_sql_file(combined_script_path, conn)
                    else:
                        # Execute the initialization scripts using local file paths
                        print("Using separate initialization scripts")
                        execute_sql_file(init_script_path, conn)
                        execute_sql_file(sample_script_path, conn)
                    
                    cursor.close()
                    conn.close()
                    
                    return {
                        "message": "Database initialized successfully using direct SQL execution",
                    }
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
        raise HTTPException(status_code=500, detail=f"Failed to seed database: {str(e)}")


if __name__ == "__main__":
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
