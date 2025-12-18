# Proxy Configuration for Barchart

## Problem
Barchart blocks automated browsers. Using a proxy (like you did with Airtop) helps bypass these restrictions.

## Solution: Configure Proxy via Environment Variables

Since the API only accepts URL, proxy is configured via Render environment variables.

---

## Step 1: Get Proxy Server Details

From your Airtop configuration, you were using:
- **Country**: Togo
- **Proxy Type**: Integrated

You'll need the actual proxy server URL. Common formats:
- `http://proxy-server.com:8080`
- `socks5://proxy-server.com:1080`
- `http://username:password@proxy-server.com:8080`

**If using a proxy service**, get the server URL from your provider.

---

## Step 2: Add Proxy to Render Environment Variables

1. Go to **Render Dashboard** → Your `screenshot-api` service
2. Click **"Environment"** tab
3. Add these environment variables:

### Basic Proxy (No Authentication)
```
PROXY_SERVER=http://your-proxy-server.com:8080
```

### Proxy with Authentication
```
PROXY_SERVER=http://your-proxy-server.com:8080
PROXY_USERNAME=your-username
PROXY_PASSWORD=your-password
```

### Example with Residential Proxy Service
```
PROXY_SERVER=http://rotating-residential-proxy.com:8080
PROXY_USERNAME=your-api-key
PROXY_PASSWORD=your-secret
```

---

## Step 3: Redeploy

After adding environment variables:
1. Click **"Save Changes"**
2. Render will automatically redeploy
3. Wait 2-3 minutes for deployment

---

## Step 4: Test

The proxy will be used automatically for all screenshot requests.

```bash
curl -X POST https://screenshotapi-nge4.onrender.com/screenshot \
  -H "X-API-KEY: your-api-key" \
  -H "Content-Type: application/json" \
  -d '{"url":"https://www.barchart.com/stocks/quotes/RMF26/overview"}' \
  --output test.jpg
```

---

## Proxy Service Recommendations

### Residential Proxy Services (Good for Barchart)
- **Bright Data** (formerly Luminati)
- **Smartproxy**
- **Oxylabs**
- **IPRoyal**

### Datacenter Proxy Services (Cheaper, may still be blocked)
- **ProxyMesh**
- **MyPrivateProxy**

---

## Troubleshooting

### Proxy Not Working?
1. Check Render logs for proxy connection errors
2. Verify proxy server URL format is correct
3. Test proxy server separately (curl through proxy)
4. Check if proxy requires authentication

### Still Getting Blocked?
- Try different proxy server/country
- Use residential proxies instead of datacenter
- Increase wait times (already optimized in code)

### Performance Issues?
- Proxy adds latency (expected)
- Consider using proxy closer to Render server location
- Some proxy services have speed tiers

---

## Environment Variables Reference

| Variable | Required | Format | Example |
|----------|----------|--------|---------|
| `PROXY_SERVER` | No | `http://host:port` or `socks5://host:port` | `http://proxy.example.com:8080` |
| `PROXY_USERNAME` | No | String | `user123` |
| `PROXY_PASSWORD` | No | String | `pass456` |

**Note:** If `PROXY_SERVER` is not set, no proxy will be used (direct connection).

