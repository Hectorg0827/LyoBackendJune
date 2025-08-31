#!/bin/bash

echo "🚀 Deploying Superior AI Backend to Cloud Run"
echo "🎯 Target: https://lyo-backend-830162750094.us-central1.run.app"

# Extract project info from the URL
# The URL format is: https://SERVICE_NAME-PROJECT_NUMBER.REGION.run.app
# We need to find the actual project ID

echo "🔍 Finding correct project ID..."

# Try to get project ID from the project number
PROJECT_NUMBER="830162750094"
PROJECT_ID=""

# Method 1: Try to get it from gcloud projects list
echo "Checking available projects..."
PROJECTS_OUTPUT=$(gcloud projects list --format="csv[no-header](projectId,projectNumber)" 2>/dev/null)

if [ ! -z "$PROJECTS_OUTPUT" ]; then
    echo "Available projects:"
    echo "$PROJECTS_OUTPUT"
    
    # Find the project ID for our project number
    PROJECT_ID=$(echo "$PROJECTS_OUTPUT" | grep "$PROJECT_NUMBER" | cut -d',' -f1)
    
    if [ ! -z "$PROJECT_ID" ]; then
        echo "✅ Found Project ID: $PROJECT_ID for Project Number: $PROJECT_NUMBER"
    else
        echo "❌ Could not find project ID for project number: $PROJECT_NUMBER"
        echo ""
        echo "🔧 Manual Setup Required:"
        echo "1. Find your project ID with: gcloud projects list"
        echo "2. Look for project number: $PROJECT_NUMBER"
        echo "3. Use the corresponding projectId"
        echo "4. Run: gcloud config set project YOUR_ACTUAL_PROJECT_ID"
        echo "5. Then run: ./simple_gcr_deploy.sh"
        exit 1
    fi
else
    echo "❌ Could not list projects. Please ensure you're authenticated:"
    echo "gcloud auth login"
    exit 1
fi

# Deploy using the found project ID
echo "🚀 Deploying with Project ID: $PROJECT_ID"

gcloud run deploy lyo-backend \
  --source . \
  --region us-central1 \
  --platform managed \
  --allow-unauthenticated \
  --port 8080 \
  --memory 2Gi \
  --cpu 2 \
  --min-instances 1 \
  --max-instances 10 \
  --timeout 300 \
  --project "$PROJECT_ID" \
  --set-env-vars "ENABLE_SUPERIOR_AI_MODE=true,ENABLE_ADAPTIVE_DIFFICULTY=true,ENABLE_ADVANCED_SOCRATIC=true"

if [ $? -eq 0 ]; then
    echo ""
    echo "🎉 SUCCESS: Superior AI Backend deployed!"
    echo "🌐 URL: https://lyo-backend-$PROJECT_NUMBER.us-central1.run.app"
    echo ""
    echo "🧪 Test your Superior AI features:"
    echo "curl https://lyo-backend-$PROJECT_NUMBER.us-central1.run.app/health"
    echo ""
    echo "🎯 Superior AI Features Now Live:"
    echo "  ✅ Advanced Socratic Questioning (6 strategies)"
    echo "  ✅ Adaptive Difficulty Engine (5 levels)"
    echo "  ✅ Superior Prompt Engineering System"
    echo "  ✅ Multi-dimensional Learning Analytics"
else
    echo "❌ Deployment failed. Check the error messages above."
    exit 1
fi
