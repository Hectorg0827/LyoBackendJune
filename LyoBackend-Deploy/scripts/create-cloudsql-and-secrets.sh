#!/usr/bin/env bash
set -euo pipefail
# Create a Cloud SQL Postgres instance, create a database/user, and store the DATABASE_URL in Secret Manager.
# Usage: ./scripts/create-cloudsql-and-secrets.sh <INSTANCE_NAME> <REGION> [--db-user=lyo_admin] [--db-name=lyo_production] [--dry-run]

if [ "${1:-}" = "" ]; then
  echo "Usage: $0 <INSTANCE_NAME> <REGION> [--db-user=lyo_admin] [--db-name=lyo_production] [--dry-run]" >&2
  exit 1
fi

INSTANCE_NAME="$1"
REGION="$2"
DB_USER="lyo_admin"
DB_NAME="lyo_production"
DRY_RUN=false

for arg in "${@:3}"; do
  case "$arg" in
    --db-user=*) DB_USER="${arg#*=}" ;;
    --db-name=*) DB_NAME="${arg#*=}" ;;
    --dry-run) DRY_RUN=true ;;
  esac
done

PROJECT=$(gcloud config get-value project 2>/dev/null || true)
if [ -z "$PROJECT" ]; then
  echo "gcloud project not set. Run 'gcloud config set project <PROJECT_ID>'" >&2
  exit 1
fi

echo "[cloudsql] Project: $PROJECT"
echo "[cloudsql] Instance: $INSTANCE_NAME (region: $REGION)"

if [ "$DRY_RUN" = true ]; then
  echo "(dry-run) would create Cloud SQL Postgres instance and database/user"
  exit 0
fi

# Create the instance (Postgres, 1 vCPU, 4GB) - you may want to adjust tier
if gcloud sql instances describe "$INSTANCE_NAME" >/dev/null 2>&1; then
  echo "Instance $INSTANCE_NAME already exists. Skipping creation."
else
  echo "Creating Cloud SQL Postgres instance $INSTANCE_NAME..."
  # Use either --tier or --cpu/--memory. We choose explicit cpu/memory here for clarity.
  gcloud sql instances create "$INSTANCE_NAME" \
    --database-version=POSTGRES_14 \
    --region="$REGION" \
    --cpu=1 --memory=3840MiB \
    --no-backup \
    --quiet
fi

# Create DB and user
# Generate a strong password
DB_PASS=$(python3 - <<'PY'
import secrets,base64
print(base64.urlsafe_b64encode(secrets.token_bytes(24)).decode())
PY
)

# Create user
if gcloud sql users list --instance="$INSTANCE_NAME" --format=json | grep -q "\"name\": \"$DB_USER\""; then
  echo "User $DB_USER already exists. Skipping user creation."
else
  echo "Creating user $DB_USER..."
  gcloud sql users create "$DB_USER" --instance="$INSTANCE_NAME" --password="$DB_PASS"
fi

# Create database
if gcloud sql databases describe "$DB_NAME" --instance="$INSTANCE_NAME" >/dev/null 2>&1; then
  echo "Database $DB_NAME already exists. Skipping."
else
  echo "Creating database $DB_NAME..."
  gcloud sql databases create "$DB_NAME" --instance="$INSTANCE_NAME"
fi

# Build DATABASE_URL
# For Cloud Run using Cloud SQL, we typically use the socket path: postgresql://USER:PASSWORD@/DB?host=/cloudsql/PROJECT:REGION:INSTANCE
DATABASE_URL="postgresql://${DB_USER}:${DB_PASS}@/${DB_NAME}?host=/cloudsql/${PROJECT}:${REGION}:${INSTANCE_NAME}"

echo "Storing DATABASE_URL into Secret Manager as 'database-url'"
printf "%s" "$DATABASE_URL" | gcloud secrets create database-url --data-file=- --replication-policy="automatic" >/dev/null || \
  printf "%s" "$DATABASE_URL" | gcloud secrets versions add database-url --data-file=- >/dev/null

# Output connection info
cat <<EOF
Created/ensured Cloud SQL instance and DB.
DB_USER=$DB_USER
DB_NAME=$DB_NAME
DB_PASS=(hidden)
DATABASE_URL=$DATABASE_URL
Note: You may want to configure authorized networks or use private IP for security.
EOF
