#!/usr/bin/env python3
"""
Comprehensive test suite for Cloud Run deployment
Usage: python test_cloud_deployment.py <service-url>
Example: python test_cloud_deployment.py https://lyo-backend-abc123-uc.a.run.app
"""

import requests
import json
import sys
import time
from typing import Dict, Any

def test_endpoint(base_url: str, endpoint: str, method: str = "GET", 
                  data: Dict[str, Any] = None, headers: Dict[str, str] = None, 
                  timeout: int = 10) -> tuple[bool, str, float]:
    """Test a single endpoint and return success, response, and latency"""
    url = f"{base_url}{endpoint}"
    start_time = time.time()
    
    try:
        if method == "GET":
            response = requests.get(url, headers=headers, timeout=timeout)
        elif method == "POST":
            response = requests.post(url, json=data, headers=headers, timeout=timeout)
        else:
            response = requests.request(method, url, json=data, headers=headers, timeout=timeout)
        
        latency = (time.time() - start_time) * 1000  # Convert to milliseconds
        success = response.status_code < 400
        
        if success:
            try:
                response_text = response.json() if response.headers.get('content-type', '').startswith('application/json') else response.text[:200]
            except:
                response_text = response.text[:200]
        else:
            response_text = f"Status {response.status_code}: {response.text[:200]}"
        
        return success, response_text, latency
        
    except Exception as e:
        latency = (time.time() - start_time) * 1000
        return False, str(e), latency

def run_tests(service_url: str):
    """Run comprehensive tests"""
    print(f"🧪 Testing LyoBackend Cloud Run Deployment")
    print(f"📍 Service URL: {service_url}")
    print("=" * 70)
    
    results = []
    total_tests = 0
    
    # Test 1: Basic Health Checks
    print("\n1️⃣ Basic Health Checks")
    print("-" * 30)
    
    tests = [
        ("/", "GET", "Root endpoint"),
        ("/health", "GET", "Health check"),
        ("/api/v1", "GET", "API v1 info"),
    ]
    
    for endpoint, method, description in tests:
        success, response, latency = test_endpoint(service_url, endpoint, method)
        icon = "✅" if success else "❌"
        print(f"{icon} {description}: {latency:.0f}ms")
        if not success:
            print(f"   Error: {response}")
        results.append(success)
        total_tests += 1
    
    # Test 2: API Documentation
    print("\n2️⃣ API Documentation")
    print("-" * 30)
    
    tests = [
        ("/docs", "GET", "Swagger UI"),
        ("/redoc", "GET", "ReDoc"),
        ("/openapi.json", "GET", "OpenAPI spec"),
    ]
    
    for endpoint, method, description in tests:
        success, response, latency = test_endpoint(service_url, endpoint, method)
        icon = "✅" if success else "❌"
        print(f"{icon} {description}: {latency:.0f}ms")
        results.append(success)
        total_tests += 1
    
    # Test 3: API Endpoints
    print("\n3️⃣ API Endpoints")
    print("-" * 30)
    
    tests = [
        ("/api/v1/features", "GET", "Production features"),
        ("/api/v1/smoke-test", "GET", "Smoke test"),
        ("/api/v1/test-ai", "GET", "AI model test"),
    ]
    
    for endpoint, method, description in tests:
        success, response, latency = test_endpoint(service_url, endpoint, method)
        icon = "✅" if success else "❌"
        print(f"{icon} {description}: {latency:.0f}ms")
        results.append(success)
        total_tests += 1
    
    # Test 4: AI Course Generation
    print("\n4️⃣ AI Course Generation")
    print("-" * 30)
    
    course_data = {
        "topic": "Cloud Computing with Google Cloud Run",
        "level": "beginner",
        "interests": ["deployment", "containerization", "serverless"]
    }
    
    success, response, latency = test_endpoint(
        service_url, 
        "/api/v1/generate-course",
        method="POST",
        data=course_data,
        headers={"Content-Type": "application/json"},
        timeout=30  # AI generation might take longer
    )
    
    icon = "✅" if success else "❌"
    print(f"{icon} Course Generation: {latency:.0f}ms")
    if success and isinstance(response, dict):
        course = response.get('course', {})
        print(f"   Generated: {course.get('title', 'N/A')}")
        print(f"   Lessons: {len(course.get('lessons', []))}")
    elif not success:
        print(f"   Error: {response}")
    
    results.append(success)
    total_tests += 1
    
    # Test 5: Performance & Load
    print("\n5️⃣ Performance Test")
    print("-" * 30)
    
    # Test multiple requests to health endpoint
    latencies = []
    successes = 0
    
    for i in range(5):
        success, _, latency = test_endpoint(service_url, "/health")
        if success:
            successes += 1
            latencies.append(latency)
        time.sleep(0.1)  # Small delay between requests
    
    if latencies:
        avg_latency = sum(latencies) / len(latencies)
        min_latency = min(latencies)
        max_latency = max(latencies)
        
        print(f"✅ Load test: {successes}/5 requests successful")
        print(f"   Avg latency: {avg_latency:.0f}ms")
        print(f"   Min latency: {min_latency:.0f}ms") 
        print(f"   Max latency: {max_latency:.0f}ms")
        
        # Performance is good if avg < 1000ms and success rate > 80%
        performance_good = avg_latency < 1000 and (successes/5) >= 0.8
        results.append(performance_good)
    else:
        print("❌ Load test: All requests failed")
        results.append(False)
    
    total_tests += 1
    
    # Test 6: Error Handling
    print("\n6️⃣ Error Handling")
    print("-" * 30)
    
    # Test non-existent endpoint
    success, response, latency = test_endpoint(service_url, "/non-existent-endpoint")
    icon = "✅" if not success else "❌"  # We expect this to fail
    print(f"{icon} 404 handling: {latency:.0f}ms")
    results.append(not success)  # Success means proper 404 handling
    total_tests += 1
    
    # Summary
    print("\n" + "=" * 70)
    success_count = sum(results)
    success_rate = (success_count / total_tests) * 100 if total_tests > 0 else 0
    
    print(f"📊 Test Results: {success_count}/{total_tests} passed ({success_rate:.1f}%)")
    
    if success_rate == 100:
        print("🎉 Perfect! All tests passed - your deployment is working flawlessly!")
        status_message = "EXCELLENT"
    elif success_rate >= 90:
        print("👍 Great! Almost all tests passed - deployment is in excellent shape!")
        status_message = "VERY_GOOD" 
    elif success_rate >= 80:
        print("✅ Good! Most tests passed - deployment is working well with minor issues!")
        status_message = "GOOD"
    elif success_rate >= 60:
        print("⚠️ Fair! Some tests failed - check the issues above!")
        status_message = "NEEDS_ATTENTION"
    else:
        print("❌ Poor! Many tests failed - please review your deployment!")
        status_message = "CRITICAL"
    
    print(f"\n🏷️ Overall Status: {status_message}")
    print(f"🌐 Your API is live at: {service_url}")
    print(f"📚 Documentation: {service_url}/docs")
    
    return success_rate >= 80

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python test_cloud_deployment.py <service-url>")
        print("Example: python test_cloud_deployment.py https://lyo-backend-abc123-uc.a.run.app")
        sys.exit(1)
    
    service_url = sys.argv[1].rstrip('/')
    
    # Validate URL format
    if not service_url.startswith(('http://', 'https://')):
        print("❌ Error: Please provide a complete URL starting with http:// or https://")
        sys.exit(1)
    
    # Install requests if not available
    try:
        import requests
    except ImportError:
        print("📦 Installing requests library...")
        import subprocess
        subprocess.run([sys.executable, "-m", "pip", "install", "requests"], check=True)
        import requests
    
    print("Starting comprehensive deployment tests...\n")
    success = run_tests(service_url)
    
    sys.exit(0 if success else 1)
