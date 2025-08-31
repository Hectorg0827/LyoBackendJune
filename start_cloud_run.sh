#!/bin/bash
# Cloud Run startup script for LyoBackend
# Ensures proper port configuration and error handling

set -e

# Set default PORT if not provided
export PORT=${PORT:-8080}
export HOST=${HOST:-0.0.0.0}
export WORKERS=${WORKERS:-1}
export FAST_STARTUP=${FAST_STARTUP:-true}

echo "🚀 Starting LyoBackend on ${HOST}:${PORT} with ${WORKERS} workers"
echo "📊 Fast startup: ${FAST_STARTUP}"

# Start with gunicorn for production
exec gunicorn lyo_app.enhanced_main:app \
    --worker-class uvicorn.workers.UvicornWorker \
    --bind "${HOST}:${PORT}" \
    --workers "${WORKERS}" \
    --timeout 120 \
    --keep-alive 2 \
    --max-requests 1000 \
    --max-requests-jitter 100 \
    --preload \
    --access-logfile - \
    --error-logfile -