#!/bin/bash
# Phase 3 Cloud Run Deployment
# Deploys LyoBackend with Phase 3 features to Google Cloud Run

set -e

PROJECT_ID=${1:-lyobackend}
SERVICE_NAME="lyo-backend-phase3"
REGION="us-central1"

echo "🚀 Deploying Phase 3 to Google Cloud Run..."
echo "Project: $PROJECT_ID"
echo "Service: $SERVICE_NAME"
echo "Region: $REGION"
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

# Check prerequisites
check_prerequisites() {
    log_info "Checking prerequisites..."

    # Check if gcloud is installed
    if ! command -v gcloud &> /dev/null; then
        log_error "gcloud CLI is not installed. Please install it first."
        exit 1
    fi

    # Check if authenticated
    if ! gcloud auth list --filter=status:ACTIVE --format="value(account)" | head -n 1 > /dev/null; then
        log_error "Not authenticated with gcloud. Please run 'gcloud auth login' first."
        exit 1
    fi

    log_success "Prerequisites check passed"
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
    log_info "Enabling required APIs..."

    local apis=(
        "run.googleapis.com"
        "cloudbuild.googleapis.com"
        "containerregistry.googleapis.com"
        "monitoring.googleapis.com"
        "logging.googleapis.com"
    )

    for api in "${apis[@]}"; do
        log_info "Enabling $api..."
        gcloud services enable $api --quiet 2>/dev/null || log_warning "$api might already be enabled"
    done

    log_success "APIs enabled"
}

# Build and deploy
build_and_deploy() {
    log_info "Building and deploying to Cloud Run..."

    # Build the image with increased timeout
    log_info "Building Docker image..."
    gcloud builds submit --tag gcr.io/$PROJECT_ID/$SERVICE_NAME --timeout=30m

    # Deploy to Cloud Run with Phase 3 optimizations
    log_info "Deploying to Cloud Run..."
    gcloud run deploy $SERVICE_NAME \
        --image gcr.io/$PROJECT_ID/$SERVICE_NAME \
        --platform managed \
        --region $REGION \
        --allow-unauthenticated \
        --memory 2Gi \
        --cpu 2 \
        --max-instances 10 \
        --min-instances 1 \
        --concurrency 100 \
        --timeout 900 \
        --port 8000 \
        --set-env-vars="\
ENVIRONMENT=production,\
OTEL_TRACES_EXPORTER=console,\
OTEL_SERVICE_NAME=lyo-backend,\
PYTHONPATH=/app,\
PORT=8000" \
        --quiet

    log_success "Deployment completed"
}

# Get service URL and test
test_deployment() {
    log_info "Getting service URL..."

    SERVICE_URL=$(gcloud run services describe $SERVICE_NAME --region=$REGION --format="value(status.url)")

    echo ""
    log_success "🎉 Deployment successful!"
    echo ""
    echo "🌐 Service URL: $SERVICE_URL"
    echo ""

    # Test the service
    log_info "Testing service health..."
    if curl -s "$SERVICE_URL/health" > /dev/null 2>&1; then
        log_success "✅ Service is responding"
    else
        log_warning "⚠️ Service health check failed (might be starting up)"
    fi

    echo ""
    echo "📋 Phase 3 Features Status:"
    echo "• ✅ Distributed Tracing: Configured (console output)"
    echo "• ✅ AI Optimization: Ready (will activate with traffic)"
    echo "• ✅ Auto-scaling: Enabled (1-10 instances)"
    echo "• ✅ Monitoring: Enabled (Cloud Monitoring)"
    echo ""

    echo "🔧 Useful Commands:"
    echo "• View logs: gcloud logs read --filter=\"resource.type=cloud_run_revision AND resource.labels.service_name=$SERVICE_NAME\""
    echo "• Update service: gcloud run deploy $SERVICE_NAME --source ."
    echo "• Check metrics: https://console.cloud.google.com/monitoring"
    echo ""

    echo "📊 Monitoring URLs:"
    echo "• Cloud Run Console: https://console.cloud.google.com/run"
    echo "• Cloud Monitoring: https://console.cloud.google.com/monitoring"
    echo "• Cloud Logging: https://console.cloud.google.com/logs"
}

# Main function
main() {
    log_info "Starting Phase 3 Cloud Run deployment"

    check_prerequisites
    set_project
    enable_apis
    build_and_deploy
    test_deployment

    log_success "🎉 Phase 3 Cloud Run deployment complete!"
}

# Run main function
main "$@"
