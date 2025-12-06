"""
Image Generation Service - DALL-E 3 Integration
Rich visual content for Lyo's AI Classroom

Creates educational diagrams, concept visualizations, and engaging imagery
for an award-winning learning experience.
"""

import asyncio
import aiohttp
import hashlib
import os
import logging
import json
from typing import Optional, Literal, Dict, Any, List
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from pathlib import Path
from enum import Enum

try:
    from lyo_app.integrations.gcp_secrets import get_secret
except Exception:
    def get_secret(name: str, default=None):
        return os.getenv(name, default)

logger = logging.getLogger(__name__)


class ImageStyle(str, Enum):
    """Available image styles for educational content"""
    VIVID = "vivid"      # Hyper-realistic, dramatic
    NATURAL = "natural"  # More natural, less hyper-real


class ImageSize(str, Enum):
    """Available image sizes"""
    SQUARE = "1024x1024"
    LANDSCAPE = "1792x1024"
    PORTRAIT = "1024x1792"


class ImageQuality(str, Enum):
    """Image quality levels"""
    STANDARD = "standard"
    HD = "hd"


# Educational prompt templates for different content types
EDUCATIONAL_PROMPTS = {
    "concept_diagram": """
Create a clean, professional educational diagram illustrating: {topic}
Style: Modern, minimalist design with clear labels
Colors: Use a cohesive color palette suitable for learning materials
Layout: Clear visual hierarchy, easy to understand at a glance
Include: Key concepts, relationships, and any relevant annotations
""",
    
    "process_flow": """
Create a clear process flow diagram showing: {topic}
Style: Clean flowchart with numbered steps
Colors: Use contrasting colors for different stages
Layout: Left-to-right or top-to-bottom flow
Include: Arrows showing direction, brief labels for each step
""",
    
    "comparison_chart": """
Create a visual comparison showing: {topic}
Style: Side-by-side or tabular comparison
Colors: Different colors for each item being compared
Layout: Clear, balanced visual representation
Include: Key differentiating features highlighted
""",
    
    "mind_map": """
Create an engaging mind map centered on: {topic}
Style: Organic, branch-like structure radiating from center
Colors: Different color for each main branch
Layout: Central concept with radiating sub-topics
Include: Icons or small illustrations for key concepts
""",
    
    "timeline": """
Create a visual timeline showing: {topic}
Style: Horizontal or vertical timeline with clear markers
Colors: Gradient or distinct colors for different eras/phases
Layout: Chronological order with even spacing
Include: Key dates, events, and brief descriptions
""",
    
    "anatomy_diagram": """
Create an educational anatomy/structure diagram of: {topic}
Style: Clean, labeled illustration
Colors: Distinct colors for different components
Layout: Clear labeling with leader lines
Include: All major components with accurate proportions
""",
    
    "infographic": """
Create an engaging educational infographic about: {topic}
Style: Modern, visually appealing data visualization
Colors: Vibrant but professional color scheme
Layout: Organized sections with visual hierarchy
Include: Key statistics, facts, and visual elements
""",
    
    "scene_illustration": """
Create an illustration depicting: {topic}
Style: Realistic but approachable educational illustration
Colors: Warm, inviting color palette
Setting: Appropriate context for the subject
Include: Relevant details that aid understanding
"""
}


@dataclass
class ImageConfig:
    """Image generation configuration"""
    api_key: str = ""
    model: str = "dall-e-3"
    default_size: ImageSize = ImageSize.SQUARE
    default_quality: ImageQuality = ImageQuality.HD
    default_style: ImageStyle = ImageStyle.NATURAL
    cache_enabled: bool = True
    cache_dir: str = "/tmp/lyo_image_cache"
    cache_ttl_hours: int = 168  # 1 week
    

@dataclass
class CachedImage:
    """Cached image entry"""
    file_path: str
    url: str
    created_at: datetime
    prompt_hash: str
    size: str
    revised_prompt: Optional[str]


@dataclass
class GeneratedImage:
    """Generated image result"""
    url: str
    revised_prompt: str
    size: str
    style: str
    prompt_used: str


class ImageService:
    """
    AI Image Generation Service for Educational Content
    
    Features:
    - DALL-E 3 integration for highest quality images
    - Educational prompt templates for various content types
    - Automatic style optimization for learning materials
    - Smart caching for performance
    - Multiple sizes for different use cases
    """
    
    def __init__(self, config: Optional[ImageConfig] = None):
        self.config = config or ImageConfig()
        self._session: Optional[aiohttp.ClientSession] = None
        self._cache: Dict[str, CachedImage] = {}
        self._initialized = False
        
    async def initialize(self):
        """Initialize image service"""
        if self._initialized:
            return
            
        api_key = get_secret("OPENAI_API_KEY", os.getenv("OPENAI_API_KEY", ""))
        if not api_key:
            logger.warning("OpenAI API key not found - Image generation will fail")
        else:
            self.config.api_key = api_key
            
        # Create cache directory
        cache_path = Path(self.config.cache_dir)
        cache_path.mkdir(parents=True, exist_ok=True)
        
        self._session = aiohttp.ClientSession(
            headers={
                "Authorization": f"Bearer {self.config.api_key}",
                "Content-Type": "application/json"
            },
            timeout=aiohttp.ClientTimeout(total=120)  # Images take longer
        )
        
        self._initialized = True
        logger.info("Image Generation Service initialized with DALL-E 3")
        
    async def close(self):
        """Cleanup resources"""
        if self._session:
            await self._session.close()
            self._session = None
        self._initialized = False
        
    def _get_cache_key(self, prompt: str, size: str, quality: str, style: str) -> str:
        """Generate cache key"""
        content = f"{prompt}:{size}:{quality}:{style}"
        return hashlib.sha256(content.encode()).hexdigest()[:16]
        
    def _get_cached_image(self, cache_key: str) -> Optional[CachedImage]:
        """Get image from cache if valid"""
        if not self.config.cache_enabled:
            return None
            
        cached = self._cache.get(cache_key)
        if not cached:
            return None
            
        if datetime.now() - cached.created_at > timedelta(hours=self.config.cache_ttl_hours):
            del self._cache[cache_key]
            return None
            
        return cached
        
    def build_educational_prompt(
        self, 
        topic: str, 
        content_type: str = "concept_diagram",
        additional_context: Optional[str] = None
    ) -> str:
        """
        Build an optimized prompt for educational image generation
        
        Args:
            topic: The subject to visualize
            content_type: Type of educational visual
            additional_context: Extra instructions
            
        Returns:
            Optimized prompt for DALL-E 3
        """
        template = EDUCATIONAL_PROMPTS.get(content_type, EDUCATIONAL_PROMPTS["concept_diagram"])
        prompt = template.format(topic=topic)
        
        if additional_context:
            prompt += f"\n\nAdditional context: {additional_context}"
            
        # Add educational optimization
        prompt += "\n\nIMPORTANT: This is for educational purposes. Make it clear, professional, and suitable for learning materials. Avoid any text that could be misspelled."
        
        return prompt
        
    async def generate(
        self,
        prompt: str,
        size: Optional[ImageSize] = None,
        quality: Optional[ImageQuality] = None,
        style: Optional[ImageStyle] = None,
        n: int = 1
    ) -> GeneratedImage:
        """
        Generate an image using DALL-E 3
        
        Args:
            prompt: Description of the image to generate
            size: Image dimensions
            quality: standard or hd
            style: vivid or natural
            n: Number of images (DALL-E 3 only supports 1)
            
        Returns:
            GeneratedImage with URL and metadata
        """
        if not self._initialized:
            await self.initialize()
            
        if not self.config.api_key:
            raise ValueError("OpenAI API key not configured")
            
        size = size or self.config.default_size
        quality = quality or self.config.default_quality
        style = style or self.config.default_style
        
        # Check cache
        cache_key = self._get_cache_key(prompt, size.value, quality.value, style.value)
        cached = self._get_cached_image(cache_key)
        if cached:
            logger.debug(f"Image cache hit: {cache_key}")
            return GeneratedImage(
                url=cached.url,
                revised_prompt=cached.revised_prompt or prompt,
                size=cached.size,
                style=style.value,
                prompt_used=prompt
            )
            
        payload = {
            "model": self.config.model,
            "prompt": prompt,
            "n": 1,  # DALL-E 3 only supports 1
            "size": size.value,
            "quality": quality.value,
            "style": style.value,
            "response_format": "url"
        }
        
        async with self._session.post(
            "https://api.openai.com/v1/images/generations",
            json=payload
        ) as response:
            if response.status != 200:
                error_text = await response.text()
                raise Exception(f"Image generation error: {response.status} - {error_text}")
                
            data = await response.json()
            
        image_data = data["data"][0]
        url = image_data["url"]
        revised_prompt = image_data.get("revised_prompt", prompt)
        
        # Cache result
        self._cache[cache_key] = CachedImage(
            file_path="",  # URL-based caching
            url=url,
            created_at=datetime.now(),
            prompt_hash=cache_key,
            size=size.value,
            revised_prompt=revised_prompt
        )
        
        logger.info(f"Image generated: {size.value}, style={style.value}")
        
        return GeneratedImage(
            url=url,
            revised_prompt=revised_prompt,
            size=size.value,
            style=style.value,
            prompt_used=prompt
        )
        
    async def generate_educational(
        self,
        topic: str,
        content_type: str = "concept_diagram",
        additional_context: Optional[str] = None,
        size: Optional[ImageSize] = None
    ) -> GeneratedImage:
        """
        Generate an educational image
        
        Convenience method that uses educational prompt templates
        """
        prompt = self.build_educational_prompt(topic, content_type, additional_context)
        
        # Educational content looks best in natural style
        return await self.generate(
            prompt=prompt,
            size=size or ImageSize.LANDSCAPE,  # Landscape works well for diagrams
            quality=ImageQuality.HD,
            style=ImageStyle.NATURAL
        )
        
    async def generate_lesson_images(
        self,
        lesson_topic: str,
        concepts: List[str],
        max_images: int = 3
    ) -> List[GeneratedImage]:
        """
        Generate images for a lesson
        
        Creates visuals for key concepts in the lesson
        """
        images = []
        
        # Generate main concept image
        main_image = await self.generate_educational(
            topic=lesson_topic,
            content_type="concept_diagram",
            size=ImageSize.LANDSCAPE
        )
        images.append(main_image)
        
        # Generate images for additional concepts (up to max_images - 1)
        for concept in concepts[:max_images - 1]:
            try:
                image = await self.generate_educational(
                    topic=concept,
                    content_type="infographic",
                    additional_context=f"Part of a lesson on {lesson_topic}",
                    size=ImageSize.SQUARE
                )
                images.append(image)
            except Exception as e:
                logger.warning(f"Failed to generate image for concept '{concept}': {e}")
                continue
                
        return images
        
    def get_content_types(self) -> Dict[str, str]:
        """Get available educational content types"""
        return {
            "concept_diagram": "Clean diagram illustrating a concept",
            "process_flow": "Flowchart showing a process",
            "comparison_chart": "Side-by-side comparison",
            "mind_map": "Mind map with branching concepts",
            "timeline": "Chronological timeline",
            "anatomy_diagram": "Labeled structure diagram",
            "infographic": "Engaging data visualization",
            "scene_illustration": "Illustrative scene"
        }


# Singleton instance
_image_service: Optional[ImageService] = None


async def get_image_service() -> ImageService:
    """Get or create the image service singleton"""
    global _image_service
    if _image_service is None:
        _image_service = ImageService()
        await _image_service.initialize()
    return _image_service
