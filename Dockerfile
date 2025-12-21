# Production Dockerfile for Screenshot API on Render
# Optimized for minimal size (Free tier friendly)

FROM python:3.11-slim as builder

WORKDIR /build

# Install minimal build dependencies only
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    && rm -rf /var/lib/apt/lists/* \
    && apt-get clean

# Copy requirements first for better caching
COPY requirements.txt .

# Install Python dependencies globally with no cache
RUN pip install --no-cache-dir -r requirements.txt


# Final stage - minimal base
FROM python:3.11-slim

WORKDIR /app

# Install only essential system packages
# Use Playwright's installer to get minimal dependencies for Chromium
RUN apt-get update && apt-get install -y --no-install-recommends \
    wget \
    ca-certificates \
    # Install playwright first to use its dependency installer
    && pip install --no-cache-dir playwright==1.41.2 \
    && playwright install-deps chromium \
    && rm -rf /var/lib/apt/lists/* \
    && apt-get clean \
    && rm -rf /tmp/* /var/tmp/* \
    && find /usr/local -name "*.pyc" -delete \
    && find /usr/local -name "__pycache__" -type d -exec rm -rf {} + 2>/dev/null || true

# Copy Python packages from builder (already installed)
COPY --from=builder /usr/local/lib/python3.11/site-packages /usr/local/lib/python3.11/site-packages
COPY --from=builder /usr/local/bin /usr/local/bin

# Install Chromium only (not other browsers)
# Clean up any accidentally installed browsers (Firefox, WebKit)
RUN playwright install chromium \
    && rm -rf /root/.cache/ms-playwright/.local-browsers/*/firefox* \
    && rm -rf /root/.cache/ms-playwright/.local-browsers/*/webkit* 2>/dev/null || true

# Copy application code
COPY app/ ./app/

# Create non-root user (required for security)
RUN useradd --create-home --shell /bin/bash appuser \
    && chown -R appuser:appuser /app

# Copy Playwright cache to appuser and clean up root cache
RUN cp -r /root/.cache /home/appuser/.cache \
    && chown -R appuser:appuser /home/appuser/.cache \
    && rm -rf /root/.cache

USER appuser

# Environment defaults
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PLAYWRIGHT_BROWSERS_PATH=/home/appuser/.cache/ms-playwright

# Expose port
EXPOSE 8000

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=60s --retries=3 \
    CMD wget --no-verbose --tries=1 --spider http://localhost:8000/health || exit 1

# Run with uvicorn
CMD ["python", "-m", "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
