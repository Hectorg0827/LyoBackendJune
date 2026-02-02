#!/usr/bin/env python3
"""
Simple server starter
"""
import uvicorn
import sys
import os

# Add current directory to path
sys.path.insert(0, os.getcwd())

if __name__ == "__main__":
    print("🚀 Starting LyoApp Backend with Educational Resources...")
    print("🌐 Server will be available at: http://localhost:8000")
    print("📚 Educational Resources API: http://localhost:8000/api/v1/resources/")
    print("📖 API Documentation: http://localhost:8000/docs")
    print("=" * 60)
    
    try:
        print("🚀 Launching Uvicorn...", flush=True)
        uvicorn.run(
            "lyo_app.main:app",
            host="0.0.0.0",
            port=8000,
            reload=True,
            log_level="debug"
        )
    except Exception as e:
        print(f"❌ Error starting server: {e}")
        sys.exit(1)
