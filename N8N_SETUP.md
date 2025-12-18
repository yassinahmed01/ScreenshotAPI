# n8n Integration Guide - Screenshot API

## Step-by-Step: Configure HTTP Request Node in n8n

### Prerequisites
- Screenshot API deployed on Render (get your API URL)
- API Key from Render environment variables
- n8n Cloud account (or self-hosted)

---

## Configuration Steps

### 1. Add HTTP Request Node

1. In your n8n workflow, click **"+"** to add a node
2. Search for **"HTTP Request"**
3. Select **"HTTP Request"** node
4. Click on the node to configure it

---

### 2. Configure HTTP Request Node

#### **Basic Settings Tab:**

| Field | Value |
|-------|-------|
| **Method** | `POST` |
| **URL** | `https://your-app-name.onrender.com/screenshot` |
| | *(Replace `your-app-name` with your Render app name)* |
| **Authentication** | `Header Auth` |
| **Header Name** | `X-API-KEY` |
| **Header Value** | `your-api-key-here` |
| | *(Use the same API_KEY from Render environment variables)* |

#### **Options Tab:**

| Field | Value |
|-------|-------|
| **Response Format** | `File` |
| **Timeout** | `120000` (120 seconds) |
| **Ignore SSL Issues** | `false` (leave unchecked) |

#### **Body Tab:**

| Field | Value |
|-------|-------|
| **Body Content Type** | `JSON` |
| **JSON Body** | See below |

**JSON Body:**
```json
{
  "url": "{{ $json.url }}"
}
```

**OR if you have the URL in a different field:**
```json
{
  "url": "{{ $json.website }}"
}
```

**OR if you want to hardcode a URL for testing:**
```json
{
  "url": "https://www.barchart.com/stocks/quotes/RMF26/overview"
}
```

---

### 3. Complete Node Configuration

**Node Name:** `Screenshot API` (optional, for clarity)

**Final Configuration Summary:**
```
Method: POST
URL: https://your-app-name.onrender.com/screenshot
Headers:
  X-API-KEY: your-api-key-here
  Content-Type: application/json
Body:
{
  "url": "{{ $json.url }}"
}
Response Format: File
Timeout: 120000ms
```

---

### 4. Connect Nodes

**Example Workflow:**
```
[Previous Node] → [HTTP Request: Screenshot API] → [OCR Node] → [Next Node]
```

**Input from Previous Node:**
The previous node should output JSON with a `url` field:
```json
{
  "url": "https://example.com"
}
```

---

### 5. Handle Response

**Response Format:**
- The HTTP Request node will output a **binary file** (JPEG image)
- File size: varies (typically 50KB - 2MB)
- Content-Type: `image/jpeg`

**Response Headers (available in n8n):**
- `X-Request-Id`: Unique request identifier
- `X-Final-Url`: Final URL after redirects
- `X-Load-Time-Ms`: Navigation time
- `X-Total-Time-Ms`: Total processing time
- `X-Warning`: Any warnings (if present)

**Access Response Data:**
- **Binary Data**: `{{ $binary.data }}`
- **Request ID**: `{{ $response.headers['x-request-id'] }}`
- **Final URL**: `{{ $response.headers['x-final-url'] }}`
- **Load Time**: `{{ $response.headers['x-load-time-ms'] }}ms`
- **Total Time**: `{{ $response.headers['x-total-time-ms'] }}ms`

---

### 6. Error Handling

**Enable Error Handling:**
1. Click on HTTP Request node
2. Go to **"Settings"** tab
3. Enable **"Continue on Fail"**
4. Add **"IF"** node after HTTP Request to check for errors

**Check for Errors:**
```javascript
// In IF node condition
{{ $json.error }} exists
```

**Error Response Format:**
```json
{
  "error_code": "timeout",
  "message": "Navigation timeout after 90000ms",
  "request_id": "abc123",
  "details": {}
}
```

---

## Example: Complete Workflow

### Workflow Structure:
```
1. [Webhook] or [Manual Trigger]
   ↓
2. [Set] - Set URL variable
   ↓
3. [HTTP Request] - Screenshot API
   ↓
4. [IF] - Check for errors
   ↓ (if success)
5. [OCR Node] - Process screenshot
   ↓
6. [Telegram] or [Email] - Send result
```

### Node 2: Set URL
**Operation:** Set
**Fields:**
- `url`: `https://www.barchart.com/stocks/quotes/RMF26/overview`

### Node 3: HTTP Request (Screenshot API)
**Method:** `POST`
**URL:** `https://your-app.onrender.com/screenshot`
**Authentication:** Header Auth
- Name: `X-API-KEY`
- Value: `your-api-key`
**Body:** JSON
```json
{
  "url": "{{ $json.url }}"
}
```
**Response Format:** `File`

### Node 4: IF (Error Check)
**Condition:** `{{ $json.error }} exists`
- **True:** Handle error (send notification)
- **False:** Continue to OCR

### Node 5: OCR Node
**Input:** Binary data from HTTP Request
**Access:** `{{ $binary.data }}`

---

## Testing in n8n

### Test with Manual Trigger:

1. Add **"Manual Trigger"** node
2. Add **"Set"** node after it
3. Set field: `url` = `https://example.com`
4. Add **"HTTP Request"** node (configured as above)
5. Click **"Execute Workflow"**
6. Check the output - you should see binary image data

### Verify Success:
- HTTP Request node shows status: `200`
- Binary data is present
- Response headers are available

---

## Troubleshooting

### Issue: 401 Unauthorized
**Solution:** Check that `X-API-KEY` header matches your Render `API_KEY` environment variable

### Issue: 408 Timeout
**Solution:** Increase timeout in HTTP Request node options (max 120000ms)

### Issue: 429 Too Many Requests
**Solution:** Wait a few seconds and retry, or increase rate limits in Render environment variables

### Issue: Empty Response
**Solution:** Check that URL is valid and accessible, verify API is running on Render

### Issue: Binary Data Not Available
**Solution:** Ensure "Response Format" is set to "File" (not "JSON")

---

## Security Best Practices

1. **Store API Key Securely:**
   - Use n8n Credentials (not hardcoded)
   - Or use environment variable: `{{ $env.SCREENSHOT_API_KEY }}`

2. **Validate URLs:**
   - Add validation before HTTP Request node
   - Ensure URLs start with `http://` or `https://`

3. **Error Handling:**
   - Always enable "Continue on Fail"
   - Log errors for debugging
   - Notify on failures

---

## Quick Reference

**API Endpoint:** `POST https://your-app.onrender.com/screenshot`

**Required Headers:**
```
X-API-KEY: your-api-key-here
Content-Type: application/json
```

**Request Body:**
```json
{
  "url": "https://example.com"
}
```

**Response:**
- Binary JPEG image (1280x720)
- Headers: X-Request-Id, X-Final-Url, X-Load-Time-Ms, X-Total-Time-Ms

**Timeout:** 90 seconds (hardcoded in API)

