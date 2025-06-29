#!/bin/bash
"""
Production Deployment Script for LyoApp AI Backend
==================================================

This script sets up the production environment for the LyoApp AI backend
with Gemma 4 and multi-language support.
"""

set -e

echo "🚀 LyoApp AI Backend Production Deployment"
echo "=========================================="

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Function to print colored output
print_status() {
    echo -e "${GREEN}[INFO]${NC} $1"
}

print_warning() {
    echo -e "${YELLOW}[WARN]${NC} $1"
}

print_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

print_step() {
    echo -e "${BLUE}[STEP]${NC} $1"
}

# Check if running as root
if [[ $EUID -eq 0 ]]; then
   print_error "This script should not be run as root"
   exit 1
fi

# Step 1: Check prerequisites
print_step "1. Checking prerequisites..."

# Check Python version
if ! command -v python3 &> /dev/null; then
    print_error "Python 3 is required but not installed"
    exit 1
fi

PYTHON_VERSION=$(python3 -c 'import sys; print(".".join(map(str, sys.version_info[:2])))')
if [[ $(echo "$PYTHON_VERSION < 3.9" | bc -l) -eq 1 ]]; then
    print_error "Python 3.9 or higher is required. Current version: $PYTHON_VERSION"
    exit 1
fi

print_status "Python version: $PYTHON_VERSION ✓"

# Check PostgreSQL
if ! command -v psql &> /dev/null; then
    print_warning "PostgreSQL client not found. Install postgresql-client if needed."
fi

# Check Redis
if ! command -v redis-cli &> /dev/null; then
    print_warning "Redis CLI not found. Install redis-tools if needed."
fi

# Step 2: Create production environment
print_step "2. Setting up production environment..."

# Create virtual environment if it doesn't exist
if [ ! -d ".venv" ]; then
    print_status "Creating virtual environment..."
    python3 -m venv .venv
fi

# Activate virtual environment
source .venv/bin/activate
print_status "Virtual environment activated ✓"

# Step 3: Install dependencies
print_step "3. Installing production dependencies..."

# Upgrade pip
pip install --upgrade pip

# Install dependencies
print_status "Installing Python packages..."
pip install -r requirements.txt

print_status "All dependencies installed ✓"

# Step 4: Set up environment variables
print_step "4. Configuring environment variables..."

if [ ! -f ".env" ]; then
    if [ -f ".env.production" ]; then
        cp .env.production .env
        print_status "Copied .env.production to .env"
    else
        print_error ".env.production file not found"
        exit 1
    fi
fi

# Check critical environment variables
print_status "Checking environment configuration..."

# Source the environment file
set -a
source .env
set +a

# Check database URL
if [ -z "$DATABASE_URL" ]; then
    print_error "DATABASE_URL not set in environment"
    exit 1
fi

# Check Redis URL
if [ -z "$REDIS_URL" ]; then
    print_error "REDIS_URL not set in environment"
    exit 1
fi

print_status "Environment configuration ✓"

# Step 5: Database setup
print_step "5. Setting up database..."

# Run database migrations
print_status "Running database migrations..."
alembic upgrade head

print_status "Database setup complete ✓"

# Step 6: AI Model setup
print_step "6. Setting up AI models..."

# Create models directory if it doesn't exist
mkdir -p models

# Check if Gemma 4 model path exists
if [ ! -z "$GEMMA_4_MODEL_PATH" ] && [ ! -d "$GEMMA_4_MODEL_PATH" ]; then
    print_warning "Gemma 4 model path not found: $GEMMA_4_MODEL_PATH"
    print_status "Creating model directory..."
    mkdir -p "$GEMMA_4_MODEL_PATH"
    
    print_warning "Please download the Gemma 4 model files to: $GEMMA_4_MODEL_PATH"
    print_status "You can continue with cloud-only mode for now."
fi

# Validate API keys (without exposing them)
if [ ! -z "$OPENAI_API_KEY" ] && [ ${#OPENAI_API_KEY} -gt 10 ]; then
    print_status "OpenAI API key configured ✓"
else
    print_warning "OpenAI API key not configured or invalid"
fi

if [ ! -z "$ANTHROPIC_API_KEY" ] && [ ${#ANTHROPIC_API_KEY} -gt 10 ]; then
    print_status "Anthropic API key configured ✓"
else
    print_warning "Anthropic API key not configured or invalid"
fi

if [ ! -z "$GEMMA_4_API_KEY" ] && [ ${#GEMMA_4_API_KEY} -gt 10 ]; then
    print_status "Gemma 4 Cloud API key configured ✓"
else
    print_warning "Gemma 4 Cloud API key not configured or invalid"
fi

# Step 7: Test the setup
print_step "7. Testing the setup..."

# Test AI orchestrator initialization
print_status "Testing AI orchestrator..."
python -c "
import asyncio
import sys
sys.path.insert(0, '.')

async def test_orchestrator():
    try:
        from lyo_app.ai_agents.orchestrator import ai_orchestrator
        success = await ai_orchestrator.initialize()
        if success:
            print('AI Orchestrator initialization: SUCCESS')
        else:
            print('AI Orchestrator initialization: PARTIAL (some models unavailable)')
        return True
    except Exception as e:
        print(f'AI Orchestrator initialization: FAILED - {e}')
        return False

result = asyncio.run(test_orchestrator())
exit(0 if result else 1)
" || {
    print_error "AI orchestrator test failed"
    exit 1
}

print_status "AI system test passed ✓"

# Step 8: Create systemd service (optional)
print_step "8. Creating systemd service..."

cat > lyoapp.service << EOF
[Unit]
Description=LyoApp AI Backend
After=network.target postgresql.service redis.service

[Service]
Type=exec
User=$USER
WorkingDirectory=$(pwd)
Environment=PATH=$(pwd)/.venv/bin
ExecStart=$(pwd)/.venv/bin/gunicorn lyo_app.main:app -c gunicorn.conf.py
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
EOF

print_status "Systemd service file created: lyoapp.service"
print_status "To install: sudo cp lyoapp.service /etc/systemd/system/"
print_status "To enable: sudo systemctl enable lyoapp"
print_status "To start: sudo systemctl start lyoapp"

# Step 9: Create gunicorn configuration
print_step "9. Creating production server configuration..."

cat > gunicorn.conf.py << 'EOF'
"""
Gunicorn configuration for production deployment
"""

import multiprocessing
import os

# Server socket
bind = "0.0.0.0:8000"
backlog = 2048

# Worker processes
workers = min(multiprocessing.cpu_count() * 2 + 1, 8)
worker_class = "uvicorn.workers.UvicornWorker"
worker_connections = 1000
timeout = 30
keepalive = 2

# Restart workers after this many requests, to help prevent memory leaks
max_requests = 1000
max_requests_jitter = 100

# Logging
accesslog = "-"
errorlog = "-"
loglevel = "info"
access_log_format = '%(h)s %(l)s %(u)s %(t)s "%(r)s" %(s)s %(b)s "%(f)s" "%(a)s" %(D)s'

# Process naming
proc_name = "lyoapp-backend"

# Preload app for better memory usage
preload_app = True

# Enable prometheus metrics
def when_ready(server):
    from prometheus_client import multiprocess
    from prometheus_client import generate_latest
    from prometheus_client import CollectorRegistry
    
    # Clear metrics before starting
    multiprocess.MultiProcessCollector(CollectorRegistry(), path=os.environ.get('PROMETHEUS_MULTIPROC_DIR', '/tmp'))

def child_exit(server, worker):
    from prometheus_client import multiprocess
    multiprocess.mark_process_dead(worker.pid)
EOF

print_status "Gunicorn configuration created ✓"

# Step 10: Final instructions
print_step "10. Deployment complete!"

echo ""
echo "🎉 LyoApp AI Backend is ready for production!"
echo ""
echo "Next steps:"
echo "1. Review and update .env file with your production values"
echo "2. Download Gemma 4 model files (optional for cloud-only setup)"
echo "3. Install systemd service: sudo cp lyoapp.service /etc/systemd/system/"
echo "4. Start the service: sudo systemctl start lyoapp"
echo ""
echo "🔧 Manual testing:"
echo "  Start development server: .venv/bin/python -m uvicorn lyo_app.main:app --host 0.0.0.0 --port 8000"
echo "  Health check: curl http://localhost:8000/health"
echo "  AI health check: curl http://localhost:8000/api/v1/ai/health"
echo ""
echo "📊 Monitoring endpoints:"
echo "  Health: /health"
echo "  AI Health: /api/v1/ai/health"
echo "  Metrics: /metrics"
echo "  Documentation: /docs"
echo ""
echo "🔐 Security reminders:"
echo "  - Change SECRET_KEY in production"
echo "  - Use strong database passwords"
echo "  - Configure proper CORS origins"
echo "  - Set up SSL/TLS"
echo "  - Configure rate limiting"
echo ""
echo "For more information, see the documentation at /docs"
echo ""
print_status "Deployment script completed successfully! 🚀"
