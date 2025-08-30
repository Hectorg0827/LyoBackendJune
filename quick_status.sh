#!/bin/bash

# Quick Deployment Status - Integration Script  
# Integrates the fresh deployment checker into existing workflows
# 
# This script can be called from other deployment scripts to get
# a quick status check without disrupting existing processes

set -e

# Get script directory
SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" &> /dev/null && pwd )"

# Colors
GREEN='\033[0;32m'
BLUE='\033[0;34m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m'

# Quick status check function
quick_status_check() {
    local project="$1"
    local region="${2:-us-central1}"
    local service="$3"
    
    echo -e "${BLUE}🔍 Quick Deployment Status Check${NC}"
    echo "=================================="
    
    # Check if we have the fresh checker
    if [[ -f "$SCRIPT_DIR/check_deployment_status_fresh.py" ]]; then
        if [[ -n "$service" ]]; then
            python3 "$SCRIPT_DIR/check_deployment_status_fresh.py" --project "$project" --region "$region" --service "$service" 2>/dev/null
        elif [[ -n "$project" ]]; then
            python3 "$SCRIPT_DIR/check_deployment_status_fresh.py" --project "$project" --region "$region" 2>/dev/null
        else
            python3 "$SCRIPT_DIR/check_deployment_status_fresh.py" 2>/dev/null
        fi
        return $?
    else
        echo -e "${YELLOW}⚠️  Fresh deployment checker not available${NC}"
        echo "Using basic status check..."
        basic_status_check "$project" "$region" "$service"
        return $?
    fi
}

# Basic fallback status check
basic_status_check() {
    local project="$1"
    local region="${2:-us-central1}"
    local service="$3"
    
    if command -v gcloud &> /dev/null; then
        if [[ -n "$service" ]]; then
            # Check specific service
            local url=$(gcloud run services describe "$service" --region="$region" --format="value(status.url)" 2>/dev/null)
            if [[ -n "$url" ]]; then
                echo -e "${GREEN}✅ Service $service found: $url${NC}"
                if curl -f -s "$url/health" > /dev/null 2>&1; then
                    echo -e "${GREEN}✅ Health check passed${NC}"
                    return 0
                else
                    echo -e "${YELLOW}⚠️  Health check failed${NC}"
                    return 1
                fi
            else
                echo -e "${RED}❌ Service $service not found${NC}"
                return 1
            fi
        else
            # List all services
            local services=$(gcloud run services list --region="$region" --format="value(metadata.name)" 2>/dev/null)
            if [[ -n "$services" ]]; then
                local count=$(echo "$services" | wc -l)
                echo -e "${GREEN}✅ Found $count Cloud Run services${NC}"
                return 0
            else
                echo -e "${YELLOW}⚠️  No Cloud Run services found${NC}"
                return 1
            fi
        fi
    else
        echo -e "${RED}❌ Google Cloud SDK not available${NC}"
        return 1
    fi
}

# Main execution
case "$1" in
    "--help"|"-h")
        echo "Quick Deployment Status Check"
        echo "Usage:"
        echo "  $0                           # Check all services in current project"
        echo "  $0 PROJECT                   # Check all services in specific project"
        echo "  $0 PROJECT REGION            # Check services in specific project/region"
        echo "  $0 PROJECT REGION SERVICE    # Check specific service"
        echo ""
        echo "Examples:"
        echo "  $0"
        echo "  $0 my-lyobackend-project"
        echo "  $0 my-project us-west1"
        echo "  $0 my-project us-central1 lyo-backend"
        exit 0
        ;;
    "--demo")
        # Run demo mode
        if [[ -f "$SCRIPT_DIR/demo_deployment_status.py" ]]; then
            python3 "$SCRIPT_DIR/demo_deployment_status.py"
        else
            echo -e "${YELLOW}Demo not available${NC}"
            exit 1
        fi
        ;;
    *)
        # Run status check with provided arguments
        quick_status_check "$1" "$2" "$3"
        exit $?
        ;;
esac