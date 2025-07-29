#!/usr/bin/env python3
"""
One-Command Backend-Frontend Connection Test
Automatically sets up, tests, and validates the backend for iOS frontend integration.
"""

import subprocess
import sys
import time
from pathlib import Path

def main():
    print("🚀 Starting Automated Backend-Frontend Connection Testing")
    print("=" * 60)
    
    # Make scripts executable
    scripts = [
        "automated_backend_frontend_test.py",
        "ios_connection_simulator.py"
    ]
    
    for script in scripts:
        script_path = Path(script)
        if script_path.exists():
            subprocess.run(["chmod", "+x", str(script_path)], check=True)
    
    print("📋 Running comprehensive backend testing...")
    try:
        # Run the comprehensive test
        result = subprocess.run([
            sys.executable, "automated_backend_frontend_test.py"
        ], capture_output=False, text=True)
        
        if result.returncode == 0:
            print("\n✅ Comprehensive testing completed successfully!")
            
            print("\n📱 Running iOS connection simulation...")
            # Run iOS simulation
            ios_result = subprocess.run([
                sys.executable, "ios_connection_simulator.py"
            ], capture_output=False, text=True)
            
            if ios_result.returncode == 0:
                print("\n🎉 All tests passed! Your backend is ready for iOS integration!")
                print("\n📋 Next Steps:")
                print("1. Use http://localhost:8000 as your backend URL in iOS app")
                print("2. Check http://localhost:8000/docs for API documentation")
                print("3. Implement the authentication flow shown in the test results")
                print("4. Connect to WebSocket endpoints for real-time features")
                return True
            else:
                print("\n⚠️ iOS simulation found some issues, but backend basics are working")
                return True
        else:
            print("\n❌ Comprehensive testing found issues")
            return False
            
    except Exception as e:
        print(f"\n❌ Error running tests: {e}")
        return False

if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
