#!/usr/bin/env bash
set -euo pipefail

# LyoBackend Google Cloud Platform Setup Script
# This script automates the initial setup of your GCP project for deployment
#
# Usage:
#   ./setup_gcp.sh PROJECT_ID
#   PROJECT_ID=my-project ./setup_gcp.sh

PROJECT_ID=${1:-${PROJECT_ID:-}}
REGION=${REGION:-us-central1}
SERVICE_NAME=${SERVICE_NAME:-lyo-backend}
SERVICE_ACCOUNT_NAME="${SERVICE_NAME}-sa"
DB_INSTANCE_NAME="lyo-postgres"
DB_NAME="lyo_db"
DB_USER="lyo_user"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

log_info() { echo -e "${BLUE}ℹ️  $1${NC}"; }
log_success() { echo -e "${GREEN}✅ $1${NC}"; }
log_warning() { echo -e "${YELLOW}⚠️  $1${NC}"; }
log_error() { echo -e "${RED}❌ $1${NC}"; exit 1; }

if [[ -z "${PROJECT_ID}" ]]; then
  log_error "PROJECT_ID not set. Usage: ./setup_gcp.sh PROJECT_ID"
fi

log_info "Setting up Google Cloud Project: ${PROJECT_ID}"

# Set active project
gcloud config set project "${PROJECT_ID}"

# Enable required APIs
log_info "Enabling required Google Cloud APIs..."
gcloud services enable \
    run.googleapis.com \
    cloudbuild.googleapis.com \
    containerregistry.googleapis.com \
    sqladmin.googleapis.com \
    secretmanager.googleapis.com \
    vertexai.googleapis.com \
    aiplatform.googleapis.com

log_success "APIs enabled successfully"

# Create service account
log_info "Creating service account: ${SERVICE_ACCOUNT_NAME}"
if gcloud iam service-accounts describe "${SERVICE_ACCOUNT_NAME}@${PROJECT_ID}.iam.gserviceaccount.com" --quiet >/dev/null 2>&1; then
    log_warning "Service account already exists"
else
    gcloud iam service-accounts create "${SERVICE_ACCOUNT_NAME}" \
        --display-name="LyoBackend Service Account" \
        --description="Service account for LyoBackend Cloud Run deployment"
    log_success "Service account created"
fi

# Grant necessary permissions
log_info "Granting IAM permissions..."
PERMISSIONS=(
    "roles/aiplatform.user"
    "roles/secretmanager.secretAccessor" 
    "roles/cloudsql.client"
    "roles/logging.logWriter"
    "roles/monitoring.metricWriter"
    "roles/cloudtrace.agent"
)

for role in "${PERMISSIONS[@]}"; do
    gcloud projects add-iam-policy-binding "${PROJECT_ID}" \
        --member="serviceAccount:${SERVICE_ACCOUNT_NAME}@${PROJECT_ID}.iam.gserviceaccount.com" \
        --role="${role}" \
        --quiet
done

log_success "IAM permissions granted"

# Create Cloud SQL instance
log_info "Creating Cloud SQL PostgreSQL instance..."
if gcloud sql instances describe "${DB_INSTANCE_NAME}" --quiet >/dev/null 2>&1; then
    log_warning "Cloud SQL instance already exists"
else
    # Generate secure database passwords
    DB_ROOT_PASSWORD=$(python3 -c "import secrets, string; print(''.join(secrets.choice(string.ascii_letters + string.digits) for _ in range(24)))")
    DB_USER_PASSWORD=$(python3 -c "import secrets, string; print(''.join(secrets.choice(string.ascii_letters + string.digits) for _ in range(24)))")
    
    gcloud sql instances create "${DB_INSTANCE_NAME}" \
        --database-version=POSTGRES_15 \
        --tier=db-g1-small \
        --region="${REGION}" \
        --storage-type=SSD \
        --storage-size=20GB \
        --storage-auto-increase \
        --backup \
        --maintenance-release-channel=production \
        --maintenance-window-day=SUN \
        --maintenance-window-hour=02 \
        --deletion-protection
    
    log_success "Cloud SQL instance created"
    
    # Set root password
    gcloud sql users set-password root \
        --instance="${DB_INSTANCE_NAME}" \
        --password="${DB_ROOT_PASSWORD}"
    
    # Create application database
    gcloud sql databases create "${DB_NAME}" --instance="${DB_INSTANCE_NAME}"
    
    # Create application user
    gcloud sql users create "${DB_USER}" \
        --instance="${DB_INSTANCE_NAME}" \
        --password="${DB_USER_PASSWORD}"
    
    # Store database credentials in Secret Manager
    echo -n "${DB_USER_PASSWORD}" | gcloud secrets create db-user-password --data-file=-
    echo -n "${DB_ROOT_PASSWORD}" | gcloud secrets create db-root-password --data-file=-
    
    log_success "Database and credentials configured"
fi

# Prompt for API keys and store in Secret Manager
log_info "Setting up API keys in Secret Manager..."

# Function to create secret if it doesn't exist
create_secret_if_not_exists() {
    local secret_name=$1
    local prompt_message=$2
    
    if gcloud secrets describe "${secret_name}" --quiet >/dev/null 2>&1; then
        log_warning "Secret '${secret_name}' already exists"
    else
        echo
        echo -e "${YELLOW}${prompt_message}${NC}"
        read -s -p "Enter the key: " api_key
        echo
        
        if [[ -n "${api_key}" && "${api_key}" != "skip" ]]; then
            echo -n "${api_key}" | gcloud secrets create "${secret_name}" --data-file=-
            log_success "Secret '${secret_name}' created"
        else
            log_warning "Skipped creating '${secret_name}' - you can create it later"
        fi
    fi
}

# Create application secret key
if ! gcloud secrets describe "secret-key" --quiet >/dev/null 2>&1; then
    SECRET_KEY=$(python3 -c "import secrets; print(secrets.token_urlsafe(32))")
    echo -n "${SECRET_KEY}" | gcloud secrets create secret-key --data-file=-
    log_success "Application secret key generated and stored"
fi

# OpenAI API Key
create_secret_if_not_exists "openai-api-key" "Please enter your OpenAI API key (or 'skip' to skip):"

# Gemini API Key  
create_secret_if_not_exists "gemini-api-key" "Please enter your Google Gemini API key (or 'skip' to skip):"

# Optional: YouTube API Key
create_secret_if_not_exists "youtube-api-key" "Please enter your YouTube API key (optional, or 'skip' to skip):"

log_success "Setup completed successfully!"

echo
echo "==================== SETUP SUMMARY ===================="
echo "Project ID: ${PROJECT_ID}"
echo "Region: ${REGION}"  
echo "Service Account: ${SERVICE_ACCOUNT_NAME}@${PROJECT_ID}.iam.gserviceaccount.com"
echo "Cloud SQL Instance: ${DB_INSTANCE_NAME}"
echo "Database: ${DB_NAME}"
echo "Database User: ${DB_USER}"
echo
echo "Connection Name: $(gcloud sql instances describe ${DB_INSTANCE_NAME} --format='value(connectionName)')"
echo
echo "==================== NEXT STEPS ========================"
echo "1. Your GCP project is now configured!"
echo "2. Deploy your application:"
echo "   ./deploy_cloudrun.sh ${PROJECT_ID}"
echo "3. Test your deployment:"
echo "   curl https://SERVICE_URL/health"
echo "4. View logs:"
echo "   gcloud logging read 'resource.type=cloud_run_revision'"
echo "========================================================="
