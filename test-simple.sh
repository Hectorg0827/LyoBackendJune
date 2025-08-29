#!/bin/bash

# Quick Test Script for LyoBackend Phase 3 Simple Deployment
# Tests the minimal setup locally before cloud deployment

set -e

echo "🧪 Testing LyoBackend Phase 3 Simple Setup..."

# Build test image
echo "🏗️ Building test Docker image..."
docker build -f Dockerfile.simple -t lyobackend-test .

# Run container for testing
echo "🚀 Starting test container..."
docker run -d --name lyobackend-test-container \
  -p 8001:8000 \
  -e ENVIRONMENT=testing \
  lyobackend-test

# Wait for startup
echo "⏳ Waiting for application to start..."
sleep 10

# Test health endpoint
echo "🏥 Testing health endpoint..."
if curl -f http://localhost:8001/health; then
    echo "✅ Health check passed!"
else
    echo "❌ Health check failed!"
    docker logs lyobackend-test-container
    docker stop lyobackend-test-container
    docker rm lyobackend-test-container
    exit 1
fi

# Test main endpoint
echo "🔍 Testing main API endpoint..."
if curl -f http://localhost:8001/; then
    echo "✅ Main endpoint responded!"
else
    echo "❌ Main endpoint failed!"
    docker logs lyobackend-test-container
    docker stop lyobackend-test-container
    docker rm lyobackend-test-container
    exit 1
fi

# Clean up
echo "🧹 Cleaning up test container..."
docker stop lyobackend-test-container
docker rm lyobackend-test-container

echo ""
echo "✅ All tests passed! Ready for cloud deployment."
echo ""
echo "🚀 To deploy to cloud, run:"
echo "./deploy-simple.sh [your-project-id]"
