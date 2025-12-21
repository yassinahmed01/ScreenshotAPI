"""FastAPI Screenshot API - Main Application."""

import logging
import time
from contextlib import asynccontextmanager

from fastapi import FastAPI, Depends, Request, HTTPException
from fastapi.responses import Response, JSONResponse
from fastapi.exceptions import RequestValidationError
import json

from app.config import get_settings
from app.models import ScreenshotRequest, HealthResponse, ErrorResponse
from app.security import verify_api_key, validate_url_security
from app.browser import take_screenshot, shutdown_browser, get_browser_manager
from app.rate_limiter import check_rate_limits, get_concurrency_limiter
from app.middleware import RequestContextMiddleware

# Configure logging
settings = get_settings()
logging.basicConfig(
    level=getattr(logging, settings.log_level.upper()),
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan handler for startup/shutdown."""
    logger.info("Screenshot API starting up...")
    # Pre-warm browser on startup (optional, can be removed for faster cold starts)
    try:
        manager = get_browser_manager()
        logger.info("Browser manager initialized")
    except Exception as e:
        logger.warning(f"Failed to pre-warm browser: {e}")
    
    yield
    
    # Shutdown
    logger.info("Screenshot API shutting down...")
    await shutdown_browser()
    logger.info("Browser shutdown complete")


app = FastAPI(
    title="Screenshot API",
    description="Production-ready HTTP Screenshot API for capturing web pages",
    version="1.0.0",
    lifespan=lifespan,
)

# Add middleware
app.add_middleware(RequestContextMiddleware)


# Exception handlers
@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    """Handle FastAPI validation errors (422 Unprocessable Entity)."""
    request_id = getattr(request.state, "request_id", "unknown")
    
    # #region agent log
    try:
        error_details = []
        for err in exc.errors():
            loc_str = " -> ".join(str(loc) for loc in err.get("loc", []))
            error_details.append({
                "location": loc_str,
                "message": err.get("msg", ""),
                "type": err.get("type", ""),
                "input": str(err.get("input", ""))[:200]
            })
        
        # Try to get body from request if available
        body_str = "unavailable"
        try:
            # Check if body was already consumed
            if hasattr(request, "_body"):
                body_str = str(request._body)[:500]
            else:
                # Try to read it (may fail if already consumed)
                try:
                    body_bytes = await request.body()
                    if body_bytes:
                        body_str = body_bytes.decode('utf-8', errors='replace')[:500]
                except Exception:
                    body_str = "already_consumed"
        except Exception:
            pass
        
        log_entry = {
            "sessionId": "debug-session",
            "runId": "validation-error",
            "hypothesisId": "A",
            "location": "main.py:validation_exception_handler",
            "message": "Validation error - request body and errors",
            "data": {
                "request_id": request_id,
                "method": request.method,
                "path": request.url.path,
                "content_type": request.headers.get("content-type", "missing"),
                "body": body_str,
                "errors": error_details,
                "error_count": len(exc.errors())
            },
            "timestamp": int(time.time() * 1000)
        }
        
        with open(r"c:\WebScreenShotAPI\.cursor\debug.log", "a", encoding="utf-8") as f:
            f.write(json.dumps(log_entry) + "\n")
    except Exception as log_err:
        # Fallback: log to Python logger
        logger.error(f"[{request_id}] Failed to write debug log: {log_err}")
    # #endregion
    
    # Format validation errors for response
    errors = []
    for error in exc.errors():
        field = ".".join(str(loc) for loc in error.get("loc", []))
        errors.append({
            "field": field,
            "message": error.get("msg", "Validation error"),
            "type": error.get("type", "unknown")
        })
    
    logger.warning(f"[{request_id}] Validation error: {errors}")
    
    return JSONResponse(
        status_code=422,
        content={
            "error_code": "invalid_request",
            "message": "Request validation failed",
            "request_id": request_id,
            "details": {
                "errors": errors
            }
        }
    )


@app.exception_handler(HTTPException)
async def http_exception_handler(request: Request, exc: HTTPException):
    """Handle HTTP exceptions with consistent error format."""
    request_id = getattr(request.state, "request_id", "unknown")
    
    # If detail is already a dict (our format), use it
    if isinstance(exc.detail, dict):
        return JSONResponse(
            status_code=exc.status_code,
            content=exc.detail,
            headers=getattr(exc, "headers", None)
        )
    
    # Otherwise, wrap it in our format
    return JSONResponse(
        status_code=exc.status_code,
        content={
            "error_code": "error",
            "message": str(exc.detail),
            "request_id": request_id,
        },
        headers=getattr(exc, "headers", None)
    )


@app.exception_handler(Exception)
async def general_exception_handler(request: Request, exc: Exception):
    """Handle unexpected exceptions."""
    request_id = getattr(request.state, "request_id", "unknown")
    # Log full traceback
    import traceback
    logger.exception(f"[{request_id}] Unexpected error: {exc}")
    logger.error(f"[{request_id}] Full traceback: {traceback.format_exc()}")
    
    return JSONResponse(
        status_code=500,
        content={
            "error_code": "internal_error",
            "message": f"An unexpected error occurred: {str(exc)}",
            "request_id": request_id,
        }
    )


@app.get("/health", response_model=HealthResponse, tags=["Health"])
async def health_check():
    """
    Health check endpoint for Render.
    Returns 200 OK if service is running.
    """
    return HealthResponse(status="ok", version="1.0.0")


@app.get("/", tags=["Health"])
async def root():
    """Root endpoint - redirect to docs."""
    return {"message": "Screenshot API", "docs": "/docs", "health": "/health"}


@app.post(
    "/screenshot",
    tags=["Screenshot"],
    responses={
        200: {
            "content": {"image/jpeg": {}, "image/png": {}},
            "description": "Screenshot image"
        },
        400: {"model": ErrorResponse, "description": "Invalid request"},
        401: {"model": ErrorResponse, "description": "Unauthorized"},
        403: {"model": ErrorResponse, "description": "Forbidden (SSRF protection)"},
        408: {"model": ErrorResponse, "description": "Timeout"},
        429: {"model": ErrorResponse, "description": "Too many requests"},
        500: {"model": ErrorResponse, "description": "Internal error"},
    }
)
async def capture_screenshot(
    request: Request,
    screenshot_request: ScreenshotRequest,
    api_key: str = Depends(verify_api_key),
):
    """
    Capture a screenshot of the specified URL.
    
    **Simplified API**: Only the `url` parameter is required. All other settings use optimal defaults:
    - Viewport: 1280x720
    - Wait strategy: "load" + 3 second delay (fast but reliable)
    - Timeout: 60 seconds
    - Format: JPEG, quality 85
    - Auto-scroll: 2 seconds
    - Human-like mouse movements (bypasses bot detection)
    - Comprehensive anti-fingerprinting
    
    **Typical response time**: 8-15 seconds for most pages.
    
    Returns the screenshot as a binary image (JPEG).
    
    Response Headers:
    - X-Request-Id: Unique request identifier
    - X-Final-Url: URL after any redirects
    - X-Load-Time-Ms: Navigation time in milliseconds
    - X-Total-Time-Ms: Total processing time in milliseconds
    - X-Warning: Any warnings (e.g., "page_may_be_empty")
    """
    request_id = getattr(request.state, "request_id", "unknown")
    
    # #region agent log
    try:
        with open(r"c:\WebScreenShotAPI\.cursor\debug.log", "a", encoding="utf-8") as f:
            f.write(json.dumps({
                "sessionId": "debug-session",
                "runId": "request-received",
                "hypothesisId": "B",
                "location": "main.py:capture_screenshot",
                "message": "Request received successfully",
                "data": {
                    "request_id": request_id,
                    "url": screenshot_request.url,
                    "wait": screenshot_request.wait.value if screenshot_request.wait else None,
                    "wait_ms": screenshot_request.wait_ms,
                    "format": screenshot_request.format.value if screenshot_request.format else None
                },
                "timestamp": int(time.time() * 1000)
            }) + "\n")
    except Exception:
        pass
    # #endregion
    
    concurrency_limiter = get_concurrency_limiter()
    
    # Check rate limits
    await check_rate_limits(request)
    
    try:
        # Validate URL for SSRF
        validate_url_security(screenshot_request.url, request_id)
        
        # Apply hardcoded optimal defaults for bot detection bypass
        # Only URL is accepted from user - all other parameters are hardcoded in code
        from app.models import WaitStrategy, ScrollMode, ScrollConfig, Viewport, ImageFormat
        
        # Create a dataclass-like object with all hardcoded defaults
        class ScreenshotConfig:
            """Internal config with all hardcoded defaults - OPTIMIZED FOR SPEED."""
            def __init__(self, url: str):
                self.url = url
                # Balanced defaults - fast but works with heavy sites like Barchart
                self.wait = WaitStrategy.DOMCONTENTLOADED  # Fires early, before all resources load
                self.wait_ms = 5000  # 5 seconds for JS to render dynamic content
                self.timeout_ms = 240000  # 240 seconds (4 minutes) for heavy pages like Barchart
                self.viewport = Viewport(width=1280, height=720)
                self.full_page = False
                self.scroll = ScrollConfig(mode=ScrollMode.AUTO, auto_duration_ms=1500)  # 1.5 second scroll
                self.format = ImageFormat.JPEG
                self.quality = 85
                self.user_agent = None
                self.headers = None
                self.cookies = None
        
        config = ScreenshotConfig(screenshot_request.url)
        
        # Take screenshot with hardcoded optimized settings
        result = await take_screenshot(config, request_id)
        
        # Build response headers
        headers = {
            "X-Request-Id": request_id,
            "X-Final-Url": result.final_url,
            "X-Load-Time-Ms": str(result.navigation_time_ms),
            "X-Total-Time-Ms": str(result.total_time_ms),
        }
        
        if result.warnings:
            headers["X-Warning"] = ",".join(result.warnings)
        
        return Response(
            content=result.image_bytes,
            media_type=result.content_type,
            headers=headers
        )
    
    except TimeoutError as e:
        logger.warning(f"[{request_id}] Timeout: {e}")
        raise HTTPException(
            status_code=408,
            detail={
                "error_code": "timeout",
                "message": str(e),
                "request_id": request_id,
            }
        )
    
    except RuntimeError as e:
        logger.error(f"[{request_id}] Runtime error: {e}")
        raise HTTPException(
            status_code=500,
            detail={
                "error_code": "internal_error",
                "message": str(e),
                "request_id": request_id,
            }
        )
    
    except Exception as e:
        # Log full traceback for debugging
        import traceback
        logger.exception(f"[{request_id}] Screenshot failed: {e}")
        logger.error(f"[{request_id}] Full traceback: {traceback.format_exc()}")
        raise HTTPException(
            status_code=500,
            detail={
                "error_code": "internal_error",
                "message": f"Failed to capture screenshot: {str(e)}",
                "request_id": request_id,
                "details": {"error": str(e), "type": type(e).__name__}
            }
        )
    
    finally:
        # Always release concurrency slot
        await concurrency_limiter.release()


@app.get("/status", tags=["Health"])
async def get_status(api_key: str = Depends(verify_api_key)):
    """
    Get current service status including concurrency info.
    Requires authentication.
    """
    limiter = get_concurrency_limiter()
    return {
        "status": "ok",
        "concurrency": {
            "current": limiter.current_count,
            "max": limiter.max_count,
            "available": limiter.available,
        }
    }

