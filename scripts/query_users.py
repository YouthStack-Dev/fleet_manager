#!/usr/bin/env python3
"""
Script to query and display user data from the fleet database
"""

import psycopg2
from tabulate import tabulate
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

def fetch_employees(conn):
    """Query all employees from the employees table"""
    with conn.cursor() as cursor:
        cursor.execute("""
            SELECT e.employee_id, e.name, e.employee_code, e.email, t.name as team_name, 
                   e.phone, e.gender, e.is_active, e.created_at 
            FROM employees e
            LEFT JOIN teams t ON e.team_id = t.team_id
            ORDER BY e.employee_id
        """)
        employees = cursor.fetchall()
        
        # Get column names
        columns = [desc[0] for desc in cursor.description]
        
        return columns, employees

def fetch_drivers(conn):
    """Query all drivers from the drivers table"""
    with conn.cursor() as cursor:
        cursor.execute("""
            SELECT d.driver_id, d.name, d.code, d.email, d.phone, 
                   d.gender, v.name as vendor_name, d.is_active, d.created_at 
            FROM drivers d
            JOIN vendors v ON d.vendor_id = v.vendor_id
            ORDER BY d.driver_id
        """)
        drivers = cursor.fetchall()
        
        # Get column names
        columns = [desc[0] for desc in cursor.description]
        
        return columns, drivers

def fetch_admins(conn):
    """Query all admins from the admins table"""
    with conn.cursor() as cursor:
        cursor.execute("""
            SELECT admin_id, name, email, phone, is_active, created_at 
            FROM admins 
            ORDER BY admin_id
        """)
        admins = cursor.fetchall()
        
        # Get column names
        columns = [desc[0] for desc in cursor.description]
        
        return columns, admins

def fetch_bookings(conn, date=None):
    """Query bookings, optionally filtering by date"""
    with conn.cursor() as cursor:
        if date:
            cursor.execute("""
                SELECT b.booking_id, e.name as employee, s.shift_code, b.booking_date,
                       b.pickup_location, b.drop_location, b.status, t.name as team_name
                FROM bookings b
                JOIN employees e ON b.employee_id = e.employee_id
                LEFT JOIN shifts s ON b.shift_id = s.shift_id
                LEFT JOIN teams t ON b.team_id = t.team_id
                WHERE b.booking_date = %s
                ORDER BY b.booking_id
            """, (date,))
        else:
            cursor.execute("""
                SELECT b.booking_id, e.name as employee, s.shift_code, b.booking_date,
                       b.pickup_location, b.drop_location, b.status, t.name as team_name
                FROM bookings b
                JOIN employees e ON b.employee_id = e.employee_id
                LEFT JOIN shifts s ON b.shift_id = s.shift_id
                LEFT JOIN teams t ON b.team_id = t.team_id
                ORDER BY b.booking_date DESC, b.booking_id
                LIMIT 20
            """)
        
        bookings = cursor.fetchall()
        columns = [desc[0] for desc in cursor.description]
        
        return columns, bookings

def fetch_routes(conn):
    """Query route information"""
    with conn.cursor() as cursor:
        cursor.execute("""
            SELECT r.route_id, r.route_code, s.shift_code, r.status,
                   r.planned_distance_km, r.planned_duration_minutes,
                   v.name as vendor_name, d.name as driver_name,
                   COUNT(rb.booking_id) as bookings_count
            FROM routes r
            LEFT JOIN shifts s ON r.shift_id = s.shift_id
            LEFT JOIN vendors v ON r.assigned_vendor_id = v.vendor_id
            LEFT JOIN drivers d ON r.assigned_driver_id = d.driver_id
            LEFT JOIN route_bookings rb ON r.route_id = rb.route_id
            GROUP BY r.route_id, r.route_code, s.shift_code, r.status,
                     r.planned_distance_km, r.planned_duration_minutes,
                     v.name, d.name
            ORDER BY r.route_id DESC
            LIMIT 10
        """)
        
        routes = cursor.fetchall()
        columns = [desc[0] for desc in cursor.description]
        
        return columns, routes

def main():
    """Main function to run the script"""
    conn = connect_to_db()
    
    try:
        print("\n" + "="*80)
        print("FLEET MANAGEMENT SYSTEM REPORT")
        print("Generated on:", datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
        print("="*80)
        
        # Check if tables exist before querying
        with conn.cursor() as cursor:
            cursor.execute("""
                SELECT EXISTS (
                    SELECT FROM information_schema.tables 
                    WHERE table_name = 'employees'
                )
            """)
            employees_exist = cursor.fetchone()[0]
            
            cursor.execute("""
                SELECT EXISTS (
                    SELECT FROM information_schema.tables 
                    WHERE table_name = 'drivers'
                )
            """)
            drivers_exist = cursor.fetchone()[0]
            
            cursor.execute("""
                SELECT EXISTS (
                    SELECT FROM information_schema.tables 
                    WHERE table_name = 'admins'
                )
            """)
            admins_exist = cursor.fetchone()[0]
            
            cursor.execute("""
                SELECT EXISTS (
                    SELECT FROM information_schema.tables 
                    WHERE table_name = 'bookings'
                )
            """)
            bookings_exist = cursor.fetchone()[0]
            
            cursor.execute("""
                SELECT EXISTS (
                    SELECT FROM information_schema.tables 
                    WHERE table_name = 'routes'
                )
            """)
            routes_exist = cursor.fetchone()[0]
        
        total_users = 0
        
        # Display admin users
        if admins_exist:
            columns, admins = fetch_admins(conn)
            print("\nADMIN USERS:")
            print(tabulate(admins, headers=columns, tablefmt="psql"))
            print(f"Total admins: {len(admins)}")
            total_users += len(admins)
        
        # Display employees
        if employees_exist:
            columns, employees = fetch_employees(conn)
            print("\nEMPLOYEES:")
            print(tabulate(employees, headers=columns, tablefmt="psql"))
            print(f"Total employees: {len(employees)}")
            total_users += len(employees)
            
            # Count employees by team
            with conn.cursor() as cursor:
                cursor.execute("""
                    SELECT t.name as team_name, COUNT(*) 
                    FROM employees e
                    LEFT JOIN teams t ON e.team_id = t.team_id
                    GROUP BY t.name
                """)
                team_counts = cursor.fetchall()
                
                print("\nEmployees by team:")
                print(tabulate(team_counts, headers=["Team", "Count"], tablefmt="psql"))
        
        # Display drivers
        if drivers_exist:
            columns, drivers = fetch_drivers(conn)
            print("\nDRIVERS:")
            print(tabulate(drivers, headers=columns, tablefmt="psql"))
            print(f"Total drivers: {len(drivers)}")
            total_users += len(drivers)
            
            # Count drivers by vendor
            with conn.cursor() as cursor:
                cursor.execute("""
                    SELECT v.name as vendor_name, COUNT(*) 
                    FROM drivers d
                    JOIN vendors v ON d.vendor_id = v.vendor_id
                    GROUP BY v.name
                """)
                vendor_counts = cursor.fetchall()
                
                print("\nDrivers by vendor:")
                print(tabulate(vendor_counts, headers=["Vendor", "Count"], tablefmt="psql"))
        
        print(f"\nTotal users in system: {total_users}")
        
        # Display bookings for today
        if bookings_exist:
            today = datetime.now().strftime("%Y-%m-%d")
            columns, today_bookings = fetch_bookings(conn, today)
            print(f"\nBOOKINGS FOR TODAY ({today}):")
            print(tabulate(today_bookings, headers=columns, tablefmt="psql"))
            print(f"Total bookings for today: {len(today_bookings)}")
            
            # Display recent bookings
            columns, recent_bookings = fetch_bookings(conn)
            print("\nRECENT BOOKINGS:")
            print(tabulate(recent_bookings, headers=columns, tablefmt="psql"))
        
        # Display routes
        if routes_exist:
            columns, routes = fetch_routes(conn)
            print("\nRECENT ROUTES:")
            print(tabulate(routes, headers=columns, tablefmt="psql"))
        
    except Exception as e:
        print(f"Error running report: {e}")
    finally:
        conn.close()
        print("\nDatabase connection closed.")

if __name__ == "__main__":
    main()
