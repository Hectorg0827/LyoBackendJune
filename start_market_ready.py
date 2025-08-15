#!/usr/bin/env python3
"""
LyoApp Market-Ready Backend Runner
==================================

Starts the complete market-ready backend system with all features.
"""

import os
import sys
import subprocess
import time
from pathlib import Path

def print_banner():
    """Print startup banner."""
    print("\n" + "="*60)
    print("🚀 LyoApp Market-Ready Backend")
    print("="*60)
    print("📚 Educational Platform Backend")
    print("🎯 Production-Grade Architecture")
    print("☁️  Google Cloud Ready")
    print("🤖 AI-Powered Learning")
    print("="*60 + "\n")

def check_requirements():
    """Check if required packages are installed."""
    required_packages = ["fastapi", "uvicorn"]
    missing_packages = []
    
    for package in required_packages:
        try:
            __import__(package)
        except ImportError:
            missing_packages.append(package)
    
    if missing_packages:
        print("❌ Missing required packages:")
        for package in missing_packages:
            print(f"   - {package}")
        
        print("\n🔧 Installing missing packages...")
        try:
            subprocess.check_call([
                sys.executable, "-m", "pip", "install", 
                "fastapi", "uvicorn[standard]", "python-multipart"
            ])
            print("✅ Packages installed successfully!")
        except subprocess.CalledProcessError as e:
            print(f"❌ Failed to install packages: {e}")
            return False
    
    return True

def start_server():
    """Start the backend server."""
    print("🌟 Starting LyoApp Backend Server...")
    print("📖 API Documentation: http://localhost:8000/v1/docs")
    print("🔍 Health Check: http://localhost:8000/health")
    print("📊 System Status: http://localhost:8000/ready")
    print("\n💡 Features Available:")
    print("   ✅ Authentication & Authorization")
    print("   ✅ Media Management (GCS Integration)")
    print("   ✅ AI-Powered Tutoring System")
    print("   ✅ Course Planning & Recommendations") 
    print("   ✅ Advanced Search & Discovery")
    print("   ✅ Real-time Messaging")
    print("   ✅ Gamification & Leaderboards")
    print("   ✅ Content Moderation")
    print("   ✅ Analytics & Monitoring")
    print("   ✅ Admin Dashboard")
    print("\n🚀 Server starting on http://localhost:8000")
    print("Press Ctrl+C to stop the server\n")
    
    # Start uvicorn server
    try:
        import uvicorn
        uvicorn.run(
            "simple_main:app",
            host="0.0.0.0",
            port=8000,
            reload=True,
            log_level="info",
            access_log=True,
        )
    except KeyboardInterrupt:
        print("\n\n👋 LyoApp Backend stopped gracefully")
        print("Thank you for using LyoApp!")
    except Exception as e:
        print(f"\n❌ Error starting server: {e}")
        sys.exit(1)

def main():
    """Main entry point."""
    print_banner()
    
    # Change to script directory
    os.chdir(Path(__file__).parent)
    
    # Check requirements
    if not check_requirements():
        sys.exit(1)
    
    # Start server
    start_server()

if __name__ == "__main__":
    main()
