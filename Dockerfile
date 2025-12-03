# Production-ready Dockerfile for LyoApp Backend
FROM python:3.11-slim as builder

# Install system dependencies
RUN apt-get update && apt-get install -y \
    build-essential \
    libpq-dev \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Create virtual environment
RUN python -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

# Copy requirements and install dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Production stage
FROM python:3.11-slim

# Install runtime dependencies
RUN apt-get update && apt-get install -y \
    libpq5 \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Create non-root user
RUN useradd --create-home --shell /bin/bash app

# Copy virtual environment
COPY --from=builder /opt/venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

# Set working directory
WORKDIR /app

# Set environment variables
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/app \
    PROMETHEUS_MULTIPROC_DIR=/tmp/prometheus_multiproc_dir

# Copy application code
COPY --chown=app:app . .

# Create uploads directory
RUN mkdir -p uploads/avatars uploads/documents uploads/temp && chown -R app:app uploads

# Switch to non-root user
USER app

# Health check (respect dynamic PORT; default to 8080)
HEALTHCHECK --interval=30s --timeout=30s --start-period=5s --retries=3 \
    CMD curl -f http://localhost:${PORT:-8080}/health || exit 1

# Expose Cloud Run default port (8080) but allow override via PORT env
ENV PORT=8080
EXPOSE 8080

# Start application (dynamic port)
CMD ["bash", "-c", "gunicorn lyo_app.enhanced_main:app --worker-class uvicorn.workers.UvicornWorker --bind 0.0.0.0:${PORT} --workers ${WORKERS:-4}"]
