#!/bin/bash

set -e

echo "🔧 Google Cloud SDK Installation & Setup"
echo "========================================"

# Detect OS
OS="$(uname -s)"
case "${OS}" in
    Linux*)     MACHINE=Linux;;
    Darwin*)    MACHINE=Mac;;
    *)          MACHINE="UNKNOWN:${OS}"
esac

echo "Detected OS: $MACHINE"

# Install gcloud SDK if not present
if ! command -v gcloud &> /dev/null; then
    echo "📦 Installing Google Cloud SDK..."
    
    if [ "$MACHINE" == "Mac" ]; then
        # Check if Homebrew is available
        if command -v brew &> /dev/null; then
            echo "Installing via Homebrew..."
            brew install --cask google-cloud-sdk
        else
            echo "Installing Homebrew first..."
            /bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"
            echo "Now installing Google Cloud SDK..."
            brew install --cask google-cloud-sdk
        fi
    elif [ "$MACHINE" == "Linux" ]; then
        # Install on Linux
        echo "Installing on Linux..."
        
        # Add the Cloud SDK distribution URI as a package source
        echo "deb [signed-by=/usr/share/keyrings/cloud.google.gpg] https://packages.cloud.google.com/apt cloud-sdk main" | sudo tee -a /etc/apt/sources.list.d/google-cloud-sdk.list
        
        # Import the Google Cloud public key
        curl https://packages.cloud.google.com/apt/doc/apt-key.gpg | sudo apt-key --keyring /usr/share/keyrings/cloud.google.gpg add -
        
        # Update and install
        sudo apt-get update && sudo apt-get install google-cloud-sdk -y
    else
        echo "❌ Unsupported operating system. Please install gcloud manually:"
        echo "https://cloud.google.com/sdk/docs/install"
        exit 1
    fi
else
    echo "✅ Google Cloud SDK already installed"
fi

# Check Docker installation
if ! command -v docker &> /dev/null; then
    echo "❌ Docker is not installed"
    echo "Please install Docker from: https://docs.docker.com/get-docker/"
    echo "Docker is required for building container images"
    exit 1
else
    echo "✅ Docker found"
    
    # Check if Docker is running
    if ! docker info > /dev/null 2>&1; then
        echo "⚠️ Docker is installed but not running"
        echo "Please start Docker and run this script again"
        exit 1
    else
        echo "✅ Docker is running"
    fi
fi

# Initialize gcloud
echo ""
echo "🔐 Authenticating with Google Cloud..."
echo "This will open a browser window for authentication"
read -p "Press Enter to continue..."

gcloud auth login

# Check if user is authenticated
if ! gcloud auth list --filter=status:ACTIVE --format="value(account)" | head -1 > /dev/null; then
    echo "❌ Authentication failed"
    exit 1
fi

echo "✅ Successfully authenticated"

# List projects
echo ""
echo "📋 Your Google Cloud Projects:"
gcloud projects list --format="table(projectId,name,projectNumber)"

echo ""
echo "💡 If you don't have a project, create one at:"
echo "https://console.cloud.google.com/projectcreate"

echo ""
echo "✅ Setup complete! Now you can run:"
echo "   ./deploy-to-gcp.sh"
echo ""
echo "📚 Helpful commands:"
echo "   gcloud projects list                    # List your projects"
echo "   gcloud config set project PROJECT_ID   # Set default project"
echo "   gcloud auth list                       # List authenticated accounts"
echo "   gcloud version                         # Check gcloud version"
