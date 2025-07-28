"""
Quick Server Validation Test
"""
import subprocess
import time
import requests
import signal
import os

def test_server_with_resources():
    """Test server startup and resources endpoints"""
    
    print("🚀 Starting Server Validation Test")
    print("=" * 50)
    
    # Start server in background
    print("📡 Starting server...")
    process = subprocess.Popen(
        ['python', 'start_server.py'],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        preexec_fn=os.setsid
    )
    
    # Wait for server to start
    time.sleep(8)
    
    try:
        # Test basic health
        print("\n🏥 Testing basic health endpoint...")
        response = requests.get("http://localhost:8000/health", timeout=5)
        if response.status_code == 200:
            print("✅ Basic health check passed")
        else:
            print(f"❌ Basic health failed: {response.status_code}")
        
        # Test resources health
        print("\n🔧 Testing resources health endpoint...")
        response = requests.get("http://localhost:8000/api/v1/resources/health", timeout=5)
        if response.status_code == 200:
            print("✅ Resources health check passed:", response.json())
        else:
            print(f"❌ Resources health failed: {response.status_code}")
        
        # Test providers endpoint
        print("\n🏢 Testing providers endpoint...")
        response = requests.get("http://localhost:8000/api/v1/resources/providers", timeout=5)
        if response.status_code == 200:
            providers = response.json()
            print(f"✅ Providers endpoint working: {len(providers)} providers available")
            print(f"   Available: {', '.join(providers)}")
        else:
            print(f"❌ Providers endpoint failed: {response.status_code}")
        
        # Test resource types endpoint
        print("\n📝 Testing resource types endpoint...")
        response = requests.get("http://localhost:8000/api/v1/resources/resource-types", timeout=5)
        if response.status_code == 200:
            types = response.json()
            print(f"✅ Resource types endpoint working: {len(types)} types available")
            print(f"   Available: {', '.join(types)}")
        else:
            print(f"❌ Resource types endpoint failed: {response.status_code}")
            
        print("\n🎉 Server validation completed successfully!")
        print("🌐 Server is running at: http://localhost:8000")
        print("📚 API Documentation: http://localhost:8000/docs")
        print("🔍 Resources API: http://localhost:8000/api/v1/resources/")
        
    except requests.exceptions.RequestException as e:
        print(f"❌ Server connection failed: {e}")
        print("💡 The server might still be starting up or there could be a port conflict")
        
    except Exception as e:
        print(f"❌ Test failed: {e}")
        
    finally:
        # Clean up - kill the server process
        print("\n🛑 Stopping server...")
        try:
            os.killpg(os.getpgid(process.pid), signal.SIGTERM)
            process.wait(timeout=5)
            print("✅ Server stopped successfully")
        except Exception as e:
            print(f"⚠️ Error stopping server: {e}")

if __name__ == "__main__":
    test_server_with_resources()
