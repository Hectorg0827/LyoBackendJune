#!/bin/bash

# Fresh Deployment Status Checker - Simple Runner
# Automatically checks the current status of all deployments
# 
# Usage:
#   ./fresh_deployment_check.sh              # Quick check
#   ./fresh_deployment_check.sh --detailed   # Detailed analysis
#   ./fresh_deployment_check.sh --help       # Show help

set -e

# Colors
GREEN='\033[0;32m'
BLUE='\033[0;34m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m' # No Color

echo -e "${BLUE}🔄 LyoBackend Fresh Deployment Status Checker${NC}"
echo "=================================================="
echo ""

# Check if Python 3 is available
if ! command -v python3 &> /dev/null; then
    echo -e "${RED}❌ Error: Python 3 is required but not found${NC}"
    echo "Please install Python 3 and try again"
    exit 1
fi

# Check if requests library is available
if ! python3 -c "import requests" 2>/dev/null; then
    echo -e "${YELLOW}📦 Installing required dependencies...${NC}"
    python3 -m pip install requests > /dev/null 2>&1
    echo -e "${GREEN}✅ Dependencies installed${NC}"
fi

# Check if gcloud is available
if ! command -v gcloud &> /dev/null; then
    echo -e "${RED}❌ Error: Google Cloud SDK is required but not found${NC}"
    echo ""
    echo "Please install the Google Cloud SDK:"
    echo "https://cloud.google.com/sdk/docs/install"
    echo ""
    exit 1
fi

# Check if user is authenticated with gcloud
if ! gcloud auth list --filter=status:ACTIVE --format="value(account)" | head -1 > /dev/null 2>&1; then
    echo -e "${YELLOW}⚠️  Not authenticated with Google Cloud${NC}"
    echo ""
    echo "Please authenticate:"
    echo "  gcloud auth login"
    echo ""
    exit 1
fi

# Get script directory
SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" &> /dev/null && pwd )"

# Check if the Python script exists
PYTHON_SCRIPT="$SCRIPT_DIR/check_deployment_status_fresh.py"
if [[ ! -f "$PYTHON_SCRIPT" ]]; then
    echo -e "${RED}❌ Error: check_deployment_status_fresh.py not found${NC}"
    exit 1
fi

echo -e "${GREEN}🚀 Starting fresh deployment status check...${NC}"
echo ""

# Run the Python script with all arguments passed through
python3 "$PYTHON_SCRIPT" "$@"

exit_code=$?

echo ""
if [[ $exit_code -eq 0 ]]; then
    echo -e "${GREEN}✅ Deployment status check completed successfully${NC}"
else
    echo -e "${YELLOW}⚠️  Issues detected in deployment - see details above${NC}"
fi

exit $exit_code