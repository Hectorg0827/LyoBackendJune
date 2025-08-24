#!/bin/bash

set -e

# Color codes for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

echo -e "${GREEN}🚀 LyoBackend Google Cloud Run Deployment Script${NC}"
echo "================================================"

# Check if gcloud is installed
if ! command -v gcloud &> /dev/null; then
    echo -e "${RED}❌ gcloud CLI is not installed${NC}"
    echo "Please run ./setup-gcp.sh first to install Google Cloud SDK"
    exit 1
fi

# Check if Docker is running
if ! docker info > /dev/null 2>&1; then
    echo -e "${RED}❌ Docker is not running${NC}"
    echo "Please start Docker and try again"
    exit 1
fi

# Configuration
echo -e "${BLUE}📋 Configuration Setup${NC}"
read -p "Enter your GCP Project ID: " PROJECT_ID
read -p "Enter your preferred region (e.g., us-central1): " REGION
read -p "Enter service name (default: lyo-backend): " SERVICE_NAME
SERVICE_NAME=${SERVICE_NAME:-lyo-backend}

echo -e "\n${YELLOW}📋 Configuration Summary:${NC}"
echo "Project ID: $PROJECT_ID"
echo "Region: $REGION"
echo "Service Name: $SERVICE_NAME"
echo ""
read -p "Continue with deployment? (y/n): " -n 1 -r
echo ""
if [[ ! $REPLY =~ ^[Yy]$ ]]; then
    exit 1
fi

# Set project
echo -e "\n${GREEN}1️⃣ Setting up GCP project...${NC}"
gcloud config set project $PROJECT_ID

# Enable required APIs
echo -e "\n${GREEN}2️⃣ Enabling required APIs...${NC}"
echo "This may take a few minutes..."
gcloud services enable \
    cloudbuild.googleapis.com \
    run.googleapis.com \
    containerregistry.googleapis.com \
    sqladmin.googleapis.com \
    secretmanager.googleapis.com \
    artifactregistry.googleapis.com \
    --quiet

# Create Artifact Registry repository if it doesn't exist
echo -e "\n${GREEN}3️⃣ Creating Artifact Registry repository...${NC}"
gcloud artifacts repositories create lyo-backend-repo \
    --repository-format=docker \
    --location=$REGION \
    --description="Lyo Backend Docker images" \
    --quiet 2>/dev/null || echo "Repository already exists"

# Configure Docker authentication
echo -e "\n${GREEN}4️⃣ Configuring Docker authentication...${NC}"
gcloud auth configure-docker ${REGION}-docker.pkg.dev --quiet

# Build and push Docker image
IMAGE_URL="${REGION}-docker.pkg.dev/${PROJECT_ID}/lyo-backend-repo/${SERVICE_NAME}:latest"
echo -e "\n${GREEN}5️⃣ Building Docker image...${NC}"
echo "Building: $IMAGE_URL"
docker build -f Dockerfile.production -t $IMAGE_URL .

echo -e "\n${GREEN}6️⃣ Pushing Docker image to registry...${NC}"
docker push $IMAGE_URL

# Create Cloud SQL instance (if needed)
echo -e "\n${GREEN}7️⃣ Setting up Cloud SQL PostgreSQL...${NC}"
read -p "Do you want to create a new Cloud SQL instance? (y/n): " -n 1 -r
echo ""
if [[ $REPLY =~ ^[Yy]$ ]]; then
    INSTANCE_NAME="${SERVICE_NAME}-db"
    echo "Creating Cloud SQL instance: $INSTANCE_NAME"
    gcloud sql instances create $INSTANCE_NAME \
        --database-version=POSTGRES_14 \
        --tier=db-f1-micro \
        --region=$REGION \
        --network=default \
        --no-backup \
        --quiet
    
    # Create database
    echo "Creating database: lyo_production"
    gcloud sql databases create lyo_production --instance=$INSTANCE_NAME --quiet
    
    # Set password for postgres user
    echo -e "\n${YELLOW}🔐 Database Password Setup${NC}"
    read -s -p "Enter password for database (min 8 characters): " DB_PASSWORD
    echo ""
    gcloud sql users set-password postgres \
        --instance=$INSTANCE_NAME \
        --password=$DB_PASSWORD \
        --quiet
    
    # Get connection string
    CONNECTION_NAME=$(gcloud sql instances describe $INSTANCE_NAME --format="value(connectionName)")
    DATABASE_URL="postgresql://postgres:${DB_PASSWORD}@/lyo_production?host=/cloudsql/${CONNECTION_NAME}"
else
    read -p "Enter your existing DATABASE_URL: " DATABASE_URL
fi

# Create secrets
echo -e "\n${GREEN}8️⃣ Creating secrets in Secret Manager...${NC}"

# Database URL secret
echo -n "$DATABASE_URL" | gcloud secrets create database-url --data-file=- --quiet 2>/dev/null || \
    echo -n "$DATABASE_URL" | gcloud secrets versions add database-url --data-file=- --quiet

# Generate JWT secret if not exists
JWT_SECRET=$(openssl rand -base64 32)
echo -n "$JWT_SECRET" | gcloud secrets create jwt-secret --data-file=- --quiet 2>/dev/null || \
    echo -n "$JWT_SECRET" | gcloud secrets versions add jwt-secret --data-file=- --quiet

# Redis URL (optional)
echo -e "\n${YELLOW}📝 Redis Configuration (Optional)${NC}"
echo "Redis options:"
echo "1. Use Redis Labs free tier (recommended): https://redis.com/try-free/"
echo "2. Use Google Memorystore (paid)"
echo "3. Skip Redis (caching features will be disabled)"
read -p "Enter Redis URL (or press Enter to skip): " REDIS_URL

if [ ! -z "$REDIS_URL" ]; then
    echo -n "$REDIS_URL" | gcloud secrets create redis-url --data-file=- --quiet 2>/dev/null || \
        echo -n "$REDIS_URL" | gcloud secrets versions add redis-url --data-file=- --quiet
fi

# Create service account
echo -e "\n${GREEN}9️⃣ Creating service account...${NC}"
SERVICE_ACCOUNT="${SERVICE_NAME}-sa@${PROJECT_ID}.iam.gserviceaccount.com"
gcloud iam service-accounts create ${SERVICE_NAME}-sa \
    --display-name="Lyo Backend Service Account" \
    --quiet 2>/dev/null || echo "Service account already exists"

# Grant permissions
echo "Granting permissions..."
gcloud projects add-iam-policy-binding $PROJECT_ID \
    --member="serviceAccount:${SERVICE_ACCOUNT}" \
    --role="roles/cloudsql.client" \
    --quiet

gcloud projects add-iam-policy-binding $PROJECT_ID \
    --member="serviceAccount:${SERVICE_ACCOUNT}" \
    --role="roles/secretmanager.secretAccessor" \
    --quiet

# Deploy to Cloud Run
echo -e "\n${GREEN}🚀 Deploying to Cloud Run...${NC}"

# Prepare environment variables
ENV_VARS="ENVIRONMENT=production,MODEL_ID=google/gemma-2b-it,PORT=8080"

# Prepare secrets
SECRETS="DATABASE_URL=database-url:latest,JWT_SECRET_KEY=jwt-secret:latest"
if [ ! -z "$REDIS_URL" ]; then
    SECRETS="${SECRETS},REDIS_URL=redis-url:latest"
fi

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
    --quiet

# Get service URL
SERVICE_URL=$(gcloud run services describe $SERVICE_NAME --region=$REGION --format="value(status.url)")

echo -e "\n${GREEN}✅ Deployment Complete!${NC}"
echo "================================"
echo -e "🌐 Service URL: ${GREEN}${SERVICE_URL}${NC}"
echo -e "📚 API Docs: ${GREEN}${SERVICE_URL}/docs${NC}"
echo -e "❤️ Health Check: ${GREEN}${SERVICE_URL}/health${NC}"
echo -e "🤖 AI Test: ${GREEN}${SERVICE_URL}/api/v1/test-ai${NC}"
echo ""

echo -e "${YELLOW}📌 Next Steps:${NC}"
echo "1. Test your deployment:"
echo "   curl ${SERVICE_URL}/health"
echo ""
echo "2. View logs:"
echo "   gcloud run logs read --service=$SERVICE_NAME --region=$REGION"
echo ""
echo "3. Monitor your service:"
echo "   ./monitor_deployment.py $SERVICE_NAME $REGION"
echo ""
echo "4. Run comprehensive tests:"
echo "   ./test_cloud_deployment.py ${SERVICE_URL}"
echo ""
echo "5. Update your mobile app to use:"
echo "   ${SERVICE_URL}"

echo -e "\n${GREEN}🎉 Your LyoBackend is now live on Google Cloud Run!${NC}"

# Save configuration for future use
cat > deployment-config.txt << EOF
Project ID: $PROJECT_ID
Region: $REGION
Service Name: $SERVICE_NAME
Service URL: $SERVICE_URL
Image URL: $IMAGE_URL
Deployed: $(date)
EOF

echo -e "\n${BLUE}📝 Configuration saved to deployment-config.txt${NC}"
