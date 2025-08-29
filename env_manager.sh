#!/bin/bash

# Environment Manager Script
# Usage: ./env_manager.sh [development|staging|production|test]

set -e

ENVIRONMENT=${1:-development}

echo "Switching to $ENVIRONMENT environment..."

# Backup current .env if it exists
if [ -f ".env" ]; then
    cp .env .env.backup
    echo "Backed up current .env to .env.backup"
fi

# Copy the appropriate environment file
if [ -f ".env.$ENVIRONMENT" ]; then
    cp ".env.$ENVIRONMENT" .env
    echo "Switched to $ENVIRONMENT environment"
else
    echo "Error: .env.$ENVIRONMENT file not found"
    exit 1
fi

echo "Environment switched successfully!"
echo "Current DATABASE_URL: $(grep DATABASE_URL .env | cut -d'=' -f2)"
