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


class YouTubeProvider(BaseResourceProvider):
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
        """Search YouTube for educational videos"""
        if resource_type and resource_type != ResourceType.VIDEO:
            return []
        
        search_params = {
            'part': 'snippet',
            'q': f"{query} education tutorial",
            'type': 'video',
            'videoDefinition': 'high',
            'videoCategory': '27',  # Education category
            'maxResults': min(limit, 50),
            'key': self.api_key,
            'order': 'relevance',
            'videoEmbeddable': 'true'
        }
        
        async with aiohttp.ClientSession() as session:
            try:
                async with session.get(f"{self.base_url}/search", params=search_params) as response:
                    if response.status == 200:
                        data = await response.json()
                        resources = []
                        
                        for item in data.get('items', []):
                            if 'videoId' not in item.get('id', {}):
                                continue
                                
                            video_id = item['id']['videoId']
                            snippet = item['snippet']
                            
                            resource = ResourceData(
                                title=snippet.get('title', ''),
                                description=snippet.get('description', ''),
                                external_url=f"https://www.youtube.com/watch?v={video_id}",
                                resource_type=ResourceType.VIDEO,
                                provider=ResourceProvider.YOUTUBE,
                                external_id=video_id,
                                author=snippet.get('channelTitle', ''),
                                thumbnail_url=snippet.get('thumbnails', {}).get('high', {}).get('url'),
                                subject_area=self.extract_subject_area(snippet.get('title', '') + ' ' + snippet.get('description', '')),
                                tags=snippet.get('tags', []),
                                raw_data=item
                            )
                            resources.append(resource)
                        
                        await asyncio.sleep(self.rate_limit_delay)
                        return resources
            except Exception as e:
                print(f"YouTube API error: {e}")
                return []
        
        return []
    
    async def get_resource_details(self, external_id: str) -> Optional[ResourceData]:
        """Get detailed information about a YouTube video"""
        params = {
            'part': 'snippet,contentDetails,statistics',
            'id': external_id,
            'key': self.api_key
        }
        
        async with aiohttp.ClientSession() as session:
            try:
                async with session.get(f"{self.base_url}/videos", params=params) as response:
                    if response.status == 200:
                        data = await response.json()
                        items = data.get('items', [])
                        if items:
                            item = items[0]
                            snippet = item['snippet']
                            
                            return ResourceData(
                                title=snippet.get('title', ''),
                                description=snippet.get('description', ''),
                                external_url=f"https://www.youtube.com/watch?v={external_id}",
                                resource_type=ResourceType.VIDEO,
                                provider=ResourceProvider.YOUTUBE,
                                external_id=external_id,
                                author=snippet.get('channelTitle', ''),
                                thumbnail_url=snippet.get('thumbnails', {}).get('high', {}).get('url'),
                                duration_minutes=self._parse_duration(item.get('contentDetails', {}).get('duration')),
                                subject_area=self.extract_subject_area(snippet.get('title', '') + ' ' + snippet.get('description', '')),
                                tags=snippet.get('tags', []),
                                raw_data=item
                            )
            except Exception as e:
                print(f"YouTube details error: {e}")
                return None
        return None
    
    def _parse_duration(self, duration_str: Optional[str]) -> Optional[int]:
        """Parse YouTube duration format (PT15M33S) to minutes"""
        if not duration_str:
            return None
        
        import re
        pattern = r'PT(?:(\d+)H)?(?:(\d+)M)?(?:(\d+)S)?'
        match = re.match(pattern, duration_str)
        
        if match:
            hours = int(match.group(1) or 0)
            minutes = int(match.group(2) or 0)
            seconds = int(match.group(3) or 0)
            return hours * 60 + minutes + (1 if seconds > 0 else 0)
        return None
    
    async def verify_resource_availability(self, external_url: str) -> bool:
        """Check if YouTube video is still available"""
        video_id = external_url.split('v=')[-1].split('&')[0]
        resource = await self.get_resource_details(video_id)
        return resource is not None
