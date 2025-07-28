"""
Educational Resources Service
Manages aggregation, curation, and AI integration of educational resources
"""
import asyncio
from typing import List, Dict, Optional, Any
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_, or_, desc
from datetime import datetime, timedelta
import logging

from .models import EducationalResource, ResourceType, ResourceProvider, ResourceTag, CourseResource
from .providers.youtube_provider import YouTubeProvider
from .providers.internet_archive_provider import InternetArchiveProvider
from .providers.khan_academy_provider import KhanAcademyProvider
from .providers.base import ResourceData

logger = logging.getLogger(__name__)

class ResourceAggregationService:
    """Service for aggregating educational resources from multiple providers"""
    
    def __init__(self, db_session: AsyncSession):
        self.db = db_session
        self.providers = self._initialize_providers()
        
    def _initialize_providers(self) -> Dict[ResourceProvider, Any]:
        """Initialize all resource providers"""
        providers = {}
        
        # Initialize providers - using mock API keys for testing
        providers[ResourceProvider.YOUTUBE] = YouTubeProvider("MOCK_YOUTUBE_API_KEY")
        providers[ResourceProvider.INTERNET_ARCHIVE] = InternetArchiveProvider()
        providers[ResourceProvider.KHAN_ACADEMY] = KhanAcademyProvider()
        
        return providers
    
    async def search_and_aggregate_resources(
        self,
        query: str,
        resource_types: Optional[List[ResourceType]] = None,
        providers: Optional[List[ResourceProvider]] = None,
        limit_per_provider: int = 20,
        subject_area: Optional[str] = None
    ) -> List[EducationalResource]:
        """Search and aggregate resources from multiple providers"""
        
        if resource_types is None:
            resource_types = [ResourceType.VIDEO, ResourceType.EBOOK, ResourceType.COURSE]
        
        if providers is None:
            providers = list(self.providers.keys())
        
        all_resources = []
        tasks = []
        
        # Create search tasks for each provider
        for provider_enum in providers:
            if provider_enum in self.providers:
                provider = self.providers[provider_enum]
                for resource_type in resource_types:
                    task = self._search_provider(provider, query, resource_type, limit_per_provider)
                    tasks.append(task)
        
        # Execute all searches concurrently
        search_results = await asyncio.gather(*tasks, return_exceptions=True)
        
        # Process results
        for result in search_results:
            if isinstance(result, Exception):
                logger.error(f"Provider search failed: {result}")
                continue
            
            for resource_data in result:
                # Filter by subject area if specified
                if subject_area and resource_data.subject_area != subject_area:
                    continue
                
                # Check if resource already exists
                existing = await self._find_existing_resource(resource_data)
                if existing:
                    continue
                
                # Create new resource
                db_resource = await self._create_resource_from_data(resource_data)
                all_resources.append(db_resource)
        
        # Sort by quality score and relevance
        all_resources.sort(key=lambda x: (x.quality_score, x.created_at), reverse=True)
        
        return all_resources
    
    async def _search_provider(
        self,
        provider: Any,
        query: str,
        resource_type: ResourceType,
        limit: int
    ) -> List[ResourceData]:
        """Search a specific provider for resources"""
        try:
            return await provider.search_resources(query, resource_type, limit)
        except Exception as e:
            logger.error(f"Error searching provider {provider.__class__.__name__}: {e}")
            return []
    
    async def _find_existing_resource(self, resource_data: ResourceData) -> Optional[EducationalResource]:
        """Check if a resource already exists in the database"""
        query = select(EducationalResource).where(
            and_(
                EducationalResource.external_id == resource_data.external_id,
                EducationalResource.provider == resource_data.provider
            )
        )
        result = await self.db.execute(query)
        return result.scalar_one_or_none()
    
    async def _create_resource_from_data(self, resource_data: ResourceData) -> EducationalResource:
        """Create a database resource from ResourceData"""
        db_resource = EducationalResource(
            title=resource_data.title,
            description=resource_data.description,
            author=resource_data.author,
            resource_type=resource_data.resource_type,
            provider=resource_data.provider,
            external_id=resource_data.external_id,
            external_url=resource_data.external_url,
            thumbnail_url=resource_data.thumbnail_url,
            download_url=resource_data.download_url,
            duration_minutes=resource_data.duration_minutes,
            page_count=resource_data.page_count,
            subject_area=resource_data.subject_area,
            difficulty_level=resource_data.difficulty_level,
            language=resource_data.language,
            isbn=resource_data.isbn,
            quality_score=self._calculate_quality_score(resource_data),
            raw_api_data=resource_data.raw_data,
            last_verified=datetime.utcnow()
        )
        
        self.db.add(db_resource)
        await self.db.flush()  # Get the ID
        
        # Add tags
        for tag in resource_data.tags:
            db_tag = ResourceTag(resource_id=db_resource.id, tag=tag[:50])  # Limit tag length
            self.db.add(db_tag)
        
        await self.db.commit()
        return db_resource
    
    def _calculate_quality_score(self, resource_data: ResourceData) -> int:
        """Calculate a quality score for the resource (0-100)"""
        score = 50  # Base score
        
        # Adjust based on provider reputation
        provider_scores = {
            ResourceProvider.KHAN_ACADEMY: 20,
            ResourceProvider.MIT_OCW: 20,
            ResourceProvider.TED: 15,
            ResourceProvider.YOUTUBE: 5,
            ResourceProvider.INTERNET_ARCHIVE: 10
        }
        score += provider_scores.get(resource_data.provider, 0)
        
        # Adjust based on content quality indicators
        if resource_data.description and len(resource_data.description) > 100:
            score += 10
        
        if resource_data.author:
            score += 5
        
        if resource_data.thumbnail_url:
            score += 5
        
        # Adjust based on duration (for videos)
        if resource_data.duration_minutes:
            if 5 <= resource_data.duration_minutes <= 60:  # Sweet spot for educational videos
                score += 10
            elif resource_data.duration_minutes > 120:  # Too long might be less engaging
                score -= 5
        
        return min(max(score, 0), 100)
    
    async def curate_resources_for_course(
        self,
        course_topic: str,
        learning_objectives: List[str],
        difficulty_level: str = "beginner",
        max_resources: int = 10
    ) -> List[EducationalResource]:
        """AI-powered curation of resources for a specific course"""
        
        curated_resources = []
        
        # Search for resources matching the course topic
        for objective in learning_objectives[:3]:  # Limit to top 3 objectives
            search_query = f"{course_topic} {objective}"
            resources = await self.search_and_aggregate_resources(
                query=search_query,
                limit_per_provider=5
            )
            
            # Filter by difficulty level
            filtered_resources = [
                r for r in resources 
                if not r.difficulty_level or r.difficulty_level == difficulty_level
            ]
            
            curated_resources.extend(filtered_resources[:3])
        
        # Remove duplicates and sort by quality
        unique_resources = {r.external_id: r for r in curated_resources}.values()
        sorted_resources = sorted(unique_resources, key=lambda x: x.quality_score, reverse=True)
        
        return sorted_resources[:max_resources]
    
    async def get_trending_resources(
        self,
        resource_type: Optional[ResourceType] = None,
        subject_area: Optional[str] = None,
        limit: int = 20
    ) -> List[EducationalResource]:
        """Get trending/popular educational resources"""
        
        query = select(EducationalResource).where(
            EducationalResource.is_active == True
        )
        
        if resource_type:
            query = query.where(EducationalResource.resource_type == resource_type)
        
        if subject_area:
            query = query.where(EducationalResource.subject_area == subject_area)
        
        # Order by quality score and recency
        query = query.order_by(
            desc(EducationalResource.quality_score),
            desc(EducationalResource.created_at)
        ).limit(limit)
        
        result = await self.db.execute(query)
        return result.scalars().all()
