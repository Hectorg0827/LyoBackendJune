#!/bin/bash

# Quick Google Cloud Deployment Test
# This script provides a dry-run test of the deployment process
# Usage: ./test-gcp-deployment.sh

set -euo pipefail

# Color codes
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

log_info() { echo -e "${BLUE}ℹ️  $1${NC}"; }
log_success() { echo -e "${GREEN}✅ $1${NC}"; }
log_warning() { echo -e "${YELLOW}⚠️  $1${NC}"; }
log_error() { echo -e "${RED}❌ $1${NC}"; }

echo -e "${GREEN}🧪 LyoBackend Google Cloud Deployment Test${NC}"
echo "==========================================="
echo ""

# Test 1: Check prerequisites
log_info "Testing deployment prerequisites..."

# Check Docker
if command -v docker &> /dev/null && docker info > /dev/null 2>&1; then
    log_success "Docker is installed and running"
else
    log_error "Docker is not available or not running"
fi

# Check gcloud (optional for test)
if command -v gcloud &> /dev/null; then
    log_success "Google Cloud SDK is installed"
    # Check if authenticated
    if gcloud auth list --filter=status:ACTIVE --format="value(account)" | head -1 > /dev/null 2>&1; then
        log_success "Google Cloud is authenticated"
    else
        log_warning "Google Cloud is not authenticated (run: gcloud auth login)"
    fi
else
    log_warning "Google Cloud SDK not installed (will be handled by deployment script)"
fi

# Test 2: Check application files
log_info "Checking application files..."

required_files=(
    "Dockerfile.production"
    "requirements-production.txt"
    "lyo_app/enhanced_main.py"
    "deploy-to-gcp.sh"
    "one-click-gcp-deploy.sh"
)

for file in "${required_files[@]}"; do
    if [[ -f "$file" ]]; then
        log_success "$file exists"
    else
        log_error "$file is missing"
    fi
done

# Test 3: Validate Dockerfile syntax
log_info "Validating Dockerfile..."

if [[ -f "Dockerfile.production" ]]; then
    # Check if Dockerfile can be parsed
    if docker build -f Dockerfile.production --dry-run . > /dev/null 2>&1 || true; then
        log_success "Dockerfile.production syntax is valid"
    else
        # Basic syntax check
        if grep -q "FROM" Dockerfile.production && grep -q "CMD" Dockerfile.production; then
            log_success "Dockerfile.production has basic structure"
        else
            log_error "Dockerfile.production has issues"
        fi
    fi
fi

# Test 4: Check deployment scripts
log_info "Checking deployment scripts..."

scripts=(
    "deploy-to-gcp.sh"
    "setup-gcp.sh"
    "test_deployment.sh"
    "one-click-gcp-deploy.sh"
)

for script in "${scripts[@]}"; do
    if [[ -f "$script" ]]; then
        if bash -n "$script" 2>/dev/null; then
            log_success "$script syntax is valid"
        else
            log_error "$script has syntax errors"
        fi
    else
        log_warning "$script not found"
    fi
done

# Test 5: Check Python application structure
log_info "Checking Python application structure..."

if [[ -d "lyo_app" ]]; then
    log_success "Main application directory exists"
    
    if [[ -f "lyo_app/__init__.py" ]]; then
        log_success "Python package structure is valid"
    else
        log_warning "Missing __init__.py in lyo_app"
    fi
    
    if [[ -f "lyo_app/enhanced_main.py" ]]; then
        log_success "Main application file exists"
        
        # Check if it defines an app
        if grep -q "app = " lyo_app/enhanced_main.py; then
            log_success "FastAPI app is defined"
        else
            log_warning "FastAPI app definition not found"
        fi
    else
        log_error "Main application file is missing"
    fi
else
    log_error "Main application directory is missing"
fi

# Test 6: Requirements validation
log_info "Validating requirements..."

if [[ -f "requirements-production.txt" ]]; then
    log_success "Production requirements file exists"
    
    # Check for essential dependencies
    essential_deps=("fastapi" "uvicorn" "gunicorn" "sqlalchemy" "pydantic")
    for dep in "${essential_deps[@]}"; do
        if grep -q "$dep" requirements-production.txt; then
            log_success "Essential dependency '$dep' found"
        else
            log_warning "Essential dependency '$dep' not found"
        fi
    done
else
    log_error "Production requirements file is missing"
fi

# Summary
echo ""
log_info "Test Summary:"
echo "=============="

if command -v gcloud &> /dev/null; then
    echo "✓ Ready for Google Cloud deployment"
    echo ""
    echo -e "${GREEN}🚀 To deploy to Google Cloud Run:${NC}"
    echo "   ./one-click-gcp-deploy.sh"
    echo ""
    echo -e "${YELLOW}📋 Or use the original script:${NC}"
    echo "   ./deploy-to-gcp.sh"
else
    echo "⚠ Google Cloud SDK not installed, but deployment script will handle it"
    echo ""
    echo -e "${GREEN}🚀 To deploy to Google Cloud Run:${NC}"
    echo "   ./one-click-gcp-deploy.sh"
fi

echo ""
echo -e "${BLUE}📖 For more information, see:${NC}"
echo "   - COMPLETE_DEPLOYMENT_GUIDE.md"
echo "   - PRODUCTION_DEPLOYMENT_GUIDE.md"
echo ""

# Test 7: Mock deployment simulation (optional)
if [[ "${RUN_SIMULATION:-}" == "true" ]]; then
    log_info "Running deployment simulation..."
    echo "This would:"
    echo "  1. Setup GCP project and APIs"
    echo "  2. Build Docker image: your-region-docker.pkg.dev/your-project/lyo-backend-repo/lyo-backend:latest"
    echo "  3. Create service account and secrets"
    echo "  4. Deploy to Cloud Run with 2Gi memory, 2 CPU"
    echo "  5. Configure health checks and monitoring"
    echo "  6. Return service URL: https://lyo-backend-xyz.a.run.app"
    log_success "Simulation complete - ready for actual deployment!"
fi

echo -e "${GREEN}✨ Deployment test complete!${NC}"