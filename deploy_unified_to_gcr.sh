#!/bin/bash
# deploy_unified_to_gcr.sh - Deploy the unified architecture to Google Container Registry

set -e  # Exit immediately if a command exits with a non-zero status

# Print colored output
GREEN='\033[0;32m'
YELLOW='\033[0;33m'
RED='\033[0;31m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

echo -e "${BLUE}====================================================${NC}"
echo -e "${BLUE}  LyoBackend Unified Architecture GCR Deployment     ${NC}"
echo -e "${BLUE}====================================================${NC}"

# Validate environment
ENV=${1:-production}
if [[ "$ENV" != "production" && "$ENV" != "staging" && "$ENV" != "development" ]]; then
  echo -e "${RED}Error: Environment must be 'production', 'staging', or 'development'${NC}"
  echo -e "Usage: $0 [environment] [project-id]"
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

# Check if docker is installed
if ! command -v docker &> /dev/null; then
  echo -e "${RED}Error: Docker is not installed${NC}"
  echo -e "Please install Docker from https://docs.docker.com/get-docker/"
  exit 1
fi

echo -e "${YELLOW}Starting deployment to GCR for ${ENV} environment in project ${PROJECT_ID}...${NC}"

# Ensure PostgreSQL is used for production and staging
if [[ "$ENV" == "production" || "$ENV" == "staging" ]]; then
  if [[ -z "${DATABASE_URL}" || "${DATABASE_URL}" == *"sqlite"* ]]; then
    echo -e "${RED}Error: PostgreSQL database URL must be provided for ${ENV} environment${NC}"
    echo -e "Please set DATABASE_URL environment variable to a valid PostgreSQL URL"
    exit 1
  fi
  echo -e "${GREEN}✓ Valid PostgreSQL database URL confirmed${NC}"
fi

# Define image names and tags
IMAGE_NAME="lyobackend-unified"
IMAGE_TAG="${ENV}-$(date +%Y%m%d-%H%M%S)"
FULL_IMAGE_NAME="gcr.io/${PROJECT_ID}/${IMAGE_NAME}:${IMAGE_TAG}"
LATEST_TAG="gcr.io/${PROJECT_ID}/${IMAGE_NAME}:${ENV}-latest"

# Configure Docker to use gcloud as credential helper
echo -e "${YELLOW}Configuring Docker to use Google Cloud credentials...${NC}"
gcloud auth configure-docker --quiet

# Build the Docker image using our unified architecture Dockerfile
echo -e "${YELLOW}Building Docker image for unified architecture...${NC}"
docker build \
  --build-arg ENV=${ENV} \
  -t ${FULL_IMAGE_NAME} \
  -t ${LATEST_TAG} \
  -f Dockerfile.unified .

echo -e "${GREEN}✓ Docker image built: ${FULL_IMAGE_NAME}${NC}"

# Push the image to Google Container Registry
echo -e "${YELLOW}Pushing Docker image to Google Container Registry...${NC}"
docker push ${FULL_IMAGE_NAME}
docker push ${LATEST_TAG}

echo -e "${GREEN}✓ Image pushed to GCR: ${FULL_IMAGE_NAME}${NC}"
echo -e "${GREEN}✓ Image also tagged as: ${LATEST_TAG}${NC}"

# Optionally deploy to Cloud Run
if [ "$3" == "--deploy-to-cloud-run" ]; then
  SERVICE_NAME=${4:-"lyobackend-unified-${ENV}"}
  REGION=${5:-"us-central1"}
  
  echo -e "${YELLOW}Deploying to Cloud Run service ${SERVICE_NAME} in ${REGION}...${NC}"
  
  gcloud run deploy ${SERVICE_NAME} \
    --image ${FULL_IMAGE_NAME} \
    --platform managed \
    --region ${REGION} \
    --allow-unauthenticated \
    --set-env-vars="ENV=${ENV}" \
    --memory=1Gi \
    --cpu=1 \
    --port=8000
  
  echo -e "${GREEN}✓ Deployed to Cloud Run: ${SERVICE_NAME}${NC}"
  
  # Get the service URL
  SERVICE_URL=$(gcloud run services describe ${SERVICE_NAME} --platform managed --region ${REGION} --format="value(status.url)")
  echo -e "${GREEN}✓ Service URL: ${SERVICE_URL}${NC}"
fi

echo -e "${GREEN}=====================================${NC}"
echo -e "${GREEN}  GCR Deployment completed successfully!  ${NC}"
echo -e "${GREEN}=====================================${NC}"
echo -e ""
echo -e "${BLUE}Image details:${NC}"
echo -e "- Registry: gcr.io/${PROJECT_ID}"
echo -e "- Image: ${IMAGE_NAME}"
echo -e "- Tag: ${IMAGE_TAG}"
echo -e "- Environment: ${ENV}"
echo -e ""
echo -e "${BLUE}To pull this image:${NC}"
echo -e "docker pull ${FULL_IMAGE_NAME}"
echo -e ""
echo -e "${BLUE}To run this image locally:${NC}"
echo -e "docker run -p 8000:8000 -e ENV=${ENV} ${FULL_IMAGE_NAME}"
echo -e ""
if [ "$3" == "--deploy-to-cloud-run" ]; then
  echo -e "${BLUE}Cloud Run service:${NC}"
  echo -e "- Name: ${SERVICE_NAME}"
  echo -e "- Region: ${REGION}"
  echo -e "- URL: ${SERVICE_URL}"
  echo -e ""
  echo -e "${BLUE}To check the logs:${NC}"
  echo -e "gcloud logging read \"resource.type=cloud_run_revision AND resource.labels.service_name=${SERVICE_NAME}\""
fi
