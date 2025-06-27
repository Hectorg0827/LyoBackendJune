#!/bin/bash
"""
Production deployment script for LyoApp Backend.
Handles database migration, application deployment, and health checks.
"""

set -e  # Exit on any error

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Configuration
APP_NAME="lyoapp-backend"
IMAGE_NAME="ghcr.io/lyoapp/lyoapp-backend"
ENVIRONMENT=${ENVIRONMENT:-production}

echo -e "${GREEN}🚀 Starting LyoApp Backend Deployment${NC}"
echo "Environment: $ENVIRONMENT"

# Check prerequisites
echo -e "${YELLOW}📋 Checking prerequisites...${NC}"

if ! command -v docker &> /dev/null; then
    echo -e "${RED}❌ Docker is not installed${NC}"
    exit 1
fi

if ! command -v docker-compose &> /dev/null; then
    echo -e "${RED}❌ Docker Compose is not installed${NC}"
    exit 1
fi

echo -e "${GREEN}✅ Prerequisites check passed${NC}"

# Load environment variables
if [ -f ".env.${ENVIRONMENT}" ]; then
    echo -e "${YELLOW}🔧 Loading environment variables from .env.${ENVIRONMENT}${NC}"
    export $(cat .env.${ENVIRONMENT} | grep -v '^#' | xargs)
else
    echo -e "${RED}❌ Environment file .env.${ENVIRONMENT} not found${NC}"
    exit 1
fi

# Create necessary directories
echo -e "${YELLOW}📁 Creating directories...${NC}"
mkdir -p uploads/avatars uploads/documents uploads/temp
mkdir -p logs backups

# Pull latest images
echo -e "${YELLOW}🐳 Pulling latest Docker images...${NC}"
docker-compose pull

# Stop existing containers
echo -e "${YELLOW}🛑 Stopping existing containers...${NC}"
docker-compose down || true

# Database migration
echo -e "${YELLOW}🗄️ Running database migrations...${NC}"
docker-compose run --rm api alembic upgrade head

# Start services
echo -e "${YELLOW}🚀 Starting services...${NC}"
docker-compose up -d

# Wait for services to be ready
echo -e "${YELLOW}⏳ Waiting for services to be ready...${NC}"
sleep 30

# Health checks
echo -e "${YELLOW}🏥 Running health checks...${NC}"

# Check API health
if curl -f -s http://localhost:8000/health > /dev/null; then
    echo -e "${GREEN}✅ API health check passed${NC}"
else
    echo -e "${RED}❌ API health check failed${NC}"
    docker-compose logs api
    exit 1
fi

# Check database connection
if curl -f -s http://localhost:8000/api/v1/health/readiness > /dev/null; then
    echo -e "${GREEN}✅ Database connection check passed${NC}"
else
    echo -e "${RED}❌ Database connection check failed${NC}"
    docker-compose logs db
    exit 1
fi

# Check Redis connection (if configured)
if [ -n "$REDIS_URL" ]; then
    if docker-compose exec -T redis redis-cli ping > /dev/null; then
        echo -e "${GREEN}✅ Redis connection check passed${NC}"
    else
        echo -e "${YELLOW}⚠️ Redis connection check failed${NC}"
    fi
fi

# Performance test
echo -e "${YELLOW}🔥 Running basic performance test...${NC}"
if command -v ab &> /dev/null; then
    ab -n 10 -c 2 http://localhost:8000/health || echo -e "${YELLOW}⚠️ Performance test failed${NC}"
else
    echo -e "${YELLOW}⚠️ Apache Bench not available, skipping performance test${NC}"
fi

# Cleanup old images
echo -e "${YELLOW}🧹 Cleaning up old Docker images...${NC}"
docker image prune -f || true

echo -e "${GREEN}🎉 Deployment completed successfully!${NC}"
echo ""
echo "Services:"
echo "🌐 API: http://localhost:8000"
echo "📖 Documentation: http://localhost:8000/docs"
echo "🏥 Health: http://localhost:8000/health"
echo ""
echo "Logs:"
echo "📝 View API logs: docker-compose logs -f api"
echo "📝 View all logs: docker-compose logs -f"
echo ""
echo "Management:"
echo "🛑 Stop services: docker-compose down"
echo "🔄 Restart: docker-compose restart"
echo "📊 Status: docker-compose ps"
