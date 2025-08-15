#!/usr/bin/env python3
"""
Quick Market-Ready Backend Validation
=====================================
"""

import subprocess
import time
import sys

def check_server():
    """Check if server is running."""
    try:
        import requests
        response = requests.get("http://localhost:8000/health", timeout=3)
        return response.status_code == 200
    except:
        return False

def main():
    print("🔍 LyoApp Market-Ready Backend - Quick Validation")
    print("=" * 50)
    
    # Check if server is running
    if check_server():
        print("✅ Server: ONLINE at http://localhost:8000")
        print("✅ Health: PASSING")
        print("✅ Status: OPERATIONAL")
        print("\n🌐 Quick Links:")
        print("   📖 API Docs: http://localhost:8000/v1/docs")
        print("   🔍 Health: http://localhost:8000/health")
        print("   📊 Status: http://localhost:8000/ready")
        print("\n🎉 LyoApp Market-Ready Backend is LIVE!")
    else:
        print("❌ Server: OFFLINE")
        print("💡 Start with: python3 start_market_ready.py")
        return 1
        
    return 0

if __name__ == "__main__":
    sys.exit(main())
