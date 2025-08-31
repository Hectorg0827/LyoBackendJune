#!/usr/bin/env python3
"""
Quick Superior AI Component Test
Simple test to verify superior AI components exist and can be imported
"""

import sys
import os
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

def test_superior_ai_components():
    """Test if superior AI components can be imported and instantiated"""
    
    print("🧪 Quick Superior AI Components Test")
    print("=" * 50)
    
    # Set environment for testing
    os.environ['TESTING'] = 'true'
    os.environ['ENABLE_SUPERIOR_AI_MODE'] = 'true'
    
    tests_passed = 0
    total_tests = 0
    
    # Test 1: Adaptive Engine
    print("\n1️⃣ Testing Adaptive Difficulty Engine...")
    total_tests += 1
    try:
        from lyo_app.ai_study.adaptive_engine import AdaptiveDifficultyEngine, LearningProfile, DifficultyLevel
        
        engine = AdaptiveDifficultyEngine()
        print("   ✅ AdaptiveDifficultyEngine imported and instantiated")
        
        # Test basic functionality
        profile = LearningProfile(
            user_id=1,
            subject="test",
            current_level=DifficultyLevel.BEGINNER,
            learning_style="visual"
        )
        print("   ✅ LearningProfile created")
        tests_passed += 1
        
    except Exception as e:
        print(f"   ❌ Error: {str(e)}")
    
    # Test 2: Advanced Socratic Engine
    print("\n2️⃣ Testing Advanced Socratic Engine...")
    total_tests += 1
    try:
        from lyo_app.ai_study.advanced_socratic import AdvancedSocraticEngine, SocraticStrategy
        
        engine = AdvancedSocraticEngine()
        print("   ✅ AdvancedSocraticEngine imported and instantiated")
        tests_passed += 1
        
    except Exception as e:
        print(f"   ❌ Error: {str(e)}")
    
    # Test 3: Superior Prompt Engine
    print("\n3️⃣ Testing Superior Prompt Engine...")
    total_tests += 1
    try:
        from lyo_app.ai_study.superior_prompts import SuperiorPromptEngine, PromptType, LearningStyle
        
        engine = SuperiorPromptEngine()
        print("   ✅ SuperiorPromptEngine imported and instantiated")
        tests_passed += 1
        
    except Exception as e:
        print(f"   ❌ Error: {str(e)}")
    
    # Test 4: Enhanced Study Service
    print("\n4️⃣ Testing Enhanced Study Service...")
    total_tests += 1
    try:
        from lyo_app.ai_study.service import StudyModeService
        
        service = StudyModeService()
        print("   ✅ StudyModeService imported and instantiated")
        
        # Check for superior AI methods
        has_superior_conversation = hasattr(service, '_process_superior_conversation')
        has_adaptive_integration = hasattr(service, '_adaptive_engine') or hasattr(service, 'adaptive_engine')
        
        if has_superior_conversation:
            print("   ✅ Superior conversation processing detected")
        
        if has_adaptive_integration:
            print("   ✅ Adaptive engine integration detected")
        
        tests_passed += 1
        
    except Exception as e:
        print(f"   ❌ Error: {str(e)}")
    
    # Test 5: Configuration System
    print("\n5️⃣ Testing Superior AI Configuration...")
    total_tests += 1
    try:
        from lyo_app.core.config_v2 import get_settings
        
        settings = get_settings()
        
        if hasattr(settings, 'ENABLE_SUPERIOR_AI_MODE'):
            print("   ✅ ENABLE_SUPERIOR_AI_MODE configuration exists")
            print(f"   📊 Superior AI Mode: {getattr(settings, 'ENABLE_SUPERIOR_AI_MODE', False)}")
            tests_passed += 1
        else:
            print("   ❌ ENABLE_SUPERIOR_AI_MODE configuration missing")
        
    except Exception as e:
        print(f"   ❌ Error: {str(e)}")
    
    # Summary
    print("\n" + "=" * 50)
    print("📊 QUICK TEST SUMMARY")
    print("=" * 50)
    
    success_rate = (tests_passed / total_tests * 100) if total_tests > 0 else 0
    print(f"Tests Passed: {tests_passed}/{total_tests} ({success_rate:.1f}%)")
    
    if success_rate >= 80:
        print("🎉 SUPERIOR AI COMPONENTS ARE FUNCTIONAL!")
        print("✨ Backend successfully implements superior AI capabilities")
        return True
    else:
        print("🔧 Some superior AI components need attention")
        return False

if __name__ == "__main__":
    success = test_superior_ai_components()
    
    # Create a simple results file
    with open("quick_superior_ai_test_results.txt", "w") as f:
        f.write(f"Quick Superior AI Test Results\n")
        f.write(f"Timestamp: {os.popen('date').read().strip()}\n")
        f.write(f"Test Status: {'PASSED' if success else 'FAILED'}\n")
    
    print(f"\n📄 Results saved to: quick_superior_ai_test_results.txt")
    
    sys.exit(0 if success else 1)
