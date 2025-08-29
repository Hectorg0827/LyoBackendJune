#!/bin/bash

# Quick Docker Test and Build Script
echo "Testing Docker and building LyoBackend with Power Users..."

# Test Docker
echo "1. Testing Docker availability..."
docker --version 2>/dev/null || { echo "Docker not available, please start Docker Desktop"; exit 1; }

# Verify files
echo "2. Verifying required files..."
ls -la lyo_app_dev.db simple_main.py requirements-minimal.txt .env

# Create minimal Dockerfile
echo "3. Creating optimized Dockerfile..."
cat > Dockerfile.gcr-optimized << 'EOF'
FROM python:3.11-slim
WORKDIR /app
RUN apt-get update && apt-get install -y gcc && rm -rf /var/lib/apt/lists/*
COPY requirements-minimal.txt .
RUN pip install -r requirements-minimal.txt
COPY . .
RUN mkdir -p uploads && echo "Setup complete"
EXPOSE 8080
ENV PORT=8080
CMD ["python", "simple_main.py"]
EOF

echo "4. Building Docker image..."
docker build -t lyo-backend-gcr -f Dockerfile.gcr-optimized . || { echo "Build failed"; exit 1; }

echo "5. Success! Image built: lyo-backend-gcr"
echo "Next steps:"
echo "  - Tag for GCR: docker tag lyo-backend-gcr gcr.io/lyobackend/lyo-backend-power-users:latest"
echo "  - Push to GCR: docker push gcr.io/lyobackend/lyo-backend-power-users:latest"
echo "  - Deploy to Cloud Run: gcloud run deploy ..."
