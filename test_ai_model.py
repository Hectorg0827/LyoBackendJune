"""
Simple AI Model Test
Tests the local AI model integration for course generation.
"""

import asyncio
import sys
import os

# Add the project root to path so we can import modules
sys.path.insert(0, '/Users/republicalatuya/Desktop/LyoBackendJune')

from ai_model_manager import model_manager, initialize_model, generate_course_content


async def test_model_loading():
    """Test loading the AI model."""
    print("🧪 Testing AI Model Loading")
    print("=" * 50)
    
    try:
        # Initialize the model
        print("Initializing AI model...")
        success = await initialize_model()
        
        if success:
            print("✅ Model loaded successfully!")
            
            # Get model info
            info = model_manager.get_model_info()
            print(f"📊 Model Info:")
            for key, value in info.items():
                print(f"   {key}: {value}")
            
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
        
        # Simple test case
        prompt = """Create a course outline for Python Programming for beginners.
        
Please provide:
1. Course title
2. 3 main lessons
3. Brief description for each lesson

Course outline:"""
        
        print("📝 Generating course content...")
        print(f"Prompt: {prompt[:100]}...")
        
        # Generate content
        generated_content = generate_course_content(
            prompt=prompt,
            max_new_tokens=200,
            temperature=0.7
        )
        
        print(f"\n✅ Generated content:")
        print("-" * 30)
        print(generated_content)
        print("-" * 30)
        
        return True
        
    except Exception as e:
        print(f"❌ Course generation failed: {e}")
        return False


async def main():
    """Run the AI model test."""
    print("🚀 LyoBackend AI Model Integration Test")
    print("=" * 60)
    
    # Test model loading
    model_loaded = await test_model_loading()
    
    if not model_loaded:
        print("\n❌ Cannot proceed - model not loaded")
        return False
    
    # Test course generation
    generation_success = test_course_generation()
    
    # Summary
    print("\n📊 Test Summary")
    print("=" * 30)
    print(f"Model Loading: {'✅ PASS' if model_loaded else '❌ FAIL'}")
    print(f"Course Generation: {'✅ PASS' if generation_success else '❌ FAIL'}")
    
    overall_success = model_loaded and generation_success
    print(f"Overall: {'✅ ALL TESTS PASSED' if overall_success else '❌ SOME TESTS FAILED'}")
    
    if overall_success:
        print("\n🎉 AI model integration is working!")
        print("✅ Ready for AI-powered course generation!")
    else:
        print("\n🔧 Please check the errors and try again.")
    
    return overall_success


if __name__ == "__main__":
    asyncio.run(main())
