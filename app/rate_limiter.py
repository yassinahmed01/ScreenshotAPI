"""Rate limiting and concurrency control."""

import asyncio
import time
from collections import deque
from typing import Optional
from fastapi import HTTPException, Request

from app.config import get_settings


class ConcurrencyLimiter:
    """
    Manages concurrent screenshot requests using a semaphore.
    Rejects requests when at capacity instead of queuing.
    """
    
    def __init__(self, max_concurrent: int):
        self._semaphore = asyncio.Semaphore(max_concurrent)
        self._max = max_concurrent
        self._current = 0
        self._lock = asyncio.Lock()
    
    @property
    def current_count(self) -> int:
        return self._current
    
    @property
    def max_count(self) -> int:
        return self._max
    
    @property
    def available(self) -> int:
        return self._max - self._current
    
    async def try_acquire(self) -> bool:
        """Try to acquire a slot without blocking."""
        async with self._lock:
            if self._current >= self._max:
                return False
            self._current += 1
            return True
    
    async def release(self):
        """Release a slot."""
        async with self._lock:
            if self._current > 0:
                self._current -= 1


class RateLimiter:
    """
    Simple in-memory rate limiter using sliding window.
    Per-minute limit tracked globally (not per-client for simplicity).
    """
    
    def __init__(self, max_per_minute: int):
        self._max = max_per_minute
        self._window: deque = deque()
        self._lock = asyncio.Lock()
    
    async def check_and_record(self) -> tuple[bool, int]:
        """
        Check if request is allowed and record it.
        Returns (allowed, retry_after_seconds).
        """
        async with self._lock:
            now = time.time()
            window_start = now - 60
            
            # Remove old entries
            while self._window and self._window[0] < window_start:
                self._window.popleft()
            
            if len(self._window) >= self._max:
                # Calculate retry-after
                oldest = self._window[0]
                retry_after = int(oldest + 60 - now) + 1
                return False, max(1, retry_after)
            
            self._window.append(now)
            return True, 0
    
    @property
    def current_count(self) -> int:
        now = time.time()
        window_start = now - 60
        return sum(1 for t in self._window if t >= window_start)


# Global instances - initialized on first import
_concurrency_limiter: Optional[ConcurrencyLimiter] = None
_rate_limiter: Optional[RateLimiter] = None


def get_concurrency_limiter() -> ConcurrencyLimiter:
    """Get or create the global concurrency limiter."""
    global _concurrency_limiter
    if _concurrency_limiter is None:
        settings = get_settings()
        _concurrency_limiter = ConcurrencyLimiter(settings.max_concurrency)
    return _concurrency_limiter


def get_rate_limiter() -> RateLimiter:
    """Get or create the global rate limiter."""
    global _rate_limiter
    if _rate_limiter is None:
        settings = get_settings()
        _rate_limiter = RateLimiter(settings.rate_limit_per_minute)
    return _rate_limiter


async def check_rate_limits(request: Request) -> None:
    """
    Check both rate limit and concurrency limit.
    Raises HTTPException if either limit is exceeded.
    """
    request_id = getattr(request.state, "request_id", "unknown")
    
    # Check rate limit first
    rate_limiter = get_rate_limiter()
    allowed, retry_after = await rate_limiter.check_and_record()
    
    if not allowed:
        raise HTTPException(
            status_code=429,
            detail={
                "error_code": "too_many_requests",
                "message": "Rate limit exceeded",
                "request_id": request_id,
                "details": {"retry_after_seconds": retry_after}
            },
            headers={"Retry-After": str(retry_after)}
        )
    
    # Check concurrency limit
    concurrency_limiter = get_concurrency_limiter()
    acquired = await concurrency_limiter.try_acquire()
    
    if not acquired:
        raise HTTPException(
            status_code=429,
            detail={
                "error_code": "too_many_requests",
                "message": "Server at maximum capacity, try again shortly",
                "request_id": request_id,
                "details": {"reason": "concurrency_limit"}
            },
            headers={"Retry-After": "5"}
        )

