import asyncio
import os
import sys

# Add directory to path to allow importing lyo_app
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from lyo_app.image_gen.service import ImageService, ImageConfig

async def test_init():
    print("Testing ImageService initialization...")
    # Provide a dummy project ID so it initializes vertex ai cleanly
    os.environ["GOOGLE_CLOUD_PROJECT"] = "dummy-project"
    service = ImageService(ImageConfig())
    
    # We only test initialization so it doesn't incur real API charges or require auth token
    try:
        await service.initialize()
        print("Initialization successful!")
        
        # Test prompt builder
        prompt = service.build_educational_prompt("Photosynthesis", "concept_diagram")
        assert "Photosynthesis" in prompt
        assert "IMPORTANT: This is for educational purposes" in prompt
        print("Prompt builder works!")
    except Exception as e:
        print(f"Failed: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    asyncio.run(test_init())
