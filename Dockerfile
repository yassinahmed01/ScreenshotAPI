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

# Install all Chromium system dependencies explicitly
# playwright install-deps doesn't always install everything, so we install manually
RUN apt-get update && apt-get install -y --no-install-recommends \
    wget \
    ca-certificates \
    # Chromium/Playwright required libraries
    libnss3 \
    libnspr4 \
    libatk1.0-0 \
    libatk-bridge2.0-0 \
    libcups2 \
    libdrm2 \
    libxkbcommon0 \
    libxcomposite1 \
    libxdamage1 \
    libxfixes3 \
    libxrandr2 \
    libgbm1 \
    libasound2 \
    libpango-1.0-0 \
    libcairo2 \
    libatspi2.0-0 \
    libgtk-3-0 \
    libx11-6 \
    libx11-xcb1 \
    libxcb1 \
    libxext6 \
    libxshmfence1 \
    # Additional required libraries (dependencies of the above)
    libglib2.0-0 \
    libgdk-pixbuf2.0-0 \
    libdbus-1-3 \
    libexpat1 \
    libxss1 \
    && rm -rf /var/lib/apt/lists/* \
    && apt-get clean \
    && rm -rf /tmp/* /var/tmp/*

# Copy Python packages from builder (includes playwright)
COPY --from=builder /usr/local/lib/python3.11/site-packages /usr/local/lib/python3.11/site-packages
COPY --from=builder /usr/local/bin /usr/local/bin

# Clean Python cache
RUN find /usr/local -name "*.pyc" -delete \
    && find /usr/local -name "__pycache__" -type d -exec rm -rf {} + 2>/dev/null || true

# Create non-root user (required for security)
RUN useradd --create-home --shell /bin/bash appuser \
    && chown -R appuser:appuser /app

# Install Chromium as appuser (so it goes to the right location)
USER appuser

# Install Chromium only (not other browsers) - now as appuser
RUN playwright install chromium \
    && rm -rf /home/appuser/.cache/ms-playwright/.local-browsers/*/firefox* \
    && rm -rf /home/appuser/.cache/ms-playwright/.local-browsers/*/webkit* 2>/dev/null || true

# Copy application code (as root, then fix ownership)
USER root
COPY app/ ./app/
RUN chown -R appuser:appuser /app

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
