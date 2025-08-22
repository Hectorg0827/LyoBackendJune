#!/usr/bin/env bash
set -euo pipefail

# Enhanced LyoBackend deployment script for Google Cloud Run
# Features:
#  - Secret Manager integration
#  - Cloud SQL connector
#  - Production-ready configuration
#  - Comprehensive error handling
#
# Requirements:
#  - gcloud CLI authenticated (gcloud auth login)
#  - PROJECT_ID exported or passed as first arg  
#  - Service account created with proper permissions
#  - Secrets stored in Secret Manager
#
# Usage:
#   PROJECT_ID=my-project REGION=us-central1 ./deploy_cloudrun.sh
#   ./deploy_cloudrun.sh my-project

PROJECT_ID=${1:-${PROJECT_ID:-}}
REGION=${REGION:-us-central1}
SERVICE=${SERVICE:-lyo-backend}
SERVICE_ACCOUNT_NAME=${SERVICE_ACCOUNT_NAME:-${SERVICE}-sa}
PORT=${PORT:-8080}
CPU=${CPU:-1}
MEMORY=${MEMORY:-1Gi}
CONCURRENCY=${CONCURRENCY:-80}
TIMEOUT=${TIMEOUT:-600}
MIN_INSTANCES=${MIN_INSTANCES:-0}
MAX_INSTANCES=${MAX_INSTANCES:-10}
PLATFORM=${PLATFORM:-managed}

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Helper functions
log_info() {
    echo -e "${BLUE}ℹ️  $1${NC}"
}

log_success() {
    echo -e "${GREEN}✅ $1${NC}"
}

log_warning() {
    echo -e "${YELLOW}⚠️  $1${NC}"
}

log_error() {
    echo -e "${RED}❌ $1${NC}"
    exit 1
}

if [[ -z "${PROJECT_ID}" ]]; then
  log_error "PROJECT_ID not set. Provide as env var or first argument."
fi

log_info "Starting deployment of '${SERVICE}' to project '${PROJECT_ID}' region '${REGION}'"

# Set active project
gcloud config set project "${PROJECT_ID}" --quiet

# Verify service account exists
if ! gcloud iam service-accounts describe "${SERVICE_ACCOUNT_NAME}@${PROJECT_ID}.iam.gserviceaccount.com" --quiet >/dev/null 2>&1; then
    log_error "Service account ${SERVICE_ACCOUNT_NAME}@${PROJECT_ID}.iam.gserviceaccount.com not found. Please create it first."
fi

# Get Cloud SQL connection name (if exists)
CONNECTION_NAME=""
if gcloud sql instances describe lyo-postgres --quiet >/dev/null 2>&1; then
    CONNECTION_NAME=$(gcloud sql instances describe lyo-postgres --format="value(connectionName)")
    log_info "Found Cloud SQL instance: ${CONNECTION_NAME}"
else
    log_warning "No Cloud SQL instance named 'lyo-postgres' found. Skipping SQL connector."
fi

# Verify required secrets exist
REQUIRED_SECRETS=("secret-key" "openai-api-key" "gemini-api-key")
for secret in "${REQUIRED_SECRETS[@]}"; do
    if ! gcloud secrets describe "${secret}" --quiet >/dev/null 2>&1; then
        log_warning "Secret '${secret}' not found. Please create it or deployment may fail."
    fi
done

log_info "Building and deploying to Cloud Run..."

# Build deployment command
DEPLOY_CMD="gcloud run deploy ${SERVICE}"
DEPLOY_CMD+=" --source ."
DEPLOY_CMD+=" --region ${REGION}"
DEPLOY_CMD+=" --platform ${PLATFORM}"
DEPLOY_CMD+=" --port ${PORT}"
DEPLOY_CMD+=" --allow-unauthenticated"
DEPLOY_CMD+=" --cpu ${CPU}"
DEPLOY_CMD+=" --memory ${MEMORY}"
DEPLOY_CMD+=" --concurrency ${CONCURRENCY}"
DEPLOY_CMD+=" --timeout ${TIMEOUT}"
DEPLOY_CMD+=" --min-instances ${MIN_INSTANCES}"
DEPLOY_CMD+=" --max-instances ${MAX_INSTANCES}"
DEPLOY_CMD+=" --service-account ${SERVICE_ACCOUNT_NAME}@${PROJECT_ID}.iam.gserviceaccount.com"

# Environment variables
DEPLOY_CMD+=" --set-env-vars ENVIRONMENT=production"
DEPLOY_CMD+=" --set-env-vars GCP_PROJECT_ID=${PROJECT_ID}"
DEPLOY_CMD+=" --set-env-vars PYTHONUNBUFFERED=1"
DEPLOY_CMD+=" --set-env-vars PORT=${PORT}"

# Secrets from Secret Manager
DEPLOY_CMD+=" --set-secrets SECRET_KEY=secret-key:latest"
DEPLOY_CMD+=" --set-secrets OPENAI_API_KEY=openai-api-key:latest"
DEPLOY_CMD+=" --set-secrets GEMINI_API_KEY=gemini-api-key:latest"

# Add Cloud SQL connector if available
if [[ -n "${CONNECTION_NAME}" ]]; then
    DEPLOY_CMD+=" --add-cloudsql-instances ${CONNECTION_NAME}"
    log_info "Adding Cloud SQL connector for: ${CONNECTION_NAME}"
fi

# Execute deployment
log_info "Executing deployment command..."
if eval $DEPLOY_CMD; then
    log_success "Deployment completed successfully!"
    
    # Get service URL
    SERVICE_URL=$(gcloud run services describe "${SERVICE}" \
        --platform managed \
        --region "${REGION}" \
        --format "value(status.url)")
    
    log_success "Service deployed at: ${SERVICE_URL}"
    log_info "API Documentation: ${SERVICE_URL}/docs"
    log_info "Health Check: ${SERVICE_URL}/health"
    log_info "Console: https://console.cloud.google.com/run/detail/${REGION}/${SERVICE}/metrics?project=${PROJECT_ID}"
    
    # Test health endpoint
    log_info "Testing health endpoint..."
    if curl -s -f "${SERVICE_URL}/health" >/dev/null; then
        log_success "Health check passed! Service is running correctly."
    else
        log_warning "Health check failed. Service may still be starting up."
    fi
    
else
    log_error "Deployment failed! Check the error messages above."
fi

log_info "🎉 Deployment process completed!"
echo
log_info "Next steps:"
echo "  1. Test your API endpoints"
echo "  2. Set up monitoring and alerting" 
echo "  3. Configure custom domain (optional)"
echo "  4. Set up CI/CD pipeline"
