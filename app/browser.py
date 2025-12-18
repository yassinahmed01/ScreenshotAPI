"""Browser automation with Playwright for screenshot capture."""

import asyncio
import logging
import time
from dataclasses import dataclass
from typing import Optional
from contextlib import asynccontextmanager

from playwright.async_api import async_playwright, Browser, BrowserContext, Page, Error as PlaywrightError

from app.config import get_settings
from app.models import ScreenshotRequest, WaitStrategy, ScrollMode, ImageFormat

logger = logging.getLogger(__name__)


@dataclass
class ScreenshotResult:
    """Result of a screenshot operation."""
    image_bytes: bytes
    content_type: str
    final_url: str
    navigation_time_ms: int
    total_time_ms: int
    warnings: list[str]


class BrowserManager:
    """
    Manages a single browser instance that is reused across requests.
    Each request gets its own isolated browser context.
    Browser is recycled after a configured number of requests to prevent memory leaks.
    """
    
    def __init__(self):
        self._browser: Optional[Browser] = None
        self._playwright = None
        self._lock = asyncio.Lock()
        self._request_count = 0
        self._settings = get_settings()
    
    async def _ensure_browser(self) -> Browser:
        """Ensure browser is running, launch if needed."""
        async with self._lock:
            # Check if browser needs recycling
            if self._browser and self._request_count >= self._settings.browser_recycle_requests:
                logger.info(f"Recycling browser after {self._request_count} requests")
                await self._close_browser()
            
            # Check if browser exists and is still connected
            if self._browser:
                try:
                    # Verify browser is still alive by checking if it's connected
                    if not self._browser.is_connected():
                        logger.warning("Browser disconnected, launching new instance")
                        await self._close_browser()
                except Exception as e:
                    logger.warning(f"Browser check failed, relaunching: {e}")
                    await self._close_browser()
            
            if self._browser is None:
                logger.info("Launching new browser instance")
                self._playwright = await async_playwright().start()
                self._browser = await self._playwright.chromium.launch(
                    headless=True,
                    args=[
                        "--no-sandbox",
                        "--disable-setuid-sandbox",
                        "--disable-dev-shm-usage",
                        "--disable-blink-features=AutomationControlled",  # Hide automation
                        "--disable-features=IsolateOrigins,site-per-process",
                        "--disable-web-security",
                        "--disable-features=VizDisplayCompositor",
                    ]
                )
                self._request_count = 0
            
            self._request_count += 1
            return self._browser
    
    async def _close_browser(self):
        """Close browser and playwright."""
        if self._browser:
            try:
                await self._browser.close()
            except Exception as e:
                logger.warning(f"Error closing browser: {e}")
            self._browser = None
        
        if self._playwright:
            try:
                await self._playwright.stop()
            except Exception as e:
                logger.warning(f"Error stopping playwright: {e}")
            self._playwright = None
    
    @asynccontextmanager
    async def get_context(self, request: ScreenshotRequest, request_id: str = "unknown"):
        """
        Get a new browser context for a request.
        Context is automatically cleaned up when done.
        """
        browser = await self._ensure_browser()
        
        # Verify browser is still connected before creating context
        try:
            if not browser.is_connected():
                logger.warning("Browser disconnected, forcing relaunch")
                await self._close_browser()
                browser = await self._ensure_browser()
        except Exception as e:
            logger.warning(f"Browser check failed: {e}, forcing relaunch")
            await self._close_browser()
            browser = await self._ensure_browser()
        
        context: Optional[BrowserContext] = None
        page: Optional[Page] = None
        
        try:
            # Determine viewport
            settings = self._settings
            viewport_width = request.viewport.width if request.viewport else settings.default_viewport_width
            viewport_height = request.viewport.height if request.viewport else settings.default_viewport_height
            
            # Create context with settings
            # Default to a realistic user agent if not provided
            default_user_agent = (
                request.user_agent 
                if request.user_agent 
                else "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
            )
            
            # Default headers to look like a real browser
            default_headers = {
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8",
                "Accept-Language": "en-US,en;q=0.9",
                "Accept-Encoding": "gzip, deflate, br",
                "DNT": "1",
                "Connection": "keep-alive",
                "Upgrade-Insecure-Requests": "1",
                "Sec-Fetch-Dest": "document",
                "Sec-Fetch-Mode": "navigate",
                "Sec-Fetch-Site": "none",
                "Sec-Fetch-User": "?1",
                "Cache-Control": "max-age=0",
            }
            
            # Merge user-provided headers with defaults (user headers take precedence)
            if request.headers:
                for key, value in request.headers.items():
                    default_headers[key] = value
            
            context_options = {
                "viewport": {"width": viewport_width, "height": viewport_height},
                "ignore_https_errors": True,
                "java_script_enabled": True,
                "user_agent": default_user_agent,
                "extra_http_headers": default_headers,
            }
            
            # Add proxy configuration if provided
            settings = self._settings
            if settings.proxy_server:
                proxy_config = {"server": settings.proxy_server}
                if settings.proxy_username and settings.proxy_password:
                    proxy_config["username"] = settings.proxy_username
                    proxy_config["password"] = settings.proxy_password
                context_options["proxy"] = proxy_config
                logger.info(f"[{request_id}] Using proxy: {settings.proxy_server}")
            
            context = await browser.new_context(**context_options)
            
            # Remove webdriver property and other automation indicators
            await context.add_init_script("""
                Object.defineProperty(navigator, 'webdriver', {
                    get: () => undefined
                });
                
                // Override permissions
                const originalQuery = window.navigator.permissions.query;
                window.navigator.permissions.query = (parameters) => (
                    parameters.name === 'notifications' ?
                        Promise.resolve({ state: Notification.permission }) :
                        originalQuery(parameters)
                );
                
                // Mock plugins
                Object.defineProperty(navigator, 'plugins', {
                    get: () => [1, 2, 3, 4, 5]
                });
                
                // Mock languages
                Object.defineProperty(navigator, 'languages', {
                    get: () => ['en-US', 'en']
                });
            """)
            
            # Set cookies if provided
            if request.cookies:
                cookies_list = []
                for cookie in request.cookies:
                    cookie_dict = {
                        "name": cookie.name,
                        "value": cookie.value,
                        "path": cookie.path or "/",
                    }
                    if cookie.domain:
                        cookie_dict["domain"] = cookie.domain
                    if cookie.secure is not None:
                        cookie_dict["secure"] = cookie.secure
                    if cookie.http_only is not None:
                        cookie_dict["httpOnly"] = cookie.http_only
                    cookies_list.append(cookie_dict)
                await context.add_cookies(cookies_list)
            
            # Block downloads
            await context.route("**/*.pdf", lambda route: route.abort())
            await context.route("**/*.zip", lambda route: route.abort())
            await context.route("**/*.exe", lambda route: route.abort())
            await context.route("**/*.dmg", lambda route: route.abort())
            
            page = await context.new_page()
            
            yield page
            
        finally:
            # Cleanup in reverse order
            if page:
                try:
                    await page.close()
                except Exception as e:
                    logger.warning(f"Error closing page: {e}")
            
            if context:
                try:
                    await context.close()
                except Exception as e:
                    logger.warning(f"Error closing context: {e}")
    
    async def close(self):
        """Shutdown browser manager."""
        await self._close_browser()


# Global browser manager instance
_browser_manager: Optional[BrowserManager] = None


def get_browser_manager() -> BrowserManager:
    """Get or create the global browser manager."""
    global _browser_manager
    if _browser_manager is None:
        _browser_manager = BrowserManager()
    return _browser_manager


async def shutdown_browser():
    """Shutdown the global browser manager."""
    global _browser_manager
    if _browser_manager:
        await _browser_manager.close()
        _browser_manager = None


async def take_screenshot(
    request: ScreenshotRequest,
    request_id: str
) -> ScreenshotResult:
    """
    Take a screenshot of the specified URL.
    
    Handles navigation, waiting, scrolling, and capture.
    """
    settings = get_settings()
    warnings: list[str] = []
    start_time = time.time()
    
    # Apply defaults
    timeout_ms = request.timeout_ms or settings.default_timeout_ms
    wait_ms = request.wait_ms if request.wait_ms is not None else settings.default_wait_ms
    quality = request.quality or settings.default_quality
    
    browser_manager = get_browser_manager()
    
    try:
        async with browser_manager.get_context(request, request_id) as page:
            # Set page timeout
            page.set_default_timeout(timeout_ms)
            
            # Navigate to URL
            nav_start = time.time()
            
            wait_until = _map_wait_strategy(request.wait)
            
            try:
                response = await page.goto(
                    request.url,
                    wait_until=wait_until,
                    timeout=timeout_ms
                )
            except PlaywrightError as e:
                error_msg = str(e).lower()
                if "timeout" in error_msg:
                    raise TimeoutError(f"Navigation timeout after {timeout_ms}ms")
                raise
            
            nav_time_ms = int((time.time() - nav_start) * 1000)
            
            # Get final URL after redirects
            final_url = page.url
            
            # Additional wait time for JS rendering
            if wait_ms > 0:
                await asyncio.sleep(wait_ms / 1000)
            
            # Handle scrolling for lazy-loaded content
            if request.scroll:
                await _handle_scroll(page, request.scroll)
            
            # Take screenshot
            screenshot_options = {
                "full_page": request.full_page,
                "type": request.format.value,
            }
            
            if request.format == ImageFormat.JPEG:
                screenshot_options["quality"] = quality
            
            # Check for potential issues
            try:
                # Simple check for page content
                body = await page.query_selector("body")
                if body:
                    box = await body.bounding_box()
                    if box and box["height"] < 100:
                        warnings.append("page_may_be_empty")
            except Exception:
                pass
            
            # Enforce max height for full page screenshots
            if request.full_page:
                try:
                    page_height = await page.evaluate("document.body.scrollHeight")
                    if page_height > settings.max_screenshot_height:
                        warnings.append(f"page_height_capped_from_{page_height}")
                        # Switch to viewport screenshot
                        screenshot_options["full_page"] = False
                except Exception:
                    pass
            
            image_bytes = await page.screenshot(**screenshot_options)
            
            total_time_ms = int((time.time() - start_time) * 1000)
            
            content_type = "image/jpeg" if request.format == ImageFormat.JPEG else "image/png"
            
            return ScreenshotResult(
                image_bytes=image_bytes,
                content_type=content_type,
                final_url=final_url,
                navigation_time_ms=nav_time_ms,
                total_time_ms=total_time_ms,
                warnings=warnings,
            )
    
    except asyncio.TimeoutError:
        raise TimeoutError(f"Operation timeout after {timeout_ms}ms")
    except PlaywrightError as e:
        error_msg = str(e)
        if "Target closed" in error_msg or "Browser closed" in error_msg or "has been closed" in error_msg:
            # Browser/page/context closed, clear the manager so next request relaunches
            logger.warning(f"[{request_id}] Browser/page closed during operation: {e}")
            global _browser_manager
            _browser_manager = None
            raise RuntimeError("Browser was closed during operation, please retry")
        raise


def _map_wait_strategy(strategy: WaitStrategy) -> str:
    """Map our wait strategy enum to Playwright's wait_until parameter."""
    mapping = {
        WaitStrategy.DOMCONTENTLOADED: "domcontentloaded",
        WaitStrategy.LOAD: "load",
        WaitStrategy.NETWORKIDLE: "networkidle",
    }
    return mapping[strategy]


async def _handle_scroll(page: Page, scroll_config) -> None:
    """Handle page scrolling based on configuration."""
    if scroll_config.mode == ScrollMode.NONE:
        return
    
    if scroll_config.mode == ScrollMode.PX:
        # Scroll down by specified pixels
        await page.evaluate(f"window.scrollBy(0, {scroll_config.value})")
        await asyncio.sleep(0.5)  # Brief pause after scroll
    
    elif scroll_config.mode == ScrollMode.AUTO:
        # Gradually scroll to trigger lazy loading
        duration_ms = scroll_config.auto_duration_ms or 2000
        steps = 5
        step_delay = duration_ms / steps / 1000
        
        # Get page height
        page_height = await page.evaluate("document.body.scrollHeight")
        step_size = page_height // steps
        
        for i in range(steps):
            await page.evaluate(f"window.scrollBy(0, {step_size})")
            await asyncio.sleep(step_delay)
        
        # Scroll back to top
        await page.evaluate("window.scrollTo(0, 0)")
        await asyncio.sleep(0.3)

