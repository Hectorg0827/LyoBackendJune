#!/bin/bash
# Quick Phase 3 Setup and Deployment
# Automated setup for Phase 3 deployment

set -e

PROJECT_ID=${1:-lyobackend}

echo "🚀 Quick Phase 3 Setup and Deployment"
echo "====================================="
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

# Step 1: Enable APIs
enable_apis() {
    echo ""
    log_info "Step 1: Enabling Google Cloud APIs..."

    ./enable-apis.sh $PROJECT_ID

    echo ""
    log_success "✅ APIs enabled successfully"
}

# Step 2: Deploy to Cloud Run
deploy_cloudrun() {
    echo ""
    log_info "Step 2: Deploying to Cloud Run..."

    ./deploy-phase3-cloudrun.sh $PROJECT_ID

    echo ""
    log_success "✅ Cloud Run deployment complete"
}

# Step 3: Show status
show_status() {
    echo ""
    log_info "Step 3: Deployment Status"

    echo ""
    echo "🎉 Phase 3 Deployment Complete!"
    echo ""
    echo "📋 What you now have:"
    echo "• ✅ LyoBackend with Phase 3 features"
    echo "• ✅ Distributed Tracing (console output)"
    echo "• ✅ AI-powered optimization ready"
    echo "• ✅ Auto-scaling (1-10 instances)"
    echo "• ✅ Cloud Monitoring integration"
    echo "• ✅ Production-ready deployment"
    echo ""

    # Get service URL
    SERVICE_URL=$(gcloud run services describe lyo-backend-phase3 --region=us-central1 --format="value(status.url)" 2>/dev/null || echo "")

    if [ -n "$SERVICE_URL" ]; then
        echo "🌐 Service URL: $SERVICE_URL"
        echo ""
        echo "🧪 Test commands:"
        echo "  curl $SERVICE_URL/health"
        echo "  curl $SERVICE_URL/docs"
        echo ""
    fi

    echo "🔧 Management commands:"
    echo "  gcloud run services list"
    echo "  gcloud logs read --filter='resource.type=cloud_run_revision'"
    echo "  gcloud run services update lyo-backend-phase3 --memory=4Gi"
    echo ""

    echo "📊 Monitoring:"
    echo "  https://console.cloud.google.com/run"
    echo "  https://console.cloud.google.com/monitoring"
    echo "  https://console.cloud.google.com/logs"
    echo ""

    echo "💡 Next Steps:"
    echo "1. Test your API endpoints"
    echo "2. Monitor performance in Cloud Console"
    echo "3. Scale up if needed: gcloud run services update lyo-backend-phase3 --max-instances=50"
    echo "4. Set up custom domain if desired"
}

# Main function
main() {
    log_info "Starting Quick Phase 3 Setup"

    # Check if user wants to skip API enabling
    if [ "${2:-}" = "--skip-apis" ]; then
        log_info "Skipping API enabling (using --skip-apis)"
    else
        enable_apis
    fi

    deploy_cloudrun
    show_status

    log_success "🎉 Quick Phase 3 setup complete!"
}

# Show usage if no arguments
if [ $# -eq 0 ]; then
    echo "Usage: $0 <project-id> [--skip-apis]"
    echo ""
    echo "Examples:"
    echo "  $0 lyobackend                    # Full setup with API enabling"
    echo "  $0 lyobackend --skip-apis        # Skip API enabling if already done"
    echo ""
    echo "This script will:"
    echo "1. Enable required Google Cloud APIs"
    echo "2. Deploy LyoBackend with Phase 3 features to Cloud Run"
    echo "3. Show deployment status and useful commands"
    echo ""
    exit 1
fi

# Run main function
main "$@"
