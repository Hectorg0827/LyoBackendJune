import asyncio
import os
import sys
from dotenv import load_dotenv

sys.path.insert(0, os.path.abspath(os.path.dirname(__file__)))

load_dotenv()
load_dotenv(".env.production")

from lyo_app.image_gen.service import ImageService, ImageSize

async def test_service():
    print("Testing ImageService with Runware Integration...")
    service = None
    try:
        service = ImageService()
        await service.initialize()
        
        print("\nRequesting an image generation via the service...")
        result = await service.generate(
            prompt="A majestic library in the clouds, ethereal lighting, concept art, highly detailed",
            size=ImageSize.SQUARE
        )
        
        print("\nSuccess! Result:")
        print(f"URL: {result.url}")
        print(f"Size Used: {result.size}")
        
    except Exception as e:
        print(f"Exception occurred: {e}")
    finally:
        if service:
            await service.close()

if __name__ == "__main__":
    asyncio.run(test_service())
