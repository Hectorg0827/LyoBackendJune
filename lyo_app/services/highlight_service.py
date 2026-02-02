
import logging
import asyncio
from typing import List, Dict, Any
from lyo_app.core.database import AsyncSessionLocal
from lyo_app.feeds.models import Post, PostType
from lyo_app.core.ai_resilience import ai_resilience_manager

logger = logging.getLogger(__name__)

class HighlightService:
    """
    Service to generate automated 'Mastery Highlights' for the social feed.
    Transforms live learning sessions into engaging social content.
    """
    
    async def generate_mastery_highlight(self, user_id: int, history: List[Dict[str, str]], session_id: int):
        """
        Analyze a completed learning session and create a feed post.
        """
        if not user_id or not history:
            return

        try:
            # 1. Extract the core concept learned
            # We filter out system messages and very short exchanges
            filtered_history = [m for m in history if m["role"] != "system" and len(m["content"]) > 10]
            if not filtered_history:
                return

            # 2. Use LLM to generate a punchy, 'addictive' learning snippet
            prompt = [
                {
                    "role": "system", 
                    "content": (
                        "You are a social media copywriter for a learning app. "
                        "Transform the following session history into a punchy, high-energy 'Mastery Highlight' post. "
                        "Style: TikTok/Instagram vibe, emojis, short (max 120 chars). "
                        "Focus on the 'aha!' moment or a key fact learned. "
                        "Format: 'Mastered [Concept] with Lyo! 🚀 [Insight]'"
                    )
                },
                {"role": "user", "content": str(filtered_history[-10:])} # Use last 10 messages
            ]
            
            response = await ai_resilience_manager.chat_completion(prompt)
            content = response.get("content", "Just mastered a new concept with Lyo! 🧠✨")
            
            # 3. Persist to the database
            async with AsyncSessionLocal() as db:
                new_post = Post(
                    author_id=user_id,
                    content=content,
                    post_type=PostType.COURSE_PROGRESS,
                    is_public=True
                )
                db.add(new_post)
                await db.commit()
                logger.info(f"✨ Mastery Highlight published for user {user_id}: {content}")
                
        except Exception as e:
            logger.error(f"Failed to generate mastery highlight: {e}")

# Global instance
highlight_service = HighlightService()
