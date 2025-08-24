#!/usr/bin/env bash
# setup-env.sh
# Create a local .env from .env.production.template
# - If gcloud + Secret Manager available and secrets exist, populate sensitive values from there
# - Otherwise generate safe defaults for JWT and leave placeholders for DATABASE_URL/REDIS_URL
# - Ensure .env is added to .gitignore

set -euo pipefail

TEMPLATE_FILE=".env.production.template"
OUT_FILE=".env"
GITIGNORE_FILE=".gitignore"

echo "[setup-env] Creating local .env from template..."

if [ ! -f "$TEMPLATE_FILE" ]; then
  echo "Template $TEMPLATE_FILE not found. Creating minimal defaults..."
  cat > "$TEMPLATE_FILE" <<'EOF'
DATABASE_URL=postgresql://postgres:PASSWORD@/lyo_production?host=/cloudsql/PROJECT_ID:REGION:INSTANCE_NAME
REDIS_URL=
JWT_SECRET_KEY=
JWT_ALGORITHM=HS256
JWT_ACCESS_TOKEN_EXPIRE_MINUTES=30
MODEL_ID=google/gemma-2b-it
MODEL_DIR=/tmp/models
MAX_NEW_TOKENS=512
ENVIRONMENT=production
DEBUG=false
PORT=8080
EOF
fi


# detect gcloud
GCLOUD_AVAILABLE=false
if command -v gcloud >/dev/null 2>&1; then
  GCLOUD_AVAILABLE=true
fi

# helper to fetch secret from Secret Manager
fetch_secret(){
  local name="$1"
  if [ "$GCLOUD_AVAILABLE" = true ]; then
    if gcloud secrets describe "$name" >/dev/null 2>&1; then
      # attempt to access latest
      if value=$(gcloud secrets versions access latest --secret="$name" 2>/dev/null); then
        echo "$value"
        return 0
      fi
    fi
  fi
  return 1
}

# generate JWT if needed
generate_jwt(){
  # 32 bytes base64
  if command -v openssl >/dev/null 2>&1; then
    openssl rand -base64 32
  else
    python3 - <<'PY'
import base64,os
print(base64.urlsafe_b64encode(os.urandom(32)).decode())
PY
  fi
}

# Known secret mapping from env var -> secret name in Secret Manager
# Use a portable function instead of associative arrays for maximum shell compatibility
secret_name_for_key(){
  case "$1" in
    DATABASE_URL) echo "database-url" ;;
    JWT_SECRET_KEY) echo "jwt-secret" ;;
    REDIS_URL) echo "redis-url" ;;
    *) echo "" ;;
  esac
}

# Build output
# helper: read and process each template line in a zsh-/POSIX-compatible way
> "$OUT_FILE"
while IFS= read -r l || [ -n "$l" ]; do
  # skip empty or comment
  case "$l" in
    ""|\#*)
      echo "$l" >> "$OUT_FILE"
      continue
      ;;
  esac

  key="${l%%=*}"
  val="${l#*=}"

  # Trim whitespace (portable)
  key_trimmed=$(echo "$key" | sed 's/^\s*//;s/\s*$//')

  outval=""
  # If secret mapping exists, try to fetch from Secret Manager
  secret_name="$(secret_name_for_key "$key_trimmed")"
  if [ -n "$secret_name" ]; then
    if secret_val=$(fetch_secret "$secret_name"); then
      outval="$secret_val"
      echo "[setup-env] Populated $key_trimmed from Secret Manager ($secret_name)"
    else
      echo "[setup-env] Secret $secret_name not found or inaccessible; will set default/placeholder for $key_trimmed"
    fi
  fi

  # If still empty, apply smart defaults
  if [ -z "$outval" ]; then
    case "$key_trimmed" in
      JWT_SECRET_KEY)
        newjwt=$(generate_jwt)
        outval="$newjwt"
        echo "[setup-env] Generated JWT_SECRET_KEY"
        ;;
      DATABASE_URL)
        if [ -n "$outval" ]; then
          :
        else
          outval="postgresql://postgres:PASSWORD@/lyo_production?host=/cloudsql/PROJECT_ID:REGION:INSTANCE_NAME"
        fi
        ;;
      REDIS_URL)
        outval=""
        ;;
      ENVIRONMENT)
        outval="production"
        ;;
      DEBUG)
        outval="false"
        ;;
      PORT)
        outval="8080"
        ;;
      MODEL_ID)
        outval="google/gemma-2b-it"
        ;;
      *)
        # fallback to template value if present
        outval="$val"
        ;;
    esac
  fi

  # write to file
  echo "$key_trimmed=$outval" >> "$OUT_FILE"
done < "$TEMPLATE_FILE"

# Ensure .env is gitignored
if [ -f "$GITIGNORE_FILE" ]; then
  if ! grep -q "^\.env$" "$GITIGNORE_FILE"; then
    echo ".env" >> "$GITIGNORE_FILE"
    echo "[setup-env] Added .env to $GITIGNORE_FILE"
  fi
else
  echo ".env" > "$GITIGNORE_FILE"
  echo "[setup-env] Created $GITIGNORE_FILE and added .env"
fi

echo "[setup-env] Wrote $OUT_FILE"

echo "[setup-env] Done. Please DO NOT commit .env to version control."
