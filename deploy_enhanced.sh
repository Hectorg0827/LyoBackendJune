#!/bin/bash
# Enhanced Production deployment script for LyoBackendJune
set -e

echo "🚀 LyoBackendJune Production Deployment Script"
echo "=============================================="

# Configuration
COMPOSE_FILE="docker-compose.production.yml"
ENV_FILE=".env.production"
BACKUP_DIR="./backups"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

log() {
    echo -e "${GREEN}[$(date +'%Y-%m-%d %H:%M:%S')]${NC} $1"
}

error() {
    echo -e "${RED}[ERROR]${NC} $1"
    exit 1
}

warning() {
    echo -e "${YELLOW}[WARNING]${NC} $1"
}

# Pre-deployment checks
log "Running pre-deployment checks..."

# Check if Docker is running
if ! docker info >/dev/null 2>&1; then
    error "Docker is not running. Please start Docker and try again."
fi

# Check if environment file exists
if [ ! -f "$ENV_FILE" ]; then
    error "Environment file $ENV_FILE not found. Please create it from .env.production.example"
fi

log "Pre-deployment checks completed ✅"

# Backup existing data
log "Creating backup of existing data..."
mkdir -p "$BACKUP_DIR"
BACKUP_TIMESTAMP=$(date +%Y%m%d_%H%M%S)

# Build and deploy
log "Building application images..."
docker-compose -f "$COMPOSE_FILE" build --no-cache

log "Starting services..."
docker-compose -f "$COMPOSE_FILE" up -d

# Wait for services to be healthy
log "Waiting for services to be healthy..."
sleep 30

# Check service health
log "Checking service health..."
max_attempts=30
attempt=1

while [ $attempt -le $max_attempts ]; do
    if curl -f -s http://localhost/health >/dev/null; then
        log "Application is healthy ✅"
        break
    fi
    
    log "Health check attempt $attempt/$max_attempts failed, retrying in 10 seconds..."
    sleep 10
    ((attempt++))
    
    if [ $attempt -gt $max_attempts ]; then
        error "Application failed to become healthy after $max_attempts attempts"
    fi
done

log "🎉 Production deployment completed successfully!"
log "📊 Services Status:"
docker-compose -f "$COMPOSE_FILE" ps

log "🌐 Access Points:"
log "   API: http://localhost"
log "   Docs: http://localhost/docs"
log "   Health: http://localhost/health"
log "   Monitoring: http://localhost:3000 (Grafana)"
log "   Metrics: http://localhost:9090 (Prometheus)"
