import os
from pydantic_settings import BaseSettings
from dotenv import load_dotenv

load_dotenv()

class Settings(BaseSettings):
    ENV: str = os.getenv("ENV", "development")
    DEBUG: bool = ENV == "development"
    
    DATABASE_URL: str = os.getenv("DATABASE_URL", "postgresql://fleetadmin:fleetpass@localhost:5434/fleet_db")
    
    SECRET_KEY: str = os.getenv("SECRET_KEY", "supersecretkey")
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 30
    
    # API specific settings
    API_PREFIX: str = "/api/v1"
    APP_NAME: str = "Fleet Manager API"
    APP_VERSION: str = "1.0.0"
    
    class Config:
        case_sensitive = True

settings = Settings()
