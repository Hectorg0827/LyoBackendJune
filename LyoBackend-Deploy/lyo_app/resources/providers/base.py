"""
Base class for all resource providers
"""
from abc import ABC, abstractmethod
from typing import List, Dict, Any, Optional
from dataclasses import dataclass
from ..models import ResourceType, ResourceProvider

@dataclass
class ResourceData:
    """Standardized resource data structure"""
    title: str
    description: str
    external_url: str
    resource_type: ResourceType
    provider: ResourceProvider
    external_id: str
    author: Optional[str] = None
    thumbnail_url: Optional[str] = None
    download_url: Optional[str] = None
    duration_minutes: Optional[int] = None
    page_count: Optional[int] = None
    subject_area: Optional[str] = None
    difficulty_level: Optional[str] = None
    language: str = 'en'
    isbn: Optional[str] = None
    tags: List[str] = None
    raw_data: Dict[str, Any] = None
    
    def __post_init__(self):
        if self.tags is None:
            self.tags = []

class BaseResourceProvider(ABC):
    """Base class for all resource providers"""
    
    def __init__(self, api_key: Optional[str] = None):
        self.api_key = api_key
        self.rate_limit_delay = 1.0  # Seconds between requests
    
    @abstractmethod
    async def search_resources(
        self, 
        query: str, 
        resource_type: Optional[ResourceType] = None,
        limit: int = 50
    ) -> List[ResourceData]:
        """Search for resources matching the query"""
        pass
    
    @abstractmethod
    async def get_resource_details(self, external_id: str) -> Optional[ResourceData]:
        """Get detailed information about a specific resource"""
        pass
    
    @abstractmethod
    async def verify_resource_availability(self, external_url: str) -> bool:
        """Check if a resource is still available"""
        pass
    
    def extract_subject_area(self, text: str) -> Optional[str]:
        """Extract subject area from text using keywords"""
        subjects = {
            'mathematics': ['math', 'algebra', 'calculus', 'geometry', 'statistics'],
            'science': ['physics', 'chemistry', 'biology', 'science'],
            'computer_science': ['programming', 'coding', 'python', 'javascript', 'computer'],
            'history': ['history', 'historical', 'ancient', 'modern'],
            'literature': ['literature', 'poetry', 'novel', 'writing'],
            'language': ['language', 'english', 'spanish', 'french', 'german'],
            'business': ['business', 'management', 'entrepreneurship', 'marketing'],
            'psychology': ['psychology', 'mental', 'behavior', 'cognitive']
        }
        
        text_lower = text.lower()
        for subject, keywords in subjects.items():
            if any(keyword in text_lower for keyword in keywords):
                return subject
        return None
