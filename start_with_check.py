#!/usr/bin/env python3
"""
Server startup script with status checking
"""
import subprocess
import sys
import time
import requests

def check_server_running():
    """Check if server is already running"""
    try:
        response = requests.get("http://localhost:8000/health", timeout=5)
        if response.status_code == 200:
            print("✅ Server is already running!")
            print(f"🌐 Visit: http://localhost:8000")
            print(f"📖 API Docs: http://localhost:8000/docs")
            return True
    except:
        pass
    return False

def start_server():
    """Start the server"""
    print("🚀 Starting LyoApp Backend Server...")
    print("📊 Environment: Development")
    print("🗄️ Database: SQLite (./lyo_app_dev.db)")
    print("🌐 URL: http://localhost:8000")
    print("📖 Docs: http://localhost:8000/docs")
    print("=" * 50)
    
    try:
        subprocess.run([
            sys.executable, "-m", "uvicorn", 
            "lyo_app.main:app", 
            "--host", "0.0.0.0", 
            "--port", "8000", 
            "--reload"
        ])
    except KeyboardInterrupt:
        print("\n👋 Server stopped")

if __name__ == "__main__":
    if not check_server_running():
        start_server()
