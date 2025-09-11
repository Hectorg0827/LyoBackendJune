#!/usr/bin/env bash
set -euo pipefail
# Verify that the expected secrets exist in Secret Manager and optionally show a masked preview
# Usage: ./scripts/verify-secrets.sh

keys=("database-url" "redis-url" "jwt-secret" "apns-key-id" "apns-team-id" "apns-bundle-id")

for s in "${keys[@]}"; do
  if gcloud secrets describe "$s" >/dev/null 2>&1; then
    echo "[FOUND] $s"
    # fetch latest but show masked
    val=$(gcloud secrets versions access latest --secret="$s" 2>/dev/null || true)
    if [ -n "$val" ]; then
      echo "   -> preview: ${val:0:8}...${val: -8} (len=${#val})"
    else
      echo "   -> no accessible value"
    fi
  else
    echo "[MISSING] $s"
  fi
done

echo "Verification complete."
