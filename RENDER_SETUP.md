# Render Deployment - Quick Fix Guide

## Current Error

```
ValidationError: 1 validation error for Settings
api_key
  Field required
```

**Meaning:** The `API_KEY` environment variable is not set in Render.

---

## Solution: Set API_KEY in Render

### Step 1: Generate API Key

**PowerShell:**
```powershell
-join ((48..57) + (65..90) + (97..122) | Get-Random -Count 32 | ForEach-Object {[char]$_})
```

**Or use online generator:**
- Visit: https://www.random.org/strings/
- Length: 32
- Characters: Alphanumeric

**Example:** `aB3dE5fG7hI9jK1lM3nO5pQ7rS9tU1vW3xY5z`

---

### Step 2: Add to Render Dashboard

1. Go to [Render Dashboard](https://dashboard.render.com)
2. Click on your **"screenshot-api"** service
3. Click **"Environment"** tab (left sidebar)
4. Scroll to **"Environment Variables"** section
5. Click **"Add Environment Variable"**
6. Fill in:
   - **Key:** `API_KEY`
   - **Value:** `your-generated-key-here` (paste the 32-character key)
7. Click **"Save Changes"**
8. Render will **automatically redeploy** your service

---

### Step 3: Verify Deployment

1. Wait 2-3 minutes for redeploy
2. Check **"Logs"** tab - should see:
   ```
   INFO:     Started server process
   INFO:     Waiting for application startup.
   INFO:     Application startup complete.
   INFO:     Uvicorn running on http://0.0.0.0:8000
   ```
3. Test health endpoint:
   ```bash
   curl https://your-app.onrender.com/health
   ```
   Should return: `{"status":"ok","version":"1.0.0"}`

---

## Required Environment Variables

| Variable | Required | Description |
|----------|----------|-------------|
| `API_KEY` | ✅ **YES** | Shared secret for API authentication |

## Optional Environment Variables

These have defaults but can be customized:

| Variable | Default | Description |
|----------|---------|-------------|
| `MAX_CONCURRENCY` | 2 | Max concurrent requests |
| `DEFAULT_TIMEOUT_MS` | 30000 | Default timeout (30s) |
| `DEFAULT_WAIT_MS` | 2000 | Default wait delay (2s) |
| `RATE_LIMIT_PER_MINUTE` | 30 | Rate limit per minute |
| `LOG_LEVEL` | INFO | Logging level |

---

## After Setting API_KEY

Once `API_KEY` is set, your service will:
1. ✅ Start successfully
2. ✅ Be accessible at `https://your-app.onrender.com`
3. ✅ Accept requests with `X-API-KEY` header

---

## Test Your Deployment

```bash
curl -X POST https://your-app.onrender.com/screenshot \
  -H "X-API-KEY: your-api-key-here" \
  -H "Content-Type: application/json" \
  -d '{"url":"https://example.com"}' \
  --output test.jpg
```

---

## Troubleshooting

### Still getting errors?
- Check Render **Logs** tab for detailed error messages
- Verify `API_KEY` is spelled exactly: `API_KEY` (all caps, underscore)
- Make sure you clicked **"Save Changes"** after adding the variable
- Wait for redeploy to complete (check "Events" tab)

### Service won't start?
- Check that `API_KEY` value doesn't have extra spaces
- Verify the key is at least 16 characters (recommended: 32)
- Check Render logs for other errors

