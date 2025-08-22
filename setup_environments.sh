#!/bin/bash

# Production Environment Configuration Script
# Sets up environment-specific configurations for different deployment stages

set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Configuration
ENVIRONMENTS=("development" "staging" "production")
CONFIG_DIR="./configs"
ENV_FILE=".env"

echo -e "${BLUE}🔧 LyoBackend Environment Configuration Setup${NC}"
echo "=============================================="

# Function to print status messages
print_status() {
    case $2 in
        "success") echo -e "${GREEN}✅ $1${NC}" ;;
        "error") echo -e "${RED}❌ $1${NC}" ;;
        "warning") echo -e "${YELLOW}⚠️  $1${NC}" ;;
        *) echo -e "${BLUE}ℹ️  $1${NC}" ;;
    esac
}

# Function to prompt for input with default value
prompt_with_default() {
    local prompt="$1"
    local default="$2"
    local result
    
    read -p "$prompt [$default]: " result
    echo "${result:-$default}"
}

# Function to prompt for secure input
prompt_secure() {
    local prompt="$1"
    local result
    
    echo -n "$prompt: "
    read -s result
    echo
    echo "$result"
}

# Create configuration directory
create_config_dir() {
    print_status "Creating configuration directory..." "info"
    mkdir -p "$CONFIG_DIR"
    mkdir -p "./logs"
    mkdir -p "./models"
    mkdir -p "./uploads"
    print_status "Configuration directories created" "success"
}

# Generate secure secret key
generate_secret_key() {
    python3 -c "import secrets; print(secrets.token_urlsafe(32))"
}

# Create environment-specific configuration files
create_environment_config() {
    local env="$1"
    local config_file="$CONFIG_DIR/$env.env"
    
    print_status "Creating configuration for $env environment..." "info"
    
    # Base configuration
    cat > "$config_file" << EOF
# LyoBackend Configuration - $env Environment
# Generated on $(date)

# Environment
ENVIRONMENT=$env

# Security
SECRET_KEY=$(generate_secret_key)
JWT_SECRET_KEY=$(generate_secret_key)
JWT_ALGORITHM=HS256

# Database Configuration
EOF
    
    # Environment-specific settings
    case $env in
        "development")
            cat >> "$config_file" << EOF
DATABASE_URL=postgresql+asyncpg://lyo_user:lyo_password@localhost:5432/lyo_dev
REDIS_URL=redis://localhost:6379/0

# Debug settings
DEBUG=true
LOG_LEVEL=DEBUG

# CORS and Security (Development)
CORS_ORIGINS=["http://localhost:3000","http://127.0.0.1:3000","http://localhost:8080"]
ALLOWED_HOSTS=["localhost","127.0.0.1"]

# API Rate Limiting (Permissive for development)
API_RATE_LIMIT=1000/minute

# External API Timeouts (Longer for development)
EXTERNAL_API_TIMEOUT=60
MODEL_DOWNLOAD_TIMEOUT=600

# JWT Settings (Longer expiration for development)
JWT_ACCESS_TOKEN_EXPIRE_MINUTES=60
JWT_REFRESH_TOKEN_EXPIRE_DAYS=30

# Security Settings (Relaxed for development)
MAX_LOGIN_ATTEMPTS=10
LOCKOUT_DURATION_MINUTES=5
PASSWORD_MIN_LENGTH=6
EOF
            ;;
            
        "staging")
            cat >> "$config_file" << EOF
DATABASE_URL=postgresql+asyncpg://\${DB_USER}:\${DB_PASSWORD}@\${DB_HOST}:\${DB_PORT}/\${DB_NAME}
REDIS_URL=redis://\${REDIS_HOST}:\${REDIS_PORT}/0

# Debug settings
DEBUG=false
LOG_LEVEL=INFO

# CORS and Security (Staging)
CORS_ORIGINS=["https://staging.lyoapp.com","https://staging-admin.lyoapp.com"]
ALLOWED_HOSTS=["staging.lyoapp.com"]

# API Rate Limiting
API_RATE_LIMIT=500/minute

# External API Timeouts
EXTERNAL_API_TIMEOUT=30
MODEL_DOWNLOAD_TIMEOUT=300

# JWT Settings
JWT_ACCESS_TOKEN_EXPIRE_MINUTES=30
JWT_REFRESH_TOKEN_EXPIRE_DAYS=7

# Security Settings
MAX_LOGIN_ATTEMPTS=5
LOCKOUT_DURATION_MINUTES=15
PASSWORD_MIN_LENGTH=8
EOF
            ;;
            
        "production")
            cat >> "$config_file" << EOF
DATABASE_URL=postgresql+asyncpg://\${DB_USER}:\${DB_PASSWORD}@\${DB_HOST}:\${DB_PORT}/\${DB_NAME}
REDIS_URL=redis://\${REDIS_HOST}:\${REDIS_PORT}/0

# Debug settings
DEBUG=false
LOG_LEVEL=WARNING

# CORS and Security (Production)
CORS_ORIGINS=["https://lyoapp.com","https://app.lyoapp.com","https://admin.lyoapp.com"]
ALLOWED_HOSTS=["lyoapp.com","api.lyoapp.com"]

# API Rate Limiting (Strict)
API_RATE_LIMIT=100/minute

# External API Timeouts
EXTERNAL_API_TIMEOUT=30
MODEL_DOWNLOAD_TIMEOUT=300

# JWT Settings (Short expiration for security)
JWT_ACCESS_TOKEN_EXPIRE_MINUTES=15
JWT_REFRESH_TOKEN_EXPIRE_DAYS=7

# Security Settings (Strict)
MAX_LOGIN_ATTEMPTS=3
LOCKOUT_DURATION_MINUTES=30
PASSWORD_MIN_LENGTH=8
EOF
            ;;
    esac
    
    # Common API keys section (to be filled by setup_api_keys.sh)
    cat >> "$config_file" << EOF

# External Services (Set by setup_api_keys.sh or manually)
# AI Services
OPENAI_API_KEY=
ANTHROPIC_API_KEY=
GOOGLE_APPLICATION_CREDENTIALS=

# Push Notifications
FCM_SERVER_KEY=
APNS_KEY_ID=
APNS_TEAM_ID=
APNS_BUNDLE_ID=

# Email Services
SENDGRID_API_KEY=
SMTP_HOST=
SMTP_PORT=587
SMTP_USERNAME=
SMTP_PASSWORD=

# Monitoring and Analytics
SENTRY_DSN=
MIXPANEL_TOKEN=
GOOGLE_ANALYTICS_ID=

# File Storage (if using cloud storage)
AWS_ACCESS_KEY_ID=
AWS_SECRET_ACCESS_KEY=
AWS_S3_BUCKET=
GCS_BUCKET=

# Feature Flags (Override environment defaults if needed)
# ENABLE_AI_GENERATION=true
# ENABLE_PUSH_NOTIFICATIONS=true
# ENABLE_WEBSOCKETS=true
# ENABLE_FEEDS=true
# ENABLE_COMMUNITY=true
# ENABLE_GAMIFICATION=true

# Performance Tuning
DATABASE_POOL_SIZE=10
DATABASE_MAX_OVERFLOW=20
REDIS_MAX_CONNECTIONS=50
CELERY_WORKER_CONCURRENCY=8
WEBSOCKET_MAX_CONNECTIONS=500

# Model Configuration
MODEL_CACHE_DIR=./models
MODEL_MAX_MEMORY=4GB
MODEL_ARTIFACT_STRATEGY=huggingface  # Options: huggingface, s3, gcs, local

# Health Checks and Monitoring
ENABLE_METRICS=true
ENABLE_TRACING=true
ENABLE_HEALTH_CHECKS=true
HEALTH_CHECK_INTERVAL=30

EOF
    
    print_status "Configuration file created: $config_file" "success"
}

# Create Docker environment files
create_docker_configs() {
    print_status "Creating Docker configuration files..." "info"
    
    # Create docker-compose override for each environment
    for env in "${ENVIRONMENTS[@]}"; do
        cat > "docker-compose.$env.yml" << EOF
version: '3.8'

services:
  app:
    environment:
      - ENVIRONMENT=$env
    env_file:
      - configs/$env.env
    
  # Environment-specific overrides
  $(case $env in
    "development")
      echo "    ports:"
      echo "      - \"8000:8000\""
      echo "    volumes:"
      echo "      - .:/app"
      echo "      - ./logs:/app/logs"
      echo "      - ./models:/app/models"
      ;;
    "staging")
      echo "    # Staging-specific configurations"
      echo "    deploy:"
      echo "      replicas: 2"
      echo "      resources:"
      echo "        limits:"
      echo "          memory: 1G"
      echo "        reservations:"
      echo "          memory: 512M"
      ;;
    "production")
      echo "    # Production-specific configurations"
      echo "    deploy:"
      echo "      replicas: 3"
      echo "      resources:"
      echo "        limits:"
      echo "          memory: 2G"
      echo "        reservations:"
      echo "          memory: 1G"
      echo "    restart: unless-stopped"
      ;;
  esac)

  redis:
    $(if [ "$env" = "production" ]; then
      echo "    deploy:"
      echo "      resources:"
      echo "        limits:"
      echo "          memory: 512M"
      echo "        reservations:"
      echo "          memory: 256M"
    fi)

  celery-worker:
    environment:
      - ENVIRONMENT=$env
    env_file:
      - configs/$env.env
    $(case $env in
      "development")
        echo "    command: celery -A lyo_app.workers.celery_app worker --loglevel=debug --concurrency=2"
        ;;
      "staging")
        echo "    command: celery -A lyo_app.workers.celery_app worker --loglevel=info --concurrency=4"
        echo "    deploy:"
        echo "      replicas: 2"
        ;;
      "production")
        echo "    command: celery -A lyo_app.workers.celery_app worker --loglevel=warning --concurrency=8"
        echo "    deploy:"
        echo "      replicas: 3"
        echo "    restart: unless-stopped"
        ;;
    esac)

EOF
    done
    
    print_status "Docker configuration files created" "success"
}

# Create startup scripts for each environment
create_startup_scripts() {
    print_status "Creating startup scripts..." "info"
    
    for env in "${ENVIRONMENTS[@]}"; do
        script_name="start_${env}.sh"
        
        cat > "$script_name" << EOF
#!/bin/bash

# LyoBackend $env Environment Startup Script
set -e

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

print_status() {
    case \$2 in
        "success") echo -e "\${GREEN}✅ \$1\${NC}" ;;
        "error") echo -e "\${RED}❌ \$1\${NC}" ;;
        "warning") echo -e "\${YELLOW}⚠️  \$1\${NC}" ;;
        *) echo -e "\${BLUE}ℹ️  \$1\${NC}" ;;
    esac
}

echo -e "\${BLUE}🚀 Starting LyoBackend - $env Environment\${NC}"
echo "=========================================="

# Load environment configuration
if [ -f "configs/$env.env" ]; then
    export \$(cat configs/$env.env | grep -v '^#' | xargs)
    print_status "Loaded $env environment configuration" "success"
else
    print_status "Environment configuration not found: configs/$env.env" "error"
    exit 1
fi

# Set environment variable
export ENVIRONMENT=$env

# Validate environment
print_status "Validating environment..." "info"
python3 -c "
try:
    from lyo_app.core.environments import env_manager
    from lyo_app.core.settings import get_settings
    print(f'Environment: {env_manager.current_env}')
    print(f'Debug mode: {env_manager.get_config().debug}')
    print('✅ Environment validation passed')
except Exception as e:
    print(f'❌ Environment validation failed: {e}')
    exit(1)
"

# Database migrations (if needed)
if command -v alembic &> /dev/null; then
    print_status "Running database migrations..." "info"
    alembic upgrade head
fi

# Start the application
case "$env" in
    "development")
        print_status "Starting development server..." "info"
        python3 start_enhanced_server_v2.py
        ;;
    "staging")
        print_status "Starting staging server with Gunicorn..." "info"
        gunicorn lyo_app.enhanced_main_v2:app -w 4 -k uvicorn.workers.UvicornWorker -b 0.0.0.0:8000 --access-logfile - --error-logfile -
        ;;
    "production")
        print_status "Starting production server with Gunicorn..." "info"
        gunicorn lyo_app.enhanced_main_v2:app -w 8 -k uvicorn.workers.UvicornWorker -b 0.0.0.0:8000 --access-logfile - --error-logfile - --preload
        ;;
esac
EOF
        
        chmod +x "$script_name"
        print_status "Created startup script: $script_name" "success"
    done
}

# Create environment switcher script
create_env_switcher() {
    print_status "Creating environment switcher..." "info"
    
    cat > "switch_environment.sh" << 'EOF'
#!/bin/bash

# Environment Switcher for LyoBackend
set -e

# Colors
GREEN='\033[0;32m'
BLUE='\033[0;34m'
YELLOW='\033[1;33m'
NC='\033[0m'

ENVIRONMENTS=("development" "staging" "production")

echo -e "${BLUE}🔄 LyoBackend Environment Switcher${NC}"
echo "=================================="

# Show current environment
if [ -f ".env" ]; then
    current_env=$(grep "^ENVIRONMENT=" .env 2>/dev/null | cut -d'=' -f2 || echo "unknown")
    echo -e "Current environment: ${YELLOW}$current_env${NC}"
else
    echo "No current environment set"
fi

echo ""
echo "Available environments:"
for i in "${!ENVIRONMENTS[@]}"; do
    echo "$((i+1)). ${ENVIRONMENTS[i]}"
done

echo ""
read -p "Select environment (1-${#ENVIRONMENTS[@]}): " choice

if [[ "$choice" -ge 1 && "$choice" -le "${#ENVIRONMENTS[@]}" ]]; then
    selected_env="${ENVIRONMENTS[$((choice-1))]}"
    config_file="configs/${selected_env}.env"
    
    if [ -f "$config_file" ]; then
        cp "$config_file" ".env"
        echo -e "${GREEN}✅ Switched to $selected_env environment${NC}"
        echo "Environment configuration loaded from: $config_file"
        echo ""
        echo "You can now start the application with:"
        echo "  ./start_${selected_env}.sh"
    else
        echo -e "${YELLOW}⚠️  Configuration file not found: $config_file${NC}"
        echo "Please run ./setup_environments.sh first"
    fi
else
    echo "Invalid selection"
    exit 1
fi
EOF
    
    chmod +x "switch_environment.sh"
    print_status "Created environment switcher: switch_environment.sh" "success"
}

# Create comprehensive validation script
create_validation_script() {
    print_status "Creating environment validation script..." "info"
    
    cat > "validate_environment.sh" << 'EOF'
#!/bin/bash

# Environment Validation Script
set -e

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

print_status() {
    case $2 in
        "success") echo -e "${GREEN}✅ $1${NC}" ;;
        "error") echo -e "${RED}❌ $1${NC}" ;;
        "warning") echo -e "${YELLOW}⚠️  $1${NC}" ;;
        *) echo -e "${BLUE}ℹ️  $1${NC}" ;;
    esac
}

# Check if environment is set
if [ -z "$ENVIRONMENT" ] && [ -f ".env" ]; then
    export $(cat .env | grep -v '^#' | xargs)
fi

current_env=${ENVIRONMENT:-"unknown"}
print_status "Validating environment: $current_env" "info"

# Run Python validation
if [ -f "production_validation_v2.py" ]; then
    python3 production_validation_v2.py
else
    print_status "Production validation script not found" "error"
    exit 1
fi
EOF
    
    chmod +x "validate_environment.sh"
    print_status "Created validation script: validate_environment.sh" "success"
}

# Main execution
main() {
    echo -e "${BLUE}Starting environment setup...${NC}"
    
    create_config_dir
    
    # Create configuration files for each environment
    for env in "${ENVIRONMENTS[@]}"; do
        create_environment_config "$env"
    done
    
    create_docker_configs
    create_startup_scripts
    create_env_switcher
    create_validation_script
    
    print_status "Environment configuration setup complete!" "success"
    echo ""
    echo "📋 Next Steps:"
    echo "1. Run ./setup_api_keys.sh to configure API keys"
    echo "2. Edit configuration files in ./configs/ as needed"
    echo "3. Use ./switch_environment.sh to select an environment"
    echo "4. Start the application with ./start_[environment].sh"
    echo "5. Validate with ./validate_environment.sh"
    echo ""
    echo "📁 Created Files:"
    echo "  • ./configs/development.env"
    echo "  • ./configs/staging.env" 
    echo "  • ./configs/production.env"
    echo "  • ./docker-compose.development.yml"
    echo "  • ./docker-compose.staging.yml"
    echo "  • ./docker-compose.production.yml"
    echo "  • ./start_development.sh"
    echo "  • ./start_staging.sh"
    echo "  • ./start_production.sh"
    echo "  • ./switch_environment.sh"
    echo "  • ./validate_environment.sh"
}

# Execute main function
main
