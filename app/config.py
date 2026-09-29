import base64
import hashlib
from typing import Optional
from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # Application
    APP_ENV: str = Field(default="development", description="Environment: development, test, production")
    SECRET_KEY: str = Field(
        default="default-mail2whatsapp-insecure-secret-key-32b",
        description="Application secret key used for token encryption and state hashing",
    )
    LOG_LEVEL: str = Field(default="INFO", description="Logging level")

    # Google OAuth 2.0
    GOOGLE_CLIENT_ID: str = Field(default="", description="Google OAuth 2.0 Client ID")
    GOOGLE_CLIENT_SECRET: str = Field(default="", description="Google OAuth 2.0 Client Secret")
    GOOGLE_REDIRECT_URI: str = Field(
        default="http://localhost:8000/auth/google/callback",
        description="OAuth callback URL",
    )

    # Gmail / Pub/Sub
    GMAIL_PUBSUB_TOPIC: str = Field(
        default="",
        description="Full Cloud Pub/Sub topic name: projects/{project}/topics/{topic}",
    )
    GOOGLE_CLOUD_PROJECT: str = Field(default="", description="Google Cloud Project ID")
    PUBSUB_VERIFICATION_TOKEN: Optional[str] = Field(
        default=None,
        description="Optional shared secret/token to verify Pub/Sub push requests",
    )

    # Database
    DATABASE_URL: str = Field(
        default="sqlite:///./mail2whatsapp.db",
        description="Database connection URL (PostgreSQL or SQLite)",
    )

    # WhatsApp Business Platform / Cloud API
    WHATSAPP_ACCESS_TOKEN: str = Field(default="", description="Meta WhatsApp Cloud API token")
    WHATSAPP_PHONE_NUMBER_ID: str = Field(default="", description="WhatsApp Phone Number ID")
    WHATSAPP_VERIFY_TOKEN: str = Field(
        default="verify-token",
        description="WhatsApp webhook verification token",
    )
    WHATSAPP_RECIPIENT_NUMBER: str = Field(
        default="",
        description="Destination WhatsApp phone number (with country code, digits only)",
    )
    WHATSAPP_API_VERSION: str = Field(default="v21.0", description="WhatsApp Graph API version")

    # Email & Operational policies
    RETAIN_EMAIL_BODIES: bool = Field(
        default=True,
        description="Whether to persist plain/HTML email bodies in database",
    )
    MAX_ATTACHMENT_SIZE_MB: int = Field(
        default=25,
        description="Maximum attachment size to process in megabytes",
    )
    RECONCILIATION_INTERVAL_HOURS: int = Field(
        default=24,
        description="Interval in hours for scheduled reconciliation sync",
    )
    WATCH_RENEWAL_WINDOW_HOURS: int = Field(
        default=24,
        description="Renew Gmail watch if expiry is within this window in hours",
    )

    @property
    def fernet_key(self) -> bytes:
        """
        Derives a standard 32-byte URL-safe base64 Fernet key from SECRET_KEY.
        Ensures consistent symmetric encryption regardless of raw secret format.
        """
        digest = hashlib.sha256(self.SECRET_KEY.encode("utf-8")).digest()
        return base64.urlsafe_b64encode(digest)


settings = Settings()
