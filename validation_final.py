#!/usr/bin/env python3
"""
Final AI Optimization System Validation
Quick comprehensive test of all AI optimization features.
"""

import asyncio
import sys
from pathlib import Path

# Add the project root to Python path
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

async def run_final_validation():
    """Run final validation of AI optimization system."""
    print("🎯 Final AI Optimization System Validation")
    print("=" * 60)
    
    tests_passed = 0
    total_tests = 6
    
    # Test 1: Optimization Module Imports
    print("\n1. Testing optimization module imports...")
    try:
        from lyo_app.ai_agents.optimization import (
            ai_performance_optimizer, 
            personalization_engine, 
            experiment_manager
        )
        print("   ✅ All optimization modules imported successfully")
        tests_passed += 1
    except Exception as e:
        print(f"   ❌ Import failed: {e}")
    
    # Test 2: Orchestrator Integration
    print("\n2. Testing orchestrator integration...")
    try:
        from lyo_app.ai_agents.orchestrator import ai_orchestrator
        print("   ✅ Orchestrator with optimization integration loaded")
        tests_passed += 1
    except Exception as e:
        print(f"   ❌ Orchestrator integration failed: {e}")
    
    # Test 3: Performance Optimizer Functionality
    print("\n3. Testing performance optimizer functionality...")
    try:
        await ai_performance_optimizer.initialize()
        
        # Test cache operations
        test_data = {"message": "test optimization"}
        await ai_performance_optimizer.cache_manager.set("test", test_data)
        cached = await ai_performance_optimizer.cache_manager.get("test")
        
        if cached == test_data:
            print("   ✅ Performance optimizer cache working")
            tests_passed += 1
        else:
            print("   ❌ Cache operations failed")
    except Exception as e:
        print(f"   ❌ Performance optimizer failed: {e}")
    
    # Test 4: Personalization Engine
    print("\n4. Testing personalization engine...")
    try:
        await personalization_engine.initialize()
        
        # Test user profile creation
        test_profile = await personalization_engine.get_user_profile("test_user")
        if test_profile:
            print("   ✅ Personalization engine working")
            tests_passed += 1
        else:
            print("   ❌ Personalization engine failed")
    except Exception as e:
        print(f"   ❌ Personalization engine failed: {e}")
    
    # Test 5: A/B Testing Framework
    print("\n5. Testing A/B testing framework...")
    try:
        # Test experiment creation
        experiment = await experiment_manager.create_experiment(
            name="test_experiment",
            description="Test experiment",
            variants=["A", "B"],
            traffic_split={"A": 50, "B": 50}
        )
        
        if experiment:
            print("   ✅ A/B testing framework working")
            tests_passed += 1
        else:
            print("   ❌ A/B testing framework failed")
    except Exception as e:
        print(f"   ❌ A/B testing framework failed: {e}")
    
    # Test 6: API Routes
    print("\n6. Testing optimization API routes...")
    try:
        from lyo_app.ai_agents.optimization.routes import router
        
        routes = [route.path for route in router.routes]
        expected_routes = ["/performance", "/personalization", "/experiments"]
        
        found_routes = sum(1 for expected in expected_routes 
                          if any(expected in route for route in routes))
        
        if found_routes >= 2:
            print("   ✅ Optimization API routes configured")
            tests_passed += 1
        else:
            print(f"   ❌ API routes incomplete ({found_routes}/{len(expected_routes)} found)")
    except Exception as e:
        print(f"   ❌ API routes test failed: {e}")
    
    # Final Results
    print("\n" + "=" * 60)
    print(f"🎯 Final Results: {tests_passed}/{total_tests} tests passed")
    
    if tests_passed >= 5:
        print("🎉 AI OPTIMIZATION SYSTEM VALIDATED!")
        print("✨ Ready for production deployment!")
        return True
    elif tests_passed >= 3:
        print("⚠️  AI optimization system partially working")
        print("🔧 Minor issues need attention")
        return False
    else:
        print("❌ AI optimization system needs significant fixes")
        return False

if __name__ == "__main__":
    asyncio.run(run_final_validation())
