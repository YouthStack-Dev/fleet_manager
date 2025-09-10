#!/usr/bin/env python3
"""
Script to query and display user data from the fleet database
"""

import psycopg2
from tabulate import tabulate

def connect_to_db():
    """Connect to the PostgreSQL database server"""
    conn = None
    try:
        # Connect to the PostgreSQL server
        print('Connecting to the PostgreSQL database...')
        conn = psycopg2.connect(
            host="localhost",
            database="fleet_db",
            user="fleetadmin",
            password="fleetpass"
        )
        return conn
    except (Exception, psycopg2.DatabaseError) as error:
        print(f"Error: {error}")
        if conn is not None:
            conn.close()
        exit(1)

def fetch_users(conn):
    """Query all users from the users table"""
    with conn.cursor() as cursor:
        cursor.execute("""
            SELECT id, username, email, full_name, role, created_at 
            FROM users 
            ORDER BY id
        """)
        users = cursor.fetchall()
        
        # Get column names
        columns = [desc[0] for desc in cursor.description]
        
        return columns, users

def main():
    """Main function to run the script"""
    conn = connect_to_db()
    
    try:
        columns, users = fetch_users(conn)
        
        # Print users in a tabular format
        print("\nUsers in the fleet management system:")
        print(tabulate(users, headers=columns, tablefmt="psql"))
        
        # Print some statistics
        print(f"\nTotal users: {len(users)}")
        
        # Count users by role
        with conn.cursor() as cursor:
            cursor.execute("""
                SELECT role, COUNT(*) 
                FROM users 
                GROUP BY role
            """)
            role_counts = cursor.fetchall()
            
            print("\nUsers by role:")
            print(tabulate(role_counts, headers=["Role", "Count"], tablefmt="psql"))
            
    finally:
        conn.close()
        print("\nDatabase connection closed.")

if __name__ == "__main__":
    main()
