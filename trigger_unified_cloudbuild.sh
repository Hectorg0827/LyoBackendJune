#!/bin/bash
# trigger_unified_cloudbuild.sh - Trigger a Cloud Build for the unified architecture

set -e  # Exit immediately if a command exits with a non-zero status

# Print colored output
GREEN='\033[0;32m'
YELLOW='\033[0;33m'
RED='\033[0;31m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

echo -e "${BLUE}====================================================${NC}"
echo -e "${BLUE}  LyoBackend Unified Architecture Cloud Build       ${NC}"
echo -e "${BLUE}====================================================${NC}"

# Validate environment
ENV=${1:-production}
if [[ "$ENV" != "production" && "$ENV" != "staging" && "$ENV" != "development" ]]; then
  echo -e "${RED}Error: Environment must be 'production', 'staging', or 'development'${NC}"
  echo -e "Usage: $0 [environment] [project-id] [deploy-to-cloud-run] [service-name] [region]"
  exit 1
fi

# Get Google Cloud project ID
PROJECT_ID=${2:-$(gcloud config get-value project 2>/dev/null)}
if [[ -z "$PROJECT_ID" ]]; then
  echo -e "${RED}Error: No Google Cloud project ID provided or configured${NC}"
  echo -e "Please provide a project ID as the second argument or set it with 'gcloud config set project YOUR_PROJECT_ID'"
  exit 1
fi

# Check if gcloud is installed
if ! command -v gcloud &> /dev/null; then
  echo -e "${RED}Error: gcloud CLI is not installed${NC}"
  echo -e "Please install the Google Cloud SDK from https://cloud.google.com/sdk/docs/install"
  exit 1
fi

# Determine if we should deploy to Cloud Run
DEPLOY_TO_CLOUD_RUN=${3:-false}
SERVICE_NAME=${4:-"lyobackend-unified-$ENV"}
REGION=${5:-"us-central1"}

echo -e "${YELLOW}Starting Cloud Build for unified architecture in ${ENV} environment...${NC}"
echo -e "${YELLOW}Project ID: ${PROJECT_ID}${NC}"
if [[ "$DEPLOY_TO_CLOUD_RUN" == "true" ]]; then
  echo -e "${YELLOW}Will deploy to Cloud Run service: ${SERVICE_NAME} in ${REGION}${NC}"
else
  echo -e "${YELLOW}Will not deploy to Cloud Run (use 'true' as third parameter to enable)${NC}"
fi

# Ensure PostgreSQL is used for production and staging
if [[ "$ENV" == "production" || "$ENV" == "staging" ]]; then
  if [[ -z "${DATABASE_URL}" || "${DATABASE_URL}" == *"sqlite"* ]]; then
    echo -e "${RED}Error: PostgreSQL database URL must be provided for ${ENV} environment${NC}"
    echo -e "Please set DATABASE_URL environment variable to a valid PostgreSQL URL"
    exit 1
  fi
  echo -e "${GREEN}✓ Valid PostgreSQL database URL confirmed${NC}"
fi

# Trigger Cloud Build
echo -e "${YELLOW}Triggering Cloud Build...${NC}"
gcloud builds submit \
  --config=cloudbuild.unified.yaml \
  --substitutions=_ENV="$ENV",_DEPLOY_TO_CLOUD_RUN="$DEPLOY_TO_CLOUD_RUN",_SERVICE_NAME="$SERVICE_NAME",_REGION="$REGION" \
  .

echo -e "${GREEN}=====================================${NC}"
echo -e "${GREEN}  Cloud Build triggered successfully!  ${NC}"
echo -e "${GREEN}=====================================${NC}"
echo -e ""
echo -e "${BLUE}Build details:${NC}"
echo -e "- Project: ${PROJECT_ID}"
echo -e "- Environment: ${ENV}"
echo -e "- Config: cloudbuild.unified.yaml"
echo -e ""
if [ "$DEPLOY_TO_CLOUD_RUN" == "true" ]; then
  echo -e "${BLUE}Cloud Run target:${NC}"
  echo -e "- Service: ${SERVICE_NAME}"
  echo -e "- Region: ${REGION}"
  echo -e ""
  echo -e "${BLUE}To check deployment status:${NC}"
  echo -e "gcloud run services describe ${SERVICE_NAME} --region ${REGION} --project ${PROJECT_ID}"
fi
echo -e ""
echo -e "${BLUE}To view build logs:${NC}"
echo -e "gcloud builds list --project ${PROJECT_ID}"
echo -e "gcloud builds log [BUILD_ID] --project ${PROJECT_ID}"
