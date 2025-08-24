#!/usr/bin/env python3
"""
AI Study Mode Startup Script
Quick deployment verification and server startup
"""

import sys
import os
import subprocess

def check_dependencies():
    """Check if required dependencies are installed"""
    
    print("🔍 Checking dependencies...")
    
    required_packages = [
        "fastapi",
        "uvicorn", 
        "sqlalchemy",
        "pydantic",
        "asyncpg"
    ]
    
    optional_packages = [
        "aiohttp",  # For AI resilience
        "google-generativeai",   # For Google Gemini integration
    ]
    
    missing_required = []
    missing_optional = []
    
    for package in required_packages:
        try:
            __import__(package)
            print(f"✅ {package}")
        except ImportError:
            missing_required.append(package)
            print(f"❌ {package} (REQUIRED)")
    
    for package in optional_packages:
        try:
            __import__(package)
            print(f"✅ {package}")
        except ImportError:
            missing_optional.append(package)
            print(f"⚠️  {package} (optional for AI features)")
    
    if missing_required:
        print(f"\n🚨 Missing required packages: {', '.join(missing_required)}")
        print("Install with: pip install " + " ".join(missing_required))
        return False
    
        if missing_optional:
            print(f"\n⚠️  Missing optional packages: {', '.join(missing_optional)}")
            print("For full AI features, install with: pip install " + " ".join(missing_optional))
        
    print("\n✅ Core dependencies satisfied!")
    return True

def check_ai_study_implementation():
    """Verify AI Study Mode implementation"""
    
    print("\n🤖 Checking AI Study Mode implementation...")
    
    try:
        # Test core config
        from lyo_app.core.config import settings
        print("✅ Core configuration")
        
        # Test AI study models  
        sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
        from lyo_app.ai_study.models import StudySession, StudyMessage, GeneratedQuiz
        print("✅ AI Study Mode database models")
        
        # Test clean routes
        from lyo_app.ai_study.clean_routes import router
        print("✅ Clean API routes")
        
        # Test monitoring
        from lyo_app.core.monitoring import monitor_request
        print("✅ Request monitoring")
        
        print("\n🎯 AI Study Mode implementation verified!")
        
        print("\n📋 Available endpoints:")
        print("  • POST /api/v1/ai/study-session")
        print("  • POST /api/v1/ai/generate-quiz") 
        print("  • POST /api/v1/ai/analyze-answer")
        
        return True
        
    except Exception as e:
        print(f"❌ Implementation check failed: {e}")
        return False

def start_server():
    """Start the LyoBackend server"""
    
    print("\n🚀 Starting LyoBackend server...")
    
    try:
        # Try to start using the existing start_server.py
        if os.path.exists("start_server.py"):
            print("Using start_server.py...")
            subprocess.run([sys.executable, "start_server.py"])
        else:
            print("Using uvicorn directly...")
            subprocess.run([
                sys.executable, "-m", "uvicorn", 
                "lyo_app.main:app", 
                "--host", "0.0.0.0", 
                "--port", "8000",
                "--reload"
            ])
            
    except KeyboardInterrupt:
        print("\n🛑 Server stopped by user")
    except Exception as e:
        print(f"❌ Failed to start server: {e}")

def main():
    """Main startup flow"""
    
    print("🔧 LyoBackend AI Study Mode - Startup Script")
    print("=" * 50)
    
    # Check dependencies
    if not check_dependencies():
        print("\n🚨 Please install missing dependencies before continuing")
        return False
    
    # Check implementation
    if not check_ai_study_implementation():
        print("\n🚨 AI Study Mode implementation has issues")
        return False
    
    print("\n" + "=" * 50)
    print("🎉 All checks passed! AI Study Mode is ready!")
    print("=" * 50)
    
    # Ask user if they want to start the server
    try:
        response = input("\nStart the server now? (y/n): ").lower().strip()
        if response in ['y', 'yes']:
            start_server()
        else:
            print("\n✅ Ready to deploy when you are!")
            print("\nTo start manually:")
            print("  python3 start_server.py")
            print("  or")
            print("  uvicorn lyo_app.main:app --host 0.0.0.0 --port 8000 --reload")
            
    except KeyboardInterrupt:
        print("\n\n✅ Setup complete!")
    
    return True

if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
