#!/usr/bin/env python3
"""
Script to validate if database tables exist and create them if they don't
"""

import sys
import os
import psycopg2
from sqlalchemy import create_engine, inspect, MetaData, Table, Column, Integer, String, Boolean, DateTime, ForeignKey, text
from sqlalchemy.orm import sessionmaker
import importlib
from datetime import datetime

# Add the project root to the Python path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from models import *


# Import database session
from database.session import engine, SessionLocal, Base

def create_tables():

    """Initialize the database and create all tables."""
    try:

        Base.metadata.create_all(bind=engine)

        print("Database initialization completed")
    
    except Exception as e:
        print(f"Database initialization failed: {str(e)}")
        raise


def connect_to_db():
    """Connect to the PostgreSQL database server"""
    conn = None
    try:
        # Connect to the PostgreSQL server
        print('Connecting to the PostgreSQL database...')
        host = os.environ.get("POSTGRES_HOST", "localhost")
        port = os.environ.get("POSTGRES_PORT", "5434")
        database = os.environ.get("POSTGRES_DB", "fleet_db")
        user = os.environ.get("POSTGRES_USER", "fleetadmin")
        password = os.environ.get("POSTGRES_PASSWORD", "fleetpass")
        
        conn = psycopg2.connect(
            host=host,
            port=port,
            database=database,
            user=user,
            password=password
        )
        return conn
    except (Exception, psycopg2.DatabaseError) as error:
        print(f"Error: {error}")
        if conn is not None:
            conn.close()
        sys.exit(1)

def check_tables_exist():
    """Check if tables exist in the database"""
    conn = connect_to_db()
    cursor = conn.cursor()
    
    try:
        cursor.execute("""
            SELECT table_name 
            FROM information_schema.tables 
            WHERE table_schema = 'public'
        """)
        tables = cursor.fetchall()
        
        print(f"Found {len(tables)} tables in the database:")
        for table in tables:
            print(f"  - {table[0]}")
        
        # Check for specific important tables
        important_tables = ['admins', 'tenants', 'employees', 'vendors', 'vendor_users', 'vehicles']
        missing_tables = []
        
        for table in important_tables:
            cursor.execute(f"""
                SELECT EXISTS (
                    SELECT FROM information_schema.tables 
                    WHERE table_schema = 'public' 
                    AND table_name = '{table}'
                )
            """)
            exists = cursor.fetchone()[0]
            if not exists:
                missing_tables.append(table)
        
        if missing_tables:
            print(f"\nMISSING IMPORTANT TABLES: {', '.join(missing_tables)}")
            return False
        else:
            print("\nAll important tables exist.")
            return True
            
    except Exception as e:
        print(f"Error checking tables: {str(e)}")
        return False
    finally:
        cursor.close()
        conn.close()

def import_models():
    """Import all model files to ensure they're registered with SQLAlchemy"""
    print("\nImporting models...")
    model_modules = [
        "app.models.admin",
        "app.models.booking", 
        "app.models.driver",
        "app.models.employee", 
        "app.models.route",
        "app.models.team",
        "app.models.tenant",
        "app.models.vehicle",
        "app.models.vehicle_type",
        "app.models.vendor",
        "app.models.vendor_user",
        "app.models.weekoff_config"
    ]
    
    for module in model_modules:
        try:
            importlib.import_module(module)
            print(f"Successfully imported {module}")
        except ImportError as e:
            print(f"Failed to import {module}: {str(e)}")

def relation_exists(conn, relation_name):
    """Check if a relation (table, index, etc.) exists in the database"""
    cursor = conn.cursor()
    try:
        cursor.execute("""
            SELECT EXISTS (
                SELECT 1 FROM pg_catalog.pg_class c
                JOIN pg_catalog.pg_namespace n ON n.oid = c.relnamespace
                WHERE n.nspname = 'public' AND c.relname = %s
            )
        """, (relation_name,))
        exists = cursor.fetchone()[0]
        return exists
    except Exception as e:
        print(f"Error checking if relation exists: {str(e)}")
        return False
    finally:
        cursor.close()


def main():
    """Main function"""
    print("\n" + "="*80)
    print("DATABASE VALIDATION")
    print("Started at:", datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
    print("="*80)
    
    tables_exist = check_tables_exist()
    
    if not tables_exist:
        print("\nCreating missing tables...")
        create_tables()
        
        # Verify tables were created
        print("\nVerifying tables after creation...")
        check_tables_exist()
    else:
        print("\nSome tables already exist.")
        print("\nAttempting to create any missing tables...")
        create_tables()
        print("\nVerifying tables after creation attempt...")
        check_tables_exist()
    
    print("\nValidation completed.")

if __name__ == "__main__":
    main()
