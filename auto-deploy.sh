#!/bin/bash
# Automatic One-Click Deployment to Google Cloud Shell
# This creates a complete deployment script that you can run in Cloud Shell

echo "🚀 Creating automatic deployment for Google Cloud Shell..."

# Open the deployment instructions
open google-cloud-shell-deploy.txt

# Also display quick instructions
echo ""
echo "=================================="
echo "🎯 QUICK DEPLOYMENT STEPS:"
echo "=================================="
echo ""
echo "1. 📂 Upload your LyoBackend-Deploy.zip to Google Drive"
echo "   - Go to https://drive.google.com"
echo "   - Upload: LyoBackend-Deploy.zip (1.4M)"
echo "   - Get shareable link"
echo ""
echo "2. 🖥️  Open Google Cloud Shell"
echo "   - Go to https://console.cloud.google.com"
echo "   - Click Cloud Shell icon (⚡)"
echo ""
echo "3. 📋 Copy & paste the commands from: google-cloud-shell-deploy.txt"
echo "   - Set your PROJECT_ID"
echo "   - Run all commands in sequence"
echo ""
echo "4. ✅ Your backend will be live in 5-10 minutes!"
echo ""
echo "🎊 No more computer crashes - everything runs in Google's cloud!"
echo "=================================="
echo ""

# Create a quick reference card
cat > QUICK_DEPLOY_REFERENCE.md << 'EOF'
# 🚀 LyoBackend Quick Deployment Reference

## Files Ready:
- ✅ `LyoBackend-Deploy.zip` (1.4M) - Your packaged backend
- ✅ `google-cloud-shell-deploy.txt` - Complete deployment commands
- ✅ `minimal-deploy.sh` - Safe local deployment option

## Deployment Options:

### Option 1: Google Cloud Shell (Recommended - No Crashes)
1. Upload `LyoBackend-Deploy.zip` to Google Drive
2. Open Google Cloud Shell
3. Copy commands from `google-cloud-shell-deploy.txt`
4. Paste and run in Cloud Shell
5. Get your live URL in 10 minutes!

### Option 2: GitHub + Cloud Shell
```bash
# In Cloud Shell:
git clone https://github.com/Hectorg0827/LyoBackendJune.git
cd LyoBackendJune
chmod +x minimal-deploy.sh
./minimal-deploy.sh your-project-id
```

### Option 3: Direct Cloud Shell Upload
1. Open Cloud Shell
2. Click "Upload file" (three dots menu)
3. Upload `LyoBackend-Deploy.zip`
4. Extract and run deployment

## Expected Result:
- 🌐 Live URL: `https://lyo-backend-xxxxx-uc.a.run.app`
- 📱 Use this URL in your iOS app instead of `localhost:8001`
- 🔍 Test: `/health`, `/docs`, `/api/v1/generate-course`

## iOS Integration:
Replace all instances of `localhost:8001` with your Cloud Run URL.

## Why This Method Works:
- ❌ No local Docker builds (prevents crashes)
- ✅ Google's infrastructure handles everything
- ✅ Scalable and production-ready
- ✅ Free tier available
EOF

echo "📝 Created QUICK_DEPLOY_REFERENCE.md for easy reference"
echo ""
echo "🎉 Everything is ready! Choose your deployment method and go live!"
