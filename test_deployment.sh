#!/usr/bin/env bash
set -euo pipefail

# LyoBackend Deployment Testing Script
# Tests all major endpoints and functionality after deployment
#
# Usage:
#   ./test_deployment.sh https://your-service-url.run.app
#   SERVICE_URL=https://your-service-url.run.app ./test_deployment.sh

SERVICE_URL=${1:-${SERVICE_URL:-}}
REGION=${REGION:-us-central1}
PROJECT_ID=${PROJECT_ID:-}

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

log_info() { echo -e "${BLUE}ℹ️  $1${NC}"; }
log_success() { echo -e "${GREEN}✅ $1${NC}"; }
log_warning() { echo -e "${YELLOW}⚠️  $1${NC}"; }
log_error() { echo -e "${RED}❌ $1${NC}"; }

# Test counter
TESTS_PASSED=0
TESTS_FAILED=0

# Function to run a test
run_test() {
    local test_name=$1
    local test_command=$2
    local expected_code=${3:-200}
    
    echo -n "Testing ${test_name}... "
    
    local response
    local http_code
    
    if response=$(eval "$test_command" 2>/dev/null); then
        http_code=$(echo "$response" | tail -n1)
        
        if [[ "$http_code" == "$expected_code" ]]; then
            echo -e "${GREEN}PASS${NC} (HTTP $http_code)"
            ((TESTS_PASSED++))
            return 0
        else
            echo -e "${RED}FAIL${NC} (HTTP $http_code, expected $expected_code)"
            ((TESTS_FAILED++))
            return 1
        fi
    else
        echo -e "${RED}FAIL${NC} (Connection error)"
        ((TESTS_FAILED++))
        return 1
    fi
}

# Function to test JSON endpoint
test_json_endpoint() {
    local name=$1
    local url=$2
    local method=${3:-GET}
    local data=${4:-}
    local expected_code=${5:-200}
    
    local curl_cmd="curl -s -w '\\n%{http_code}' -X $method"
    
    if [[ -n "$data" ]]; then
        curl_cmd+=" -H 'Content-Type: application/json' -d '$data'"
    fi
    
    curl_cmd+=" '$url'"
    
    run_test "$name" "$curl_cmd" "$expected_code"
}

if [[ -z "${SERVICE_URL}" ]]; then
    if [[ -n "${PROJECT_ID}" ]]; then
        # Try to get service URL from Cloud Run
        SERVICE_URL=$(gcloud run services describe lyo-backend \
            --platform managed \
            --region "${REGION}" \
            --format "value(status.url)" 2>/dev/null || echo "")
    fi
    
    if [[ -z "${SERVICE_URL}" ]]; then
        log_error "SERVICE_URL not provided. Usage: ./test_deployment.sh https://your-service-url.run.app"
    fi
fi

# Remove trailing slash
SERVICE_URL=${SERVICE_URL%/}

log_info "Testing LyoBackend deployment at: ${SERVICE_URL}"
log_info "Starting comprehensive endpoint tests..."

echo
echo "==================== HEALTH & STATUS TESTS ===================="

# Health check
test_json_endpoint "Health Check" "${SERVICE_URL}/health"

# Root endpoint
test_json_endpoint "Root Endpoint" "${SERVICE_URL}/"

# API Documentation
run_test "API Documentation" "curl -s -w '\\n%{http_code}' '${SERVICE_URL}/docs'" 200

# OpenAPI Schema
test_json_endpoint "OpenAPI Schema" "${SERVICE_URL}/openapi.json"

echo
echo "==================== AUTHENTICATION TESTS ===================="

# Test user registration
REGISTER_DATA='{
  "email": "test@example.com",
  "password": "TestPassword123!",
  "full_name": "Test User",
  "username": "testuser"
}'

test_json_endpoint "User Registration" "${SERVICE_URL}/api/v1/auth/register" "POST" "$REGISTER_DATA" 201

# Test user login
LOGIN_DATA='{
  "email": "test@example.com", 
  "password": "TestPassword123!"
}'

echo -n "Testing User Login... "
LOGIN_RESPONSE=$(curl -s -w '\n%{http_code}' -X POST \
  -H "Content-Type: application/json" \
  -d "$LOGIN_DATA" \
  "${SERVICE_URL}/api/v1/auth/login" || echo "")

if [[ -n "$LOGIN_RESPONSE" ]]; then
    HTTP_CODE=$(echo "$LOGIN_RESPONSE" | tail -n1)
    RESPONSE_BODY=$(echo "$LOGIN_RESPONSE" | head -n -1)
    
    if [[ "$HTTP_CODE" == "200" ]]; then
        # Extract token for authenticated tests
        ACCESS_TOKEN=$(echo "$RESPONSE_BODY" | grep -o '"access_token":"[^"]*' | cut -d'"' -f4)
        echo -e "${GREEN}PASS${NC} (HTTP $HTTP_CODE)"
        ((TESTS_PASSED++))
    else
        echo -e "${RED}FAIL${NC} (HTTP $HTTP_CODE)"
        ((TESTS_FAILED++))
        ACCESS_TOKEN=""
    fi
else
    echo -e "${RED}FAIL${NC} (Connection error)"
    ((TESTS_FAILED++))
    ACCESS_TOKEN=""
fi

echo
echo "==================== PROTECTED ENDPOINT TESTS ===================="

if [[ -n "$ACCESS_TOKEN" ]]; then
    # Test protected endpoint
    run_test "User Profile (Protected)" \
        "curl -s -w '\\n%{http_code}' -H 'Authorization: Bearer $ACCESS_TOKEN' '${SERVICE_URL}/api/v1/users/me'" 200
    
    # Test AI chat endpoint
    AI_CHAT_DATA='{
      "message": "Hello, how are you?",
      "context": {},
      "session_id": "test-session"
    }'
    
    run_test "AI Chat (Protected)" \
        "curl -s -w '\\n%{http_code}' -X POST -H 'Authorization: Bearer $ACCESS_TOKEN' -H 'Content-Type: application/json' -d '$AI_CHAT_DATA' '${SERVICE_URL}/api/v1/ai/chat'" 200

else
    log_warning "Skipping protected endpoint tests (no access token)"
fi

echo
echo "==================== API ENDPOINT TESTS ===================="

# Test various public endpoints
test_json_endpoint "Study Resources" "${SERVICE_URL}/api/v1/resources/study"
test_json_endpoint "Educational Content" "${SERVICE_URL}/api/v1/content/educational" 
test_json_endpoint "Public Content" "${SERVICE_URL}/api/v1/content/public"

echo
echo "==================== AI INTEGRATION TESTS ===================="

if [[ -n "$ACCESS_TOKEN" ]]; then
    # Test AI study mode
    AI_STUDY_DATA='{
      "topic": "Python programming",
      "difficulty": "beginner",
      "learning_style": "visual"
    }'
    
    run_test "AI Study Mode" \
        "curl -s -w '\\n%{http_code}' -X POST -H 'Authorization: Bearer $ACCESS_TOKEN' -H 'Content-Type: application/json' -d '$AI_STUDY_DATA' '${SERVICE_URL}/api/v1/ai/study'" 200

    # Test content generation
    CONTENT_GEN_DATA='{
      "type": "quiz",
      "subject": "mathematics",
      "difficulty": "intermediate"
    }'
    
    run_test "Content Generation" \
        "curl -s -w '\\n%{http_code}' -X POST -H 'Authorization: Bearer $ACCESS_TOKEN' -H 'Content-Type: application/json' -d '$CONTENT_GEN_DATA' '${SERVICE_URL}/api/v1/ai/generate-content'" 200

else
    log_warning "Skipping AI integration tests (authentication required)"
fi

echo
echo "==================== PERFORMANCE TESTS ===================="

# Test response time
echo -n "Testing Response Time... "
START_TIME=$(date +%s.%N)
curl -s "${SERVICE_URL}/health" > /dev/null
END_TIME=$(date +%s.%N)
RESPONSE_TIME=$(echo "$END_TIME - $START_TIME" | bc)

if (( $(echo "$RESPONSE_TIME < 2.0" | bc -l) )); then
    echo -e "${GREEN}PASS${NC} (${RESPONSE_TIME}s)"
    ((TESTS_PASSED++))
else
    echo -e "${YELLOW}SLOW${NC} (${RESPONSE_TIME}s)"
    ((TESTS_FAILED++))
fi

# Test concurrent requests
echo -n "Testing Concurrent Requests... "
for i in {1..5}; do
    curl -s "${SERVICE_URL}/health" > /dev/null &
done
wait

if [[ $? -eq 0 ]]; then
    echo -e "${GREEN}PASS${NC}"
    ((TESTS_PASSED++))
else
    echo -e "${RED}FAIL${NC}"
    ((TESTS_FAILED++))
fi

echo
echo "==================== INFRASTRUCTURE TESTS ===================="

# Test HTTPS
echo -n "Testing HTTPS/SSL... "
if curl -s --fail "https://$(echo $SERVICE_URL | cut -d'/' -f3)/health" > /dev/null; then
    echo -e "${GREEN}PASS${NC}"
    ((TESTS_PASSED++))
else
    echo -e "${RED}FAIL${NC}"
    ((TESTS_FAILED++))
fi

# Test CORS headers
echo -n "Testing CORS Headers... "
CORS_HEADERS=$(curl -s -I -X OPTIONS "${SERVICE_URL}/api/v1/auth/register" | grep -i "access-control")
if [[ -n "$CORS_HEADERS" ]]; then
    echo -e "${GREEN}PASS${NC}"
    ((TESTS_PASSED++))
else
    echo -e "${YELLOW}WARNING${NC} (No CORS headers found)"
    ((TESTS_FAILED++))
fi

echo
echo "==================== DEPLOYMENT VALIDATION ===================="

# Check if secrets are properly loaded
if [[ -n "$ACCESS_TOKEN" ]]; then
    echo -n "Testing AI Integration (OpenAI)... "
    AI_TEST_RESPONSE=$(curl -s -w '\n%{http_code}' -X POST \
        -H "Authorization: Bearer $ACCESS_TOKEN" \
        -H "Content-Type: application/json" \
        -d '{"message":"Test"}' \
        "${SERVICE_URL}/api/v1/ai/chat" || echo "")
    
    if [[ -n "$AI_TEST_RESPONSE" ]]; then
        AI_HTTP_CODE=$(echo "$AI_TEST_RESPONSE" | tail -n1)
        if [[ "$AI_HTTP_CODE" == "200" ]]; then
            echo -e "${GREEN}PASS${NC} (Secrets properly loaded)"
            ((TESTS_PASSED++))
        else
            echo -e "${YELLOW}WARNING${NC} (HTTP $AI_HTTP_CODE - Check API keys)"
            ((TESTS_FAILED++))
        fi
    else
        echo -e "${RED}FAIL${NC} (Connection error)"
        ((TESTS_FAILED++))
    fi
fi

echo
echo "==================== TEST SUMMARY ===================="
log_info "Service URL: ${SERVICE_URL}"
log_success "Tests Passed: ${TESTS_PASSED}"
if [[ $TESTS_FAILED -gt 0 ]]; then
    log_error "Tests Failed: ${TESTS_FAILED}"
else
    log_success "Tests Failed: ${TESTS_FAILED}"
fi

TOTAL_TESTS=$((TESTS_PASSED + TESTS_FAILED))
SUCCESS_RATE=$(( (TESTS_PASSED * 100) / TOTAL_TESTS ))

echo "Success Rate: ${SUCCESS_RATE}%"

if [[ $SUCCESS_RATE -ge 80 ]]; then
    echo
    log_success "🎉 Deployment is healthy and ready for production!"
    echo
    echo "Your LyoBackend API endpoints:"
    echo "• API Documentation: ${SERVICE_URL}/docs"
    echo "• Health Check: ${SERVICE_URL}/health"  
    echo "• Authentication: ${SERVICE_URL}/api/v1/auth/"
    echo "• AI Services: ${SERVICE_URL}/api/v1/ai/"
    echo "• User Management: ${SERVICE_URL}/api/v1/users/"
    echo "• Content: ${SERVICE_URL}/api/v1/content/"
    echo
    exit 0
else
    echo
    log_warning "⚠️  Some tests failed. Review the results above and check logs."
    echo
    echo "Troubleshooting commands:"
    echo "• Check logs: gcloud logging read 'resource.type=cloud_run_revision'"
    echo "• Service details: gcloud run services describe lyo-backend --region ${REGION}"
    echo "• Test manually: curl -v ${SERVICE_URL}/health"
    echo
    exit 1
fi
