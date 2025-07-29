#!/bin/bash
# LyoApp Backend Production Deployment Script

set -e  # Exit on any error

echo "🚀 Starting LyoApp Backend Production Deployment"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Function to print colored output
print_status() {
    echo -e "${BLUE}[INFO]${NC} $1"
}

print_success() {
    echo -e "${GREEN}[SUCCESS]${NC} $1"
}

print_warning() {
    echo -e "${YELLOW}[WARNING]${NC} $1"
}

print_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

# Check if Docker is installed
if ! command -v docker &> /dev/null; then
    print_error "Docker is not installed. Please install Docker first."
    exit 1
fi

# Check if Docker Compose is installed
if ! command -v docker-compose &> /dev/null; then
    print_error "Docker Compose is not installed. Please install Docker Compose first."
    exit 1
fi

# Check if .env file exists
if [ ! -f .env ]; then
    print_warning ".env file not found. Creating from template..."
    if [ -f .env.template ]; then
        cp .env.template .env
        print_warning "Please edit .env file with your actual configuration values before continuing."
        print_warning "Required: SECRET_KEY, POSTGRES_PASSWORD, API keys, etc."
        exit 1
    else
        print_error ".env.template not found. Cannot create .env file."
        exit 1
    fi
fi

# Source environment variables
source .env

# Validate required environment variables
print_status "Validating environment configuration..."

required_vars=("SECRET_KEY" "POSTGRES_PASSWORD")
missing_vars=()

for var in "${required_vars[@]}"; do
    if [ -z "${!var}" ]; then
        missing_vars+=("$var")
    fi
done

if [ ${#missing_vars[@]} -gt 0 ]; then
    print_error "Missing required environment variables:"
    printf '%s\n' "${missing_vars[@]}"
    exit 1
fi

# Check if SECRET_KEY is secure enough
if [ ${#SECRET_KEY} -lt 32 ]; then
    print_error "SECRET_KEY must be at least 32 characters long for production."
    exit 1
fi

print_success "Environment validation passed"

# Create necessary directories
print_status "Creating necessary directories..."
mkdir -p uploads/avatars uploads/documents uploads/temp
mkdir -p logs
mkdir -p nginx/ssl

# Build and deploy
print_status "Building Docker images..."
docker-compose -f docker-compose.production.yml build --no-cache

print_status "Starting services..."
docker-compose -f docker-compose.production.yml up -d

# Wait for services to be ready
print_status "Waiting for services to be ready..."
sleep 30

# Check service health
print_status "Checking service health..."

# Check if API is responding
if curl -f http://localhost:8000/health &> /dev/null; then
    print_success "API service is healthy"
else
    print_error "API service is not responding"
    print_status "Checking logs..."
    docker-compose -f docker-compose.production.yml logs api
    exit 1
fi

# Check if database is ready
if docker-compose -f docker-compose.production.yml exec -T postgres pg_isready -U postgres &> /dev/null; then
    print_success "Database service is healthy"
else
    print_error "Database service is not ready"
    exit 1
fi

# Check if Redis is ready
if docker-compose -f docker-compose.production.yml exec -T redis redis-cli ping &> /dev/null; then
    print_success "Redis service is healthy"
else
    print_error "Redis service is not ready"
    exit 1
fi

# Run database migrations
print_status "Running database migrations..."
docker-compose -f docker-compose.production.yml exec -T api alembic upgrade head

# Check if Nginx is ready (if enabled)
if docker-compose -f docker-compose.production.yml ps nginx &> /dev/null; then
    if curl -f http://localhost/health &> /dev/null; then
        print_success "Nginx reverse proxy is healthy"
    else
        print_warning "Nginx is running but health check failed"
    fi
fi

print_success "🎉 LyoApp Backend deployment completed successfully!"

echo
echo "📊 Service Status:"
docker-compose -f docker-compose.production.yml ps

echo
echo "🔗 Available Endpoints:"
echo "  • API Documentation: http://localhost:8000/docs"
echo "  • Health Check: http://localhost:8000/health"
echo "  • API Base: http://localhost:8000/api/v1"
echo "  • Admin Interface: http://localhost:8000/admin"

if docker-compose -f docker-compose.production.yml ps grafana &> /dev/null; then
    echo "  • Grafana Dashboard: http://localhost:3000 (admin/your-grafana-password)"
fi

if docker-compose -f docker-compose.production.yml ps prometheus &> /dev/null; then
    echo "  • Prometheus Metrics: http://localhost:9090"
fi

echo
echo "📝 Next Steps:"
echo "  1. Configure your domain and SSL certificates"
echo "  2. Set up proper firewall rules"
echo "  3. Configure monitoring alerts"
echo "  4. Set up automated backups"
echo "  5. Test all API endpoints with your iOS app"

echo
echo "🔧 Management Commands:"
echo "  • View logs: docker-compose -f docker-compose.production.yml logs -f"
echo "  • Restart services: docker-compose -f docker-compose.production.yml restart"
echo "  • Stop services: docker-compose -f docker-compose.production.yml down"
echo "  • Update deployment: ./deploy-production.sh"
