#!/usr/bin/env python3
"""
Super Simple Backend Test
Just test if the server starts and basic endpoints work.
"""

import subprocess
import time
import sys
import requests
from pathlib import Path

def main():
    print("🚀 Starting Simple Backend Connection Test")
    print("=" * 50)
    
    # Start the server
    print("📋 Starting backend server...")
    try:
        # Try to start the server
        server_process = subprocess.Popen([
            sys.executable, "start_server.py"
        ], stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        
        # Wait a bit for server to start
        print("⏳ Waiting for server to start...")
        time.sleep(5)
        
        # Test if server is running
        try:
            response = requests.get("http://localhost:8000/health", timeout=5)
            if response.status_code == 200:
                print("✅ Server is running!")
                print("✅ Health endpoint working!")
                
                # Test docs endpoint
                try:
                    docs_response = requests.get("http://localhost:8000/docs", timeout=5)
                    if docs_response.status_code == 200:
                        print("✅ API docs accessible!")
                    else:
                        print("⚠️ API docs not accessible")
                except:
                    print("⚠️ API docs not accessible")
                
                print("\n📱 iOS Integration Info:")
                print(f"   Backend URL: http://localhost:8000")
                print(f"   API Docs: http://localhost:8000/docs")
                print(f"   Health Check: http://localhost:8000/health")
                
                print("\n🎉 Your backend is ready for iOS frontend connection!")
                print("\n📋 Next Steps:")
                print("   1. Use 'http://localhost:8000' as your backend URL in iOS")
                print("   2. Check the API documentation at /docs")
                print("   3. Implement authentication using /api/v1/auth endpoints")
                
                return True
            else:
                print(f"❌ Server health check failed: {response.status_code}")
                return False
                
        except Exception as e:
            print(f"❌ Failed to connect to server: {e}")
            return False
        
    except Exception as e:
        print(f"❌ Failed to start server: {e}")
        return False
    
    finally:
        # Don't stop the server - let it keep running
        print("\n📋 Server will continue running in the background")
        print("   Use Ctrl+C in the server terminal to stop it")

if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
