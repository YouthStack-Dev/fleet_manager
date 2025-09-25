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
    REDIS_HOST: str = os.getenv("REDIS_HOST", "localhost")
    REDIS_PORT: int = int(os.getenv("REDIS_PORT", "6379"))
    REDIS_DB: int = int(os.getenv("REDIS_DB", "0"))
    REDIS_PASSWORD: str = os.getenv("REDIS_PASSWORD", "")
    USE_REDIS: bool = os.getenv("USE_REDIS", "0") == "1"
    
    # Auth settings
    SECRET_KEY: str = os.getenv("SECRET_KEY", "supersecretkey")
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60*24
    TOKEN_EXPIRY_HOURS: int = int(os.getenv("TOKEN_EXPIRY_HOURS", "24"))
    OAUTH2_URL: str = os.getenv("OAUTH2_URL", "")
    X_INTROSPECT_SECRET: str = os.getenv("X_INTROSPECT_SECRET", "")
    OAUTH2_ENV: str = os.getenv("OAUTH2_ENV", "dev")
    
    # SMTP Email settings - Single Global Admin Email
    SMTP_SERVER: str = os.getenv("SMTP_SERVER", "")
    SMTP_PORT: int = int(os.getenv("SMTP_PORT", "587"))
    SMTP_USERNAME: str = os.getenv("SMTP_USERNAME", "")
    SMTP_PASSWORD: str = os.getenv("SMTP_PASSWORD", "")
    SMTP_USE_TLS: bool = os.getenv("SMTP_USE_TLS", "true").lower() == "true"
    SMTP_USE_SSL: bool = os.getenv("SMTP_USE_SSL", "false").lower() == "true"
    
    # Global Admin Email Settings (single sender for all emails)
    SENDER_EMAIL: str = os.getenv("SENDER_EMAIL", "")
    SENDER_NAME: str = os.getenv("SENDER_NAME", "Fleet Manager Admin")
    SUPPORT_EMAIL: str = os.getenv("SUPPORT_EMAIL", "")
    
    # Email delivery settings
    EMAIL_ENABLED: bool = os.getenv("EMAIL_ENABLED", "true").lower() == "true"
    EMAIL_RETRY_ATTEMPTS: int = int(os.getenv("EMAIL_RETRY_ATTEMPTS", "3"))
    EMAIL_RETRY_DELAY: int = int(os.getenv("EMAIL_RETRY_DELAY", "5"))
    EMAIL_QUEUE_ENABLED: bool = os.getenv("EMAIL_QUEUE_ENABLED", "false").lower() == "true"
    
    # Frontend URL for email links
    FRONTEND_URL: str = os.getenv("FRONTEND_URL", "http://localhost:3000")
    
    # API specific settings
    API_PREFIX: str = "/api/v1"
    APP_NAME: str = "Fleet Manager"
    APP_VERSION: str = "1.0.0"
    
    class Config:
        case_sensitive = True
        env_file = None

settings = Settings()