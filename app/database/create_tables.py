#!/usr/bin/env python3
"""
Script to validate if database tables exist and create them if they don't
"""

import sys
import os
import psycopg2
import importlib
from datetime import datetime

# Add the project root to the Python path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.models import *


# Import database session
from app.database.session import engine, SessionLocal, Base

def create_tables():

    """Initialize the database and create all tables."""
    try:

        Base.metadata.create_all(bind=engine)

        print("Database initialization completed")
    
    except Exception as e:
        print(f"Database initialization failed: {str(e)}")
        raise

