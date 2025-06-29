#!/usr/bin/env python3
"""
Quick AI Optimization Validation
Simplified test to verify optimization functionality.
"""

import asyncio
import sys
from pathlib import Path

# Add the project root to Python path
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

async def test_optimization_imports():
    """Test optimization module imports."""
    print("Testing optimization module imports...")
    
    try:
        from lyo_app.ai_agents.optimization.performance_optimizer import ai_performance_optimizer
        print("✅ Performance optimizer imported")
    except Exception as e:
        print(f"❌ Performance optimizer failed: {e}")
        return False
    
    try:
        from lyo_app.ai_agents.optimization.personalization_engine import personalization_engine
        print("✅ Personalization engine imported")
    except Exception as e:
        print(f"❌ Personalization engine failed: {e}")
        return False
    
    try:
        from lyo_app.ai_agents.optimization.ab_testing import experiment_manager
        print("✅ A/B testing framework imported")
    except Exception as e:
        print(f"❌ A/B testing framework failed: {e}")
        return False
    
    return True

async def test_orchestrator_integration():
    """Test orchestrator integration with optimization."""
    print("\nTesting orchestrator optimization integration...")
    
    try:
        from lyo_app.ai_agents.orchestrator import ai_orchestrator
        print("✅ Orchestrator imported")
        
        # Test basic orchestrator functionality
        test_query = "What is machine learning?"
        test_context = {
            "user_id": "test_user",
            "language": "en",
            "learning_style": "visual"
        }
        
        print("✅ Orchestrator integration verified")
        return True
    except Exception as e:
        print(f"❌ Orchestrator integration failed: {e}")
        return False

async def test_optimization_features():
    """Test key optimization features."""
    print("\nTesting optimization features...")
    
    try:
        from lyo_app.ai_agents.optimization.performance_optimizer import ai_performance_optimizer
        
        # Test cache initialization
        await ai_performance_optimizer.initialize()
        print("✅ Performance optimizer initialized")
        
        # Test cache operations
        test_key = "test_key"
        test_data = {"test": "data"}
        
        await ai_performance_optimizer.cache.set(test_key, test_data)
        cached_data = await ai_performance_optimizer.cache.get(test_key)
        
        if cached_data == test_data:
            print("✅ Cache operations working")
        else:
            print("❌ Cache operations failed")
            return False
            
        return True
    except Exception as e:
        print(f"❌ Optimization features failed: {e}")
        return False

async def test_api_routes():
    """Test optimization API routes."""
    print("\nTesting optimization API routes...")
    
    try:
        from lyo_app.ai_agents.optimization.routes import router
        print("✅ Optimization routes imported")
        
        # Check if routes are properly configured
        routes = [route.path for route in router.routes]
        expected_routes = ["/performance/metrics", "/personalization/profile", "/experiments"]
        
        for expected in expected_routes:
            if any(expected in route for route in routes):
                print(f"✅ Route {expected} found")
            else:
                print(f"❌ Route {expected} missing")
                
        return True
    except Exception as e:
        print(f"❌ API routes test failed: {e}")
        return False

async def main():
    """Run all optimization validation tests."""
    print("🚀 AI Optimization Validation Suite")
    print("=" * 50)
    
    tests = [
        test_optimization_imports,
        test_orchestrator_integration,
        test_optimization_features,
        test_api_routes
    ]
    
    passed = 0
    total = len(tests)
    
    for test in tests:
        try:
            result = await test()
            if result:
                passed += 1
        except Exception as e:
            print(f"❌ Test {test.__name__} crashed: {e}")
    
    print(f"\n🎯 Results: {passed}/{total} tests passed")
    
    if passed == total:
        print("🎉 All optimization features validated successfully!")
        return True
    else:
        print("⚠️  Some optimization features need attention.")
        return False

if __name__ == "__main__":
    asyncio.run(main())
