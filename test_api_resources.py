"""
Simple API Test for Educational Resources
"""
import requests
import json

def test_resources_api():
    """Test the educational resources API endpoints"""
    
    base_url = "http://localhost:8000/api/v1/resources"
    
    print("🧪 Testing Educational Resources API")
    print("=" * 50)
    
    # Test 1: Health check
    print("\n1. Testing health endpoint...")
    try:
        response = requests.get(f"{base_url}/health")
        if response.status_code == 200:
            print("✅ Health check passed:", response.json())
        else:
            print("❌ Health check failed:", response.status_code)
    except Exception as e:
        print("❌ Health check error:", str(e))
    
    # Test 2: Get available providers
    print("\n2. Testing providers endpoint...")
    try:
        response = requests.get(f"{base_url}/providers")
        if response.status_code == 200:
            providers = response.json()
            print("✅ Available providers:", providers)
        else:
            print("❌ Providers endpoint failed:", response.status_code)
    except Exception as e:
        print("❌ Providers endpoint error:", str(e))
    
    # Test 3: Get resource types
    print("\n3. Testing resource types endpoint...")
    try:
        response = requests.get(f"{base_url}/resource-types")
        if response.status_code == 200:
            types = response.json()
            print("✅ Available resource types:", types)
        else:
            print("❌ Resource types endpoint failed:", response.status_code)
    except Exception as e:
        print("❌ Resource types endpoint error:", str(e))
    
    # Test 4: Get trending resources (without auth for now)
    print("\n4. Testing trending resources endpoint...")
    try:
        response = requests.get(f"{base_url}/trending")
        if response.status_code == 200:
            trending = response.json()
            print("✅ Trending resources:", len(trending), "items")
        elif response.status_code == 401:
            print("ℹ️ Trending endpoint requires authentication (expected)")
        else:
            print("❌ Trending endpoint failed:", response.status_code)
    except Exception as e:
        print("❌ Trending endpoint error:", str(e))
    
    print("\n🎉 API Test Complete!")

if __name__ == "__main__":
    test_resources_api()
