# 🚀 AWS Deployment Script for LyoBackendJune

#!/bin/bash

set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

echo -e "${BLUE}🚀 AWS Deployment for LyoBackendJune${NC}"
echo ""

# Configuration
PROJECT_NAME="lyobackend"
ENVIRONMENT=${1:-production}
AWS_REGION=${2:-us-east-1}
DB_PASSWORD=${3:-$(openssl rand -base64 32)}

# Validate prerequisites
echo -e "${YELLOW}🔍 Checking prerequisites...${NC}"

# Check if AWS CLI is installed
if ! command -v aws &> /dev/null; then
    echo -e "${RED}❌ AWS CLI is not installed${NC}"
    echo "Please install AWS CLI: https://aws.amazon.com/cli/"
    exit 1
fi

# Check if Terraform is installed
if ! command -v terraform &> /dev/null; then
    echo -e "${RED}❌ Terraform is not installed${NC}"
    echo "Please install Terraform: https://terraform.io/"
    exit 1
fi

# Check if Docker is installed
if ! command -v docker &> /dev/null; then
    echo -e "${RED}❌ Docker is not installed${NC}"
    echo "Please install Docker: https://docker.com/"
    exit 1
fi

# Check AWS credentials
if ! aws sts get-caller-identity &> /dev/null; then
    echo -e "${RED}❌ AWS credentials not configured${NC}"
    echo "Please run: aws configure"
    exit 1
fi

echo -e "${GREEN}✅ Prerequisites check passed${NC}"

# Get AWS account ID
AWS_ACCOUNT_ID=$(aws sts get-caller-identity --query Account --output text)
echo -e "${BLUE}📋 AWS Account ID: ${AWS_ACCOUNT_ID}${NC}"
echo -e "${BLUE}📋 Region: ${AWS_REGION}${NC}"
echo -e "${BLUE}📋 Environment: ${ENVIRONMENT}${NC}"

# Initialize Terraform
echo -e "${YELLOW}🏗️ Initializing Terraform...${NC}"
cd infrastructure/aws
terraform init

# Plan Terraform deployment
echo -e "${YELLOW}📋 Planning Terraform deployment...${NC}"
terraform plan \
  -var="project_name=${PROJECT_NAME}" \
  -var="environment=${ENVIRONMENT}" \
  -var="region=${AWS_REGION}" \
  -var="db_password=${DB_PASSWORD}" \
  -out=tfplan

# Confirm deployment
echo ""
echo -e "${YELLOW}⚠️ This will create AWS resources that may incur charges.${NC}"
read -p "Continue with deployment? (y/N): " -n 1 -r
echo
if [[ ! $REPLY =~ ^[Yy]$ ]]; then
    echo -e "${RED}❌ Deployment cancelled${NC}"
    exit 1
fi

# Apply Terraform
echo -e "${YELLOW}🚀 Deploying infrastructure...${NC}"
terraform apply tfplan

# Get outputs
echo -e "${YELLOW}📊 Getting infrastructure outputs...${NC}"
ECR_REPOSITORY_URL=$(terraform output -raw ecr_repository_url)
ECS_CLUSTER_NAME=$(terraform output -raw ecs_cluster_name)
LOAD_BALANCER_DNS=$(terraform output -raw load_balancer_dns)
S3_BUCKET=$(terraform output -raw s3_bucket)

echo ""
echo -e "${GREEN}✅ Infrastructure deployed successfully!${NC}"
echo -e "${BLUE}📋 ECR Repository: ${ECR_REPOSITORY_URL}${NC}"
echo -e "${BLUE}📋 ECS Cluster: ${ECS_CLUSTER_NAME}${NC}"
echo -e "${BLUE}📋 Load Balancer: ${LOAD_BALANCER_DNS}${NC}"
echo -e "${BLUE}📋 S3 Bucket: ${S3_BUCKET}${NC}"

# Go back to project root
cd ../..

# Build and push Docker image
echo -e "${YELLOW}🐳 Building and pushing Docker image...${NC}"

# Login to ECR
aws ecr get-login-password --region ${AWS_REGION} | docker login --username AWS --password-stdin ${ECR_REPOSITORY_URL}

# Build image
docker build -f Dockerfile.production -t ${PROJECT_NAME}:latest .

# Tag for ECR
docker tag ${PROJECT_NAME}:latest ${ECR_REPOSITORY_URL}:latest

# Push to ECR
docker push ${ECR_REPOSITORY_URL}:latest

echo -e "${GREEN}✅ Docker image pushed successfully!${NC}"

# Update ECS service
echo -e "${YELLOW}🔄 Updating ECS service...${NC}"
aws ecs update-service \
  --cluster ${ECS_CLUSTER_NAME} \
  --service ${PROJECT_NAME}-app-service \
  --force-new-deployment \
  --region ${AWS_REGION}

# Wait for deployment to complete
echo -e "${YELLOW}⏳ Waiting for deployment to complete...${NC}"
aws ecs wait services-stable \
  --cluster ${ECS_CLUSTER_NAME} \
  --services ${PROJECT_NAME}-app-service \
  --region ${AWS_REGION}

echo -e "${GREEN}✅ Deployment completed successfully!${NC}"

# Health check
echo -e "${YELLOW}🏥 Performing health check...${NC}"
sleep 30

HEALTH_URL="http://${LOAD_BALANCER_DNS}/health"
if curl -s -f "${HEALTH_URL}" > /dev/null; then
    echo -e "${GREEN}✅ Application is healthy!${NC}"
else
    echo -e "${RED}❌ Health check failed${NC}"
    echo -e "${YELLOW}⚠️ Check ECS service logs for troubleshooting${NC}"
fi

# Save environment configuration
echo -e "${YELLOW}💾 Saving environment configuration...${NC}"
cat > .env.aws.${ENVIRONMENT} << EOF
# AWS Environment Configuration
AWS_REGION=${AWS_REGION}
AWS_ACCOUNT_ID=${AWS_ACCOUNT_ID}
ECR_REPOSITORY_URL=${ECR_REPOSITORY_URL}
ECS_CLUSTER_NAME=${ECS_CLUSTER_NAME}
LOAD_BALANCER_DNS=${LOAD_BALANCER_DNS}
S3_BUCKET=${S3_BUCKET}
APPLICATION_URL=http://${LOAD_BALANCER_DNS}
EOF

echo ""
echo -e "${GREEN}🎉 AWS Deployment Complete!${NC}"
echo ""
echo -e "${BLUE}📋 Deployment Summary:${NC}"
echo -e "• Application URL: ${GREEN}http://${LOAD_BALANCER_DNS}${NC}"
echo -e "• Health Check: ${GREEN}http://${LOAD_BALANCER_DNS}/health${NC}"
echo -e "• API Documentation: ${GREEN}http://${LOAD_BALANCER_DNS}/docs${NC}"
echo -e "• Environment Config: ${GREEN}.env.aws.${ENVIRONMENT}${NC}"
echo ""
echo -e "${YELLOW}📝 Next Steps:${NC}"
echo -e "1. Configure your domain to point to: ${LOAD_BALANCER_DNS}"
echo -e "2. Set up SSL certificate using AWS Certificate Manager"
echo -e "3. Configure monitoring and alerting"
echo -e "4. Set up CI/CD pipeline for automated deployments"
echo ""
echo -e "${GREEN}✅ Your LyoBackendJune is now running on AWS!${NC}"
