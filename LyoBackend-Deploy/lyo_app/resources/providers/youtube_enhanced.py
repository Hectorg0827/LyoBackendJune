"""
Enhanced YouTube educational content provider with quota management and caching.
"""
import re
import logging
from typing import List, Optional, Dict, Any
from datetime import timedelta, datetime

from lyo_app.core.api_client import BaseAPIClient, QuotaExceededError
from lyo_app.core.config import settings
from .base import BaseResourceProvider, ResourceData
from ..models import ResourceType, ResourceProvider

logger = logging.getLogger(__name__)


class YouTubeProviderEnhanced(BaseResourceProvider):
    """Enhanced YouTube Data API v3 provider for educational videos."""
    
    # Educational channels with high-quality content
    EDUCATIONAL_CHANNELS = {
        'UC4a-Gbdw7vOaccHmFo40b9g': 'Khan Academy',
        'UCsooa4yRKGN_zEE8iknghZA': 'TED-Ed',
        'UCP7jMXSY2xbc3KCAE0MHQ-A': 'The Brain Scoop',
        'UC2C_jShtL725hvbm1arSV9w': 'CGP Grey',
        'UCX6b17PVsYBQ0ip5gyeme-Q': 'CrashCourse',
        'UC8butISFwT-Wl7EV0hUK0BQ': 'freeCodeCamp',
        'UCJ0-OtVpF0wOKEqT2Z1HEtA': 'ElectroBOOM',
        'UCiPiO_dN4S24823bAQf-Xow': 'Practical Engineering',
        'UC9-y-6csu5WGm29I7JiwpnA': 'Computerphile',
        'UCYO_jab_esuFRV4b17AJtAw': '3Blue1Brown'
    }
    
    # API quota costs for different operations
    QUOTA_COSTS = {
        "search": 100,
        "videos": 1,
        "channels": 1,
        "playlists": 1
    }
    
    def __init__(self, api_key: str):
        """Initialize YouTube provider with enhanced configuration."""
        super().__init__(api_key)
        self.api_client = BaseAPIClient(
            base_url="https://www.googleapis.com/youtube/v3",
            api_key=api_key,
            rate_limit=(100, 60),  # YouTube allows 100 requests per minute
            timeout=30
        )
        self.daily_quota_used = 0
        self.daily_quota_limit = settings.youtube_daily_quota
    
    async def search_resources(
        self, 
        query: str, 
        resource_type: Optional[ResourceType] = None,
        limit: int = 50
    ) -> List[ResourceData]:
        """Search YouTube for educational videos with enhanced filtering."""
        if resource_type and resource_type != ResourceType.VIDEO:
            return []
        
        # Check quota before making request
        if not await self._check_quota("search"):
            logger.warning("YouTube search quota exceeded")
            return []
        
        search_params = {
            'part': 'snippet',
            'q': f"{query} education tutorial",
            'type': 'video',
            'videoDefinition': 'high',
            'videoCategory': '27',  # Education category
            'maxResults': min(limit, 50),
            'order': 'relevance',
            'videoEmbeddable': 'true',
            'videoSyndicated': 'true',
            'videoDuration': 'medium',  # Filter out very short/long videos
            'relevanceLanguage': 'en'
        }
        
        try:
            async with self.api_client as client:
                response_data = await client.get("/search", params=search_params)
                
                # Update quota usage
                await self._update_quota_usage("search")
                
                # Get video IDs for detailed information
                video_ids = [item['id']['videoId'] for item in response_data.get('items', [])
                           if 'videoId' in item.get('id', {})]
                
                if not video_ids:
                    return []
                
                # Get detailed video information
                videos_data = await self._get_video_details(video_ids)
                
                # Convert to ResourceData objects
                resources = []
                for video in videos_data:
                    try:
                        resource = self._convert_to_resource_data(video)
                        if resource and self._is_educational_content(resource):
                            resources.append(resource)
                    except Exception as e:
                        logger.error(f"Error converting YouTube video to resource: {e}")
                        continue
                
                logger.info(f"YouTube search returned {len(resources)} educational videos")
                return resources
                
        except QuotaExceededError:
            logger.error("YouTube API quota exceeded")
            return []
        except Exception as e:
            logger.error(f"YouTube search error: {e}")
            return []
    
    async def _check_quota(self, operation: str) -> bool:
        """Check if we have enough quota for the operation."""
        cost = self.QUOTA_COSTS.get(operation, 1)
        return (self.daily_quota_used + cost) <= self.daily_quota_limit
    
    async def _update_quota_usage(self, operation: str):
        """Update quota usage after successful API call."""
        cost = self.QUOTA_COSTS.get(operation, 1)
        self.daily_quota_used += cost
        
        logger.info(
            f"YouTube API {operation} used {cost} quota points. "
            f"Total: {self.daily_quota_used}/{self.daily_quota_limit}"
        )
        
        # Log warning if approaching quota limit
        if self.daily_quota_used > (self.daily_quota_limit * 0.8):
            logger.warning(
                f"YouTube API quota usage at {(self.daily_quota_used/self.daily_quota_limit)*100:.1f}%"
            )
    
    async def _get_video_details(self, video_ids: List[str]) -> List[Dict[str, Any]]:
        """Get detailed information for multiple videos."""
        if not video_ids:
            return []
        
        if not await self._check_quota("videos"):
            return []
        
        params = {
            'part': 'snippet,contentDetails,statistics,status',
            'id': ','.join(video_ids)
        }
        
        try:
            async with self.api_client as client:
                response_data = await client.get("/videos", params=params)
                await self._update_quota_usage("videos")
                return response_data.get('items', [])
        except Exception as e:
            logger.error(f"Error getting video details: {e}")
            return []
    
    def _convert_to_resource_data(self, video_data: Dict[str, Any]) -> Optional[ResourceData]:
        """Convert YouTube video data to ResourceData object."""
        try:
            snippet = video_data.get('snippet', {})
            content_details = video_data.get('contentDetails', {})
            statistics = video_data.get('statistics', {})
            
            # Parse duration
            duration_str = content_details.get('duration', 'PT0M')
            duration_minutes = self._parse_duration(duration_str)
            
            # Skip videos that are too short or too long
            if duration_minutes < 2 or duration_minutes > 180:  # 2 min to 3 hours
                return None
            
            # Calculate difficulty based on title and description
            difficulty = self._estimate_difficulty(snippet)
            
            # Get best thumbnail
            thumbnails = snippet.get('thumbnails', {})
            thumbnail_url = (
                thumbnails.get('maxres', {}).get('url') or
                thumbnails.get('high', {}).get('url') or
                thumbnails.get('medium', {}).get('url') or
                thumbnails.get('default', {}).get('url')
            )
            
            return ResourceData(
                title=snippet.get('title', ''),
                description=snippet.get('description', '')[:500],  # Limit description length
                external_url=f"https://www.youtube.com/watch?v={video_data['id']}",
                external_id=video_data['id'],
                resource_type=ResourceType.VIDEO,
                provider=ResourceProvider.YOUTUBE,
                author=snippet.get('channelTitle', ''),
                thumbnail_url=thumbnail_url,
                duration_minutes=duration_minutes,
                difficulty_level=difficulty,
                subject_area=self.extract_subject_area(snippet.get('title', '') + ' ' + snippet.get('description', '')),
                tags=snippet.get('tags', [])[:10],  # Limit tags
                raw_data=video_data
            )
        except Exception as e:
            logger.error(f"Error converting video data: {e}")
            return None
    
    def _parse_duration(self, duration: str) -> int:
        """Parse ISO 8601 duration (PT1H2M3S) to minutes."""
        if not duration:
            return 0
            
        match = re.match(r'PT(?:(\d+)H)?(?:(\d+)M)?(?:(\d+)S)?', duration)
        if match:
            hours = int(match.group(1) or 0)
            minutes = int(match.group(2) or 0)
            seconds = int(match.group(3) or 0)
            return hours * 60 + minutes + (seconds // 60)
        return 0
    
    def _estimate_difficulty(self, snippet: Dict[str, Any]) -> str:
        """Estimate content difficulty based on title, description, and channel."""
        title = snippet.get('title', '').lower()
        description = snippet.get('description', '').lower()
        channel_title = snippet.get('channelTitle', '').lower()
        
        # Keywords for different difficulty levels
        beginner_keywords = [
            'introduction', 'intro', 'basics', 'beginner', '101', 'fundamental',
            'getting started', 'tutorial', 'how to', 'explained', 'simple'
        ]
        
        advanced_keywords = [
            'advanced', 'expert', 'deep dive', 'masterclass', 'pro', 'professional',
            'complex', 'detailed', 'comprehensive', 'in-depth', 'research'
        ]
        
        text = f"{title} {description} {channel_title}"
        
        # Count keyword matches
        beginner_score = sum(1 for keyword in beginner_keywords if keyword in text)
        advanced_score = sum(1 for keyword in advanced_keywords if keyword in text)
        
        if beginner_score > advanced_score:
            return 'beginner'
        elif advanced_score > beginner_score:
            return 'advanced'
        else:
            return 'intermediate'
    
    def _is_educational_content(self, resource: ResourceData) -> bool:
        """Check if content is educational based on various signals."""
        title = resource.title.lower()
        description = resource.description.lower()
        
        # Educational indicators
        educational_keywords = [
            'learn', 'education', 'tutorial', 'course', 'lesson', 'lecture',
            'explained', 'guide', 'how to', 'science', 'math', 'programming',
            'history', 'physics', 'chemistry', 'biology', 'engineering'
        ]
        
        # Non-educational indicators (exclude entertainment content)
        non_educational_keywords = [
            'funny', 'prank', 'reaction', 'meme', 'entertainment', 'music video',
            'vlog', 'gaming', 'unboxing', 'review'
        ]
        
        text = f"{title} {description}"
        
        educational_score = sum(1 for keyword in educational_keywords if keyword in text)
        non_educational_score = sum(1 for keyword in non_educational_keywords if keyword in text)
        
        # Must have educational indicators and minimal non-educational content
        return educational_score >= 1 and educational_score > non_educational_score
