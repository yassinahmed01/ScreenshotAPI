"""Configuration management from environment variables."""

from pydantic_settings import BaseSettings
from pydantic import Field
from typing import Optional
from functools import lru_cache


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""
    
    # Authentication
    api_key: str = Field(..., description="Shared secret for API authentication")
    
    # Concurrency and rate limiting
    max_concurrency: int = Field(default=2, ge=1, le=10)
    rate_limit_per_minute: int = Field(default=30, ge=1, le=100)
    
    # Default screenshot options
    default_timeout_ms: int = Field(default=30000, ge=5000, le=300000)  # Max 5 minutes for slow pages
    default_wait_ms: int = Field(default=2000, ge=0, le=30000)
    default_viewport_width: int = Field(default=1280, ge=320, le=3840)
    default_viewport_height: int = Field(default=720, ge=240, le=2160)
    default_quality: int = Field(default=85, ge=1, le=100)
    
    # Limits
    max_screenshot_height: int = Field(default=16384, ge=768, le=32768)
    max_url_length: int = Field(default=2048, ge=100, le=8192)
    
    # Security
    allowed_domains: Optional[str] = Field(default=None, description="Comma-separated list of allowed domains")
    
    # Logging
    log_level: str = Field(default="INFO")
    
    # Browser settings
    browser_timeout_ms: int = Field(default=60000, ge=10000, le=300000)  # Max 5 minutes for slow pages
    browser_recycle_requests: int = Field(default=50, ge=1, le=500)
    
    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"
        case_sensitive = False

    def get_allowed_domains_list(self) -> list[str]:
        """Parse allowed domains into a list."""
        if not self.allowed_domains:
            return []
        return [d.strip().lower() for d in self.allowed_domains.split(",") if d.strip()]


@lru_cache()
def get_settings() -> Settings:
    """Get cached settings instance."""
    return Settings()

