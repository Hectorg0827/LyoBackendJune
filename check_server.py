#!/usr/bin/env python3
"""
Check server status and start if needed
"""
import requests
import subprocess
import time
import sys

def check_server():
    try:
        response = requests.get("http://localhost:8000/health", timeout=5)
        if response.status_code == 200:
            print("✅ Server is running and responding!")
            print("✅ Docs available at: http://localhost:8000/docs")
            return True
    except requests.exceptions.RequestException:
        print("❌ Server is not responding")
        return False

def start_server():
    print("🚀 Starting FastAPI server...")
    try:
        # Start server in background
        process = subprocess.Popen([
            sys.executable, "-m", "uvicorn", 
            "lyo_app.main:app", 
            "--reload", 
            "--host", "0.0.0.0", 
            "--port", "8000"
        ])
        
        # Wait a bit for server to start
        time.sleep(3)
        
        # Check if it's working
        if check_server():
            print(f"🎉 Server started successfully! PID: {process.pid}")
            return True
        else:
            print("❌ Server failed to start properly")
            return False
            
    except Exception as e:
        print(f"❌ Error starting server: {e}")
        return False

if __name__ == "__main__":
    if not check_server():
        start_server()
    else:
        print("🌐 Visit: http://localhost:8000/docs")
