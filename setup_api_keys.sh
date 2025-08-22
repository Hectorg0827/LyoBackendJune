#!/bin/bash
# Complete API Key Setup Script for LyoBackend Production
set -euo pipefail

PROJECT_ID=${1:-${PROJECT_ID:-}}
if [[ -z "${PROJECT_ID}" ]]; then
  echo "Usage: ./setup_api_keys.sh PROJECT_ID" >&2
  echo "Example: ./setup_api_keys.sh lyo-backend-prod" >&2
  exit 1
fi

echo "🔑 Setting up API keys for project: $PROJECT_ID"
echo "==============================================="

# Set the project
gcloud config set project $PROJECT_ID

# Enable required APIs
echo "🔧 Enabling required Google Cloud APIs..."
gcloud services enable secretmanager.googleapis.com
gcloud services enable run.googleapis.com
gcloud services enable sqladmin.googleapis.com
gcloud services enable redis.googleapis.com

# Function to create or update secret
create_or_update_secret() {
  local secret_name=$1
  local secret_value=$2
  
  if gcloud secrets describe "$secret_name" &>/dev/null; then
    echo "Updating existing secret: $secret_name"
    echo -n "$secret_value" | gcloud secrets versions add "$secret_name" --data-file=-
  else
    echo "Creating new secret: $secret_name"
    echo -n "$secret_value" | gcloud secrets create "$secret_name" --data-file=-
  fi
}

# 1. Generate strong JWT secret key if not provided
echo "🔐 Setting up JWT Secret Key..."
if [[ -z "${JWT_SECRET_KEY:-}" ]]; then
  JWT_SECRET_KEY=$(openssl rand -base64 64)
  echo "Generated secure JWT secret key"
else
  echo "Using provided JWT secret key"
fi
create_or_update_secret "jwt-secret-key" "$JWT_SECRET_KEY"

# 2. OpenAI API Key
echo "🤖 Setting up OpenAI API Key..."
if [[ -z "${OPENAI_API_KEY:-}" ]]; then
  read -p "Enter your OpenAI API key (from platform.openai.com): " OPENAI_KEY
  if [[ -z "$OPENAI_KEY" ]]; then
    echo "⚠️  OpenAI API key is required for AI Study Mode"
    exit 1
  fi
else
  OPENAI_KEY="${OPENAI_API_KEY}"
fi
create_or_update_secret "openai-api-key" "$OPENAI_KEY"

# 3. Google Gemini API Key
echo "🧠 Setting up Gemini API Key..."
if [[ -z "${GEMINI_API_KEY:-}" ]]; then
  read -p "Enter your Gemini API key (from aistudio.google.com): " GEMINI_KEY
  if [[ -z "$GEMINI_KEY" ]]; then
    echo "⚠️  Gemini API key recommended for multi-model support"
    GEMINI_KEY="not-configured"
  fi
else
  GEMINI_KEY="${GEMINI_API_KEY}"
fi
create_or_update_secret "gemini-api-key" "$GEMINI_KEY"

# 4. Anthropic Claude API Key (optional)
echo "💭 Setting up Anthropic API Key (optional)..."
if [[ -z "${ANTHROPIC_API_KEY:-}" ]]; then
  read -p "Enter your Anthropic API key (optional, press Enter to skip): " ANTHROPIC_KEY
  if [[ -z "$ANTHROPIC_KEY" ]]; then
    ANTHROPIC_KEY="not-configured"
  fi
else
  ANTHROPIC_KEY="${ANTHROPIC_API_KEY}"
fi
create_or_update_secret "anthropic-api-key" "$ANTHROPIC_KEY"

# 5. Database URL (generate Cloud SQL connection if needed)
echo "🗄️  Setting up Database URL..."
if [[ -z "${DATABASE_URL:-}" ]]; then
  read -p "Enter your database URL (PostgreSQL connection string): " DB_URL
  if [[ -z "$DB_URL" ]]; then
    echo "⚠️  Database URL is required"
    exit 1
  fi
else
  DB_URL="${DATABASE_URL}"
fi
create_or_update_secret "database-url" "$DB_URL"

# 6. Redis URL
echo "📦 Setting up Redis URL..."
if [[ -z "${REDIS_URL:-}" ]]; then
  read -p "Enter your Redis URL (default: redis://localhost:6379): " REDIS_URL_INPUT
  if [[ -z "$REDIS_URL_INPUT" ]]; then
    REDIS_URL_INPUT="redis://localhost:6379/0"
  fi
else
  REDIS_URL_INPUT="${REDIS_URL}"
fi
create_or_update_secret "redis-url" "$REDIS_URL_INPUT"

# 7. Email Service (SendGrid recommended)
echo "📧 Setting up Email Service..."
if [[ -z "${EMAIL_API_KEY:-}" ]]; then
  read -p "Enter your email service API key (SendGrid recommended): " EMAIL_KEY
  if [[ -z "$EMAIL_KEY" ]]; then
    EMAIL_KEY="not-configured"
    echo "⚠️  Email notifications will be disabled"
  fi
else
  EMAIL_KEY="${EMAIL_API_KEY}"
fi
create_or_update_secret "email-api-key" "$EMAIL_KEY"

# 8. Push Notification Keys (iOS)
echo "📱 Setting up iOS Push Notifications..."
if [[ -z "${APNS_KEY_ID:-}" ]]; then
  read -p "Enter your APNs Key ID (for iOS push): " APNS_KEY_ID_INPUT
  if [[ -z "$APNS_KEY_ID_INPUT" ]]; then
    APNS_KEY_ID_INPUT="not-configured"
    echo "⚠️  iOS push notifications will be disabled"
  fi
else
  APNS_KEY_ID_INPUT="${APNS_KEY_ID}"
fi
create_or_update_secret "apns-key-id" "$APNS_KEY_ID_INPUT"

if [[ "$APNS_KEY_ID_INPUT" != "not-configured" ]]; then
  if [[ -z "${APNS_TEAM_ID:-}" ]]; then
    read -p "Enter your APNs Team ID: " APNS_TEAM_ID_INPUT
  else
    APNS_TEAM_ID_INPUT="${APNS_TEAM_ID}"
  fi
  create_or_update_secret "apns-team-id" "$APNS_TEAM_ID_INPUT"
  
  if [[ -z "${APNS_PRIVATE_KEY:-}" ]]; then
    echo "Paste your APNs .p8 private key content (press Enter twice when done):"
    APNS_KEY=""
    while IFS= read -r line; do
      if [[ -z "$line" ]]; then
        break
      fi
      APNS_KEY="$APNS_KEY$line"$'\n'
    done
  else
    APNS_KEY="${APNS_PRIVATE_KEY}"
  fi
  create_or_update_secret "apns-private-key" "$APNS_KEY"
fi

# 9. Sentry DSN for error tracking (optional)
echo "🔍 Setting up Sentry for error tracking (optional)..."
if [[ -z "${SENTRY_DSN:-}" ]]; then
  read -p "Enter your Sentry DSN (optional, press Enter to skip): " SENTRY_DSN_INPUT
  if [[ -z "$SENTRY_DSN_INPUT" ]]; then
    SENTRY_DSN_INPUT="not-configured"
  fi
else
  SENTRY_DSN_INPUT="${SENTRY_DSN}"
fi
create_or_update_secret "sentry-dsn" "$SENTRY_DSN_INPUT"

# 10. YouTube Data API Key (optional)
echo "📺 Setting up YouTube Data API (optional)..."
if [[ -z "${YOUTUBE_API_KEY:-}" ]]; then
  read -p "Enter your YouTube Data API key (optional, press Enter to skip): " YOUTUBE_KEY
  if [[ -z "$YOUTUBE_KEY" ]]; then
    YOUTUBE_KEY="not-configured"
  fi
else
  YOUTUBE_KEY="${YOUTUBE_API_KEY}"
fi
create_or_update_secret "youtube-api-key" "$YOUTUBE_KEY"

# Grant Cloud Run access to secrets
echo "🔐 Granting Cloud Run service access to secrets..."
PROJECT_NUMBER=$(gcloud projects describe $PROJECT_ID --format="value(projectNumber)")
CLOUD_RUN_SA="${PROJECT_NUMBER}-compute@developer.gserviceaccount.com"

secrets=(
  "jwt-secret-key"
  "openai-api-key"
  "gemini-api-key"
  "anthropic-api-key"
  "database-url"
  "redis-url"
  "email-api-key"
  "apns-key-id"
  "apns-team-id"
  "apns-private-key"
  "sentry-dsn"
  "youtube-api-key"
)

for secret in "${secrets[@]}"; do
  if gcloud secrets describe "$secret" &>/dev/null; then
    gcloud secrets add-iam-policy-binding "$secret" \
      --member="serviceAccount:$CLOUD_RUN_SA" \
      --role="roles/secretmanager.secretAccessor" &>/dev/null || true
  fi
done

echo "✅ All API keys have been securely stored in Google Secret Manager"
echo "🔐 Secrets are accessible by Cloud Run service: $CLOUD_RUN_SA"
echo ""
echo "📝 Next Steps:"
echo "  1. Run: ./deploy_cloudrun.sh $PROJECT_ID"
echo "  2. Test: python validate_production_ready.py"
echo ""
echo "🎉 API Key setup complete!"
