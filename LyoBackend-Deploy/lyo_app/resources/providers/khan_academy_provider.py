"""
Khan Academy provider for educational content
"""
import asyncio
from typing import List, Optional
from .base import BaseResourceProvider, ResourceData
from ..models import ResourceType, ResourceProvider

class KhanAcademyProvider(BaseResourceProvider):
    """Khan Academy provider"""
    
    def __init__(self):
        super().__init__()
        self.base_url = "https://www.khanacademy.org"
    
    async def search_resources(
        self, 
        query: str, 
        resource_type: Optional[ResourceType] = None,
        limit: int = 50
    ) -> List[ResourceData]:
        """Search Khan Academy for educational content"""
        
        # Khan Academy primarily has videos and exercises
        if resource_type and resource_type not in [ResourceType.VIDEO, ResourceType.COURSE]:
            return []
        
        # Mock implementation for testing
        resources = []
        
        # Create mock Khan Academy resources
        for i in range(min(limit, 3)):
            resource_type_choice = ResourceType.VIDEO if i % 2 == 0 else ResourceType.COURSE
            
            resource = ResourceData(
                title=f"Khan Academy {resource_type_choice.value}: {query} - Part {i+1}",
                description=f"Learn about {query} with this comprehensive Khan Academy {resource_type_choice.value}.",
                external_url=f"{self.base_url}/learn/{query.lower().replace(' ', '-')}-{i+1}",
                resource_type=resource_type_choice,
                provider=ResourceProvider.KHAN_ACADEMY,
                external_id=f"ka_{query.lower().replace(' ', '_')}_{i+1}",
                author="Khan Academy",
                duration_minutes=15 if resource_type_choice == ResourceType.VIDEO else None,
                subject_area=self.extract_subject_area(query),
                difficulty_level='beginner',
                tags=[query, "khan academy", "free"],
                raw_data={"mock": True, "query": query}
            )
            resources.append(resource)
        
        return resources
    
    async def get_resource_details(self, external_id: str) -> Optional[ResourceData]:
        """Get detailed information about a Khan Academy resource"""
        # Mock implementation
        return ResourceData(
            title=f"Khan Academy Resource: {external_id}",
            description="Detailed Khan Academy educational content.",
            external_url=f"{self.base_url}/resource/{external_id}",
            resource_type=ResourceType.VIDEO,
            provider=ResourceProvider.KHAN_ACADEMY,
            external_id=external_id,
            author="Khan Academy",
            duration_minutes=15,
            subject_area="mathematics",
            difficulty_level='beginner',
            tags=["khan academy", "education"],
            raw_data={"mock": True, "external_id": external_id}
        )
    
    async def verify_resource_availability(self, external_url: str) -> bool:
        """Check if Khan Academy resource is still available"""
        # For testing, always return True
        return True
