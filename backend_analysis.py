#!/usr/bin/env python3
"""
Comprehensive LyoBackend Analysis & Test Suite
"""
import subprocess
import sys
import json
import time
from typing import Dict, Any, List

class BackendAnalyzer:
    def __init__(self):
        self.base_url = "http://localhost:8082"
        self.results = []
        
    def run_curl_test(self, method: str, endpoint: str, data: Dict = None) -> Dict[str, Any]:
        """Run a curl test on an endpoint."""
        url = f"{self.base_url}{endpoint}"
        
        try:
            if method == "GET":
                cmd = ["curl", "-s", "-m", "10", url]
            elif method == "POST":
                cmd = ["curl", "-s", "-m", "10", "-X", "POST", "-H", "Content-Type: application/json", "-d", json.dumps(data), url]
            
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=15)
            
            if result.returncode == 0:
                try:
                    response_data = json.loads(result.stdout)
                    # Check for mock indicators
                    mock_indicators = ["Sample", "Mock", "Fallback", "Demo", "Trending Item", "Example", "Test data"]
                    mock_detected = any(indicator in json.dumps(response_data) for indicator in mock_indicators)
                    
                    return {
                        "endpoint": f"{method} {endpoint}",
                        "success": True,
                        "status": 200,
                        "mock_detected": mock_detected,
                        "response": response_data,
                        "error": None
                    }
                except json.JSONDecodeError:
                    return {
                        "endpoint": f"{method} {endpoint}",
                        "success": True,
                        "status": 200,
                        "mock_detected": False,
                        "response": result.stdout[:200],
                        "error": None
                    }
            else:
                return {
                    "endpoint": f"{method} {endpoint}",
                    "success": False,
                    "status": "ERROR",
                    "mock_detected": False,
                    "response": None,
                    "error": result.stderr
                }
        except Exception as e:
            return {
                "endpoint": f"{method} {endpoint}",
                "success": False,
                "status": "EXCEPTION",
                "mock_detected": False,
                "response": None,
                "error": str(e)
            }
    
    def test_core_endpoints(self):
        """Test core system endpoints."""
        print("🔍 TESTING CORE ENDPOINTS")
        print("-" * 40)
        
        core_tests = [
            ("GET", "/"),
            ("GET", "/health"),
            ("GET", "/docs"),
            ("GET", "/openapi.json"),
            ("GET", "/api/v1/test-real")
        ]
        
        for method, endpoint in core_tests:
            result = self.run_curl_test(method, endpoint)
            self.results.append(result)
            
            status_emoji = "✅" if result["success"] else "❌"
            mock_emoji = "⚠️" if result["mock_detected"] else "✅"
            
            print(f"{status_emoji} {result['endpoint']}")
            print(f"   Mock Data: {mock_emoji} {'DETECTED' if result['mock_detected'] else 'CLEAN'}")
            
            if result["success"] and isinstance(result["response"], dict):
                if "message" in result["response"]:
                    print(f"   Message: {result['response']['message'][:60]}...")
                if "status" in result["response"]:
                    print(f"   Status: {result['response']['status']}")
            
            print()
    
    def test_ai_endpoints(self):
        """Test AI functionality endpoints."""
        print("🤖 TESTING AI ENDPOINTS")
        print("-" * 40)
        
        ai_tests = [
            ("POST", "/api/v1/ai/study-session", {
                "userInput": "What is photosynthesis?",
                "resourceId": "biology_basics"
            }),
            ("POST", "/api/v1/ai/generate-quiz", {
                "topic": "Basic Mathematics",
                "difficulty": "easy",
                "num_questions": 2
            }),
            ("POST", "/api/v1/ai/analyze-answer", {
                "question": "What is 2+2?",
                "answer": "4",
                "correct_answer": "4"
            })
        ]
        
        for method, endpoint, data in ai_tests:
            result = self.run_curl_test(method, endpoint, data)
            self.results.append(result)
            
            status_emoji = "✅" if result["success"] else "❌"
            mock_emoji = "⚠️" if result["mock_detected"] else "✅"
            
            print(f"{status_emoji} {result['endpoint']}")
            print(f"   Mock Data: {mock_emoji} {'DETECTED' if result['mock_detected'] else 'CLEAN'}")
            
            if result["success"] and isinstance(result["response"], dict):
                if "response" in result["response"]:
                    ai_response = result["response"]["response"]
                    print(f"   AI Response: {ai_response[:80]}...")
                if "success" in result["response"]:
                    print(f"   Success: {result['response']['success']}")
            
            if result["error"]:
                print(f"   Error: {result['error']}")
            
            print()
            time.sleep(1)  # Rate limit AI calls
    
    def test_platform_endpoints(self):
        """Test platform feature endpoints."""
        print("📚 TESTING PLATFORM ENDPOINTS")
        print("-" * 40)
        
        platform_tests = [
            ("GET", "/api/v1/courses"),
            ("GET", "/api/v1/feeds/personalized"),
            ("GET", "/api/v1/feeds/trending"),
            ("GET", "/api/v1/gamification/profile"),
            ("GET", "/api/v1/gamification/leaderboard"),
            ("POST", "/api/v1/auth/test", {})
        ]
        
        for method, endpoint, *data in platform_tests:
            test_data = data[0] if data else None
            result = self.run_curl_test(method, endpoint, test_data)
            self.results.append(result)
            
            status_emoji = "✅" if result["success"] else "❌"
            mock_emoji = "⚠️" if result["mock_detected"] else "✅"
            
            print(f"{status_emoji} {result['endpoint']}")
            print(f"   Mock Data: {mock_emoji} {'DETECTED' if result['mock_detected'] else 'CLEAN'}")
            
            if result["success"] and isinstance(result["response"], dict):
                if "message" in result["response"]:
                    print(f"   Message: {result['response']['message'][:60]}...")
            
            print()
    
    def generate_analysis_report(self):
        """Generate comprehensive analysis report."""
        print("=" * 60)
        print("📊 COMPREHENSIVE BACKEND ANALYSIS REPORT")
        print("=" * 60)
        
        total = len(self.results)
        successful = sum(1 for r in self.results if r["success"])
        failed = total - successful
        mock_detected = sum(1 for r in self.results if r["mock_detected"])
        
        print(f"📈 STATISTICS:")
        print(f"   Total Endpoints Tested: {total}")
        print(f"   ✅ Successful: {successful}")
        print(f"   ❌ Failed: {failed}")
        print(f"   ⚠️  Mock Data Detected: {mock_detected}")
        print()
        
        # Category breakdown
        core_endpoints = [r for r in self.results if not r["endpoint"].startswith("POST /api") or "/auth/test" in r["endpoint"]]
        ai_endpoints = [r for r in self.results if "/ai/" in r["endpoint"]]
        platform_endpoints = [r for r in self.results if r["endpoint"].startswith(("GET /api", "POST /api")) and "/ai/" not in r["endpoint"] and "/auth/test" not in r["endpoint"]]
        
        core_success = sum(1 for r in core_endpoints if r["success"])
        ai_success = sum(1 for r in ai_endpoints if r["success"])
        platform_success = sum(1 for r in platform_endpoints if r["success"])
        
        print(f"📊 CATEGORY BREAKDOWN:")
        print(f"   Core Endpoints: {core_success}/{len(core_endpoints)} working")
        print(f"   AI Endpoints: {ai_success}/{len(ai_endpoints)} working")
        print(f"   Platform Endpoints: {platform_success}/{len(platform_endpoints)} working")
        print()
        
        # Mock data analysis
        if mock_detected > 0:
            print("⚠️  MOCK DATA DETECTED IN:")
            for result in self.results:
                if result["mock_detected"]:
                    print(f"   • {result['endpoint']}")
            print()
        
        # Overall verdict
        print("🏆 OVERALL VERDICT:")
        if successful == total and mock_detected == 0:
            print("   🎉 FULLY FUNCTIONAL - ZERO MOCK DATA!")
            print("   ✅ All endpoints working perfectly")
            print("   ✅ No mock/fallback data detected")
            print("   ✅ Ready for production deployment")
        elif successful >= total * 0.9 and mock_detected == 0:
            print("   ✅ EXCELLENT - Minor Issues Only")
            print("   ✅ Core functionality fully working")
            print("   ✅ No mock data detected")
            print("   ⚠️  Some endpoints may need attention")
        elif mock_detected == 0:
            print("   ✅ NO MOCK DATA - Good Clean Architecture")
            print("   ⚠️  Some endpoints need debugging")
        else:
            print("   ⚠️  MOCK DATA DETECTED - Cleanup Required")
            print("   ❌ Contains fallback/mock responses")
        
        print()
        print("📋 RECOMMENDATIONS:")
        if successful == total and mock_detected == 0:
            print("   🎯 Backend is production ready!")
            print("   🔧 Consider adding monitoring and metrics")
            print("   📊 Set up automated testing pipeline")
            print("   🚀 Ready for frontend integration")
        elif mock_detected > 0:
            print("   🧹 Remove all mock/fallback functions")
            print("   🔌 Ensure all AI endpoints use real APIs")
            print("   🗃️  Replace hardcoded responses with database queries")
        else:
            print("   🔧 Debug failing endpoints")
            print("   📋 Check server logs for errors")
            print("   🔍 Verify service dependencies")
    
    def run_full_analysis(self):
        """Run complete backend analysis."""
        print("🚀 LYOBACKEND COMPREHENSIVE ANALYSIS")
        print("=" * 60)
        print(f"Testing server at: {self.base_url}")
        print(f"Analysis started: {time.strftime('%Y-%m-%d %H:%M:%S')}")
        print()
        
        self.test_core_endpoints()
        self.test_ai_endpoints()
        self.test_platform_endpoints()
        self.generate_analysis_report()

if __name__ == "__main__":
    analyzer = BackendAnalyzer()
    analyzer.run_full_analysis()
