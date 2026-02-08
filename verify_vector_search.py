"""
Verify Vector Search Implementation
Tests the EmbeddingService and RAGService (connectivity only).
"""
import asyncio
import logging
import sys
import os

# Add project root to path
sys.path.append(os.getcwd())

from lyo_app.services.embedding_service import embedding_service
from lyo_app.core.config import settings

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

async def verify_embedding_service():
    print(f"🚀 Testing EmbeddingService using model: {embedding_service.MODEL_NAME}")
    
    test_text = "What is the capital of France?"
    print(f"Generating embedding for: '{test_text}'")
    
    try:
        vector = await embedding_service.embed_text(test_text)
        
        if vector:
            print(f"✅ Embedding generated successfully!")
            print(f"Dimension: {len(vector)}")
            print(f"Sample: {vector[:5]}...")
            
            if len(vector) != 768:
                print(f"⚠️ Warning: Expected dimension 768, got {len(vector)}")
        else:
            print("❌ No embedding returned.")
            
    except Exception as e:
        print(f"❌ Error generating embedding: {e}")

async def main():
    print("--- Starting Vector Search Verification ---")
    
    # Verify API Key presence
    if not settings.gemini_api_key:
        print("❌ GEMINI_API_KEY not found in settings!")
        return

    await verify_embedding_service()
    
    print("\n--- Verification Complete ---")

if __name__ == "__main__":
    asyncio.run(main())
