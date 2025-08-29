#!/bin/bash
# setup_unified.sh - Setup script for LyoBackend unified architecture

set -e  # Exit immediately if a command exits with a non-zero status

# Print colored output
GREEN='\033[0;32m'
YELLOW='\033[0;33m'
RED='\033[0;31m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

echo -e "${BLUE}====================================================${NC}"
echo -e "${BLUE}  LyoBackend Unified Architecture Setup Script      ${NC}"
echo -e "${BLUE}====================================================${NC}"

# Check if Python is installed
if ! command -v python3 &> /dev/null; then
    echo -e "${RED}Error: Python 3 is not installed. Please install Python 3 and try again.${NC}"
    exit 1
fi

# Check Python version
PYTHON_VERSION=$(python3 --version | awk '{print $2}')
echo -e "${GREEN}Python version: ${PYTHON_VERSION}${NC}"

# Create virtual environment
echo -e "${YELLOW}Creating virtual environment...${NC}"
if [ -d ".venv" ]; then
    echo -e "${YELLOW}Virtual environment already exists. Skipping creation.${NC}"
else
    python3 -m venv .venv
    echo -e "${GREEN}✓ Virtual environment created${NC}"
fi

# Activate virtual environment
echo -e "${YELLOW}Activating virtual environment...${NC}"
source .venv/bin/activate
echo -e "${GREEN}✓ Virtual environment activated${NC}"

# Install requirements
echo -e "${YELLOW}Installing dependencies...${NC}"
pip install --upgrade pip
if [ -f "requirements.txt" ]; then
    pip install -r requirements.txt
    echo -e "${GREEN}✓ Dependencies installed${NC}"
else
    echo -e "${RED}Error: requirements.txt not found${NC}"
    exit 1
fi

# Create environment file from template if it doesn't exist
if [ ! -f ".env" ]; then
    echo -e "${YELLOW}Creating .env file from template...${NC}"
    if [ -f ".env.unified.template" ]; then
        cp .env.unified.template .env
        echo -e "${GREEN}✓ Created .env file from template${NC}"
    else
        echo -e "${YELLOW}Template not found. Creating basic .env file...${NC}"
        cat > .env << EOL
# Environment variables for LyoBackend unified architecture
ENV=development
DATABASE_URL=sqlite:///./lyo_app_dev.db
SECRET_KEY=development-secret-key-please-change-in-production
LOG_LEVEL=debug
ALLOWED_ORIGINS=*
EOL
        echo -e "${GREEN}✓ Created basic .env file${NC}"
    fi
else
    echo -e "${YELLOW}Environment file already exists. Skipping creation.${NC}"
fi

# Run database migrations if available
if [ -d "migrations" ]; then
    echo -e "${YELLOW}Running database migrations...${NC}"
    export PYTHONPATH=$PYTHONPATH:$(pwd)
    alembic upgrade head
    echo -e "${GREEN}✓ Database migrations completed${NC}"
fi

echo -e "${GREEN}=====================================${NC}"
echo -e "${GREEN}  Setup completed successfully!      ${NC}"
echo -e "${GREEN}=====================================${NC}"
echo -e ""
echo -e "${BLUE}Next steps:${NC}"
echo -e "1. Edit the .env file with your specific configuration"
echo -e "2. Start the application with: ${YELLOW}./start_unified.py${NC}"
echo -e "3. Run tests with: ${YELLOW}./test_unified_architecture.py${NC}"
echo -e ""
echo -e "For more information, see the ${YELLOW}UNIFIED_ARCHITECTURE_README.md${NC} file."
