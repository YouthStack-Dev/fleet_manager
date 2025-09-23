import os
from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    ENV: str = os.getenv("ENV", "development")
    DEBUG: bool = ENV == "development"
    
    # Database settings
    POSTGRES_HOST: str = os.getenv("POSTGRES_HOST", "localhost")
    POSTGRES_USER: str = os.getenv("POSTGRES_USER", "fleetadmin")
    POSTGRES_PASSWORD: str = os.getenv("POSTGRES_PASSWORD", "fleetpass")
    POSTGRES_DB: str = os.getenv("POSTGRES_DB", "fleet_db")
    PORT: int = int(os.getenv("PORT", "5432"))
    DATABASE_URL: str = os.getenv("DATABASE_URL", f"postgresql://{POSTGRES_USER}:{POSTGRES_PASSWORD}@{POSTGRES_HOST}:{PORT}/{POSTGRES_DB}")
    
    # Redis settings - handle Docker and local environments
    REDIS_HOST: str = os.getenv("REDIS_HOST", "localhost")  # In Docker, this might be "redis" or "redis_server"
    REDIS_PORT: int = int(os.getenv("REDIS_PORT", "6379"))
    REDIS_DB: int = int(os.getenv("REDIS_DB", "0"))
    REDIS_PASSWORD: str = os.getenv("REDIS_PASSWORD", "")
    USE_REDIS: bool = os.getenv("USE_REDIS", "0") == "1"  # Default to False for development
    
    # Auth settings
    SECRET_KEY: str = os.getenv("SECRET_KEY", "supersecretkey")
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60*24
    TOKEN_EXPIRY_HOURS: int = int(os.getenv("TOKEN_EXPIRY_HOURS", "24"))
    OAUTH2_URL: str = os.getenv("OAUTH2_URL", "")
    X_INTROSPECT_SECRET: str = os.getenv("X_INTROSPECT_SECRET", "")
    OAUTH2_ENV: str = os.getenv("OAUTH2_ENV", "dev")
    
    # API specific settings
    API_PREFIX: str = "/api/v1"
    APP_NAME: str = "Fleet Manager API"
    APP_VERSION: str = "1.0.0"
    
    class Config:
        case_sensitive = True
        # Don't read from .env file to avoid conflicts with Docker environment variables
        env_file = None

settings = Settings()