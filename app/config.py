import os
from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    ENV: str = os.getenv("ENV", "development")  # development, dev-server, production
    DEBUG: bool = ENV in ["development", "dev-server"]
    
    # Database settings
    POSTGRES_HOST: str = os.getenv("POSTGRES_HOST", "localhost")
    POSTGRES_USER: str = os.getenv("POSTGRES_USER", "fleetadmin")
    POSTGRES_PASSWORD: str = os.getenv("POSTGRES_PASSWORD", "fleetpass")
    POSTGRES_DB: str = os.getenv("POSTGRES_DB", "fleet_db")
    POSTGRES_PORT: int = int(os.getenv("POSTGRES_PORT", os.getenv("PORT", "5432")))
    DATABASE_URL: str = os.getenv("DATABASE_URL", f"postgresql://{POSTGRES_USER}:{POSTGRES_PASSWORD}@{POSTGRES_HOST}:{POSTGRES_PORT}/{POSTGRES_DB}")
    
    # Database connection pool settings
    DB_POOL_SIZE: int = int(os.getenv("DB_POOL_SIZE", "10"))
    DB_MAX_OVERFLOW: int = int(os.getenv("DB_MAX_OVERFLOW", "20"))
    DB_POOL_TIMEOUT: int = int(os.getenv("DB_POOL_TIMEOUT", "30"))
    DB_POOL_RECYCLE: int = int(os.getenv("DB_POOL_RECYCLE", "3600"))
    
    # Redis settings - handle Docker and local environments
    REDIS_HOST: str = os.getenv("REDIS_HOST", "localhost")
    REDIS_PORT: int = int(os.getenv("REDIS_PORT", "6379"))
    REDIS_DB: int = int(os.getenv("REDIS_DB", "0"))
    REDIS_PASSWORD: str = os.getenv("REDIS_PASSWORD", "")
    USE_REDIS: bool = os.getenv("USE_REDIS", "0") == "1"
    
    # Storage Configuration - Environment Based
    STORAGE_TYPE: str = os.getenv("STORAGE_TYPE", "filesystem")  # filesystem, s3, gcs, azure
    
    # Local development storage (relative to project root)
    LOCAL_DEV_STORAGE_PATH: str = os.getenv("LOCAL_DEV_STORAGE_PATH", "./local_storage")
    
    # Dev Server storage (absolute path on dev server)
    DEV_SERVER_STORAGE_PATH: str = os.getenv("DEV_SERVER_STORAGE_PATH", "/var/lib/fleet/dev-storage")
    
    # Production server storage (absolute path on production server)
    PROD_SERVER_STORAGE_PATH: str = os.getenv("PROD_SERVER_STORAGE_PATH", "/var/lib/fleet/storage")
    
    # Cloud storage URLs (for future migration)
    S3_STORAGE_URL: str = os.getenv("S3_STORAGE_URL", "s3://your-fleet-bucket/documents")
    GCS_STORAGE_URL: str = os.getenv("GCS_STORAGE_URL", "gcs://your-fleet-bucket/documents")
    AZURE_STORAGE_URL: str = os.getenv("AZURE_STORAGE_URL", "abfs://container@account.dfs.core.windows.net/documents")
    
    # Auto-detect storage based on environment
    @property
    def STORAGE_BASE_URL(self) -> str:
        """
        Automatically determine storage URL based on environment and storage type
        
        Environment mapping:
        - development: Local machine filesystem (./local_storage)
        - dev-server: Dev server filesystem (/var/lib/fleet/dev-storage)
        - production: Production filesystem or cloud storage
        """
        storage_type = self.STORAGE_TYPE.lower()
        
        if storage_type == "filesystem":
            if self.ENV == "development":
                # Local development - relative path
                return f"file://{os.path.abspath(self.LOCAL_DEV_STORAGE_PATH)}"
            elif self.ENV == "dev-server":
                # Dev server - absolute path
                return f"file://{self.DEV_SERVER_STORAGE_PATH}"
            elif self.ENV == "production":
                # Production server - absolute path
                return f"file://{self.PROD_SERVER_STORAGE_PATH}"
            else:
                # Default to local for unknown environments
                return f"file://{os.path.abspath(self.LOCAL_DEV_STORAGE_PATH)}"
                
        elif storage_type == "s3":
            return self.S3_STORAGE_URL
        elif storage_type == "gcs":
            return self.GCS_STORAGE_URL
        elif storage_type == "azure":
            return self.AZURE_STORAGE_URL
        else:
            # Default to filesystem for unknown storage types
            if self.ENV == "development":
                return f"file://{os.path.abspath(self.LOCAL_DEV_STORAGE_PATH)}"
            elif self.ENV == "dev-server":
                return f"file://{self.DEV_SERVER_STORAGE_PATH}"
            else:
                return f"file://{self.PROD_SERVER_STORAGE_PATH}"
    
    # File upload settings
    MAX_FILE_SIZE_MB: int = int(os.getenv("MAX_FILE_SIZE_MB", "5"))
    ALLOWED_FILE_TYPES: list = ["image/jpeg", "image/png", "application/pdf"]
    
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