"""
Asset Pipeline Service for Interactive Cinema Playback

This service handles pre-fetching, caching, and delivery of multimedia assets
(audio narration, images) for the "Netflix-like" node playback experience.

Features:
- Pre-fetches assets for next N nodes (lookahead)
- Intelligent voice selection based on node type
- Parallel asset generation for speed
- Cache management with TTL
- Asset status tracking for client buffering
"""

import asyncio
import hashlib
import logging
from typing import Optional, Dict, List, Any, Tuple
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, update

from lyo_app.ai_classroom.models import LearningNode, LearningEdge, GraphCourse
from lyo_app.tts.service import TTSService, VOICE_PROFILES
from lyo_app.image_gen.service import ImageService, ImageSize, ImageQuality, ImageStyle

logger = logging.getLogger(__name__)


class AssetType(str, Enum):
    """Types of assets for nodes"""
    AUDIO = "audio"
    IMAGE = "image"
    VIDEO = "video"  # Future consideration


class AssetStatus(str, Enum):
    """Status of asset generation"""
    PENDING = "pending"
    GENERATING = "generating"
    READY = "ready"
    FAILED = "failed"
    EXPIRED = "expired"


@dataclass
class AssetMetadata:
    """Metadata for a generated asset"""
    asset_type: AssetType
    url: str
    status: AssetStatus
    created_at: datetime
    expires_at: datetime
    size_bytes: Optional[int] = None
    duration_seconds: Optional[float] = None  # For audio
    voice_used: Optional[str] = None
    content_hash: str = ""
    generation_time_ms: Optional[int] = None


@dataclass
class NodeAssets:
    """All assets for a single node"""
    node_id: UUID
    audio: Optional[AssetMetadata] = None
    image: Optional[AssetMetadata] = None
    all_ready: bool = False
    error: Optional[str] = None


@dataclass
class AssetConfig:
    """Configuration for asset pipeline"""
    lookahead_count: int = 3  # Pre-fetch next N nodes
    audio_cache_ttl_hours: int = 24
    image_cache_ttl_hours: int = 72
    max_parallel_generations: int = 4
    enable_audio: bool = True
    enable_images: bool = True
    default_voice: str = "nova"
    audio_format: str = "mp3"
    image_size: str = "1024x1024"


# Voice selection based on node type for educational variety
NODE_TYPE_VOICES = {
    "hook": "nova",          # Energetic to grab attention
    "narrative": "echo",     # Warm for storytelling
    "explanation": "alloy",  # Clear for teaching
    "interaction": "nova",   # Encouraging for questions
    "remediation": "shimmer", # Gentle for correction
    "summary": "alloy",      # Clear recap
    "review": "fable",       # Engaging for review
    "transition": "nova",    # Quick and energetic
    "celebration": "nova",   # Excited for wins
}


class AssetPipelineService:
    """
    Manages multimedia asset generation and delivery for node playback.
    
    The service:
    1. Pre-fetches assets for upcoming nodes (lookahead)
    2. Selects appropriate voices based on content type
    3. Generates images for visual learners
    4. Caches assets with intelligent TTL
    5. Tracks generation status for client buffering UI
    """
    
    def __init__(
        self,
        tts_service: Optional[TTSService] = None,
        image_service: Optional[ImageService] = None,
        config: Optional[AssetConfig] = None
    ):
        self.config = config or AssetConfig()
        self.tts_service = tts_service
        self.image_service = image_service
        
        # In-memory cache for asset metadata
        # Key: content_hash -> AssetMetadata
        self._asset_cache: Dict[str, AssetMetadata] = {}
        
        # Track in-progress generations to avoid duplicates
        self._generation_locks: Dict[str, asyncio.Lock] = {}
        
        # Semaphore to limit parallel generations
        self._generation_semaphore = asyncio.Semaphore(
            self.config.max_parallel_generations
        )
        
        self._initialized = False
    
    async def initialize(self):
        """Initialize asset services"""
        if self._initialized:
            return
        
        # Initialize TTS if not provided
        if self.tts_service is None:
            self.tts_service = TTSService()
        await self.tts_service.initialize()
        
        # Initialize Image service if not provided
        if self.image_service is None:
            self.image_service = ImageService()
        await self.image_service.initialize()
        
        self._initialized = True
        logger.info("Asset Pipeline Service initialized")
    
    async def close(self):
        """Cleanup resources"""
        if self.tts_service:
            await self.tts_service.close()
        if self.image_service:
            await self.image_service.close()
        self._initialized = False
    
    def _get_content_hash(self, content: str, asset_type: AssetType) -> str:
        """Generate hash for content caching"""
        hash_input = f"{asset_type.value}:{content}"
        return hashlib.sha256(hash_input.encode()).hexdigest()[:16]
    
    def _select_voice_for_node(self, node: LearningNode) -> str:
        """
        Select the best TTS voice for a node based on its type and content.
        
        Provides variety in the learning experience by matching voice
        personality to content type.
        """
        # Check node type first
        voice = NODE_TYPE_VOICES.get(node.node_type, self.config.default_voice)
        
        # Override based on specific content cues
        content_lower = node.script_text.lower() if node.script_text else ""
        
        if any(word in content_lower for word in ["congratulations", "excellent", "great job", "well done"]):
            voice = "nova"  # Celebratory
        elif any(word in content_lower for word in ["don't worry", "let's try", "it's okay"]):
            voice = "shimmer"  # Encouraging
        elif any(word in content_lower for word in ["important", "key concept", "remember"]):
            voice = "onyx"  # Authoritative
        elif any(word in content_lower for word in ["story", "once upon", "long ago"]):
            voice = "echo"  # Storytelling
        
        return voice
    
    async def _get_or_create_lock(self, key: str) -> asyncio.Lock:
        """Get or create a lock for a specific generation task"""
        if key not in self._generation_locks:
            self._generation_locks[key] = asyncio.Lock()
        return self._generation_locks[key]
    
    async def generate_audio_for_node(
        self,
        node: LearningNode,
        force_regenerate: bool = False
    ) -> Optional[AssetMetadata]:
        """
        Generate TTS audio for a node's script.
        
        Args:
            node: The learning node to generate audio for
            force_regenerate: Skip cache and regenerate
            
        Returns:
            AssetMetadata with audio URL or None if failed
        """
        if not self.config.enable_audio:
            return None
        
        if not node.script_text:
            logger.debug(f"Node {node.id} has no script text")
            return None
        
        content_hash = self._get_content_hash(node.script_text, AssetType.AUDIO)
        
        # Check cache first
        if not force_regenerate and content_hash in self._asset_cache:
            cached = self._asset_cache[content_hash]
            if cached.expires_at > datetime.utcnow():
                logger.debug(f"Audio cache hit for node {node.id}")
                return cached
        
        # Get lock to prevent duplicate generation
        lock = await self._get_or_create_lock(f"audio:{content_hash}")
        
        async with lock:
            # Double-check cache after acquiring lock
            if not force_regenerate and content_hash in self._asset_cache:
                cached = self._asset_cache[content_hash]
                if cached.expires_at > datetime.utcnow():
                    return cached
            
            try:
                async with self._generation_semaphore:
                    start_time = datetime.utcnow()
                    
                    voice = self._select_voice_for_node(node)
                    
                    # Generate audio
                    audio_data = await self.tts_service.generate(
                        text=node.script_text,
                        voice=voice,
                        format=self.config.audio_format
                    )
                    
                    generation_time = int(
                        (datetime.utcnow() - start_time).total_seconds() * 1000
                    )
                    
                    # Create metadata
                    metadata = AssetMetadata(
                        asset_type=AssetType.AUDIO,
                        url=audio_data.get("url", "") if isinstance(audio_data, dict) else getattr(audio_data, "url", ""),
                        status=AssetStatus.READY,
                        created_at=datetime.utcnow(),
                        expires_at=datetime.utcnow() + timedelta(
                            hours=self.config.audio_cache_ttl_hours
                        ),
                        duration_seconds=audio_data.get("duration") if isinstance(audio_data, dict) else getattr(audio_data, "duration", None),
                        voice_used=voice,
                        content_hash=content_hash,
                        generation_time_ms=generation_time
                    )
                    
                    # Cache it
                    self._asset_cache[content_hash] = metadata
                    
                    logger.info(
                        f"Audio generated for node {node.id} "
                        f"voice={voice} time={generation_time}ms"
                    )
                    
                    return metadata
                    
            except Exception as e:
                logger.error(f"Failed to generate audio for node {node.id}: {e}")
                return AssetMetadata(
                    asset_type=AssetType.AUDIO,
                    url="",
                    status=AssetStatus.FAILED,
                    created_at=datetime.utcnow(),
                    expires_at=datetime.utcnow(),
                    content_hash=content_hash
                )
    
    async def generate_image_for_node(
        self,
        node: LearningNode,
        force_regenerate: bool = False
    ) -> Optional[AssetMetadata]:
        """
        Generate an educational image for a node.
        
        Args:
            node: The learning node to generate image for
            force_regenerate: Skip cache and regenerate
            
        Returns:
            AssetMetadata with image URL or None if failed
        """
        if not self.config.enable_images:
            return None
        
        # Only generate images for certain node types
        if node.node_type not in ["narrative", "explanation", "hook", "summary"]:
            return None
        
        # Use node's visual cue or script for image generation
        image_prompt = node.visual_cue or node.title or node.script_text[:200] if node.script_text else None
        
        if not image_prompt:
            return None
        
        content_hash = self._get_content_hash(image_prompt, AssetType.IMAGE)
        
        # Check cache
        if not force_regenerate and content_hash in self._asset_cache:
            cached = self._asset_cache[content_hash]
            if cached.expires_at > datetime.utcnow():
                logger.debug(f"Image cache hit for node {node.id}")
                return cached
        
        lock = await self._get_or_create_lock(f"image:{content_hash}")
        
        async with lock:
            if not force_regenerate and content_hash in self._asset_cache:
                cached = self._asset_cache[content_hash]
                if cached.expires_at > datetime.utcnow():
                    return cached
            
            try:
                async with self._generation_semaphore:
                    start_time = datetime.utcnow()
                    
                    # Determine content type for image generation
                    content_type = "concept_diagram"
                    if node.node_type == "hook":
                        content_type = "engaging_visual"
                    elif node.node_type == "narrative":
                        content_type = "story_illustration"
                    elif node.node_type == "summary":
                        content_type = "infographic"
                    
                    # Generate image
                    image_result = await self.image_service.generate_educational(
                        topic=image_prompt,
                        content_type=content_type,
                        size=ImageSize.LANDSCAPE
                    )
                    
                    generation_time = int(
                        (datetime.utcnow() - start_time).total_seconds() * 1000
                    )
                    
                    metadata = AssetMetadata(
                        asset_type=AssetType.IMAGE,
                        url=image_result.url,
                        status=AssetStatus.READY,
                        created_at=datetime.utcnow(),
                        expires_at=datetime.utcnow() + timedelta(
                            hours=self.config.image_cache_ttl_hours
                        ),
                        content_hash=content_hash,
                        generation_time_ms=generation_time
                    )
                    
                    self._asset_cache[content_hash] = metadata
                    
                    logger.info(
                        f"Image generated for node {node.id} "
                        f"type={content_type} time={generation_time}ms"
                    )
                    
                    return metadata
                    
            except Exception as e:
                logger.error(f"Failed to generate image for node {node.id}: {e}")
                return AssetMetadata(
                    asset_type=AssetType.IMAGE,
                    url="",
                    status=AssetStatus.FAILED,
                    created_at=datetime.utcnow(),
                    expires_at=datetime.utcnow(),
                    content_hash=content_hash
                )
    
    async def get_node_assets(
        self,
        node: LearningNode,
        generate_if_missing: bool = True
    ) -> NodeAssets:
        """
        Get all assets for a node, generating if needed.
        
        Args:
            node: The learning node
            generate_if_missing: Whether to generate missing assets
            
        Returns:
            NodeAssets with all asset metadata
        """
        if not self._initialized:
            await self.initialize()
        
        assets = NodeAssets(node_id=node.id)
        
        try:
            if generate_if_missing:
                # Generate both in parallel
                audio_task = self.generate_audio_for_node(node)
                image_task = self.generate_image_for_node(node)
                
                audio_result, image_result = await asyncio.gather(
                    audio_task, image_task,
                    return_exceptions=True
                )
                
                if isinstance(audio_result, AssetMetadata):
                    assets.audio = audio_result
                elif isinstance(audio_result, Exception):
                    logger.error(f"Audio generation error: {audio_result}")
                
                if isinstance(image_result, AssetMetadata):
                    assets.image = image_result
                elif isinstance(image_result, Exception):
                    logger.error(f"Image generation error: {image_result}")
            else:
                # Check cache only
                if node.script_text:
                    audio_hash = self._get_content_hash(node.script_text, AssetType.AUDIO)
                    if audio_hash in self._asset_cache:
                        assets.audio = self._asset_cache[audio_hash]
                
                image_prompt = node.visual_cue or node.title
                if image_prompt:
                    image_hash = self._get_content_hash(image_prompt, AssetType.IMAGE)
                    if image_hash in self._asset_cache:
                        assets.image = self._asset_cache[image_hash]
            
            # Determine if all required assets are ready
            audio_ready = (
                assets.audio is None or 
                assets.audio.status == AssetStatus.READY
            )
            image_ready = (
                assets.image is None or 
                assets.image.status == AssetStatus.READY
            )
            assets.all_ready = audio_ready and image_ready
            
        except Exception as e:
            logger.error(f"Error getting assets for node {node.id}: {e}")
            assets.error = str(e)
        
        return assets
    
    async def prefetch_lookahead_assets(
        self,
        db: AsyncSession,
        course_id: UUID,
        current_node_id: UUID,
        lookahead_count: Optional[int] = None
    ) -> Dict[str, NodeAssets]:
        """
        Pre-fetch assets for upcoming nodes in the learning path.
        
        This enables the "Netflix-like" experience where content is
        buffered ahead of time for seamless playback.
        
        Args:
            db: Database session
            course_id: Course being played
            current_node_id: Current playback position
            lookahead_count: Number of nodes to prefetch (defaults to config)
            
        Returns:
            Dict mapping node_id -> NodeAssets
        """
        if not self._initialized:
            await self.initialize()
        
        count = lookahead_count or self.config.lookahead_count
        
        # Get upcoming nodes
        # This finds nodes connected from current via edges
        result = await db.execute(
            select(LearningNode)
            .join(LearningEdge, LearningEdge.target_node_id == LearningNode.id)
            .where(
                LearningEdge.source_node_id == current_node_id,
                LearningNode.course_id == course_id
            )
            .limit(count)
        )
        upcoming_nodes = result.scalars().all()
        
        if not upcoming_nodes:
            logger.debug(f"No upcoming nodes to prefetch from {current_node_id}")
            return {}
        
        # Generate assets for all upcoming nodes in parallel
        prefetch_results: Dict[str, NodeAssets] = {}
        
        async def prefetch_node(node: LearningNode):
            assets = await self.get_node_assets(node, generate_if_missing=True)
            return str(node.id), assets
        
        tasks = [prefetch_node(node) for node in upcoming_nodes]
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        for result in results:
            if isinstance(result, tuple):
                node_id, assets = result
                prefetch_results[node_id] = assets
            elif isinstance(result, Exception):
                logger.error(f"Prefetch error: {result}")
        
        logger.info(
            f"Prefetched assets for {len(prefetch_results)} nodes "
            f"from course {course_id}"
        )
        
        return prefetch_results
    
    async def get_asset_status(
        self,
        node_ids: List[UUID]
    ) -> Dict[str, Dict[str, AssetStatus]]:
        """
        Get asset generation status for multiple nodes.
        
        Used by client to show buffering progress.
        
        Args:
            node_ids: List of node IDs to check
            
        Returns:
            Dict mapping node_id -> {asset_type -> status}
        """
        status_map: Dict[str, Dict[str, AssetStatus]] = {}
        
        for node_id in node_ids:
            node_status: Dict[str, AssetStatus] = {}
            
            # Check each asset type in cache
            for asset_type in [AssetType.AUDIO, AssetType.IMAGE]:
                # We'd need the content to check cache
                # For now, return pending if not found
                found = False
                for hash_key, metadata in self._asset_cache.items():
                    if metadata.asset_type == asset_type:
                        # This is a simplified check - in production,
                        # we'd track node_id -> content_hash mapping
                        node_status[asset_type.value] = metadata.status
                        found = True
                        break
                
                if not found:
                    node_status[asset_type.value] = AssetStatus.PENDING
            
            status_map[str(node_id)] = node_status
        
        return status_map
    
    def clear_expired_cache(self) -> int:
        """
        Clear expired assets from cache.
        
        Returns:
            Number of items cleared
        """
        now = datetime.utcnow()
        expired_keys = [
            key for key, meta in self._asset_cache.items()
            if meta.expires_at <= now
        ]
        
        for key in expired_keys:
            del self._asset_cache[key]
        
        if expired_keys:
            logger.info(f"Cleared {len(expired_keys)} expired cache entries")
        
        return len(expired_keys)
    
    def get_cache_stats(self) -> Dict[str, Any]:
        """Get cache statistics for monitoring"""
        now = datetime.utcnow()
        
        audio_count = sum(
            1 for m in self._asset_cache.values() 
            if m.asset_type == AssetType.AUDIO
        )
        image_count = sum(
            1 for m in self._asset_cache.values() 
            if m.asset_type == AssetType.IMAGE
        )
        ready_count = sum(
            1 for m in self._asset_cache.values() 
            if m.status == AssetStatus.READY
        )
        expired_count = sum(
            1 for m in self._asset_cache.values() 
            if m.expires_at <= now
        )
        
        total_gen_time = sum(
            m.generation_time_ms or 0 
            for m in self._asset_cache.values()
        )
        
        return {
            "total_cached": len(self._asset_cache),
            "audio_count": audio_count,
            "image_count": image_count,
            "ready_count": ready_count,
            "expired_count": expired_count,
            "avg_generation_time_ms": (
                total_gen_time / len(self._asset_cache) 
                if self._asset_cache else 0
            ),
            "cache_config": {
                "audio_ttl_hours": self.config.audio_cache_ttl_hours,
                "image_ttl_hours": self.config.image_cache_ttl_hours,
                "lookahead_count": self.config.lookahead_count
            }
        }


# Singleton instance for app-wide use
_asset_service: Optional[AssetPipelineService] = None


async def get_asset_service() -> AssetPipelineService:
    """Get or create the asset pipeline service singleton"""
    global _asset_service
    if _asset_service is None:
        _asset_service = AssetPipelineService()
        await _asset_service.initialize()
    return _asset_service


async def cleanup_asset_service():
    """Cleanup the asset service on shutdown"""
    global _asset_service
    if _asset_service:
        await _asset_service.close()
        _asset_service = None
