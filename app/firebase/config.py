from dotenv import load_dotenv
load_dotenv()  # It will load .env file values into os.environ


import os
import firebase_admin
from firebase_admin import credentials, initialize_app
from firebase_admin import db


firebase_key_path = os.getenv("FIREBASE_KEY_PATH", "/app/app/firebase/firebase_key.json")

# For local development/testing, try alternate paths
if not os.path.exists(firebase_key_path):
    # Try local development path
    local_path = os.path.join(os.path.dirname(__file__), "firebase_key.json")
    if os.path.exists(local_path):
        firebase_key_path = local_path
    else:
        # Only raise error if not in test environment
        import sys
        if 'pytest' not in sys.modules:
            raise FileNotFoundError(f"Firebase key not found at: {firebase_key_path}. "
                                    "Check your docker-compose volume mount.")

def init_firebase():
    print("Firebase key path:", firebase_key_path)
    if not os.path.exists(firebase_key_path):
        raise FileNotFoundError(f"Firebase key not found at: {firebase_key_path}")
    try:
        if not firebase_admin._apps:
            cred = credentials.Certificate(firebase_key_path)
            initialize_app(cred, {
                'databaseURL': os.getenv("FIREBASE_DATABASE_URL")
            })
    except Exception as e:
        print("Error initializing Firebase:", str(e))
        raise

