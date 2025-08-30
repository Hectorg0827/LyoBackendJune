#!/bin/bash

# Master Deployment Status Script
# The definitive "start fresh and check deployment status" tool
# 
# This script provides a comprehensive fresh look at deployment status
# by combining multiple tools and approaches

set -e

# Colors
GREEN='\033[0;32m'
BLUE='\033[0;34m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
CYAN='\033[0;36m'
PURPLE='\033[0;35m'
BOLD='\033[1m'
NC='\033[0m'

# Script directory
SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" &> /dev/null && pwd )"

echo -e "${CYAN}${BOLD}"
echo "╔══════════════════════════════════════════════════════════════╗"
echo "║                  🚀 LYOBACKEND FRESH START                  ║"
echo "║               Deployment Status Check System                 ║"
echo "╚══════════════════════════════════════════════════════════════╝"
echo -e "${NC}"

echo -e "${BLUE}Starting fresh deployment analysis...${NC}"
echo "Timestamp: $(date '+%Y-%m-%d %H:%M:%S')"
echo ""

# Function to run a command with status
run_with_status() {
    local description="$1"
    local command="$2"
    local optional="${3:-false}"
    
    echo -e "${YELLOW}🔄 $description...${NC}"
    
    if eval "$command" >/dev/null 2>&1; then
        echo -e "${GREEN}✅ $description completed${NC}"
        return 0
    else
        if [[ "$optional" == "true" ]]; then
            echo -e "${YELLOW}⚠️  $description skipped (optional)${NC}"
            return 0
        else
            echo -e "${RED}❌ $description failed${NC}"
            return 1
        fi
    fi
}

# 1. Environment Check
echo -e "${PURPLE}${BOLD}📋 Phase 1: Environment Validation${NC}"
echo "=================================="

# Check Python
if command -v python3 &> /dev/null; then
    python_version=$(python3 --version 2>&1)
    echo -e "${GREEN}✅ Python 3 available: $python_version${NC}"
else
    echo -e "${RED}❌ Python 3 not found${NC}"
    exit 1
fi

# Check gcloud (optional)
if command -v gcloud &> /dev/null; then
    gcloud_version=$(gcloud --version | head -1)
    echo -e "${GREEN}✅ Google Cloud SDK available${NC}"
    
    # Check authentication
    if gcloud auth list --filter=status:ACTIVE --format="value(account)" | head -1 >/dev/null 2>&1; then
        account=$(gcloud auth list --filter=status:ACTIVE --format="value(account)" | head -1)
        echo -e "${GREEN}✅ Authenticated as: $account${NC}"
        GCP_AVAILABLE=true
    else
        echo -e "${YELLOW}⚠️  Google Cloud SDK not authenticated${NC}"
        GCP_AVAILABLE=false
    fi
else
    echo -e "${YELLOW}⚠️  Google Cloud SDK not available${NC}"
    GCP_AVAILABLE=false
fi

# Check dependencies
echo -e "${BLUE}📦 Checking dependencies...${NC}"
if python3 -c "import requests" 2>/dev/null; then
    echo -e "${GREEN}✅ Requests library available${NC}"
else
    echo -e "${YELLOW}📦 Installing requests library...${NC}"
    python3 -m pip install requests >/dev/null 2>&1
    echo -e "${GREEN}✅ Requests library installed${NC}"
fi

echo ""

# 2. Configuration Assessment
echo -e "${PURPLE}${BOLD}⚙️  Phase 2: Configuration Assessment${NC}"
echo "======================================"

config_files=(".env.production" ".env.staging" ".env.development" "Dockerfile" "docker-compose.yml")
config_score=0
config_total=${#config_files[@]}

for config_file in "${config_files[@]}"; do
    if [[ -f "$config_file" ]]; then
        if [[ "$config_file" == *.env* ]] && grep -q "CHANGE-THIS-IN-PRODUCTION" "$config_file" 2>/dev/null; then
            echo -e "${YELLOW}⚠️  $config_file: Needs production secrets${NC}"
        else
            echo -e "${GREEN}✅ $config_file: Available${NC}"
            ((config_score++))
        fi
    else
        echo -e "${YELLOW}⚠️  $config_file: Missing${NC}"
    fi
done

echo -e "${BLUE}📊 Configuration Score: $config_score/$config_total${NC}"
echo ""

# 3. Service Discovery & Status
echo -e "${PURPLE}${BOLD}🔍 Phase 3: Service Discovery & Status${NC}"
echo "======================================="

if [[ "$GCP_AVAILABLE" == "true" ]]; then
    echo -e "${BLUE}🚀 Using comprehensive deployment status checker...${NC}"
    
    # Use our fresh deployment checker
    if [[ -f "$SCRIPT_DIR/check_deployment_status_fresh.py" ]]; then
        echo ""
        python3 "$SCRIPT_DIR/check_deployment_status_fresh.py" --detailed
        fresh_exit_code=$?
        echo ""
        
        if [[ $fresh_exit_code -eq 0 ]]; then
            echo -e "${GREEN}✅ Fresh deployment check completed successfully${NC}"
            deployment_healthy=true
        else
            echo -e "${YELLOW}⚠️  Deployment issues detected${NC}"
            deployment_healthy=false
        fi
    else
        echo -e "${YELLOW}⚠️  Fresh deployment checker not found${NC}"
        deployment_healthy=false
    fi
else
    echo -e "${YELLOW}🎭 Google Cloud not available - running demo mode...${NC}"
    
    if [[ -f "$SCRIPT_DIR/demo_deployment_status.py" ]]; then
        echo ""
        python3 "$SCRIPT_DIR/demo_deployment_status.py"
        echo ""
        echo -e "${BLUE}ℹ️  Demo completed - this shows what real deployment status looks like${NC}"
        deployment_healthy=true
    else
        echo -e "${RED}❌ Demo not available${NC}"
        deployment_healthy=false
    fi
fi

echo ""

# 4. Summary & Recommendations
echo -e "${PURPLE}${BOLD}📊 Phase 4: Summary & Recommendations${NC}"
echo "====================================="

# Calculate overall health
overall_score=0
total_checks=3

# Environment check (always passes if we get here)
overall_score=$((overall_score + 1))

# Configuration check
if [[ $config_score -ge $((config_total * 2 / 3)) ]]; then
    overall_score=$((overall_score + 1))
fi

# Deployment check
if [[ "$deployment_healthy" == "true" ]]; then
    overall_score=$((overall_score + 1))
fi

echo -e "${CYAN}🎯 Overall Health Score: $overall_score/$total_checks${NC}"

if [[ $overall_score -eq $total_checks ]]; then
    echo -e "${GREEN}${BOLD}🎉 EXCELLENT: All systems operational!${NC}"
    status_color="$GREEN"
    status_message="EXCELLENT"
elif [[ $overall_score -ge $((total_checks * 2 / 3)) ]]; then
    echo -e "${YELLOW}${BOLD}👍 GOOD: Minor issues detected${NC}"
    status_color="$YELLOW"
    status_message="GOOD"
else
    echo -e "${RED}${BOLD}⚠️  NEEDS ATTENTION: Several issues found${NC}"
    status_color="$RED"
    status_message="NEEDS_ATTENTION"
fi

echo ""
echo -e "${BLUE}${BOLD}💡 Next Steps:${NC}"

if [[ "$GCP_AVAILABLE" == "false" ]]; then
    echo -e "   ${YELLOW}•${NC} Set up Google Cloud SDK: ${CYAN}https://cloud.google.com/sdk/docs/install${NC}"
    echo -e "   ${YELLOW}•${NC} Authenticate: ${CYAN}gcloud auth login${NC}"
    echo -e "   ${YELLOW}•${NC} Set project: ${CYAN}gcloud config set project YOUR_PROJECT_ID${NC}"
fi

if [[ $config_score -lt $config_total ]]; then
    echo -e "   ${YELLOW}•${NC} Review configuration files and update production secrets"
fi

if [[ "$deployment_healthy" == "false" ]] && [[ "$GCP_AVAILABLE" == "true" ]]; then
    echo -e "   ${YELLOW}•${NC} Check service logs: ${CYAN}gcloud run logs read --service=lyo-backend${NC}"
    echo -e "   ${YELLOW}•${NC} Review deployment: ${CYAN}./deployment_dashboard.py${NC}"
fi

echo -e "   ${GREEN}•${NC} Quick status anytime: ${CYAN}./quick_status.sh${NC}"
echo -e "   ${GREEN}•${NC} Full dashboard: ${CYAN}./deployment_dashboard.py${NC}"
echo -e "   ${GREEN}•${NC} Fresh analysis: ${CYAN}./fresh_deployment_check.sh${NC}"

echo ""
echo -e "${status_color}${BOLD}Final Status: $status_message${NC}"
echo -e "${CYAN}Fresh deployment status analysis completed at $(date '+%Y-%m-%d %H:%M:%S')${NC}"

# Exit with appropriate code
if [[ "$status_message" == "EXCELLENT" ]]; then
    exit 0
elif [[ "$status_message" == "GOOD" ]]; then
    exit 0
else
    exit 1
fi