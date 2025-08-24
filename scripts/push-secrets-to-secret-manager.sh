#!/usr/bin/env bash
set -euo pipefail
# Push selected .env values into Google Secret Manager
# Usage: ./scripts/push-secrets-to-secret-manager.sh [--dry-run]

DRY_RUN=false
if [ "${1:-}" = "--dry-run" ]; then DRY_RUN=true; fi

ENV_FILE=".env"
if [ ! -f "$ENV_FILE" ]; then
  echo "ERROR: $ENV_FILE not found in project root. Run ./setup-env.sh first or create a .env." >&2
  exit 1
fi

# If GOOGLE_CLOUD_PROJECT present in .env, set gcloud project to it for convenience
if grep -qE "^GOOGLE_CLOUD_PROJECT=" "$ENV_FILE"; then
  proj=$(grep -E "^GOOGLE_CLOUD_PROJECT=" "$ENV_FILE" | sed 's/^GOOGLE_CLOUD_PROJECT=//;s/"//g')
  if [ -n "$proj" ]; then
    echo "[push-secrets] Setting gcloud project to: $proj"
    gcloud config set project "$proj" >/dev/null || true
  fi
fi

# list of env keys we consider secrets
keys=("DATABASE_URL" "REDIS_URL" "JWT_SECRET_KEY" "APNS_KEY_ID" "APNS_TEAM_ID" "APNS_BUNDLE_ID")

secret_name_for_key(){
  case "$1" in
    DATABASE_URL) echo "database-url" ;;
    JWT_SECRET_KEY) echo "jwt-secret" ;;
    REDIS_URL) echo "redis-url" ;;
    APNS_KEY_ID) echo "apns-key-id" ;;
    APNS_TEAM_ID) echo "apns-team-id" ;;
    APNS_BUNDLE_ID) echo "apns-bundle-id" ;;
    *) echo "" ;;
  esac
}

get_env(){
  local k="$1"
  # safe grep for exact key
  local line
  line=$(grep -E "^${k}=" "$ENV_FILE" || true)
  if [ -z "$line" ]; then
    echo ""
    return
  fi
  local value="${line#*=}"
  # strip surrounding quotes if present
  value=$(echo "$value" | sed 's/^"//;s/"$//')
  echo "$value"
}

for k in "${keys[@]}"; do
  name=$(secret_name_for_key "$k")
  val=$(get_env "$k")
  if [ -z "$name" ]; then
    continue
  fi
  if [ -z "$val" ]; then
    echo "[skip] $k is empty or not set in $ENV_FILE"
    continue
  fi
  echo "[push] Preparing to push $k -> secret '$name'"
  if [ "$DRY_RUN" = true ]; then
    echo "  (dry-run) would create/add secret '$name'"
    continue
  fi

  if gcloud secrets describe "$name" >/dev/null 2>&1; then
    echo "  secret exists: adding new version..."
    # add a new version from stdin
    printf "%s" "$val" | gcloud secrets versions add "$name" --data-file=- >/dev/null
  else
    echo "  secret not found: creating secret and adding version..."
    # create secret with automatic replication and add current value
    printf "%s" "$val" | gcloud secrets create "$name" --data-file=- --replication-policy="automatic" >/dev/null
  fi
  echo "  OK"
done

echo "All done."
