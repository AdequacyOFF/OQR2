"""Application configuration using pydantic-settings."""

from typing import List
from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict
import json


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore"
    )

    # Application
    app_name: str = Field(default="OlimpQR", description="Application name")
    environment: str = Field(default="development", description="Environment (development, staging, production)")
    debug: bool = Field(default=False, description="Debug mode")

    # Security
    secret_key: str = Field(..., description="Secret key for JWT tokens")
    hmac_secret_key: str = Field(..., description="Secret key for HMAC token hashing")
    jwt_algorithm: str = Field(default="HS256", description="JWT signing algorithm")
    jwt_expire_minutes: int = Field(default=1440, description="JWT token expiration in minutes (24 hours)")

    # Database
    database_url: str = Field(..., description="PostgreSQL connection URL")

    # Redis
    redis_url: str = Field(..., description="Redis connection URL")

    # MinIO
    minio_endpoint: str = Field(..., description="MinIO endpoint (host:port)")
    minio_public_endpoint: str = Field(default="", description="MinIO public endpoint for browser access")
    minio_access_key: str = Field(..., description="MinIO access key")
    minio_secret_key: str = Field(..., description="MinIO secret key")
    minio_secure: bool = Field(default=False, description="Use HTTPS for MinIO")
    minio_bucket_sheets: str = Field(default="answer-sheets", description="Bucket for answer sheets")
    minio_bucket_scans: str = Field(default="scans", description="Bucket for scans")

    # Celery
    celery_broker_url: str = Field(..., description="Celery broker URL")
    celery_result_backend: str = Field(default="", description="Celery result backend URL")

    # API
    api_v1_prefix: str = Field(default="/api/v1", description="API v1 prefix")
    backend_cors_origins: List[str] = Field(
        default=["http://localhost:3000", "http://localhost:5173"],
        description="CORS allowed origins"
    )

    # OCR Settings - Score field position in bottom-right of answer frame
    # Calculated: x = 20 + 170 - 10 - 40 = 140mm from left
    # y = 297 - (37 + 10 + 5) = 245mm from top (where 37mm is frame bottom from page bottom)
    ocr_score_field_x: int = Field(default=140, description="Score field X coordinate (mm)")
    ocr_score_field_y: int = Field(default=245, description="Score field Y coordinate (mm)")
    ocr_score_field_width: int = Field(default=40, description="Score field width (mm)")
    ocr_score_field_height: int = Field(default=15, description="Score field height (mm)")
    ocr_confidence_threshold: float = Field(default=0.7, description="OCR confidence threshold for auto-apply")
    ocr_use_gpu: bool = Field(default=False, description="Use GPU for OCR")

    # QR Code Settings
    qr_token_size_bytes: int = Field(default=32, description="Token size in bytes (256 bits)")
    qr_error_correction: str = Field(default="H", description="QR error correction level (L, M, Q, H)")
    entry_token_expire_hours: int = Field(default=24, description="Entry token expiration in hours")
    sheet_template_path: str = Field(
        default="",
        description="Optional JSON path for answer sheet template overrides",
    )

    @field_validator("backend_cors_origins", mode="before")
    @classmethod
    def parse_cors_origins(cls, v: str | List[str]) -> List[str]:
        """Parse CORS origins from JSON string or list."""
        if isinstance(v, str):
            try:
                return json.loads(v)
            except json.JSONDecodeError:
                return [origin.strip() for origin in v.split(",")]
        return v

    @property
    def is_production(self) -> bool:
        """Check if running in production environment."""
        return self.environment.lower() == "production"

    @property
    def is_development(self) -> bool:
        """Check if running in development environment."""
        return self.environment.lower() == "development"


# Global settings instance
settings = Settings()
