#!/bin/bash
# Local Phase 3 Test Deployment
# Test Phase 3 features locally without cloud deployment

set -e

echo "🏠 Local Phase 3 Test Deployment"
echo "==============================="
echo ""

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

log_info() {
    echo -e "${BLUE}[INFO]${NC} $1"
}

log_success() {
    echo -e "${GREEN}[SUCCESS]${NC} $1"
}

log_warning() {
    echo -e "${YELLOW}[WARNING]${NC} $1"
}

log_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

# Check if virtual environment is active
check_venv() {
    log_info "Checking Python virtual environment..."

    if [[ "$VIRTUAL_ENV" != "" ]]; then
        log_success "Virtual environment is active: $VIRTUAL_ENV"
    else
        log_warning "No virtual environment detected"
        log_info "Consider activating your virtual environment:"
        echo "  source .venv/bin/activate"
    fi
}

# Install/update dependencies
install_deps() {
    log_info "Installing/updating dependencies..."

    if [ -f "requirements.txt" ]; then
        pip install -r requirements.txt
        log_success "Dependencies installed"
    else
        log_error "requirements.txt not found"
        exit 1
    fi
}

# Set up environment variables for Phase 3
setup_env() {
    log_info "Setting up Phase 3 environment variables..."

    export ENVIRONMENT=development
    export OTEL_TRACES_EXPORTER=console
    export OTEL_SERVICE_NAME=lyo-backend-local
    export PYTHONPATH=/Users/republicalatuya/Desktop/LyoBackendJune
    export PORT=8000

    log_success "Environment variables set"
}

# Start the application with Phase 3 features
start_app() {
    log_info "Starting LyoBackend with Phase 3 features..."

    echo ""
    echo "🚀 Starting server on http://localhost:8000"
    echo ""
    echo "📋 Phase 3 Features Active:"
    echo "• ✅ Distributed Tracing (console output)"
    echo "• ✅ AI Optimization Engine"
    echo "• ✅ Performance Monitoring"
    echo "• ✅ Database Optimization"
    echo "• ✅ API Optimization"
    echo ""
    echo "🧪 Test endpoints:"
    echo "• Health: http://localhost:8000/health"
    echo "• Optimization Health: http://localhost:8000/health/optimization"
    echo "• API Docs: http://localhost:8000/docs"
    echo ""
    echo "⚡ Press Ctrl+C to stop the server"
    echo ""

    # Start the server
    python start_unified.py --host 0.0.0.0 --port 8000
}

# Main function
main() {
    log_info "Starting local Phase 3 deployment"

    check_venv
    install_deps
    setup_env
    start_app
}

# Show usage if requested
if [ "$1" = "--help" ] || [ "$1" = "-h" ]; then
    echo "Local Phase 3 Test Deployment"
    echo ""
    echo "This script starts LyoBackend locally with all Phase 3 features enabled:"
    echo "• Distributed Tracing"
    echo "• AI Optimization Engine"
    echo "• Performance Monitoring"
    echo "• Database Optimization"
    echo "• API Optimization"
    echo ""
    echo "Usage:"
    echo "  $0              # Start the server"
    echo "  $0 --help       # Show this help"
    echo ""
    echo "The server will be available at: http://localhost:8000"
    echo "Health check: http://localhost:8000/health"
    echo "API docs: http://localhost:8000/docs"
    exit 0
fi

# Run main function
main "$@"
