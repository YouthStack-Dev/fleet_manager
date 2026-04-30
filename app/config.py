import os
from typing import List
from pydantic_settings import BaseSettings
from pydantic import ConfigDict, field_validator, model_validator


class Settings(BaseSettings):
    ENV: str = "development"  # development | dev-server | production
    DEBUG: bool = False       # computed: True when ENV is development or dev-server

    # ── Database ──────────────────────────────────────────────────
    POSTGRES_HOST: str = "localhost"
    POSTGRES_USER: str = "fleetadmin"
    POSTGRES_PASSWORD: str = ""               # optional when DATABASE_URL is provided directly
    POSTGRES_DB: str = "fleet_db"
    POSTGRES_PORT: int = 5432
    DATABASE_URL: str = ""                    # auto-built from above if left empty

    # Database connection pool
    DB_POOL_SIZE: int = 10
    DB_MAX_OVERFLOW: int = 20
    DB_POOL_TIMEOUT: int = 30
    DB_POOL_RECYCLE: int = 3600

    # ── Redis ─────────────────────────────────────────────────────
    REDIS_HOST: str = "localhost"
    REDIS_PORT: int = 6379
    REDIS_DB: int = 0
    REDIS_PASSWORD: str = ""
    USE_REDIS: bool = False

    # ── Storage ───────────────────────────────────────────────────
    STORAGE_TYPE: str = "filesystem"  # filesystem | s3 | gcs | azure

    LOCAL_DEV_STORAGE_PATH: str = "./local_storage"
    DEV_SERVER_STORAGE_PATH: str = "/var/lib/fleet/dev-storage"
    PROD_SERVER_STORAGE_PATH: str = "/var/lib/fleet/storage"

    S3_STORAGE_URL: str = "s3://your-fleet-bucket/documents"
    GCS_STORAGE_URL: str = "gcs://your-fleet-bucket/documents"
    AZURE_STORAGE_URL: str = "abfs://container@account.dfs.core.windows.net/documents"

    @property
    def STORAGE_BASE_URL(self) -> str:
        """
        Automatically determine storage URL based on environment and storage type.

        Environment mapping:
        - development: Local machine filesystem (./local_storage)
        - dev-server:  Dev server filesystem (/var/lib/fleet/dev-storage)
        - production:  Production filesystem or cloud storage
        """
        storage_type = self.STORAGE_TYPE.lower()

        if storage_type == "filesystem":
            if self.ENV == "development":
                return f"file://{os.path.abspath(self.LOCAL_DEV_STORAGE_PATH)}"
            elif self.ENV == "dev-server":
                return f"file://{self.DEV_SERVER_STORAGE_PATH}"
            elif self.ENV in ("production", "staging"):
                return f"file://{self.PROD_SERVER_STORAGE_PATH}"
            else:
                return f"file://{os.path.abspath(self.LOCAL_DEV_STORAGE_PATH)}"
        elif storage_type == "s3":
            return self.S3_STORAGE_URL
        elif storage_type == "gcs":
            return self.GCS_STORAGE_URL
        elif storage_type == "azure":
            return self.AZURE_STORAGE_URL
        else:
            if self.ENV == "development":
                return f"file://{os.path.abspath(self.LOCAL_DEV_STORAGE_PATH)}"
            elif self.ENV == "dev-server":
                return f"file://{self.DEV_SERVER_STORAGE_PATH}"
            else:
                return f"file://{self.PROD_SERVER_STORAGE_PATH}"

    # ── File upload ───────────────────────────────────────────────
    MAX_FILE_SIZE_MB: int = 5
    ALLOWED_FILE_TYPES: List[str] = ["image/jpeg", "image/png", "application/pdf"]

    @field_validator("ALLOWED_FILE_TYPES", mode="before")
    @classmethod
    def parse_allowed_types(cls, v: object) -> List[str]:
        """Accept a comma-separated string from env or a list directly."""
        if isinstance(v, str):
            return [t.strip() for t in v.split(",") if t.strip()]
        return v  # type: ignore[return-value]

    # ── Auth ──────────────────────────────────────────────────────
    SECRET_KEY: str                           # required — no insecure default
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 1440   # 60 * 24
    TOKEN_EXPIRY_HOURS: int = 24
    OAUTH2_URL: str = ""
    X_INTROSPECT_SECRET: str = ""
    OAUTH2_ENV: str = "dev"

    # ── SMTP / Email ──────────────────────────────────────────────
    SMTP_SERVER: str = ""
    SMTP_PORT: int = 587
    SMTP_USERNAME: str = ""
    SMTP_PASSWORD: str = ""
    SMTP_USE_TLS: bool = True
    SMTP_USE_SSL: bool = False

    SENDER_EMAIL: str = ""
    SENDER_NAME: str = "Fleet Manager Admin"
    SUPPORT_EMAIL: str = ""

    EMAIL_ENABLED: bool = True
    EMAIL_RETRY_ATTEMPTS: int = 3
    EMAIL_RETRY_DELAY: int = 5
    EMAIL_QUEUE_ENABLED: bool = False

    FRONTEND_URL: str = "http://localhost:3000"

    # ── Twilio SMS ────────────────────────────────────────────────
    TWILIO_ENABLED: bool = False
    TWILIO_ACCOUNT_SID: str = ""
    TWILIO_AUTH_TOKEN: str = ""
    TWILIO_PHONE_NUMBER: str = ""
    TWILIO_VERIFY_SERVICE_SID: str = ""

    # ── Firebase / FCM ────────────────────────────────────────────
    FCM_ENABLED: bool = True
    FIREBASE_KEY_PATH: str = "/app/firebase/firebase_key.json"
    FIREBASE_DATABASE_URL: str = ""

    PUSH_NOTIFICATION_BATCH_SIZE: int = 500
    PUSH_NOTIFICATION_DEFAULT_PRIORITY: str = "high"
    SESSION_CACHE_TTL: int = 3600   # seconds
    SESSION_EXPIRY_DAYS: int = 30

    # ── Observability ─────────────────────────────────────────────
    # Leave blank in development to allow open access; set both in production.
    METRICS_USER: str = ""
    METRICS_PASSWORD: str = ""

    # ── Migrations ────────────────────────────────────────────────
    # Set to False when using a Docker init container for migrations.
    # The init container runs `alembic upgrade head` once before the API pod
    # starts, avoiding races in multi-replica deployments.
    RUN_MIGRATIONS_ON_STARTUP: bool = True

    # ── API ───────────────────────────────────────────────────────
    API_PREFIX: str = "/api/v1"
    APP_NAME: str = "Fleet Manager"
    APP_VERSION: str = "1.0.0"

    # ── Derived fields ────────────────────────────────────────────
    @model_validator(mode="after")
    def _compute_derived(self) -> "Settings":
        # DEBUG reflects ENV.
        object.__setattr__(self, "DEBUG", self.ENV in ("development", "dev-server", "staging"))

        # Build DATABASE_URL from components when not supplied directly.
        if not self.DATABASE_URL:
            if not self.POSTGRES_PASSWORD:
                raise ValueError(
                    "Either POSTGRES_PASSWORD or DATABASE_URL must be provided."
                )
            object.__setattr__(
                self,
                "DATABASE_URL",
                (
                    f"postgresql://{self.POSTGRES_USER}:{self.POSTGRES_PASSWORD}"
                    f"@{self.POSTGRES_HOST}:{self.POSTGRES_PORT}/{self.POSTGRES_DB}"
                ),
            )
        return self

    model_config = ConfigDict(
        case_sensitive=True,
        env_file=".env",
        extra="ignore",
    )


settings = Settings()
