# Production-ready Dockerfile for LyoApp Backend - STABILIZED
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
    PYTHONPATH=/app

# --- CACHE BUSTER START ---
# This forces Railway to re-copy all files even if it thinks nothing changed
RUN echo "Fresh Build Triggered at: $(date)" > /build_timestamp.txt
# --- CACHE BUSTER END ---

# Copy application code
COPY --chown=app:app . .

# Health check (very generous start period)
HEALTHCHECK --interval=10s --timeout=5s --start-period=60s --retries=5 \
    CMD curl -f http://localhost:${PORT:-8080}/health || exit 1

# Create uploads directory
RUN mkdir -p uploads/avatars uploads/documents uploads/temp && chown -R app:app uploads

# Switch to non-root user
USER app

# Start application using the STABILIZED bootloader
CMD ["bash", "-c", "uvicorn lyo_app.STABILIZED_MAIN:app --host 0.0.0.0 --port ${PORT:-8080} --proxy-headers"]
