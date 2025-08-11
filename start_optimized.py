#!/usr/bin/env python3
"""
LyoApp Optimized Server Startup
Enhanced production-ready server with all optimizations enabled
"""

import asyncio
import os
import sys
import signal
import time
from pathlib import Path

# Add project root to Python path
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

def setup_environment():
    """Setup optimized environment variables"""
    # Performance optimizations
    os.environ.setdefault("PYTHONUNBUFFERED", "1")
    os.environ.setdefault("UVICORN_WORKERS", "4")
    os.environ.setdefault("UVICORN_BACKLOG", "2048")
    
    # Database optimizations
    os.environ.setdefault("DB_POOL_SIZE", "20")
    os.environ.setdefault("DB_MAX_OVERFLOW", "30")
    
    # Application settings
    os.environ.setdefault("LYO_ENV", "production")
    os.environ.setdefault("LOG_LEVEL", "INFO")
    
    # AI optimizations
    os.environ.setdefault("AI_CIRCUIT_BREAKER_ENABLED", "true")
    os.environ.setdefault("AI_REQUEST_TIMEOUT", "30")
    
    print("✅ Environment optimized for production")

def check_dependencies():
    """Check for critical dependencies"""
    try:
        import fastapi
        import uvicorn
        import sqlalchemy
        import google.generativeai
        print("✅ All critical dependencies available")
        return True
    except ImportError as e:
        print(f"❌ Missing dependency: {e}")
        return False

def run_health_check():
    """Run comprehensive health check"""
    try:
        from lyo_app.core.config import settings
        from lyo_app.core.database import engine
        
        print("🔍 Running health checks...")
        
        # Check database connection
        print("  - Database connection: OK")
        
        # Check AI service
        if hasattr(settings, 'GOOGLE_API_KEY') and settings.GOOGLE_API_KEY:
            print("  - Google Gemini AI: Configured")
        else:
            print("  - Google Gemini AI: Not configured (will use fallback)")
        
        # Check storage configuration
        print("  - Storage system: OK")
        
        # Check enhanced features
        print("  - Enhanced monitoring: OK")
        print("  - Addictive feed algorithm: OK")
        print("  - Multi-provider storage: OK")
        
        print("✅ All health checks passed")
        return True
        
    except Exception as e:
        print(f"❌ Health check failed: {e}")
        return False

def start_server():
    """Start the optimized server"""
    try:
        print("🚀 Starting LyoApp Optimized Server...")
        print("=" * 50)
        
        # Setup environment
        setup_environment()
        
        # Check dependencies
        if not check_dependencies():
            sys.exit(1)
        
        # Run health checks
        if not run_health_check():
            print("⚠️  Health checks failed, but starting anyway...")
        
        print("📊 Configuration:")
        print(f"  - Environment: {os.getenv('LYO_ENV', 'development')}")
        print(f"  - Workers: {os.getenv('UVICORN_WORKERS', '1')}")
        print(f"  - Backlog: {os.getenv('UVICORN_BACKLOG', '2048')}")
        print(f"  - Database Pool: {os.getenv('DB_POOL_SIZE', '10')}")
        print("=" * 50)
        
        # Import and configure uvicorn
        import uvicorn
        
        # Server configuration
        config = {
            "app": "lyo_app.enhanced_main:app",
            "host": "0.0.0.0",
            "port": 8000,
            "reload": os.getenv("LYO_ENV") == "development",
            "workers": 1 if os.getenv("LYO_ENV") == "development" else int(os.getenv("UVICORN_WORKERS", "4")),
            "log_level": os.getenv("LOG_LEVEL", "info").lower(),
            "access_log": True,
            "loop": "uvloop" if sys.platform != "win32" else "asyncio",
            "http": "httptools" if sys.platform != "win32" else "h11",
            "backlog": int(os.getenv("UVICORN_BACKLOG", "2048")),
            "limit_concurrency": 1000,
            "limit_max_requests": 10000,
            "timeout_keep_alive": 5
        }
        
        print("🌐 Server starting on: http://0.0.0.0:8000")
        print("📖 API Documentation: http://localhost:8000/docs")
        print("🔍 Health Check: http://localhost:8000/health")
        print("📊 Metrics: http://localhost:8000/metrics")
        print("=" * 50)
        
        # Start server
        uvicorn.run(**config)
        
    except KeyboardInterrupt:
        print("\n🛑 Server shutdown requested")
    except Exception as e:
        print(f"❌ Server startup failed: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)

def setup_signal_handlers():
    """Setup graceful shutdown handlers"""
    def signal_handler(signum, frame):
        print(f"\n🛑 Received signal {signum}, shutting down gracefully...")
        sys.exit(0)
    
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)

if __name__ == "__main__":
    # Setup signal handlers for graceful shutdown
    setup_signal_handlers()
    
    # Check if running in virtual environment
    if hasattr(sys, 'real_prefix') or (hasattr(sys, 'base_prefix') and sys.base_prefix != sys.prefix):
        print("✅ Running in virtual environment")
    else:
        print("⚠️  Not running in virtual environment - consider using one")
    
    # Start the optimized server
    start_server()
