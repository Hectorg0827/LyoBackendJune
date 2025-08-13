#!/usr/bin/env bash
set -euo pipefail

# Simple helper script to build & deploy the service to Google Cloud Run.
# Requirements:
#  - gcloud CLI authenticated (gcloud auth login / application-default login)
#  - PROJECT_ID exported or passed as first arg
#  - Artifact Registry repo (or use Cloud Build default) if customizing
# Usage:
#   PROJECT_ID=my-project REGION=us-central1 SERVICE=lyo-backend ./deploy_cloudrun.sh
#   ./deploy_cloudrun.sh my-project

PROJECT_ID=${1:-${PROJECT_ID:-}}
REGION=${REGION:-us-central1}
SERVICE=${SERVICE:-lyo-backend}
PORT=${PORT:-8080}
CPU=${CPU:-1}
MEMORY=${MEMORY:-512Mi}
CONCURRENCY=${CONCURRENCY:-80}
TIMEOUT=${TIMEOUT:-600}
MIN_INSTANCES=${MIN_INSTANCES:-0}
MAX_INSTANCES=${MAX_INSTANCES:-4}
PLATFORM=${PLATFORM:-managed}

if [[ -z "${PROJECT_ID}" ]]; then
  echo "PROJECT_ID not set. Provide as env var or first argument." >&2
  exit 1
fi

echo "Deploying service '${SERVICE}' to project '${PROJECT_ID}' region '${REGION}'"

gcloud config set project "${PROJECT_ID}" 1>/dev/null

echo "Building & deploying (Cloud Build) ..."

gcloud run deploy "${SERVICE}" \
  --source . \
  --region "${REGION}" \
  --platform "${PLATFORM}" \
  --port "${PORT}" \
  --allow-unauthenticated \
  --cpu "${CPU}" \
  --memory "${MEMORY}" \
  --concurrency "${CONCURRENCY}" \
  --timeout "${TIMEOUT}" \
  --min-instances "${MIN_INSTANCES}" \
  --max-instances "${MAX_INSTANCES}" \
  --set-env-vars "PYTHONUNBUFFERED=1" \
  --set-env-vars "PORT=${PORT}" \
  --set-env-vars "ENVIRONMENT=production" \
  --set-env-vars "GCP_PROJECT_ID=${PROJECT_ID}" \
  --service-account "${SERVICE}-sa@${PROJECT_ID}.iam.gserviceaccount.com"

echo "Deployment initiated. Review status: https://console.cloud.google.com/run?project=${PROJECT_ID}"
echo "(Make sure this script is executable: chmod +x deploy_cloudrun.sh)"
