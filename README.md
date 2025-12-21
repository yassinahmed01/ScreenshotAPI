# Screenshot API

Production-ready HTTP Screenshot API for capturing web pages using headless Chromium. Designed to replace Airtop nodes in n8n Cloud workflows.

---

## A) Architecture Overview

```
┌──────────────┐     HTTPS/POST      ┌─────────────────────────────────┐
│              │ ──────────────────► │                                 │
│   n8n Cloud  │                     │   Screenshot API (FastAPI)      │
│              │ ◄────────────────── │                                 │
└──────────────┘     image/jpeg      │   ┌─────────────────────────┐   │
                                     │   │  Playwright + Chromium  │   │
                                     │   │  (headless browser)     │   │
                                     │   └─────────────────────────┘   │
                                     │                                 │
                                     │   Hosted on Render (Docker)     │
                                     └─────────────────────────────────┘
```

**Components:**
- **Client:** n8n Cloud (HTTP Request nodes)
- **Service:** FastAPI application
- **Browser:** Playwright + Chromium (headless)
- **Storage:** None (returns binary JPG directly)
- **Deployment:** Render (Docker)

**Request Flow:**
1. n8n sends `POST /screenshot` with **only URL** in request body
2. API validates request and authenticates via X-API-KEY header
3. API validates URL for SSRF protection
4. API checks rate limits and concurrency
5. Creates isolated browser context with hardcoded optimal settings
6. Navigate → wait → delay → auto-scroll → screenshot
7. Encode as JPEG (1280x720)
8. Return binary image with metadata headers
9. Cleanup browser resources (guaranteed via finally block)

---

## B) API Specification

### Endpoints

#### GET /health
Health check for Render.

**Response:** `200 OK`
```json
{"status": "ok", "version": "1.0.0"}
```

#### POST /screenshot
Capture a screenshot of a URL.

**Simplified API**: Only `url` is required. All other parameters are hardcoded with optimal defaults.

**Headers:**
- `X-API-KEY` (required): Shared secret for authentication
- `Content-Type: application/json`

**Request Body:**
```json
{
  "url": "https://example.com"
}
```

**Hardcoded Defaults (not configurable via API):**
- Viewport: 1280x720
- Wait strategy: "networkidle" + 15000ms delay (optimized for dynamic content)
- Timeout: 240000ms (240 seconds / 4 minutes)
- Format: JPEG, quality 85
- Full page: false (exact 1280x720 size)
- Scroll: auto (5000ms duration)
- Anti-bot detection: comprehensive stealth techniques (see Browser Automation section)

**Success Response:** `200 OK`
- Body: Binary image (JPEG or PNG)
- Content-Type: `image/jpeg` or `image/png`
- Headers:
  - `X-Request-Id`: Unique request identifier
  - `X-Final-Url`: URL after redirects
  - `X-Load-Time-Ms`: Navigation time
  - `X-Total-Time-Ms`: Total processing time
  - `X-Warning`: Comma-separated warnings (optional)

**Error Responses:**
| Status | Code | Description |
|--------|------|-------------|
| 400 | invalid_request | Invalid URL, missing fields, bad options |
| 401 | unauthorized | Missing/invalid X-API-KEY |
| 403 | forbidden | Blocked domain/private IP (SSRF) |
| 408 | timeout | Navigation or total timeout exceeded |
| 429 | too_many_requests | Rate/concurrency limit exceeded |
| 500 | internal_error | Unexpected error |

**Error Body:**
```json
{
  "error_code": "string",
  "message": "string",
  "request_id": "string",
  "details": {}
}
```

#### GET /status (authenticated)
Get service status including concurrency info.

---

## C) Browser Automation Design

### Browser Lifecycle
- **Single browser process** reused across requests (memory efficient)
- **New browser context** per request (isolation)
- **Browser recycled** after 50 requests (prevents memory leaks)
- **Auto-relaunch** on crash

### Wait Strategy
1. Navigate with `wait_until` event (domcontentloaded/load/networkidle)
2. Additional sleep for `wait_ms` to allow JS rendering
3. Optional scroll to trigger lazy loading
4. Take screenshot

### Scroll Modes
- `none`: No scrolling
- `px`: Scroll down by specified pixels
- `auto`: Gradually scroll full page, then return to top

### Screenshot Capture
- Full page by default (configurable)
- JPEG encoding with configurable quality
- Max height enforcement (16384px) to prevent huge images

### Protections
- Block file downloads (pdf, zip, exe, dmg)
- Ignore HTTPS errors
- Page timeout enforcement
- Viewport bounds validation

### Anti-Bot Detection Bypass
The API implements comprehensive stealth techniques to bypass bot detection systems:

**Browser Fingerprinting Protection:**
- Removes `navigator.webdriver` property (primary bot detection flag)
- Mocks Chrome runtime objects (`window.chrome`)
- Realistic browser plugins array (matches real Chrome)
- Proper platform, hardware concurrency, and device memory values
- Realistic navigator.languages, vendor, and appVersion

**Fingerprint Randomization:**
- Canvas fingerprint protection (adds imperceptible noise)
- WebGL vendor/renderer spoofing (Intel Iris)
- Audio context fingerprint randomization
- Connection API mocking (4G network characteristics)

**Headers & User Agent:**
- Chrome 131 user agent (latest stable)
- Realistic HTTP headers including Sec-Ch-Ua values
- Proper Accept, Accept-Language, Accept-Encoding headers
- Correct Sec-Fetch-* headers for navigation

**Browser Launch Arguments:**
- `--disable-blink-features=AutomationControlled` flag
- Comprehensive Chrome flags to minimize automation detection
- Window size matching viewport (1280x720)

**JavaScript Stealth Injection:**
- Removes automation indicators before page scripts execute
- Overrides permission APIs
- Fixes missing browser APIs that reveal automation
- Prevents detection via iframe analysis

These techniques work together to make the headless browser appear as a real user's Chrome browser, bypassing most bot detection systems including CloudFront, Akamai, and other WAF solutions.

### Metadata Captured
- Final URL after redirects
- Navigation time
- Total processing time
- Warnings (empty page detection)

---

## D) Reliability Design

### Timeouts
| Timeout | Default | Range | Description |
|---------|---------|-------|-------------|
| Navigation | 30s | 5-120s | Page load timeout |
| Browser | 60s | 10-180s | Browser operation timeout |
| Overall | Per request | - | Configurable per request |

### Concurrency Control
- **Semaphore-based** limiting (default: 2 concurrent)
- **Reject when busy** (returns 429, not queue)
- `Retry-After` header in 429 responses

### Rate Limiting
- **Sliding window** (per minute)
- **In-memory** (resets on restart)
- Default: 30 requests/minute

### Stability
- Browser recycled every 50 requests
- Crash recovery (auto-relaunch)
- Guaranteed cleanup via finally blocks
- Graceful shutdown on SIGTERM

### No Retry by Default
Retries disabled to avoid duplicate loads on expensive pages. Client (n8n) should implement retry logic if needed.

---

## E) Security Design

### Authentication
- **Header:** `X-API-KEY`
- **Storage:** Environment variable `API_KEY`
- Constant-time comparison (implicit via string equality)

### SSRF Protection
Blocked IP ranges:
- Private: 10.0.0.0/8, 172.16.0.0/12, 192.168.0.0/16
- Loopback: 127.0.0.0/8
- Link-local: 169.254.0.0/16
- Cloud metadata: 169.254.169.254
- IPv6 equivalents

DNS resolution performed **before** navigation to detect DNS rebinding.

### Domain Allowlist (Optional)
Set `ALLOWED_DOMAINS=example.com,example.org` to restrict URLs.

### Input Validation
- Max URL length: 2048 chars
- Max headers: 20
- Max cookies: 50
- Viewport bounds: 320-3840 × 240-2160
- Quality bounds: 1-100
- Timeout bounds: 5000-120000ms

### Logging Security
- Request ID logged (for tracing)
- URL hostname logged (not full URL with params)
- **Never log API keys**
- Structured logging format

---

## F) Render Deployment Plan

### Deployment Mode
**Docker on Render** (recommended for Playwright)

### System Dependencies (in Dockerfile)
- Minimal dependencies installed via `playwright install-deps chromium`
- Only Chromium browser installed (Firefox/WebKit removed)
- Optimized for smallest possible image size (Free tier friendly)

### Environment Variables
| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| API_KEY | ✓ | - | Shared secret |
| MAX_CONCURRENCY | - | 2 | Max concurrent screenshots |
| DEFAULT_TIMEOUT_MS | - | 30000 | Default timeout |
| DEFAULT_WAIT_MS | - | 2000 | Default extra wait |
| RATE_LIMIT_PER_MINUTE | - | 30 | Rate limit |
| ALLOWED_DOMAINS | - | "" | Comma-separated allowlist |
| LOG_LEVEL | - | INFO | Logging level |

### Health Check
- Path: `/health`
- Interval: 30s
- Timeout: 10s
- Start period: 60s (browser warmup)

### Scaling
- **Start with 1 instance**
- Concurrency handled in-app
- Multiple instances require distributed rate limiting (not implemented)

### Render Settings
- Plan: Starter (upgrade to Standard for production)
- Region: Oregon (or closest to n8n Cloud)
- Docker deployment

---

## G) n8n Integration Mapping

### Replace Airtop with HTTP Request Node

**Node Configuration:**
| Setting | Value |
|---------|-------|
| Method | POST |
| URL | https://your-app.onrender.com/screenshot |
| Authentication | Header Auth |
| Header Name | X-API-KEY |
| Header Value | {{$env.SCREENSHOT_API_KEY}} |
| Body Content Type | JSON |
| Response Format | File |

**Request Body (JSON) - Simplified:**
```json
{
  "url": "{{$node.Previous.json.url}}"
}
```

That's it! All other settings are automatically applied with optimal defaults.

**Downstream Processing:**
1. HTTP Request node → receives binary JPG
2. OCR node → consumes binary JPG
3. Analysis node → consumes OCR output
4. Telegram node → sends screenshot + summary

**Error Handling in n8n:**
- Enable "Continue on Fail"
- Check `$node.HTTP_Request.error` for failures
- Use status code from response headers
- Access `X-Request-Id` for debugging

---

## H) Test Plan

### Local Tests

#### Health Check
```bash
curl http://localhost:8000/health
# Expected: {"status":"ok","version":"1.0.0"}
```

#### Authentication
```bash
# Missing key - expect 401
curl -X POST http://localhost:8000/screenshot \
  -H "Content-Type: application/json" \
  -d '{"url":"https://example.com"}'

# Invalid key - expect 401
curl -X POST http://localhost:8000/screenshot \
  -H "X-API-KEY: wrong-key" \
  -H "Content-Type: application/json" \
  -d '{"url":"https://example.com"}'
```

#### Valid Screenshots
```bash
# Simple static page
curl -X POST http://localhost:8000/screenshot \
  -H "X-API-KEY: your-key" \
  -H "Content-Type: application/json" \
  -d '{"url":"https://example.com"}' \
  --output test.jpg

# JS-heavy page
curl -X POST http://localhost:8000/screenshot \
  -H "X-API-KEY: your-key" \
  -H "Content-Type: application/json" \
  -d '{"url":"https://news.ycombinator.com","wait":"networkidle","wait_ms":3000}' \
  --output hn.jpg

# Page with redirects
curl -X POST http://localhost:8000/screenshot \
  -H "X-API-KEY: your-key" \
  -H "Content-Type: application/json" \
  -d '{"url":"http://github.com"}' \
  --output github.jpg
# Check X-Final-Url header
```

#### SSRF Protection
```bash
# Private IP - expect 403
curl -X POST http://localhost:8000/screenshot \
  -H "X-API-KEY: your-key" \
  -H "Content-Type: application/json" \
  -d '{"url":"http://192.168.1.1"}'

# Localhost - expect 403
curl -X POST http://localhost:8000/screenshot \
  -H "X-API-KEY: your-key" \
  -H "Content-Type: application/json" \
  -d '{"url":"http://localhost:8080"}'
```

#### Timeout Handling
```bash
# Forced timeout - expect 408
curl -X POST http://localhost:8000/screenshot \
  -H "X-API-KEY: your-key" \
  -H "Content-Type: application/json" \
  -d '{"url":"https://example.com","timeout_ms":1}'
```

### Load Tests
```bash
# 10 sequential screenshots
for i in {1..10}; do
  curl -s -X POST http://localhost:8000/screenshot \
    -H "X-API-KEY: your-key" \
    -H "Content-Type: application/json" \
    -d '{"url":"https://example.com"}' \
    --output /dev/null -w "Request $i: %{http_code}\n"
done

# Concurrent requests (expect some 429s)
for i in {1..5}; do
  curl -s -X POST http://localhost:8000/screenshot \
    -H "X-API-KEY: your-key" \
    -H "Content-Type: application/json" \
    -d '{"url":"https://example.com"}' \
    --output /dev/null -w "%{http_code}\n" &
done
wait
```

### Staging Tests on Render
1. Deploy to Render
2. Verify `/health` returns 200
3. Test screenshot capture with real URLs
4. Verify n8n can receive binary image
5. Test timeout and error handling
6. Monitor memory usage over multiple requests

### Definition of Done
- [ ] `/health` returns 200
- [ ] Screenshots work for static, JS-heavy, and redirect pages
- [ ] Headers returned: X-Request-Id, X-Final-Url, X-Load-Time-Ms, X-Total-Time-Ms
- [ ] Auth: 401 for missing/invalid key
- [ ] SSRF: 403 for private IPs
- [ ] Timeout: 408 when exceeded
- [ ] Rate limit: 429 when exceeded
- [ ] n8n workflow receives usable JPG or clear error
- [ ] No orphaned browser processes after 50+ requests
- [ ] Memory stable across extended usage

---

## I) Failure Modes Checklist

| Failure Mode | Detection | API Response | Mitigation |
|--------------|-----------|--------------|------------|
| **Blank screenshot** | Check body height < 100px | 200 + X-Warning: page_may_be_empty | Increase wait_ms, use networkidle, add scroll |
| **Slow page** | Navigation timeout | 408 timeout | Increase timeout_ms |
| **CAPTCHA** | Heuristic (optional) | 200 + X-Warning: captcha_suspected | Return screenshot as-is, client handles |
| **Huge full-page** | Height > 16384px | 200 (viewport only) + warning | Auto-switch to viewport, cap max height |
| **Infinite loading** | Total timeout | 408 timeout | Hard timeout enforced |
| **Browser crash** | Playwright error | 500 internal_error | Auto-relaunch on next request |
| **DNS failure** | dns.resolver exception | 400 invalid_request | Clear error message |
| **SSRF attempt** | IP validation | 403 forbidden | Block and log |
| **Rate exceeded** | Counter check | 429 + Retry-After | Client retries after delay |
| **Concurrency exceeded** | Semaphore full | 429 + Retry-After: 5 | Client retries |
| **Invalid input** | Pydantic validation | 400 invalid_request | Detailed error message |
| **Auth failure** | Key mismatch | 401 unauthorized | No details (security) |

---

## Quick Start

### Local Development

1. **Clone and setup:**
```bash
cd WebScreenShotAPI
pip install -r requirements.txt
playwright install chromium
```

2. **Set environment:**
```bash
# Windows PowerShell
$env:API_KEY="your-dev-key"

# Linux/Mac
export API_KEY="your-dev-key"
```

3. **Run:**
```bash
uvicorn app.main:app --reload --port 8000
```

4. **Test:**
```bash
curl http://localhost:8000/health
```

### Docker Local

```bash
docker-compose up --build
```

### Deploy to Render

1. Push code to GitHub
2. Create new Web Service on Render
3. Select Docker environment
4. Set `API_KEY` in environment variables
5. Deploy

---

## Environment Variables Reference

```env
# Required
API_KEY=your-secure-api-key-here

# Optional - defaults shown
MAX_CONCURRENCY=2
DEFAULT_TIMEOUT_MS=30000
DEFAULT_WAIT_MS=2000
DEFAULT_VIEWPORT_WIDTH=1365
DEFAULT_VIEWPORT_HEIGHT=768
DEFAULT_QUALITY=85
MAX_SCREENSHOT_HEIGHT=16384
RATE_LIMIT_PER_MINUTE=30
ALLOWED_DOMAINS=
LOG_LEVEL=INFO
```

