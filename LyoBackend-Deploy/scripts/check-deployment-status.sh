#!/usr/bin/env bash
set -euo pipefail
# Check Cloud Run deployment status and test the service
# Usage: ./scripts/check-deployment-status.sh [PROJECT] [REGION] [SERVICE]

PROJECT="${1:-lyobackend}"
REGION="${2:-us-central1}"
SERVICE="${3:-lyo-backend}"

echo "[status] Checking Cloud Run service: $SERVICE in $REGION"

# Get service status
if gcloud run services describe "$SERVICE" --region="$REGION" --format="value(status.url)" 2>/dev/null; then
  SERVICE_URL=$(gcloud run services describe "$SERVICE" --region="$REGION" --format="value(status.url)")
  echo "[status] Service URL: $SERVICE_URL"
  
  # Test health endpoint
  echo "[status] Testing health endpoint..."
  if curl -f -s "$SERVICE_URL/health" >/dev/null; then
    echo "[status] ✅ Health check passed"
    echo "[status] Testing /health response:"
    curl -s "$SERVICE_URL/health" | python -m json.tool || echo "(non-JSON response)"
  else
    echo "[status] ❌ Health check failed"
  fi
  
  # Test AI endpoint
  echo "[status] Testing AI endpoint..."
  if curl -f -s "$SERVICE_URL/api/v1/test-ai" >/dev/null; then
    echo "[status] ✅ AI endpoint accessible"
  else
    echo "[status] ❌ AI endpoint failed"
  fi
  
else
  echo "[status] ❌ Service not found or not ready"
  exit 1
fi

echo "[status] Deployment check complete"
