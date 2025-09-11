#!/usr/bin/env bash
set -euo pipefail
# Wrapper to run the safe-cloud-deploy flow which uses Cloud Build to build and deploy to Cloud Run
# Usage: ./scripts/deploy-safe-cloud-run.sh <GCP_PROJECT> <REGION> [--service=lyo-backend] [--image=IMAGE_NAME]

if [ "${1:-}" = "" ]; then
  echo "Usage: $0 <GCP_PROJECT> <REGION> [--service=lyo-backend] [--image=IMAGE_NAME]" >&2
  exit 1
fi

PROJECT="$1"
REGION="$2"
SERVICE="lyo-backend"
IMAGE_NAME="gcr.io/$PROJECT/lyo-backend"

for arg in "${@:3}"; do
  case "$arg" in
    --service=*) SERVICE="${arg#*=}" ;;
    --image=*) IMAGE_NAME="${arg#*=}" ;;
  esac
done

echo "[deploy] Project: $PROJECT"
echo "[deploy] Region: $REGION"
echo "[deploy] Service: $SERVICE"
echo "[deploy] Image: $IMAGE_NAME"

# Ensure project set
gcloud config set project "$PROJECT"

# Run the cloud build which uses cloudbuild.yaml present at repo root (safe-cloud-deploy.sh created earlier)
# We assume cloudbuild.yaml is configured to build and deploy. If you prefer Artifact Registry, adjust IMAGE name.

gcloud builds submit --config cloudbuild.yaml --substitutions=_SERVICE="$SERVICE",_REGION="$REGION",_IMAGE="$IMAGE_NAME" .

echo "Deploy submitted. Use 'gcloud run services describe $SERVICE --region $REGION' to view status."
