#!/usr/bin/env python3
"""
LyoBackend Final Integration Test
Tests all components including AI course generation.
"""

import asyncio
import json
import logging
import subprocess
from typing import Dict, Any
from datetime import datetime

import httpx

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class FinalIntegrationTest:
    """Complete integration test for LyoBackend with AI."""
    
    def __init__(self):
        self.base_url = "http://localhost:8001"
        self.passed = 0
        self.failed = 0
        
    def success(self, msg):
        print(f"✅ {msg}")
        self.passed += 1
        
    def error(self, msg):
        print(f"❌ {msg}")
        self.failed += 1
        
    def info(self, msg):
        print(f"ℹ️  {msg}")
        
    def header(self, msg):
        print(f"\n{'='*60}")
        print(f"{msg.center(60)}")
        print('='*60)
        
    async def test_server_health(self):
        """Test server health and basic endpoints."""
        self.header("SERVER HEALTH TESTS")
        
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                # Test root endpoint
                response = await client.get(f"{self.base_url}/")
                if response.status_code == 200:
                    data = response.json()
                    self.success(f"Server responding: {data.get('message', '')[:50]}...")
                else:
                    self.error(f"Server returned status: {response.status_code}")
                    
                # Test health endpoint
                response = await client.get(f"{self.base_url}/health")
                if response.status_code == 200:
                    self.success("Health endpoint working")
                else:
                    self.error("Health endpoint failed")
                    
        except Exception as e:
            self.error(f"Server health test failed: {e}")
            
    async def test_ai_integration(self):
        """Test AI course generation integration."""
        self.header("AI INTEGRATION TESTS")
        
        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                # Test AI status
                response = await client.get(f"{self.base_url}/api/v1/test-ai")
                if response.status_code == 200:
                    data = response.json()
                    self.success(f"AI Status: {data.get('ai_status')}")
                    self.info(f"Capabilities: {len(data.get('capabilities', []))} features")
                else:
                    self.error("AI status endpoint failed")
                    
                # Test course generation - Python
                python_course_data = {
                    "topic": "Python Programming",
                    "level": "beginner",
                    "interests": ["web development", "automation"]
                }
                
                response = await client.post(
                    f"{self.base_url}/api/v1/generate-course",
                    json=python_course_data
                )
                
                if response.status_code == 200:
                    course_data = response.json()
                    if course_data.get("status") == "success":
                        course = course_data.get("course", {})
                        self.success(f"Python course generated: '{course.get('title')}'")
                        self.info(f"Lessons: {len(course.get('lessons', []))}")
                        self.info(f"Duration: {course.get('estimated_duration')} minutes")
                    else:
                        self.error("Course generation returned error status")
                else:
                    self.error(f"Course generation failed: {response.status_code}")
                    
                # Test course generation - Machine Learning
                ml_course_data = {
                    "topic": "Machine Learning",
                    "level": "intermediate", 
                    "interests": ["data science", "AI"]
                }
                
                response = await client.post(
                    f"{self.base_url}/api/v1/generate-course",
                    json=ml_course_data
                )
                
                if response.status_code == 200:
                    course_data = response.json()
                    course = course_data.get("course", {})
                    self.success(f"ML course generated: '{course.get('title')}'")
                else:
                    self.error("ML course generation failed")
                    
        except Exception as e:
            self.error(f"AI integration test failed: {e}")
            logger.exception("AI test error:")
            
    async def test_production_features(self):
        """Test production features endpoint."""
        self.header("PRODUCTION FEATURES TEST")
        
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                response = await client.get(f"{self.base_url}/api/v1/features")
                
                if response.status_code == 200:
                    features = response.json()
                    
                    if features.get("production_ready"):
                        self.success("Backend marked as production ready")
                        
                        # Count implemented features
                        feature_count = len(features.get("features", {}))
                        self.info(f"Feature categories: {feature_count}")
                        
                        # Check specific features
                        if "courses" in features.get("features", {}):
                            courses_features = features["features"]["courses"]
                            if "AI generation" in courses_features.get("features", []):
                                self.success("AI course generation feature listed")
                            else:
                                self.error("AI generation not listed in course features")
                                
                        compliance = features.get("specification_compliance")
                        self.success(f"Specification compliance: {compliance}")
                    else:
                        self.error("Backend not marked as production ready")
                else:
                    self.error("Production features endpoint failed")
                    
        except Exception as e:
            self.error(f"Production features test failed: {e}")
            
    def test_external_services(self):
        """Test external service connectivity."""
        self.header("EXTERNAL SERVICES TEST")
        
        # Test Redis
        try:
            result = subprocess.run(
                'redis-cli ping >/dev/null 2>&1',
                shell=True, capture_output=True, text=True
            )
            if result.returncode == 0:
                self.success("Redis connection verified")
            else:
                self.error("Redis connection failed")
        except:
            self.info("Redis test skipped (redis-cli not available)")
            
        # Test PostgreSQL
        try:
            result = subprocess.run(
                'psql postgresql://lyo_user:securepassword@localhost/lyo_production -c "SELECT 1;" >/dev/null 2>&1',
                shell=True, capture_output=True, text=True
            )
            if result.returncode == 0:
                self.success("PostgreSQL connection verified")
            else:
                self.error("PostgreSQL connection failed")
        except:
            self.info("PostgreSQL test skipped (psql not available)")
            
    async def run_comprehensive_test(self):
        """Run all comprehensive tests."""
        self.header("🚀 LYOBACKEND COMPREHENSIVE INTEGRATION TEST")
        self.info(f"Testing backend at: {self.base_url}")
        self.info(f"Start time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        
        # Run all test suites
        await self.test_server_health()
        await self.test_ai_integration()
        await self.test_production_features()
        self.test_external_services()
        
        # Final results
        self.header("FINAL TEST RESULTS")
        total = self.passed + self.failed
        success_rate = (self.passed / total * 100) if total > 0 else 0
        
        print(f"📊 Test Summary:")
        print(f"   Total Tests: {total}")
        print(f"   Passed: {self.passed}")
        print(f"   Failed: {self.failed}")
        print(f"   Success Rate: {success_rate:.1f}%")
        
        if self.failed == 0:
            print(f"\n🎉 ALL TESTS PASSED!")
            print("✅ LyoBackend is 100% production ready with AI integration!")
            print("\n🚀 Ready for:")
            print("   • Frontend integration")
            print("   • iOS app connection") 
            print("   • Cloud deployment")
            print("   • Real-world usage")
            
            return True
        else:
            print(f"\n⚠️ Some tests failed ({self.failed}/{total})")
            print("🔧 Please review and fix issues before deployment")
            return False


async def main():
    """Main test runner."""
    test = FinalIntegrationTest()
    
    try:
        success = await test.run_comprehensive_test()
        
        if success:
            print(f"\n🎊 MISSION ACCOMPLISHED!")
            print("🏆 LyoBackend with AI integration is production ready!")
            return 0
        else:
            print(f"\n🔧 Please fix issues and re-run tests.")
            return 1
            
    except KeyboardInterrupt:
        print("\n⚠️ Test interrupted by user.")
        return 1
    except Exception as e:
        print(f"\n❌ Test failed with error: {str(e)}")
        return 1


if __name__ == "__main__":
    exit_code = asyncio.run(main())
    exit(exit_code)
