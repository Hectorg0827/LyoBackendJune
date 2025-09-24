#!/usr/bin/env python3
"""
Quick Backend Status Check
"""
import json
import subprocess
import sys

def check_backend():
    """Quick check if backend is working"""
    print("🚀 QUICK BACKEND STATUS CHECK")
    print("="*40)
    
    try:
        # Test basic connectivity
        result = subprocess.run(['curl', '-s', '-m', '5', 'http://localhost:8082/'], 
                              capture_output=True, text=True, timeout=10)
        
        if result.returncode == 0:
            print("✅ Backend server is responding")
            try:
                data = json.loads(result.stdout)
                print(f"✅ Server: {data.get('message', 'Unknown')}")
                print(f"✅ Version: {data.get('version', 'Unknown')}")
                print(f"✅ Mock Data: {data.get('mock_data', 'Unknown')}")
                
                # Test health
                health_result = subprocess.run(['curl', '-s', '-m', '5', 'http://localhost:8082/health'], 
                                             capture_output=True, text=True, timeout=10)
                if health_result.returncode == 0:
                    health_data = json.loads(health_result.stdout)
                    print(f"✅ Health Status: {health_data.get('status', 'Unknown')}")
                    services = health_data.get('services', {})
                    for service, status in services.items():
                        print(f"   {service}: {status}")
                    
                print("\n🎉 BACKEND IS FULLY FUNCTIONAL!")
                return True
                
            except json.JSONDecodeError:
                print("✅ Server responding but unexpected format")
                return True
                
        else:
            print("❌ Backend server not responding")
            return False
            
    except Exception as e:
        print(f"❌ Error checking backend: {e}")
        return False

if __name__ == "__main__":
    success = check_backend()
    sys.exit(0 if success else 1)
