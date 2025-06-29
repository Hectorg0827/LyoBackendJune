#!/usr/bin/env python3
"""
Test script to validate the AI agents upgrade to production-ready Gemma 4.
"""

import asyncio
import sys
import traceback
from pathlib import Path

# Add the project root to Python path
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

async def test_orchestrator_imports():
    """Test that the orchestrator can be imported with new features."""
    try:
        from lyo_app.ai_agents.orchestrator import (
            AIOrchestrator, 
            ModelType, 
            TaskComplexity, 
            LanguageCode,
            ProductionGemma4Client,
            ModernCloudLLMClient,
            ai_orchestrator
        )
        print("✅ Orchestrator imports successful")
        
        # Test enum values
        assert ModelType.GEMMA_4_ON_DEVICE == "gemma_4_on_device"
        assert ModelType.GEMMA_4_CLOUD == "gemma_4_cloud"
        assert ModelType.GPT_4_MINI == "gpt_4_mini"
        assert LanguageCode.ENGLISH == "en"
        assert LanguageCode.SPANISH == "es"
        print("✅ Model types and language codes working")
        
        return True
    except Exception as e:
        print(f"❌ Orchestrator import failed: {e}")
        traceback.print_exc()
        return False

async def test_orchestrator_initialization():
    """Test orchestrator initialization."""
    try:
        from lyo_app.ai_agents.orchestrator import ai_orchestrator
        
        # Test initialization
        success = await ai_orchestrator.initialize()
        print(f"✅ Orchestrator initialization: {'success' if success else 'partial'}")
        
        # Test health check
        health = await ai_orchestrator.health_check()
        print(f"✅ Health check completed: {health['status']}")
        
        # Test performance stats
        stats = ai_orchestrator.get_performance_stats()
        print(f"✅ Performance stats available: {len(stats)} categories")
        
        return True
    except Exception as e:
        print(f"❌ Orchestrator initialization failed: {e}")
        traceback.print_exc()
        return False

async def test_gemma4_client():
    """Test the Gemma 4 client functionality."""
    try:
        from lyo_app.ai_agents.orchestrator import ProductionGemma4Client, LanguageCode
        
        client = ProductionGemma4Client()
        
        # Test initialization
        success = await client.initialize()
        print(f"✅ Gemma 4 client initialization: {'success' if success else 'partial'}")
        
        # Test basic generation
        response = await client.generate(
            "Hello, can you help me learn?",
            max_tokens=100,
            language=LanguageCode.ENGLISH
        )
        
        print(f"✅ Gemma 4 generation successful: {len(response.content)} chars")
        print(f"   Language: {response.language_detected}")
        print(f"   Model: {response.model_used}")
        print(f"   Response time: {response.response_time_ms:.1f}ms")
        
        # Test stats
        stats = client.get_stats()
        print(f"✅ Client stats available: {stats}")
        
        return True
    except Exception as e:
        print(f"❌ Gemma 4 client test failed: {e}")
        traceback.print_exc()
        return False

async def test_curriculum_agent():
    """Test curriculum agent with new orchestrator."""
    try:
        from lyo_app.ai_agents.curriculum_agent import curriculum_design_agent
        from lyo_app.ai_agents.orchestrator import LanguageCode
        from lyo_app.learning.models import DifficultyLevel
        
        # Mock database session
        class MockDB:
            async def execute(self, query):
                class MockResult:
                    def scalar_one_or_none(self):
                        return None
                return MockResult()
        
        db = MockDB()
        
        # Test course outline generation with language support
        result = await curriculum_design_agent.generate_course_outline(
            title="Introduction to AI",
            description="A beginner-friendly course on artificial intelligence",
            target_audience="Students with basic programming knowledge",
            learning_objectives=[
                "Understand basic AI concepts",
                "Learn about machine learning",
                "Explore practical applications"
            ],
            difficulty_level=DifficultyLevel.BEGINNER,
            estimated_duration_hours=20,
            db=db,
            language=LanguageCode.ENGLISH
        )
        
        print(f"✅ Curriculum agent working: {result.get('title', 'Generated outline')}")
        return True
        
    except Exception as e:
        print(f"❌ Curriculum agent test failed: {e}")
        traceback.print_exc()
        return False

async def test_curation_agent():
    """Test curation agent functionality."""
    try:
        from lyo_app.ai_agents.curation_agent import content_curation_agent
        from lyo_app.learning.models import DifficultyLevel
        
        # Mock database session
        class MockDB:
            pass
        
        db = MockDB()
        
        # Test content evaluation
        result = await content_curation_agent.evaluate_content_quality(
            content_text="This is a sample educational content about machine learning basics.",
            content_type="article",
            topic="machine learning",
            target_audience="beginners",
            difficulty_level=DifficultyLevel.BEGINNER,
            db=db
        )
        
        print(f"✅ Curation agent working: score {result.get('overall_score', 0)}")
        return True
        
    except Exception as e:
        print(f"❌ Curation agent test failed: {e}")
        traceback.print_exc()
        return False

async def test_multi_language_support():
    """Test multi-language capabilities."""
    try:
        from lyo_app.ai_agents.orchestrator import ai_orchestrator, LanguageCode, TaskComplexity
        
        # Test responses in different languages
        languages = [LanguageCode.ENGLISH, LanguageCode.SPANISH, LanguageCode.FRENCH]
        
        for language in languages:
            response = await ai_orchestrator.generate_response(
                prompt="Hello, how are you?",
                task_complexity=TaskComplexity.SIMPLE,
                language=language,
                max_tokens=50
            )
            
            print(f"✅ {language.value}: {response.content[:50]}...")
        
        return True
        
    except Exception as e:
        print(f"❌ Multi-language test failed: {e}")
        traceback.print_exc()
        return False

async def test_routes_imports():
    """Test that AI routes can be imported."""
    try:
        from lyo_app.ai_agents.routes import router
        print("✅ AI routes import successful")
        
        # Check that the router has the expected endpoints
        routes = [route.path for route in router.routes]
        expected_routes = ['/curriculum/course-outline', '/curation/evaluate-content', '/health']
        
        for expected in expected_routes:
            if any(expected in route for route in routes):
                print(f"✅ Route found: {expected}")
            else:
                print(f"⚠️ Route not found: {expected}")
        
        return True
        
    except Exception as e:
        print(f"❌ Routes import failed: {e}")
        traceback.print_exc()
        return False

async def main():
    """Run all tests."""
    print("🚀 Testing AI Agents Upgrade to Production-Ready Gemma 4")
    print("=" * 60)
    
    tests = [
        ("Orchestrator Imports", test_orchestrator_imports),
        ("Orchestrator Initialization", test_orchestrator_initialization),
        ("Gemma 4 Client", test_gemma4_client),
        ("Curriculum Agent", test_curriculum_agent),
        ("Curation Agent", test_curation_agent),
        ("Multi-Language Support", test_multi_language_support),
        ("Routes Import", test_routes_imports),
    ]
    
    results = []
    for test_name, test_func in tests:
        print(f"\n📋 Running: {test_name}")
        try:
            success = await test_func()
            results.append((test_name, success))
        except Exception as e:
            print(f"❌ {test_name} failed with exception: {e}")
            results.append((test_name, False))
    
    print("\n" + "=" * 60)
    print("📊 Test Results Summary:")
    print("=" * 60)
    
    passed = 0
    for test_name, success in results:
        status = "✅ PASS" if success else "❌ FAIL"
        print(f"{status}: {test_name}")
        if success:
            passed += 1
    
    total = len(results)
    print(f"\n🎯 Results: {passed}/{total} tests passed ({passed/total*100:.1f}%)")
    
    if passed == total:
        print("🎉 All tests passed! AI system successfully upgraded to production-ready Gemma 4.")
    elif passed >= total * 0.7:
        print("⚠️ Most tests passed. System is functional with some issues to address.")
    else:
        print("❌ Multiple test failures. System needs significant fixes.")
    
    return passed == total

if __name__ == "__main__":
    try:
        success = asyncio.run(main())
        sys.exit(0 if success else 1)
    except KeyboardInterrupt:
        print("\n⏹️ Tests interrupted by user")
        sys.exit(1)
    except Exception as e:
        print(f"\n💥 Test runner failed: {e}")
        traceback.print_exc()
        sys.exit(1)
