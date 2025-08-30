#!/bin/bash
# Enable Google Cloud APIs for Phase 3 Deployment
# This script enables all required APIs for GKE and related services

set -e

PROJECT_ID=${1:-lyobackend}

echo "🔧 Enabling Google Cloud APIs for Phase 3 Deployment..."
echo "Project: $PROJECT_ID"
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

# Check if gcloud is authenticated
check_auth() {
    log_info "Checking gcloud authentication..."

    if ! gcloud auth list --filter=status:ACTIVE --format="value(account)" | head -n 1 > /dev/null; then
        log_error "Not authenticated with gcloud. Please run:"
        echo "  gcloud auth login"
        exit 1
    fi

    log_success "Authenticated with gcloud"
}

# Set project
set_project() {
    log_info "Setting project to $PROJECT_ID..."

    if ! gcloud config set project $PROJECT_ID; then
        log_error "Failed to set project. Please check if project exists and you have access."
        exit 1
    fi

    log_success "Project set to $PROJECT_ID"
}

# Enable required APIs
enable_apis() {
    log_info "Enabling required Google Cloud APIs..."

    # List of required APIs for Phase 3 deployment
    local apis=(
        "container.googleapis.com"          # Kubernetes Engine API
        "containerregistry.googleapis.com"  # Container Registry API
        "cloudbuild.googleapis.com"         # Cloud Build API
        "run.googleapis.com"               # Cloud Run API
        "monitoring.googleapis.com"        # Cloud Monitoring API
        "logging.googleapis.com"           # Cloud Logging API
        "compute.googleapis.com"           # Compute Engine API
        "servicenetworking.googleapis.com" # Service Networking API
        "cloudresourcemanager.googleapis.com" # Resource Manager API
    )

    for api in "${apis[@]}"; do
        log_info "Enabling $api..."
        if gcloud services enable $api --quiet; then
            log_success "✅ $api enabled"
        else
            log_warning "⚠️ Failed to enable $api (might already be enabled)"
        fi
    done

    log_success "All APIs enabled successfully"
}

# Wait for APIs to propagate
wait_for_apis() {
    log_info "Waiting for APIs to propagate (this may take a few minutes)..."

    # Wait for Kubernetes Engine API specifically
    local max_attempts=30
    local attempt=1

    while [ $attempt -le $max_attempts ]; do
        log_info "Checking API status (attempt $attempt/$max_attempts)..."

        if gcloud services list --enabled --filter="container.googleapis.com" --format="value(name)" | grep -q "container.googleapis.com"; then
            log_success "✅ Kubernetes Engine API is ready"
            return 0
        fi

        log_info "Waiting 10 seconds before next check..."
        sleep 10
        ((attempt++))
    done

    log_warning "⚠️ API propagation may still be in progress"
    log_info "You can continue with deployment, but it might fail if APIs aren't fully ready"
}

# Verify APIs are enabled
verify_apis() {
    log_info "Verifying API status..."

    echo ""
    echo "📋 Enabled APIs:"
    gcloud services list --enabled --filter="container.googleapis.com OR cloudbuild.googleapis.com OR run.googleapis.com" --format="table(name,displayName)"

    echo ""
    log_success "API verification complete"
}

# Main function
main() {
    log_info "Starting Google Cloud API setup for Phase 3"

    check_auth
    set_project
    enable_apis
    wait_for_apis
    verify_apis

    echo ""
    log_success "🎉 Google Cloud APIs are ready for Phase 3 deployment!"
    echo ""
    echo "🚀 You can now run your Phase 3 deployment:"
    echo "  ./minimal-phase3-deploy.sh lyo $PROJECT_ID lyo-backend-cluster us-central1"
    echo ""
    echo "📖 Alternative: If you prefer not to use GKE, try:"
    echo "  ./minimal-deploy.sh $PROJECT_ID"
    echo "  (This deploys to Cloud Run instead of GKE)"
}

# Run main function
main "$@"
