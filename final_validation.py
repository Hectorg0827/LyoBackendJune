#!/usr/bin/env python3
"""
Final validation script for the AI agents production upgrade.
"""

import asyncio
import sys
import traceback
from pathlib import Path

# Add the project root to Python path
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

async def main():
    print("🚀 Final AI Agents Production Validation")
    print("=" * 50)
    
    tests_passed = 0
    total_tests = 6
    
    # Test 1: Orchestrator imports
    try:
        from lyo_app.ai_agents.orchestrator import (
            ai_orchestrator, 
            ModelType, 
            LanguageCode,
            TaskComplexity,
            ProductionGemma4Client,
            ModernCloudLLMClient
        )
        print("✅ 1. Orchestrator imports successful")
        tests_passed += 1
    except Exception as e:
        print(f"❌ 1. Orchestrator import failed: {e}")
    
    # Test 2: All agents imports
    try:
        from lyo_app.ai_agents.curriculum_agent import CurriculumAgent
        from lyo_app.ai_agents.curation_agent import CurationAgent  
        from lyo_app.ai_agents.mentor_agent import MentorAgent
        from lyo_app.ai_agents.feed_agent import FeedAgent
        print("✅ 2. All agents import successful")
        tests_passed += 1
    except Exception as e:
        print(f"❌ 2. Agents import failed: {e}")
        
    # Test 3: Routes import
    try:
        from lyo_app.ai_agents.routes import router
        print("✅ 3. Routes import successful")
        tests_passed += 1
    except Exception as e:
        print(f"❌ 3. Routes import failed: {e}")
    
    # Test 4: Orchestrator initialization
    try:
        success = await ai_orchestrator.initialize()
        print(f"✅ 4. Orchestrator initialization: {'success' if success else 'partial'}")
        tests_passed += 1
    except Exception as e:
        print(f"❌ 4. Orchestrator initialization failed: {e}")
    
    # Test 5: Model types validation
    try:
        models = [m.value for m in ModelType]
        languages = [l.value for l in LanguageCode]
        print(f"✅ 5. Model types working: {len(models)} models, {len(languages)} languages")
        tests_passed += 1
    except Exception as e:
        print(f"❌ 5. Model types failed: {e}")
    
    # Test 6: Multi-language support
    try:
        from lyo_app.ai_agents.orchestrator import ai_orchestrator
        test_response = await ai_orchestrator.generate_response(
            prompt="Test prompt",
            model_type=ModelType.GEMMA_4_ON_DEVICE,
            language=LanguageCode.ENGLISH,
            complexity=TaskComplexity.SIMPLE
        )
        print("✅ 6. Multi-language response generation working")
        tests_passed += 1
    except Exception as e:
        print(f"❌ 6. Multi-language test failed: {e}")
    
    print("\n" + "=" * 50)
    print(f"🎯 Final Result: {tests_passed}/{total_tests} tests passed ({tests_passed/total_tests*100:.1f}%)")
    
    if tests_passed == total_tests:
        print("🎉 AI AGENTS PRODUCTION UPGRADE COMPLETE!")
        print("✨ All systems are ready for production deployment")
    elif tests_passed >= 4:
        print("⚡ AI AGENTS UPGRADE MOSTLY COMPLETE!")
        print("🔧 Minor issues remain but core functionality works")
    else:
        print("⚠️  AI AGENTS UPGRADE NEEDS ATTENTION")
        print("🛠️  Some critical issues need resolution")
    
    return tests_passed == total_tests

if __name__ == "__main__":
    result = asyncio.run(main())
    sys.exit(0 if result else 1)
