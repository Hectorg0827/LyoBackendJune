"""
AI-powered course generation test script.
Tests the local Gemma model integration for course creation.
"""

import asyncio
import logging
from typing import Dict, Any

from lyo_app.models.loading import model_manager, initialize_model, generate_course_content

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


async def test_model_loading():
    """Test loading the Gemma model."""
    print("🧪 Testing Gemma Model Loading")
    print("=" * 50)
    
    try:
        # Initialize the model
        logger.info("Initializing Gemma model...")
        success = await initialize_model()
        
        if success:
            print("✅ Model loaded successfully!")
            
            # Get model info
            info = model_manager.get_model_info()
            print(f"📊 Model Info:")
            print(f"   Status: {info.get('status')}")
            print(f"   Model ID: {info.get('model_id')}")
            print(f"   Device: {info.get('device')}")
            print(f"   Memory: {info.get('memory_footprint', 'N/A')}")
            
            return True
        else:
            print("❌ Model loading failed")
            return False
            
    except Exception as e:
        print(f"❌ Error during model loading: {e}")
        return False


def test_course_generation():
    """Test course generation using the loaded model."""
    print("\n🎓 Testing Course Generation")
    print("=" * 50)
    
    try:
        if not model_manager.is_loaded():
            print("❌ Model not loaded, cannot test generation")
            return False
        
        # Test course generation
        test_cases = [
            {
                "topic": "Python Programming",
                "level": "beginner",
                "interests": ["web development", "data science"]
            },
            {
                "topic": "Machine Learning",
                "level": "intermediate", 
                "interests": ["AI", "data analysis"]
            }
        ]
        
        for i, test_case in enumerate(test_cases, 1):
            print(f"\n📝 Test Case {i}: {test_case['topic']}")
            
            # Create course generation prompt
            prompt = f"""Create a course outline for:
Topic: {test_case['topic']}
Level: {test_case['level']}
Interests: {', '.join(test_case['interests'])}

Provide a structured course with 3-4 lessons, each with clear objectives."""
            
            # Generate content
            logger.info(f"Generating course for: {test_case['topic']}")
            generated_content = generate_course_content(
                prompt=prompt,
                max_new_tokens=512,
                temperature=0.7
            )
            
            print(f"✅ Generated content:")
            print(f"📄 Content preview:")
            print(generated_content[:300] + "..." if len(generated_content) > 300 else generated_content)
            print()
        
        return True
        
    except Exception as e:
        print(f"❌ Course generation failed: {e}")
        logger.exception("Course generation error:")
        return False


async def run_comprehensive_test():
    """Run comprehensive test of the AI course generation system."""
    print("🚀 LyoBackend AI Course Generation Test")
    print("=" * 60)
    
    # Test 1: Model Loading
    model_loaded = await test_model_loading()
    
    if not model_loaded:
        print("\n❌ Cannot proceed with course generation tests - model not loaded")
        return False
    
    # Test 2: Course Generation 
    generation_success = test_course_generation()
    
    # Summary
    print("\n📊 Test Summary")
    print("=" * 30)
    print(f"Model Loading: {'✅ PASS' if model_loaded else '❌ FAIL'}")
    print(f"Course Generation: {'✅ PASS' if generation_success else '❌ FAIL'}")
    
    overall_success = model_loaded and generation_success
    print(f"Overall: {'✅ ALL TESTS PASSED' if overall_success else '❌ SOME TESTS FAILED'}")
    
    if overall_success:
        print("\n🎉 Your backend is ready for AI-powered course generation!")
    else:
        print("\n🔧 Please check the logs and fix any issues before proceeding.")
    
    return overall_success


if __name__ == "__main__":
    asyncio.run(run_comprehensive_test())
