#!/usr/bin/env python3
"""
Script to initialize the fleet database with schema and sample data
"""

import psycopg2
import os
import sys
from datetime import datetime

def connect_to_db():
    """Connect to the PostgreSQL database server"""
    conn = None
    try:
        # Connect to the PostgreSQL server
        print('Connecting to the PostgreSQL database...')
        conn = psycopg2.connect(
            host=os.environ.get("POSTGRES_HOST", "localhost"),
            port=os.environ.get("POSTGRES_PORT", "5434"),
            database=os.environ.get("POSTGRES_DB", "fleet_db"),
            user=os.environ.get("POSTGRES_USER", "fleetadmin"),
            password=os.environ.get("POSTGRES_PASSWORD", "fleetpass")
        )
        return conn
    except (Exception, psycopg2.DatabaseError) as error:
        print(f"Error: {error}")
        if conn is not None:
            conn.close()
        sys.exit(1)

def execute_sql_file(conn, file_path):
    """Execute SQL statements from a file"""
    try:
        print(f"Executing SQL file: {file_path}")
        with open(file_path, 'r') as sql_file:
            sql = sql_file.read()
            
        with conn.cursor() as cursor:
            cursor.execute(sql)
        
        conn.commit()
        print(f"Successfully executed {file_path}")
        
    except Exception as e:
        print(f"Error executing {file_path}: {e}")
        conn.rollback()
        raise

def main():
    """Main function to initialize the database"""
    conn = connect_to_db()
    
    try:
        print("\n" + "="*80)
        print("DATABASE INITIALIZATION")
        print("Started at:", datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
        print("="*80)
        
        # Get the directory of this script
        script_dir = os.path.dirname(os.path.abspath(__file__))
        
        # Get the parent directory (project root)
        project_dir = os.path.dirname(script_dir)
        
        # SQL file paths
        schema_file = os.path.join(project_dir, "sql", "01_init.sql")
        sample_data_file = os.path.join(project_dir, "sql", "02_sample_data.sql")
        
        # Execute schema SQL
        print("\nCreating database schema...")
        execute_sql_file(conn, schema_file)
        
        # Execute sample data SQL
        print("\nLoading sample data...")
        execute_sql_file(conn, sample_data_file)
        
        print("\nDatabase initialization completed successfully!")
        
    except Exception as e:
        print(f"\nError during database initialization: {e}")
        sys.exit(1)
    finally:
        if conn is not None:
            conn.close()
            print("Database connection closed.")

if __name__ == "__main__":
    main()
