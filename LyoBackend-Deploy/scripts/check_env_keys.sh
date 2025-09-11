#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."

if [[ ! -f .env ]]; then
  echo "❌ .env file not found in project root" >&2
  exit 1
fi

declare -a REQUIRED=(
  OPENAI_API_KEY
  DATABASE_URL
  REDIS_URL
  SECRET_KEY
  JWT_SECRET_KEY
)

MISSING=0
for key in "${REQUIRED[@]}"; do
  if ! grep -q "^${key}=" .env; then
    echo "❌ ${key} - MISSING"
    ((MISSING++)) || true
  else
    val=$(grep "^${key}=" .env | cut -d'=' -f2-)
    if [[ -z "$val" || "$val" == your-* || "$val" == xxx* || "$val" == change* ]]; then
      echo "❌ ${key} - NOT CONFIGURED"
      ((MISSING++)) || true
    else
      echo "✅ ${key} - CONFIGURED"
    fi
  fi
done

if [[ $MISSING -gt 0 ]]; then
  echo "\n⚠️  ${MISSING} required keys missing or not configured"
  exit 2
fi

echo "\n✅ All required keys are configured"
