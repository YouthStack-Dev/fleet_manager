from dotenv import load_dotenv
load_dotenv()  # It will load .env file values into os.environ


import os
import firebase_admin
from firebase_admin import credentials, initialize_app
from firebase_admin import db


firebase_key_path = os.getenv("FIREBASE_KEY_PATH", "/app/app/firebase/firebase_key.json")
if not os.path.exists(firebase_key_path):
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

