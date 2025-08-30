#!/bin/bash
# 🚀 Deploy Power Users to Production
# Builds and deploys updated backend with 20 power users

set -e

echo "🌟 DEPLOYING POWER USERS TO PRODUCTION"
echo "========================================"

# Check if database exists
if [ ! -f "lyo_app_dev.db" ]; then
    echo "❌ Database not found. Please run the power users script first."
    exit 1
fi

# Verify power users exist
POWER_USER_COUNT=$(sqlite3 lyo_app_dev.db "SELECT COUNT(*) FROM users WHERE email LIKE '%@company.com'")
echo "📊 Found ${POWER_USER_COUNT} power users in database"

if [ "$POWER_USER_COUNT" -eq 0 ]; then
    echo "❌ No power users found. Please run quick_power_users.py first."
    exit 1
fi

# Build Docker image with power users
echo ""
echo "🐳 Building Docker image with power users..."
docker build -t lyo-backend-with-power-users -f Dockerfile.seeded . --no-cache

# Tag for Google Cloud Registry
echo ""
echo "🏷️  Tagging image for Google Cloud Registry..."
docker tag lyo-backend-with-power-users gcr.io/lyobackend/lyo-backend-power-users:latest

# Push to Google Cloud Registry
echo ""
echo "☁️  Pushing to Google Cloud Registry..."
docker push gcr.io/lyobackend/lyo-backend-power-users:latest

# Deploy to Cloud Run
echo ""
echo "🚀 Deploying to Cloud Run..."
gcloud run deploy lyo-backend-power-users \
    --image=gcr.io/lyobackend/lyo-backend-power-users:latest \
    --region=us-central1 \
    --allow-unauthenticated \
    --memory=2Gi \
    --cpu=1 \
    --max-instances=10 \
    --set-env-vars="GCS_BUCKET_NAME=lyobackend-storage,DATABASE_URL=sqlite+aiosqlite:///./lyo_app_dev.db,SECRET_KEY=P9tr2ptj1LZxVYmeygu6GbVWicoiU3058pbL+ZmcaMY=,JWT_SECRET_KEY=P9tr2ptj1LZxVYmeygu6GbVWicoiU3058pbL+ZmcaMY="

echo ""
echo "✅ DEPLOYMENT COMPLETE!"
echo "========================================"
echo "🌟 Power Users Backend is now live!"
echo ""
echo "📊 POWER USER STATISTICS:"
echo "   Total Power Users: ${POWER_USER_COUNT}"
echo "   Password: PowerUser123!"
echo ""
echo "🧪 TEST POWER USERS:"
sqlite3 lyo_app_dev.db "SELECT '   📧 ' || email FROM users WHERE email LIKE '%@company.com' LIMIT 5"
echo ""
echo "🔗 NEXT STEPS:"
echo "   1. Test power user login at Cloud Run URL"
echo "   2. Verify rich bios and verified status"
echo "   3. Update frontend to use new backend URL"
echo "   4. Share power user credentials with team"
echo ""
