#!/bin/bash
# Push the env vars Railway needs from a local .env file (no deploy).
# Use this when you only want to refresh secrets on Railway without triggering
# a redeploy. Run `railway up` afterwards to apply.
#
# Usage:  ./set_railway_vars.sh
set -euo pipefail

export PATH="/Users/hectorgarcia/.npm-global/bin:$PATH"

if [ ! -f .env ]; then
  echo "Error: .env file not found. Run from LyoBackendJune directory." >&2
  exit 1
fi

if ! command -v railway >/dev/null 2>&1; then
  echo "Error: railway CLI not found. npm install -g @railway/cli" >&2
  exit 1
fi

if ! railway whoami >/dev/null 2>&1; then
  echo "Error: not logged in. Run: railway login" >&2
  exit 1
fi

if ! railway status >/dev/null 2>&1; then
  echo "Error: directory not linked. Run: railway link" >&2
  exit 1
fi

set -a
# shellcheck disable=SC1091
source .env
set +a

SECRET_KEY="${SECRET_KEY:-$(openssl rand -hex 32)}"
JWT_SECRET_KEY="${JWT_SECRET_KEY:-$(openssl rand -hex 32)}"

set_var() {
  railway variable set --skip-deploys "$1" >/dev/null
  echo "  ✓ ${1%%=*}"
}

echo "Setting Railway environment variables (no redeploy)..."
set_var "GEMINI_API_KEY=${GEMINI_API_KEY:-}"
set_var "GOOGLE_API_KEY=${GOOGLE_API_KEY:-${GEMINI_API_KEY:-}}"
set_var "OPENAI_API_KEY=${OPENAI_API_KEY:-}"
set_var "SECRET_KEY=${SECRET_KEY}"
set_var "JWT_SECRET_KEY=${JWT_SECRET_KEY}"
set_var "JWT_ALGORITHM=${JWT_ALGORITHM:-HS256}"
set_var "JWT_ACCESS_TOKEN_EXPIRE_MINUTES=${JWT_ACCESS_TOKEN_EXPIRE_MINUTES:-1440}"
set_var "JWT_REFRESH_TOKEN_EXPIRE_DAYS=${JWT_REFRESH_TOKEN_EXPIRE_DAYS:-30}"
set_var "ENVIRONMENT=production"
set_var "DEBUG=false"
set_var "AI_FALLBACK_ENABLED=false"
set_var "AI_MOCK_MODE=false"
set_var "AI_FORCE_REAL_RESPONSES=true"
set_var "LOG_LEVEL=INFO"
set_var "DEEPGRAM_API_KEY=${DEEPGRAM_API_KEY:-}"
set_var "RUNWAYML_API_SECRET=${RUNWAYML_API_SECRET:-}"
set_var "RUNWAY_API_KEY=${RUNWAY_API_KEY:-}"
set_var "RESEND_API_KEY=${RESEND_API_KEY:-}"
set_var "TAVILY_API_KEY=${TAVILY_API_KEY:-}"
set_var "RUNWARE_API_KEY=${RUNWARE_API_KEY:-}"

echo ""
echo "Done. Trigger a deploy with:  railway up --detach"
