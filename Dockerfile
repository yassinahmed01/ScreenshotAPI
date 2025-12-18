# Production Dockerfile for Screenshot API on Render
# Uses multi-stage build for smaller final image

FROM python:3.11-slim as builder

WORKDIR /build

# Install build dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements first for better caching
COPY requirements.txt .

# Install Python dependencies globally (not --user)
RUN pip install --no-cache-dir -r requirements.txt


# Final stage
FROM python:3.11-slim

WORKDIR /app

# Install Playwright system dependencies for Chromium
# These are required for headless Chromium to run
RUN apt-get update && apt-get install -y --no-install-recommends \
    # Playwright Chromium dependencies
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
    # Fonts
    fonts-liberation \
    fonts-noto-color-emoji \
    # X11 libs
    libx11-6 \
    libx11-xcb1 \
    libxcb1 \
    libxext6 \
    # Misc
    ca-certificates \
    wget \
    && rm -rf /var/lib/apt/lists/* \
    && apt-get clean

# Copy Python packages from builder (installed globally)
COPY --from=builder /usr/local/lib/python3.11/site-packages /usr/local/lib/python3.11/site-packages
COPY --from=builder /usr/local/bin /usr/local/bin

# Install Playwright browsers (Chromium only) as root
RUN playwright install chromium

# Copy application code
COPY app/ ./app/

# Create non-root user for security
RUN useradd --create-home --shell /bin/bash appuser \
    && chown -R appuser:appuser /app

# Copy Playwright browsers to appuser home
RUN cp -r /root/.cache /home/appuser/.cache \
    && chown -R appuser:appuser /home/appuser/.cache

USER appuser

# Environment defaults
ENV PYTHONUNBUFFERED=1
ENV PYTHONDONTWRITEBYTECODE=1

# Expose port
EXPOSE 8000

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=60s --retries=3 \
    CMD wget --no-verbose --tries=1 --spider http://localhost:8000/health || exit 1

# Run with uvicorn
CMD ["python", "-m", "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]

