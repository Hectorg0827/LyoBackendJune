#!/usr/bin/env python3
"""
LyoBackendJune Installation and Setup Script
Automates the setup process for development and production environments.
"""

import os
import sys
import subprocess
import asyncio
from pathlib import Path
from typing import List, Dict, Any
import json

class LyoBackendSetup:
    """Setup manager for LyoBackendJune."""
    
    def __init__(self, environment: str = "development"):
        self.environment = environment
        self.project_root = Path(__file__).parent
        self.requirements_installed = False
        
    def run_setup(self):
        """Run the complete setup process."""
        print("🚀 Starting LyoBackendJune setup...")
        print(f"📋 Environment: {self.environment}")
        print("-" * 50)
        
        try:
            # Step 1: Check Python version
            self.check_python_version()
            
            # Step 2: Install dependencies (if not skipped)
            if not self.requirements_installed:
                self.install_dependencies()
            else:
                print("📦 Skipping dependency installation...")
            
            # Step 3: Setup environment file
            self.setup_environment()
            
            # Step 4: Setup database
            self.setup_database()
            
            # Step 5: Run migrations
            self.run_migrations()
            
            # Step 6: Setup Redis (optional)
            self.setup_redis()
            
            # Step 7: Validate setup
            self.validate_setup()
            
            print("\n✅ Setup completed successfully!")
            print("\n📖 Next steps:")
            print("1. Add your API keys to .env file")
            print("2. Start the server: python start_server.py")
            print("3. Visit http://localhost:8000/docs for API documentation")
            
        except Exception as e:
            print(f"\n❌ Setup failed: {e}")
            sys.exit(1)
    
    def check_python_version(self):
        """Check if Python version is compatible."""
        print("🐍 Checking Python version...")
        
        version = sys.version_info
        if version.major != 3 or version.minor < 9:
            raise Exception(f"Python 3.9+ required, but found {version.major}.{version.minor}")
        
        print(f"✅ Python {version.major}.{version.minor}.{version.micro} found")
    
    def install_dependencies(self):
        """Install Python dependencies."""
        print("📦 Installing dependencies...")
        
        try:
            # Install from requirements.txt
            subprocess.run([
                sys.executable, "-m", "pip", "install", "-r", "requirements.txt"
            ], check=True, capture_output=True, text=True)
            
            self.requirements_installed = True
            print("✅ Dependencies installed successfully")
            
        except subprocess.CalledProcessError as e:
            print(f"❌ Failed to install dependencies: {e}")
            print(f"Error output: {e.stderr}")
            raise
    
    def setup_environment(self):
        """Setup environment configuration."""
        print("🔧 Setting up environment configuration...")
        
        env_file = self.project_root / ".env"
        env_example = self.project_root / ".env.example"
        
        if env_file.exists():
            print("⚠️  .env file already exists, skipping creation")
            return
        
        if not env_example.exists():
            print("⚠️  .env.example not found, creating basic .env")
            self.create_basic_env_file(env_file)
        else:
            # Copy from example
            import shutil
            shutil.copy(env_example, env_file)
            print("✅ Created .env from .env.example")
        
        print("📝 Please edit .env file with your configuration")
    
    def create_basic_env_file(self, env_file: Path):
        """Create a basic .env file."""
        content = f"""# LyoBackendJune Environment Configuration
# Environment
DEBUG=true
ENVIRONMENT={self.environment}

# Database
DATABASE_URL=sqlite+aiosqlite:///./lyo_app_dev.db
DATABASE_ECHO=false

# Security
SECRET_KEY={"your-very-secure-secret-key-" + os.urandom(16).hex()}
ALGORITHM=HS256
ACCESS_TOKEN_EXPIRE_MINUTES=30

# Redis
REDIS_URL=redis://localhost:6379/0
CELERY_BROKER_URL=redis://localhost:6379/1
CELERY_RESULT_BACKEND=redis://localhost:6379/2

# API Keys (Add your actual keys here)
YOUTUBE_API_KEY=your-youtube-api-key-here
GEMINI_API_KEY=your-gemini-api-key-here

# Email Configuration
SMTP_SERVER=smtp.gmail.com
SMTP_PORT=587
SMTP_USERNAME=your-email@gmail.com
SMTP_PASSWORD=your-app-password
SMTP_FROM_EMAIL=noreply@lyoapp.com
SMTP_USE_TLS=true

# File Upload
MAX_FILE_SIZE=10485760
UPLOAD_DIR=uploads
"""
        env_file.write_text(content)
    
    def setup_database(self):
        """Setup database configuration."""
        print("🗄️  Setting up database...")
        
        # Create uploads directory
        uploads_dir = self.project_root / "uploads"
        uploads_dir.mkdir(exist_ok=True)
        print("✅ Created uploads directory")
        
        # For SQLite, just ensure the directory exists
        db_path = self.project_root / "lyo_app_dev.db"
        if not db_path.exists():
            print("✅ Database will be created on first run")
        else:
            print("✅ Database file already exists")
    
    def run_migrations(self):
        """Run database migrations."""
        print("🔄 Running database migrations...")
        
        try:
            # Initialize alembic if not already done
            alembic_dir = self.project_root / "alembic"
            if not alembic_dir.exists():
                subprocess.run([
                    sys.executable, "-m", "alembic", "init", "alembic"
                ], check=True, capture_output=True)
                print("✅ Initialized Alembic")
            
            # Run migrations
            subprocess.run([
                sys.executable, "-m", "alembic", "upgrade", "head"
            ], check=True, capture_output=True)
            
            print("✅ Database migrations completed")
            
        except subprocess.CalledProcessError as e:
            print(f"⚠️  Migration warning: {e}")
            print("You may need to run migrations manually later")
    
    def setup_redis(self):
        """Setup Redis connection (optional)."""
        print("🔴 Checking Redis connection...")
        
        try:
            import redis
            r = redis.Redis(host='localhost', port=6379, db=0)
            r.ping()
            print("✅ Redis connection successful")
        except Exception as e:
            print(f"⚠️  Redis not available: {e}")
            print("📝 Install Redis for caching and background jobs:")
            print("   - macOS: brew install redis")
            print("   - Ubuntu: sudo apt-get install redis-server")
            print("   - Docker: docker run -d -p 6379:6379 redis:alpine")
    
    def validate_setup(self):
        """Validate the setup by importing key modules."""
        print("🔍 Validating setup...")
        
        if not self.requirements_installed:
            print("⚠️  Dependencies not installed, skipping validation")
            return
        
        try:
            # Test imports
            from lyo_app.main import app
            from lyo_app.core.config import settings
            from lyo_app.core.database import engine
            
            print("✅ Core modules import successfully")
            print(f"✅ Configuration loaded (environment: {settings.environment})")
            
        except ImportError as e:
            print(f"⚠️  Import warning: {e}")
            print("Some modules may not be available until dependencies are properly installed")
    
    def generate_api_keys_guide(self):
        """Generate a guide for obtaining API keys."""
        guide = """
📋 API Keys Setup Guide
======================

Required APIs for LyoBackendJune:

1. 🎥 YouTube Data API v3
   - Website: https://console.cloud.google.com/
   - Steps: Create project → Enable YouTube Data API v3 → Create API key
   - Free Tier: 10,000 quota units/day
   - Add to .env: YOUTUBE_API_KEY=your_key_here

2. 🤖 OpenAI API
   - Website: https://platform.openai.com/
   - Steps: Create account → Generate API key
   - Add to .env: OPENAI_API_KEY=your_key_here

3. 🔮 Anthropic API (Optional)
   - Website: https://console.anthropic.com/
   - Steps: Create account → Generate API key
   - Add to .env: ANTHROPIC_API_KEY=your_key_here

4. 🌟 Google Gemini API (Optional)
   - Website: https://makersuite.google.com/
   - Steps: Create account → Get API key
   - Add to .env: GEMINI_API_KEY=your_key_here

5. 📧 Email Configuration
   - Gmail: Enable 2FA → Generate App Password
   - Add to .env: SMTP_USERNAME and SMTP_PASSWORD

💡 Start with YouTube and OpenAI APIs for core functionality.
"""
        
        guide_file = self.project_root / "API_SETUP_GUIDE.md"
        guide_file.write_text(guide)
        print(f"✅ Created {guide_file}")
        
        return guide


def main():
    """Main setup function."""
    import argparse
    
    parser = argparse.ArgumentParser(description="LyoBackendJune Setup Script")
    parser.add_argument(
        "--environment", 
        choices=["development", "production"], 
        default="development",
        help="Environment to setup for"
    )
    parser.add_argument(
        "--skip-deps", 
        action="store_true",
        help="Skip dependency installation"
    )
    parser.add_argument(
        "--api-guide",
        action="store_true", 
        help="Generate API keys setup guide only"
    )
    
    args = parser.parse_args()
    
    setup = LyoBackendSetup(args.environment)
    
    if args.api_guide:
        print(setup.generate_api_keys_guide())
        return
    
    if args.skip_deps:
        setup.requirements_installed = True
    
    setup.run_setup()


if __name__ == "__main__":
    main()
