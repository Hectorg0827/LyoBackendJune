#!/bin/bash
# Deploy the Python (FastAPI) backend to Railway and push the env vars it needs.
#
# Prereqs (one-time):
#   1. npm install -g @railway/cli --prefix /Users/hectorgarcia/.npm-global
#   2. railway login            # browser flow (or `railway login --browserless`)
#   3. cd LyoBackendJune
#   4. railway link             # pick the project + service for this repo
#      (or:  railway init       # to create a new project)
#   5. (Highly recommended) Add a Postgres plugin in the Railway dashboard so
#      DATABASE_URL is auto-injected — otherwise the app falls back to ephemeral SQLite.
#
# Then just:
#   ./deploy_to_railway.sh

set -euo pipefail

export PATH="/Users/hectorgarcia/.npm-global/bin:$PATH"

if ! command -v railway &>/dev/null; then
  cat <<'EOF' >&2
Railway CLI not found. Install with:
  npm install -g @railway/cli --prefix /Users/hectorgarcia/.npm-global
EOF
  exit 1
fi

echo "=== Checking Railway auth ==="
if ! railway whoami >/dev/null 2>&1; then
  cat <<'EOF' >&2

Not logged in. Run one of:
  railway login                  # opens browser
  railway login --browserless    # paste a code (works over SSH / no GUI)

Then re-run this script.
EOF
  exit 1
fi
railway whoami

echo ""
echo "=== Checking project link ==="
if ! railway status >/dev/null 2>&1; then
  cat <<'EOF' >&2

This directory is not linked to a Railway project. Run:
  railway link        # to attach an existing project + service
  # or:
  railway init        # to create a new one
Then re-run this script.
EOF
  exit 1
fi
railway status || true

echo ""
echo "=== Loading API keys from .env ==="
if [ ! -f .env ]; then
  echo "ERROR: .env not found in $(pwd). Run from LyoBackendJune directory." >&2
  exit 1
fi
# shellcheck disable=SC1091
set -a
source .env
set +a

# Force strong 64-character secrets for production deployment
if [ -z "${SECRET_KEY:-}" ] || [ ${#SECRET_KEY} -lt 64 ]; then
  SECRET_KEY=$(openssl rand -hex 32)
fi
if [ -z "${JWT_SECRET_KEY:-}" ] || [ ${#JWT_SECRET_KEY} -lt 64 ]; then
  JWT_SECRET_KEY=$(openssl rand -hex 32)
fi

echo ""
echo "=== Setting environment variables on Railway in one batch call ==="

# Build list of variables to set
VARS=()
VARS+=("GEMINI_API_KEY=${GEMINI_API_KEY:-}")
VARS+=("GOOGLE_API_KEY=${GOOGLE_API_KEY:-${GEMINI_API_KEY:-}}")
VARS+=("OPENAI_API_KEY=${OPENAI_API_KEY:-}")
VARS+=("SECRET_KEY=${SECRET_KEY}")
VARS+=("JWT_SECRET_KEY=${JWT_SECRET_KEY}")
VARS+=("JWT_ALGORITHM=HS256")
VARS+=("JWT_ACCESS_TOKEN_EXPIRE_MINUTES=1440")
VARS+=("JWT_REFRESH_TOKEN_EXPIRE_DAYS=30")

# Production behavior
VARS+=("ENVIRONMENT=production")
VARS+=("DEBUG=false")
VARS+=("AI_FALLBACK_ENABLED=false")
VARS+=("AI_MOCK_MODE=false")
VARS+=("AI_FORCE_REAL_RESPONSES=true")
VARS+=("LOG_LEVEL=INFO")
VARS+=("ENABLE_METRICS=true")

# CORS — must use valid URLs in production; allow the deployed service domain by default
VARS+=("CORS_ORIGINS=[\"https://lyobackendjune-lyo.up.railway.app\"]")

# Optional integrations (forwarded if present in .env)
VARS+=("DEEPGRAM_API_KEY=${DEEPGRAM_API_KEY:-}")
VARS+=("RUNWAYML_API_SECRET=${RUNWAYML_API_SECRET:-}")
VARS+=("RUNWAY_API_KEY=${RUNWAY_API_KEY:-}")
VARS+=("RESEND_API_KEY=${RESEND_API_KEY:-}")
VARS+=("TAVILY_API_KEY=${TAVILY_API_KEY:-}")
VARS+=("RUNWARE_API_KEY=${RUNWARE_API_KEY:-}")

# Set variables and skip deploys (we trigger the deploy immediately after)
railway variable set --skip-deploys "${VARS[@]}"
echo "  ✓ All environment variables set successfully!"

echo ""
echo "=== Deploying Python backend to Railway (this triggers the actual build) ==="
railway up --detach --ci

cat <<'EOF'

✅ Deployment uploaded.

Track build & runtime logs (any of):
  railway logs           # tail the active deployment
  open https://railway.app

Smoke-test once status flips to "Active":
  HOST="$(railway status --json 2>/dev/null | jq -r '.service.serviceDomains[0].domain' 2>/dev/null)"
  : "${HOST:=lyo-production.up.railway.app}"
  curl -i "https://$HOST/health"
  curl -i "https://$HOST/"
  curl -i -X POST "https://$HOST/api/v1/ai/chat" \
    -H 'Content-Type: application/json' \
    -d '{"message":"What is gravity?"}'

If /health returns the rich JSON (services map) and / returns the FastAPI root
payload, the real backend is live.

EOF
