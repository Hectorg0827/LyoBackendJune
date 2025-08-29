#!/bin/bash
# deploy_unified.sh - Deployment script for LyoBackend with unified architecture

set -e  # Exit immediately if a command exits with a non-zero status

# Print colored output
GREEN='\033[0;32m'
YELLOW='\033[0;33m'
RED='\033[0;31m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

echo -e "${BLUE}====================================================${NC}"
echo -e "${BLUE}  LyoBackend Unified Architecture Deployment Script  ${NC}"
echo -e "${BLUE}====================================================${NC}"

# Validate environment
ENV=${1:-production}
if [[ "$ENV" != "production" && "$ENV" != "staging" && "$ENV" != "development" ]]; then
  echo -e "${RED}Error: Environment must be 'production', 'staging', or 'development'${NC}"
  echo -e "Usage: $0 [environment]"
  exit 1
fi

echo -e "${YELLOW}Starting deployment for ${ENV} environment...${NC}"

# Ensure PostgreSQL is used for production and staging
if [[ "$ENV" == "production" || "$ENV" == "staging" ]]; then
  if [[ -z "${DATABASE_URL}" || "${DATABASE_URL}" == *"sqlite"* ]]; then
    echo -e "${RED}Error: PostgreSQL database URL must be provided for ${ENV} environment${NC}"
    echo -e "Please set DATABASE_URL environment variable to a valid PostgreSQL URL"
    exit 1
  fi
  echo -e "${GREEN}✓ Valid PostgreSQL database URL confirmed${NC}"
fi

# Install dependencies
echo -e "${YELLOW}Installing dependencies...${NC}"
python -m pip install --upgrade pip
pip install -r requirements.txt
echo -e "${GREEN}✓ Dependencies installed${NC}"

# Run database migrations if needed
if [ -d "migrations" ]; then
  echo -e "${YELLOW}Running database migrations...${NC}"
  export PYTHONPATH=$PYTHONPATH:$(pwd)
  alembic upgrade head
  echo -e "${GREEN}✓ Database migrations completed${NC}"
fi

# Build Docker image if requested
if [ "$2" == "--docker" ]; then
  echo -e "${YELLOW}Building Docker image...${NC}"
  docker build -t lyobackend-unified:${ENV} -f Dockerfile.unified --build-arg ENV=${ENV} .
  echo -e "${GREEN}✓ Docker image built: lyobackend-unified:${ENV}${NC}"
fi

# Start the application with the unified architecture
echo -e "${YELLOW}Starting LyoBackend with unified architecture...${NC}"
if [ "$2" == "--docker" ]; then
  echo -e "${YELLOW}Starting Docker container...${NC}"
  docker run -d --name lyobackend-unified-${ENV} -p 8000:8000 -e ENV=${ENV} lyobackend-unified:${ENV}
  echo -e "${GREEN}✓ Docker container started${NC}"
else
  echo -e "${YELLOW}Starting application directly...${NC}"
  export ENV=${ENV}
  ./start_unified.py
fi

echo -e "${GREEN}=====================================${NC}"
echo -e "${GREEN}  Deployment completed successfully!  ${NC}"
echo -e "${GREEN}=====================================${NC}"
