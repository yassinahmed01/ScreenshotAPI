# Deployment Guide - Screenshot API on Render

## Quick Start

### 1. Push to GitHub

```bash
git init
git add .
git commit -m "Initial commit: Screenshot API"
git remote add origin https://github.com/yourusername/screenshot-api.git
git push -u origin main
```

### 2. Deploy on Render

#### Option A: Using Render Dashboard (Recommended)

1. Go to [Render Dashboard](https://dashboard.render.com)
2. Click **"New +"** → **"Web Service"**
3. Connect your GitHub repository
4. Configure:
   - **Name**: `screenshot-api`
   - **Environment**: `Docker`
   - **Region**: `Oregon` (or closest to n8n Cloud)
   - **Branch**: `main`
   - **Root Directory**: (leave empty)
   - **Dockerfile Path**: `Dockerfile`
   - **Docker Build Context**: (leave empty)

5. **Environment Variables** (click "Advanced"):
   ```
   API_KEY=your-secure-random-key-here
   MAX_CONCURRENCY=2
   DEFAULT_TIMEOUT_MS=30000
   DEFAULT_WAIT_MS=2000
   RATE_LIMIT_PER_MINUTE=30
   LOG_LEVEL=INFO
   ```

6. **Health Check Path**: `/health`

7. Click **"Create Web Service"**

8. Wait for build to complete (~5-10 minutes for first build)

#### Option B: Using Render Blueprint (render.yaml)

1. Push code to GitHub (main branch)
2. In Render Dashboard, click **"New +"** → **"Blueprint"**
3. Connect repository
4. Render will read `render.yaml` and create the service
5. **Important**: Set `API_KEY` manually in Environment Variables
6. **Note**: Make sure branch is set to `main` (not `master`)

### 3. Get Your API URL

After deployment, Render provides:
- **Service URL**: `https://screenshot-api.onrender.com`
- **Health Check**: `https://screenshot-api.onrender.com/health`

### 4. Test the API

```bash
curl -X POST https://screenshot-api.onrender.com/screenshot \
  -H "X-API-KEY: your-api-key" \
  -H "Content-Type: application/json" \
  -d '{"url":"https://example.com"}' \
  --output test.jpg
```

### 5. Configure n8n

In your n8n workflow:
- **HTTP Request Node** → POST to `https://screenshot-api.onrender.com/screenshot`
- **Header**: `X-API-KEY: your-api-key`
- **Body**: `{"url": "{{$json.url}}"}`

## Environment Variables

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `API_KEY` | ✅ Yes | - | Shared secret for API authentication |
| `MAX_CONCURRENCY` | No | 2 | Max concurrent screenshot requests |
| `DEFAULT_TIMEOUT_MS` | No | 30000 | Default timeout (30s) |
| `DEFAULT_WAIT_MS` | No | 2000 | Default wait delay (2s) |
| `RATE_LIMIT_PER_MINUTE` | No | 30 | Rate limit per minute |
| `LOG_LEVEL` | No | INFO | Logging level (DEBUG, INFO, WARNING, ERROR) |
| `ALLOWED_DOMAINS` | No | "" | Comma-separated domain allowlist (optional) |

## Generate Secure API Key

```bash
# Linux/Mac
openssl rand -hex 32

# PowerShell (Windows)
-join ((48..57) + (65..90) + (97..122) | Get-Random -Count 32 | ForEach-Object {[char]$_})
```

## Troubleshooting

### Build Fails
- Check Dockerfile syntax
- Verify Playwright browsers install correctly
- Check Render build logs

### 500 Errors
- Check Render logs for browser crashes
- Verify API_KEY is set correctly
- Check memory limits (upgrade plan if needed)

### Timeouts
- Increase `DEFAULT_TIMEOUT_MS` in environment variables
- Check target URL accessibility
- Verify network connectivity

### Rate Limits
- Adjust `RATE_LIMIT_PER_MINUTE` if needed
- Check `MAX_CONCURRENCY` setting
- Monitor Render metrics

## Scaling

- **Starter Plan**: 1 instance, 512MB RAM (sufficient for testing)
- **Standard Plan**: Better performance, more RAM (recommended for production)
- **Multiple Instances**: Not recommended (rate limiting is per-instance)

## Monitoring

- **Render Dashboard**: View logs, metrics, and health status
- **Health Endpoint**: `/health` returns `{"status":"ok","version":"1.0.0"}`
- **Status Endpoint**: `/status` (requires auth) shows concurrency info

## Cost Estimate

- **Starter Plan**: Free tier available (with limitations)
- **Standard Plan**: ~$7/month per instance
- **Bandwidth**: Included in plan

## Security Checklist

- ✅ Set strong `API_KEY` (32+ random characters)
- ✅ Use HTTPS (Render provides automatically)
- ✅ Configure `ALLOWED_DOMAINS` if restricting access
- ✅ Monitor logs for suspicious activity
- ✅ Keep dependencies updated

