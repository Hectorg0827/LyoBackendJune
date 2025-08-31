# Dockerfile for LyoBackend Phase 3
# Optimized for Google Cloud Run deployment with all Phase 3 features

# Use Python 3.9 slim as base image
FROM python:3.9-slim

# Set working directory
WORKDIR /app

# Set environment variables for production
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=off \
    PIP_DISABLE_PIP_VERSION_CHECK=on \
    PORT=8080 \
    PYTHONPATH=/app \
    ENVIRONMENT=production

# Create non-root user for security
RUN addgroup --system app && \
    adduser --system --ingroup app app

# Install system dependencies
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
    gcc \
    curl \
    postgresql-client \
    libpq-dev \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

# Install Google Cloud client libraries for monitoring and logging
RUN pip install --no-cache-dir \
    google-cloud-logging \
    google-cloud-trace \
    google-cloud-monitoring \
    opencensus-ext-stackdriver

# Copy cloud-optimized requirements first for better layer caching
COPY requirements-cloud.txt .

# Install Python dependencies using cloud-optimized requirements
RUN pip install --no-cache-dir -r requirements-cloud.txt

# Copy application code
COPY . .

# Make startup scripts executable
RUN chmod +x start_unified.py start_server.py start_cloud_run.sh

# Set proper permissions
RUN chown -R app:app /app

# Switch to non-root user
USER app

# Expose port
EXPOSE 8080

# Health check for Cloud Run - increased start period for complex app
HEALTHCHECK --interval=30s --timeout=30s --start-period=60s --retries=3 \
  CMD curl -f http://localhost:${PORT}/health || exit 1

# Start the application with enhanced_main (Cloud Run compatible)
CMD ["bash", "-c", "gunicorn lyo_app.enhanced_main:app --worker-class uvicorn.workers.UvicornWorker --bind 0.0.0.0:${PORT} --workers ${WORKERS:-1}"]
