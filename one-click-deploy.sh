#!/bin/bash

# 🎯 One-Click Cloud Run Deployment for LyoBackend
# This script will automatically deploy your backend to Google Cloud Run

set -e

echo "🚀 LyoBackend - Automatic Cloud Run Deployment"
echo "==============================================="
echo ""
echo "This will automatically:"
echo "✅ Set up Google Cloud SDK"
echo "✅ Build and deploy your backend"
echo "✅ Create database and secrets"
echo "✅ Test the deployment"
echo ""

read -p "Ready to deploy to Google Cloud Run? (y/n): " -n 1 -r
echo ""
if [[ ! $REPLY =~ ^[Yy]$ ]]; then
    echo "Deployment cancelled."
    exit 1
fi

echo ""
echo "🔧 Step 1: Setting up Google Cloud SDK..."
./setup-gcp.sh

echo ""
echo "🚀 Step 2: Deploying to Cloud Run..."
./deploy-to-gcp.sh

# Get the service URL from deployment config if it exists
if [ -f "deployment-config.txt" ]; then
    SERVICE_URL=$(grep "Service URL:" deployment-config.txt | cut -d' ' -f3-)
    if [ ! -z "$SERVICE_URL" ]; then
        echo ""
        echo "🧪 Step 3: Testing deployment..."
        python3 test_cloud_deployment.py "$SERVICE_URL"
        
        echo ""
        echo "🎉 Deployment Complete!"
        echo "======================="
        echo "Your LyoBackend is now live at:"
        echo "🌐 $SERVICE_URL"
        echo "📚 API Docs: $SERVICE_URL/docs"
        echo ""
        echo "🎯 Next Steps:"
        echo "1. Update your mobile app to use: $SERVICE_URL"
        echo "2. Monitor: ./monitor_deployment.py lyo-backend us-central1"
        echo "3. View logs: gcloud run logs read --service=lyo-backend"
    fi
else
    echo ""
    echo "⚠️ Could not find deployment configuration."
    echo "Please check the deployment logs above."
fi

echo ""
echo "🎊 Your backend is now running on Google Cloud Run!"
