import sys
import os

# Get the directory of this file
current_dir = os.path.dirname(os.path.abspath(__file__))

# Add the parent directory to Python's path
# This allows imports like 'from app.models.employee import Employee' to work
sys.path.append(current_dir)
