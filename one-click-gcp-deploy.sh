#!/bin/bash

# One-Click Google Cloud Deployment for LyoBackend
# This script provides a complete, automated deployment solution
# 
# Usage: ./one-click-gcp-deploy.sh [OPTIONS] [PROJECT_ID] [REGION] [SERVICE_NAME]
#
# Options:
#   -h, --help     Show help message and exit
#   -v, --version  Show version information and exit
#
# Examples:
#   ./one-click-gcp-deploy.sh                                # Interactive mode
#   ./one-click-gcp-deploy.sh my-project                     # With project ID
#   ./one-click-gcp-deploy.sh my-project us-west1            # With project and region
#   ./one-click-gcp-deploy.sh my-project us-west1 my-backend # All parameters

set -euo pipefail

# Color codes for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
PURPLE='\033[0;35m'
NC='\033[0m' # No Color

# Configuration defaults
DEFAULT_REGION="us-central1"
DEFAULT_SERVICE_NAME="lyo-backend"

# Helper functions
log_info() { echo -e "${BLUE}ℹ️  $1${NC}"; }
log_success() { echo -e "${GREEN}✅ $1${NC}"; }
log_warning() { echo -e "${YELLOW}⚠️  $1${NC}"; }
log_error() { echo -e "${RED}❌ $1${NC}"; }
log_step() { echo -e "${PURPLE}🚀 $1${NC}"; }

# Banner
echo -e "${GREEN}"
cat << "EOF"
  ██╗  ██╗   ██╗ ██████╗     ██████╗  █████╗  ██████╗██╗  ██╗███████╗███╗   ██╗██████╗ 
  ██║  ╚██╗ ██╔╝██╔═══██╗    ██╔══██╗██╔══██╗██╔════╝██║ ██╔╝██╔════╝████╗  ██║██╔══██╗
  ██║   ╚████╔╝ ██║   ██║    ██████╔╝███████║██║     █████╔╝ █████╗  ██╔██╗ ██║██║  ██║
  ██║    ╚██╔╝  ██║   ██║    ██╔══██╗██╔══██║██║     ██╔═██╗ ██╔══╝  ██║╚██╗██║██║  ██║
  ███████╗██║   ╚██████╔╝    ██████╔╝██║  ██║╚██████╗██║  ██╗███████╗██║ ╚████║██████╔╝
  ╚══════╝╚═╝    ╚═════╝     ╚═════╝ ╚═╝  ╚═╝ ╚═════╝╚═╝  ╚═╝╚══════╝╚═╝  ╚═══╝╚═════╝ 
                                                                                          
  🚀 One-Click Google Cloud Deployment
EOF
echo -e "${NC}"

# Function to show help
show_help() {
    echo -e "${BLUE}Usage: $0 [OPTIONS] [PROJECT_ID] [REGION] [SERVICE_NAME]${NC}"
    echo ""
    echo "One-Click Google Cloud Deployment for LyoBackend"
    echo ""
    echo "OPTIONS:"
    echo "  -h, --help     Show this help message and exit"
    echo "  -v, --version  Show version information and exit"
    echo ""
    echo "ARGUMENTS:"
    echo "  PROJECT_ID     Google Cloud Project ID (required if not provided interactively)"
    echo "  REGION         Google Cloud region (default: ${DEFAULT_REGION})"
    echo "  SERVICE_NAME   Cloud Run service name (default: ${DEFAULT_SERVICE_NAME})"
    echo ""
    echo "EXAMPLES:"
    echo "  $0                                    # Interactive mode"
    echo "  $0 my-project                        # Specify project ID"
    echo "  $0 my-project us-west1               # Specify project and region"
    echo "  $0 my-project us-west1 my-backend    # Specify all parameters"
    echo ""
    echo "ENVIRONMENT VARIABLES:"
    echo "  SKIP_CONFIRM=true    Skip confirmation prompts"
    echo ""
}

# Function to show version
show_version() {
    echo -e "${GREEN}LyoBackend One-Click GCP Deploy v1.0.0${NC}"
    echo "Google Cloud Run deployment automation script"
}

# Parse command line arguments
while [[ $# -gt 0 ]]; do
    case $1 in
        -h|--help)
            show_help
            exit 0
            ;;
        -v|--version)
            show_version
            exit 0
            ;;
        -*)
            log_error "Unknown option $1"
            echo "Use $0 --help for usage information"
            exit 1
            ;;
        *)
            # Positional arguments
            if [[ -z "$PROJECT_ID" ]]; then
                PROJECT_ID="$1"
            elif [[ -z "$REGION_ARG" ]]; then
                REGION_ARG="$1"
            elif [[ -z "$SERVICE_NAME_ARG" ]]; then
                SERVICE_NAME_ARG="$1"
            else
                log_error "Too many arguments"
                echo "Use $0 --help for usage information"
                exit 1
            fi
            ;;
    esac
    shift
done

# Set defaults for region and service name
REGION=${REGION_ARG:-$DEFAULT_REGION}
SERVICE_NAME=${SERVICE_NAME_ARG:-$DEFAULT_SERVICE_NAME}

# Interactive configuration if not provided
if [[ -z "$PROJECT_ID" ]]; then
    echo -e "${BLUE}📋 Configuration Setup${NC}"
    echo "Please provide the required deployment configuration:"
    echo ""
    read -p "Enter your GCP Project ID: " PROJECT_ID
    if [[ -z "$REGION_ARG" ]]; then
        read -p "Enter your preferred region (default: ${DEFAULT_REGION}): " USER_REGION
        REGION=${USER_REGION:-$DEFAULT_REGION}
    fi
    if [[ -z "$SERVICE_NAME_ARG" ]]; then
        read -p "Enter service name (default: ${DEFAULT_SERVICE_NAME}): " USER_SERVICE_NAME
        SERVICE_NAME=${USER_SERVICE_NAME:-$DEFAULT_SERVICE_NAME}
    fi
fi

# Validate inputs
if [[ -z "$PROJECT_ID" ]]; then
    log_error "Project ID is required"
    echo "Use $0 --help for usage information"
    exit 1
fi

# Validate PROJECT_ID format (Google Cloud project IDs must be lowercase, 6-30 chars, letters/numbers/hyphens)
if [[ ! "$PROJECT_ID" =~ ^[a-z][a-z0-9-]{4,29}$ ]]; then
    log_warning "Project ID format may be invalid"
    log_info "Google Cloud Project IDs should be 6-30 characters, lowercase letters, numbers, and hyphens only"
    log_info "Must start with a letter"
    if [[ "${SKIP_CONFIRM:-}" != "true" ]]; then
        read -p "Continue anyway? (y/n): " -n 1 -r
        echo ""
        if [[ ! $REPLY =~ ^[Yy]$ ]]; then
            exit 1
        fi
    fi
fi

log_step "Configuration Summary"
echo "Project ID: $PROJECT_ID"
echo "Region: $REGION"
echo "Service Name: $SERVICE_NAME"
echo ""

if [[ "${SKIP_CONFIRM:-}" != "true" ]]; then
    read -p "Continue with deployment? (y/n): " -n 1 -r
    echo ""
    if [[ ! $REPLY =~ ^[Yy]$ ]]; then
        exit 1
    fi
fi

# Step 1: Prerequisites Check
log_step "Step 1: Checking Prerequisites"

# Check if gcloud is installed
if ! command -v gcloud &> /dev/null; then
    log_error "Google Cloud SDK is not installed"
    log_info "Installing Google Cloud SDK..."
    if [[ "$OSTYPE" == "darwin"* ]]; then
        # macOS
        if command -v brew &> /dev/null; then
            brew install --cask google-cloud-sdk
        else
            log_error "Homebrew not found. Please install Google Cloud SDK manually: https://cloud.google.com/sdk/docs/install"
            exit 1
        fi
    else
        # Linux
        curl https://sdk.cloud.google.com | bash
        source ~/.bashrc
    fi
fi

# Check if Docker is running
if ! docker info > /dev/null 2>&1; then
    log_error "Docker is not running. Please start Docker and try again."
    exit 1
fi

log_success "Prerequisites check complete"

# Step 2: Authentication and Project Setup
log_step "Step 2: Setting up Google Cloud Project"

# Set active project
gcloud config set project $PROJECT_ID || {
    log_error "Failed to set project. Please check if project exists and you have access."
    exit 1
}

# Check authentication
if ! gcloud auth list --filter=status:ACTIVE --format="value(account)" | head -1 > /dev/null 2>&1; then
    log_warning "Not authenticated with Google Cloud"
    gcloud auth login
fi

log_success "Google Cloud project configured"

# Step 3: Enable APIs
log_step "Step 3: Enabling required Google Cloud APIs"

# Enable all required APIs in one command
gcloud services enable \
    cloudbuild.googleapis.com \
    run.googleapis.com \
    containerregistry.googleapis.com \
    artifactregistry.googleapis.com \
    sqladmin.googleapis.com \
    secretmanager.googleapis.com \
    compute.googleapis.com \
    --quiet || {
    log_error "Failed to enable APIs. Please check permissions."
    exit 1
}

log_success "APIs enabled successfully"

# Step 4: Setup Artifact Registry
log_step "Step 4: Setting up Artifact Registry"

REPO_NAME="lyo-backend-repo"
gcloud artifacts repositories create $REPO_NAME \
    --repository-format=docker \
    --location=$REGION \
    --description="LyoBackend Docker images" \
    --quiet 2>/dev/null || log_info "Artifact Registry repository already exists"

# Configure Docker authentication
gcloud auth configure-docker ${REGION}-docker.pkg.dev --quiet

log_success "Artifact Registry configured"

# Step 5: Build and Push Docker Image
log_step "Step 5: Building and pushing Docker image"

IMAGE_URL="${REGION}-docker.pkg.dev/${PROJECT_ID}/${REPO_NAME}/${SERVICE_NAME}:latest"
log_info "Building image: $IMAGE_URL"

# Build using production Dockerfile
docker build -f Dockerfile.production -t $IMAGE_URL . || {
    log_error "Docker build failed"
    exit 1
}

log_info "Pushing image to registry..."
docker push $IMAGE_URL || {
    log_error "Docker push failed"
    exit 1
}

log_success "Docker image built and pushed"

# Step 6: Setup Secrets
log_step "Step 6: Setting up secrets in Secret Manager"

# Generate JWT secret
JWT_SECRET=$(openssl rand -base64 32)
echo -n "$JWT_SECRET" | gcloud secrets create jwt-secret --data-file=- --quiet 2>/dev/null || \
    echo -n "$JWT_SECRET" | gcloud secrets versions add jwt-secret --data-file=- --quiet

# Create database URL secret (placeholder for now)
DATABASE_URL="postgresql://postgres:changeme@localhost:5432/lyo_production"
echo -n "$DATABASE_URL" | gcloud secrets create database-url --data-file=- --quiet 2>/dev/null || \
    echo -n "$DATABASE_URL" | gcloud secrets versions add database-url --data-file=- --quiet

log_success "Secrets configured"

# Step 7: Create Service Account
log_step "Step 7: Creating service account and setting permissions"

SERVICE_ACCOUNT="${SERVICE_NAME}-sa@${PROJECT_ID}.iam.gserviceaccount.com"
gcloud iam service-accounts create ${SERVICE_NAME}-sa \
    --display-name="LyoBackend Service Account" \
    --quiet 2>/dev/null || log_info "Service account already exists"

# Grant required permissions
gcloud projects add-iam-policy-binding $PROJECT_ID \
    --member="serviceAccount:${SERVICE_ACCOUNT}" \
    --role="roles/cloudsql.client" \
    --quiet

gcloud projects add-iam-policy-binding $PROJECT_ID \
    --member="serviceAccount:${SERVICE_ACCOUNT}" \
    --role="roles/secretmanager.secretAccessor" \
    --quiet

log_success "Service account configured"

# Step 8: Deploy to Cloud Run
log_step "Step 8: Deploying to Google Cloud Run"

# Prepare environment variables
ENV_VARS="ENVIRONMENT=production,PORT=8080"

# Prepare secrets
SECRETS="DATABASE_URL=database-url:latest,JWT_SECRET_KEY=jwt-secret:latest"

# Deploy to Cloud Run
gcloud run deploy $SERVICE_NAME \
    --image=$IMAGE_URL \
    --platform=managed \
    --region=$REGION \
    --allow-unauthenticated \
    --service-account=$SERVICE_ACCOUNT \
    --set-env-vars="$ENV_VARS" \
    --set-secrets="$SECRETS" \
    --memory=2Gi \
    --cpu=2 \
    --timeout=300 \
    --max-instances=100 \
    --min-instances=0 \
    --port=8080 \
    --quiet || {
    log_error "Cloud Run deployment failed"
    exit 1
}

# Get service URL
SERVICE_URL=$(gcloud run services describe $SERVICE_NAME --region=$REGION --format="value(status.url)")

log_success "Deployment to Cloud Run complete!"

# Step 9: Test Deployment
log_step "Step 9: Testing deployment"

# Wait for service to be ready
sleep 10

# Test health endpoint
if curl -f "$SERVICE_URL/health" > /dev/null 2>&1; then
    log_success "Health check passed!"
else
    log_warning "Health check failed - service may still be starting up"
fi

# Step 10: Final Summary
log_step "Deployment Summary"
echo ""
echo -e "${GREEN}🎉 LyoBackend successfully deployed to Google Cloud Run!${NC}"
echo ""
echo -e "${YELLOW}📋 Deployment Details:${NC}"
echo "Project ID: $PROJECT_ID"
echo "Region: $REGION"
echo "Service Name: $SERVICE_NAME"
echo "Service URL: $SERVICE_URL"
echo "Image URL: $IMAGE_URL"
echo ""

echo -e "${YELLOW}🔗 Quick Links:${NC}"
echo -e "🌐 Service URL: ${GREEN}${SERVICE_URL}${NC}"
echo -e "📚 API Docs: ${GREEN}${SERVICE_URL}/docs${NC}"
echo -e "❤️ Health Check: ${GREEN}${SERVICE_URL}/health${NC}"
echo -e "📊 Cloud Console: ${GREEN}https://console.cloud.google.com/run/detail/${REGION}/${SERVICE_NAME}/metrics?project=${PROJECT_ID}${NC}"
echo ""

echo -e "${YELLOW}📌 Next Steps:${NC}"
echo "1. Set up your database (Cloud SQL PostgreSQL recommended)"
echo "2. Update the DATABASE_URL secret with your actual database connection"
echo "3. Configure your domain (optional)"
echo "4. Set up monitoring and alerts"
echo "5. Configure your mobile app to use: ${SERVICE_URL}"
echo ""

echo -e "${YELLOW}🛠️ Useful Commands:${NC}"
echo "View logs: gcloud run logs read --service=${SERVICE_NAME} --region=${REGION}"
echo "Update service: gcloud run deploy ${SERVICE_NAME} --image=${IMAGE_URL} --region=${REGION}"
echo "Delete service: gcloud run services delete ${SERVICE_NAME} --region=${REGION}"
echo ""

# Save deployment config
cat > deployment-config.txt << EOF
# LyoBackend Google Cloud Deployment Configuration
# Generated on: $(date)

PROJECT_ID=$PROJECT_ID
REGION=$REGION
SERVICE_NAME=$SERVICE_NAME
SERVICE_URL=$SERVICE_URL
IMAGE_URL=$IMAGE_URL
SERVICE_ACCOUNT=$SERVICE_ACCOUNT

# Quick Commands
# View logs: gcloud run logs read --service=$SERVICE_NAME --region=$REGION
# Update: gcloud run deploy $SERVICE_NAME --image=$IMAGE_URL --region=$REGION
# Delete: gcloud run services delete $SERVICE_NAME --region=$REGION
EOF

log_success "Deployment configuration saved to deployment-config.txt"
echo ""
echo -e "${GREEN}✨ Deployment complete! Your LyoBackend is now running on Google Cloud.${NC}"