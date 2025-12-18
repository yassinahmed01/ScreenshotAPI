"""Request middleware for logging, request IDs, and timing."""

import logging
import time
import uuid
import json
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

logger = logging.getLogger(__name__)


class RequestContextMiddleware(BaseHTTPMiddleware):
    """
    Middleware that adds request ID, timing, and logging to all requests.
    """
    
    async def dispatch(self, request: Request, call_next) -> Response:
        # Generate unique request ID
        request_id = str(uuid.uuid4())[:8]
        request.state.request_id = request_id
        
        # Record start time
        start_time = time.time()
        
        # Log incoming request (sanitized)
        path = request.url.path
        method = request.method
        
        # Don't log health checks to reduce noise
        is_health_check = path == "/health"
        
        # #region agent log
        if path == "/screenshot" and method == "POST":
            try:
                # Log headers only (body will be logged in validation handler if error occurs)
                headers_dict = {k: v for k, v in request.headers.items() if k.lower() != "authorization"}
                with open(r"c:\WebScreenShotAPI\.cursor\debug.log", "a", encoding="utf-8") as f:
                    f.write(json.dumps({
                        "sessionId": "debug-session",
                        "runId": "middleware-request",
                        "hypothesisId": "C",
                        "location": "middleware.py:dispatch",
                        "message": "Request received in middleware",
                        "data": {
                            "request_id": request_id,
                            "method": method,
                            "path": path,
                            "content_type": request.headers.get("content-type", "missing"),
                            "headers": headers_dict
                        },
                        "timestamp": int(time.time() * 1000)
                    }) + "\n")
            except Exception as log_err:
                pass
        # #endregion
        
        if not is_health_check:
            logger.info(f"[{request_id}] {method} {path} - started")
        
        # Process request
        try:
            response = await call_next(request)
        except Exception as e:
            # #region agent log
            try:
                with open(r"c:\WebScreenShotAPI\.cursor\debug.log", "a", encoding="utf-8") as f:
                    f.write(json.dumps({
                        "sessionId": "debug-session",
                        "runId": "middleware-error",
                        "hypothesisId": "D",
                        "location": "middleware.py:dispatch",
                        "message": "Exception in middleware",
                        "data": {
                            "request_id": request_id,
                            "method": method,
                            "path": path,
                            "error": str(e),
                            "error_type": type(e).__name__
                        },
                        "timestamp": int(time.time() * 1000)
                    }) + "\n")
            except Exception:
                pass
            # #endregion
            # Log error and re-raise
            duration_ms = int((time.time() - start_time) * 1000)
            logger.error(f"[{request_id}] {method} {path} - error after {duration_ms}ms: {str(e)}")
            raise
        
        # Calculate duration
        duration_ms = int((time.time() - start_time) * 1000)
        
        # Add request ID to response headers
        response.headers["X-Request-Id"] = request_id
        
        # Log completion
        if not is_health_check:
            logger.info(
                f"[{request_id}] {method} {path} - "
                f"completed {response.status_code} in {duration_ms}ms"
            )
        
        return response

