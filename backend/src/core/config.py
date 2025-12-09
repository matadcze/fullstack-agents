"""Application configuration settings."""

from pathlib import Path
from typing import List, Optional

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",  # Ignore extra environment variables
    )

    # Application Information
    app_name: str = "{{PROJECT_NAME}} API"
    app_version: str = "0.1.0"
    debug: bool = False

    # Database Configuration
    database_url: str

    # Redis Configuration
    redis_url: str = "redis://localhost:6379/0"

    # Celery Configuration (defaults to redis_url if not set)
    celery_broker_url: Optional[str] = None
    celery_result_backend: Optional[str] = None

    # JWT Authentication
    jwt_secret_key: str
    jwt_algorithm: str = "HS256"
    access_token_expire_minutes: int = 15
    refresh_token_expire_days: int = 7

    # Rate Limiting
    rate_limit_per_minute: int = 100

    # Security Headers
    enable_hsts: bool = False  # Set to True in production when behind HTTPS

    # CORS Configuration
    cors_origins: List[str] = [
        "http://localhost",
        "http://localhost:3000",
        "http://localhost:8000",
    ]

    # File uploads (used by readiness check)
    upload_dir: Path = Path("uploads")

    # LLM / agent settings (override when wiring to a real provider)
    llm_provider: str = "stub"
    llm_model: str = "placeholder-model"
    llm_api_key: Optional[str] = None
    llm_api_base: Optional[str] = None

    def model_post_init(self, __context):
        """Post-initialization hook to set derived values."""
        # Default Celery URLs to Redis URL if not specified
        if not self.celery_broker_url:
            object.__setattr__(self, "celery_broker_url", self.redis_url)
        if not self.celery_result_backend:
            object.__setattr__(self, "celery_result_backend", self.redis_url)
        # Always allow localhost (port 80) for Nginx in local/dev setups
        if "http://localhost" not in self.cors_origins:
            object.__setattr__(self, "cors_origins", [*self.cors_origins, "http://localhost"])
        # Ensure upload directory exists for basic readiness checks
        self.upload_dir.mkdir(parents=True, exist_ok=True)


settings = Settings()
