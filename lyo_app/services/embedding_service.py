"""
Embedding Service
Handles generation of vector embeddings for RAG system using Google's Gemini API.
"""
import logging
import google.generativeai as genai
import asyncio
from typing import List, Optional
from tenacity import retry, stop_after_attempt, wait_exponential

from lyo_app.core.config import settings

logger = logging.getLogger(__name__)

# Configure Gemini
if settings.gemini_api_key:
    genai.configure(api_key=settings.gemini_api_key)

class EmbeddingService:
    """Service to generate embeddings for text content."""
    
    MODEL_NAME = "models/gemini-embedding-001"
    DIMENSION = 768

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=2, max=10))
    async def embed_text(self, text: str) -> Optional[List[float]]:
        """
        Generate embedding for a single text string.
        Returns a list of floats (vector).
        """
        if not text:
            return None
            
        try:
            # Run in executor since the library is synchronous
            result = await asyncio.to_thread(
                genai.embed_content,
                model=self.MODEL_NAME,
                content=text,
                task_type="retrieval_document",
                output_dimensionality=self.DIMENSION
            )
            
            if 'embedding' in result:
                return result['embedding']
            else:
                logger.warning("No embedding returned from Gemini API")
                return None
                
        except Exception as e:
            logger.error(f"Error generating embedding: {e}")
            raise e

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=2, max=10))
    async def embed_query(self, query: str) -> Optional[List[float]]:
        """
        Generate embedding for a search query.
        Uses 'retrieval_query' task type for better matching.
        """
        if not query:
            return None
            
        try:
            result = await asyncio.to_thread(
                genai.embed_content,
                model=self.MODEL_NAME,
                content=query,
                task_type="retrieval_query",
                output_dimensionality=self.DIMENSION
            )
            
            if 'embedding' in result:
                return result['embedding']
            return None
            
        except Exception as e:
            logger.error(f"Error generating query embedding: {e}")
            raise e

# Global instance
embedding_service = EmbeddingService()
