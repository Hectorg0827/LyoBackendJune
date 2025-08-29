#!/bin/bash

# Start Docker Desktop on macOS
# This script helps start Docker if it's not running

echo "🐳 Starting Docker Desktop..."

# Check if Docker Desktop is installed
if [ ! -d "/Applications/Docker.app" ]; then
    echo "❌ Docker Desktop not found in Applications folder"
    echo "📥 Please install Docker Desktop from: https://www.docker.com/products/docker-desktop"
    exit 1
fi

# Start Docker Desktop
echo "🚀 Launching Docker Desktop..."
open -a Docker

echo "⏳ Waiting for Docker to start..."
echo "   This may take 30-60 seconds..."

# Wait for Docker daemon to be available
for i in {1..30}; do
    if docker info >/dev/null 2>&1; then
        echo "✅ Docker is now running!"
        echo ""
        echo "🧪 You can now run local tests:"
        echo "   ./test-simple.sh"
        echo ""
        echo "☁️ Or deploy directly to cloud:"
        echo "   ./direct-deploy.sh YOUR_PROJECT_ID"
        exit 0
    fi
    echo "   Waiting... ($i/30)"
    sleep 2
done

echo "⚠️  Docker is taking longer than expected to start"
echo "💡 You can:"
echo "   1. Wait a bit more and try: docker info"
echo "   2. Skip local testing and deploy directly: ./direct-deploy.sh YOUR_PROJECT_ID"
echo "   3. Check Docker Desktop manually"
