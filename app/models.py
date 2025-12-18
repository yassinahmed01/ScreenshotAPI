"""Pydantic models for request/response schemas."""

from pydantic import BaseModel, Field, field_validator, model_validator
from typing import Optional, Literal
from enum import Enum


class WaitStrategy(str, Enum):
    """Page load wait strategies."""
    DOMCONTENTLOADED = "domcontentloaded"
    LOAD = "load"
    NETWORKIDLE = "networkidle"


class ScrollMode(str, Enum):
    """Scroll behavior modes."""
    NONE = "none"
    PX = "px"
    AUTO = "auto"


class ImageFormat(str, Enum):
    """Output image formats."""
    JPEG = "jpeg"
    PNG = "png"


class Viewport(BaseModel):
    """Browser viewport dimensions."""
    width: int = Field(default=1280, ge=320, le=3840)
    height: int = Field(default=720, ge=240, le=2160)


class ScrollConfig(BaseModel):
    """Scroll configuration for lazy-loading content."""
    mode: ScrollMode = Field(default=ScrollMode.NONE)
    value: Optional[int] = Field(default=None, ge=0, le=50000, description="Pixels to scroll if mode is 'px'")
    auto_duration_ms: Optional[int] = Field(default=2000, ge=500, le=10000, description="Duration for auto scroll")

    @model_validator(mode="after")
    def validate_scroll_config(self):
        if self.mode == ScrollMode.PX and self.value is None:
            raise ValueError("value is required when scroll mode is 'px'")
        return self


class Cookie(BaseModel):
    """Browser cookie for authenticated sessions."""
    name: str = Field(..., min_length=1, max_length=256)
    value: str = Field(..., max_length=4096)
    domain: Optional[str] = Field(default=None, max_length=256)
    path: Optional[str] = Field(default="/", max_length=512)
    secure: Optional[bool] = Field(default=True)
    http_only: Optional[bool] = Field(default=False)


class ScreenshotRequest(BaseModel):
    """Request body for screenshot endpoint. Only URL is accepted - all other parameters are hardcoded defaults."""
    url: str = Field(..., min_length=10, max_length=2048, description="URL to capture")

    @field_validator("url")
    @classmethod
    def validate_url(cls, v: str) -> str:
        v = v.strip()
        if not v.startswith(("http://", "https://")):
            raise ValueError("URL must start with http:// or https://")
        return v


class ErrorResponse(BaseModel):
    """Standard error response schema."""
    error_code: str = Field(..., description="Machine-readable error code")
    message: str = Field(..., description="Human-readable error message")
    request_id: str = Field(..., description="Unique request identifier")
    details: Optional[dict] = Field(default=None, description="Additional error details")


class HealthResponse(BaseModel):
    """Health check response."""
    status: str = Field(default="ok")
    version: str = Field(default="1.0.0")

