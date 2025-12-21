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
                        "--disable-blink-features=AutomationControlled",
                        "--disable-features=IsolateOrigins,site-per-process",
                        "--disable-web-security",
                        "--disable-features=VizDisplayCompositor",
                        "--disable-background-networking",
                        "--disable-background-timer-throttling",
                        "--disable-breakpoint",
                        "--disable-client-side-phishing-detection",
                        "--disable-component-update",
                        "--disable-default-apps",
                        "--disable-domain-reliability",
                        "--disable-extensions",
                        "--disable-features=AudioServiceOutOfProcess",
                        "--disable-hang-monitor",
                        "--disable-ipc-flooding-protection",
                        "--disable-notifications",
                        "--disable-offer-store-unmasked-wallet-cards",
                        "--disable-popup-blocking",
                        "--disable-prompt-on-repost",
                        "--disable-renderer-backgrounding",
                        "--disable-speech-api",
                        "--disable-sync",
                        "--hide-scrollbars",
                        "--ignore-gpu-blacklist",
                        "--metrics-recording-only",
                        "--mute-audio",
                        "--no-default-browser-check",
                        "--no-first-run",
                        "--no-pings",
                        "--no-zygote",
                        "--password-store=basic",
                        "--use-gl=swiftshader",
                        "--use-mock-keychain",
                        "--window-size=1280,720",
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
            # Default to a realistic, current Chrome user agent if not provided
            # Updated to match latest Chrome version for better compatibility
            default_user_agent = (
                request.user_agent 
                if request.user_agent 
                else "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
            )
            
            # Realistic browser headers matching Chrome 131 on Windows
            # These headers are critical for bypassing bot detection systems
            default_headers = {
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.7",
                "Accept-Language": "en-US,en;q=0.9",
                "Accept-Encoding": "gzip, deflate, br, zstd",
                "Sec-Ch-Ua": '"Google Chrome";v="131", "Chromium";v="131", "Not_A Brand";v="24"',
                "Sec-Ch-Ua-Mobile": "?0",
                "Sec-Ch-Ua-Platform": '"Windows"',
                "Sec-Fetch-Dest": "document",
                "Sec-Fetch-Mode": "navigate",
                "Sec-Fetch-Site": "none",
                "Sec-Fetch-User": "?1",
                "Upgrade-Insecure-Requests": "1",
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
            
            context = await browser.new_context(**context_options)
            
            # Comprehensive anti-bot detection bypass script
            # This script addresses multiple bot detection vectors:
            # - webdriver property removal
            # - Chrome runtime object mocking
            # - Realistic browser fingerprinting (plugins, languages, hardware)
            # - Canvas/WebGL/Audio fingerprint randomization
            # - Automation indicator removal
            await context.add_init_script("""
                // Remove webdriver property (primary bot detection flag)
                Object.defineProperty(navigator, 'webdriver', {
                    get: () => undefined,
                    configurable: true
                });
                
                // Override Chrome runtime to hide automation
                window.chrome = {
                    runtime: {},
                    loadTimes: function() {},
                    csi: function() {},
                    app: {}
                };
                
                // Fix permissions API
                const originalQuery = window.navigator.permissions.query;
                window.navigator.permissions.query = (parameters) => (
                    parameters.name === 'notifications' ?
                        Promise.resolve({ state: Notification.permission }) :
                        originalQuery(parameters)
                );
                
                // Realistic plugins array (matching Chrome)
                Object.defineProperty(navigator, 'plugins', {
                    get: () => {
                        const plugins = [
                            {
                                0: {type: "application/x-google-chrome-pdf", suffixes: "pdf", description: "Portable Document Format"},
                                description: "Portable Document Format",
                                filename: "internal-pdf-viewer",
                                length: 1,
                                name: "Chrome PDF Plugin"
                            },
                            {
                                0: {type: "application/pdf", suffixes: "pdf", description: ""},
                                description: "",
                                filename: "mhjfbmdgcfjbbpaeojofohoefgiehjai",
                                length: 1,
                                name: "Chrome PDF Viewer"
                            },
                            {
                                0: {type: "application/x-nacl", suffixes: "", description: "Native Client Executable"},
                                1: {type: "application/x-pnacl", suffixes: "", description: "Portable Native Client Executable"},
                                description: "",
                                filename: "internal-nacl-plugin",
                                length: 2,
                                name: "Native Client"
                            }
                        ];
                        return plugins;
                    },
                    configurable: true
                });
                
                // Realistic languages
                Object.defineProperty(navigator, 'languages', {
                    get: () => ['en-US', 'en'],
                    configurable: true
                });
                
                // Fix platform
                Object.defineProperty(navigator, 'platform', {
                    get: () => 'Win32',
                    configurable: true
                });
                
                // Fix hardware concurrency (realistic CPU cores)
                Object.defineProperty(navigator, 'hardwareConcurrency', {
                    get: () => 8,
                    configurable: true
                });
                
                // Fix device memory
                Object.defineProperty(navigator, 'deviceMemory', {
                    get: () => 8,
                    configurable: true
                });
                
                // Override getBattery if present (can reveal automation)
                if (navigator.getBattery) {
                    navigator.getBattery = undefined;
                }
                
                // Mock connection (network info)
                Object.defineProperty(navigator, 'connection', {
                    get: () => ({
                        effectiveType: '4g',
                        rtt: 50,
                        downlink: 10,
                        saveData: false,
                        onchange: null
                    }),
                    configurable: true
                });
                
                // Canvas fingerprint protection - add noise to prevent tracking
                const originalToDataURL = HTMLCanvasElement.prototype.toDataURL;
                HTMLCanvasElement.prototype.toDataURL = function(type) {
                    if (type === 'image/png' || type === 'image/jpeg') {
                        const context = this.getContext('2d');
                        if (context) {
                            const imageData = context.getImageData(0, 0, this.width, this.height);
                            // Add minimal random noise (undetectable to human eye)
                            for (let i = 0; i < imageData.data.length; i += 4) {
                                if (Math.random() > 0.999) {
                                    imageData.data[i] = Math.min(255, imageData.data[i] + Math.random() * 2 - 1);
                                }
                            }
                            context.putImageData(imageData, 0, 0);
                        }
                    }
                    return originalToDataURL.apply(this, arguments);
                };
                
                // WebGL fingerprint protection
                const getParameter = WebGLRenderingContext.prototype.getParameter;
                WebGLRenderingContext.prototype.getParameter = function(parameter) {
                    if (parameter === 37445) { // UNMASKED_VENDOR_WEBGL
                        return 'Intel Inc.';
                    }
                    if (parameter === 37446) { // UNMASKED_RENDERER_WEBGL
                        return 'Intel Iris OpenGL Engine';
                    }
                    return getParameter.apply(this, arguments);
                };
                
                // Audio context fingerprint protection
                if (window.AudioContext || window.webkitAudioContext) {
                    const AudioContext = window.AudioContext || window.webkitAudioContext;
                    const originalCreateOscillator = AudioContext.prototype.createOscillator;
                    AudioContext.prototype.createOscillator = function() {
                        const oscillator = originalCreateOscillator.apply(this, arguments);
                        const originalFrequency = oscillator.frequency.value;
                        Object.defineProperty(oscillator.frequency, 'value', {
                            get: function() {
                                return originalFrequency + (Math.random() * 0.0001 - 0.00005);
                            }
                        });
                        return oscillator;
                    };
                }
                
                // Fix missing vendor
                Object.defineProperty(navigator, 'vendor', {
                    get: () => 'Google Inc.',
                    configurable: true
                });
                
                // Fix appVersion to match user agent
                Object.defineProperty(navigator, 'appVersion', {
                    get: () => '5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36',
                    configurable: true
                });
                
                // Override toString methods to prevent detection
                Object.defineProperty(navigator, 'webdriver', {
                    get: () => undefined,
                    configurable: true
                });
                
                // Fix missing automation indicators
                delete navigator.__proto__.webdriver;
                
                // Prevent detection via iframe
                Object.defineProperty(window, 'outerHeight', {
                    get: () => window.innerHeight,
                    configurable: true
                });
                
                Object.defineProperty(window, 'outerWidth', {
                    get: () => window.innerWidth,
                    configurable: true
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

