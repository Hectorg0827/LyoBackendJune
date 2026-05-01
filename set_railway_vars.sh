#!/bin/bash
# Push required env vars to Railway from your local .env file
# Usage: ./set_railway_vars.sh
set -euo pipefail

# Load values from .env
if [ ! -f .env ]; then
  echo "Error: .env file not found. Run from LyoBackendJune directory." >&2
  exit 1
fi

source .env

echo "Setting Railway environment variables..."

railway variables set \
  GEMINI_API_KEY="${GEMINI_API_KEY}" \
  GOOGLE_API_KEY="${GOOGLE_API_KEY}" \
  OPENAI_API_KEY="${OPENAI_API_KEY}" \
  SECRET_KEY="${SECRET_KEY}" \
  JWT_SECRET_KEY="${JWT_SECRET_KEY}" \
  JWT_ALGORITHM="${JWT_ALGORITHM}" \
  JWT_ACCESS_TOKEN_EXPIRE_MINUTES="${JWT_ACCESS_TOKEN_EXPIRE_MINUTES}" \
  JWT_REFRESH_TOKEN_EXPIRE_DAYS="${JWT_REFRESH_TOKEN_EXPIRE_DAYS}" \
  ENVIRONMENT="production" \
  DEBUG="false" \
  AI_FALLBACK_ENABLED="false" \
  AI_MOCK_MODE="false" \
  AI_FORCE_REAL_RESPONSES="true" \
  DEEPGRAM_API_KEY="${DEEPGRAM_API_KEY}" \
  RUNWAYML_API_SECRET="${RUNWAYML_API_SECRET}" \
  RUNWAY_API_KEY="${RUNWAY_API_KEY}" \
  RESEND_API_KEY="${RESEND_API_KEY}" \
  TAVILY_API_KEY="${TAVILY_API_KEY}" \
  RUNWARE_API_KEY="${RUNWARE_API_KEY}"

echo "Done. Trigger a Railway redeploy to apply changes."
