"""
Educational Resources API Routes
"""
from fastapi import APIRouter, Depends, HTTPException, Query, BackgroundTasks
from sqlalchemy.ext.asyncio import AsyncSession
from typing import List, Optional
from pydantic import BaseModel

from lyo_app.core.database import get_db
from lyo_app.auth.dependencies import get_current_user
from lyo_app.models.enhanced import User
from .service import ResourceAggregationService
from .models import EducationalResource, ResourceType, ResourceProvider

router = APIRouter()

class ResourceSearchRequest(BaseModel):
    query: str
    resource_types: Optional[List[ResourceType]] = None
    providers: Optional[List[ResourceProvider]] = None
    subject_area: Optional[str] = None
    limit_per_provider: int = 20

class ResourceResponse(BaseModel):
    id: int
    title: str
    description: Optional[str]
    author: Optional[str]
    resource_type: ResourceType
    provider: ResourceProvider
    external_url: str
    thumbnail_url: Optional[str]
    download_url: Optional[str]
    duration_minutes: Optional[int]
    page_count: Optional[int]
    subject_area: Optional[str]
    difficulty_level: Optional[str]
    quality_score: int
    language: str = 'en'
    isbn: Optional[str] = None
    tags: List[str] = []
    
    model_config = {
        "from_attributes": True
    }

class CourseCurationRequest(BaseModel):
    course_topic: str
    learning_objectives: List[str]
    difficulty_level: str = "beginner"
    max_resources: int = 10

@router.post("/search", response_model=List[ResourceResponse])
async def search_educational_resources(
    request: ResourceSearchRequest,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Search for educational resources across multiple providers"""
    
    service = ResourceAggregationService(db)
    
    try:
        resources = await service.search_and_aggregate_resources(
            query=request.query,
            resource_types=request.resource_types,
            providers=request.providers,
            limit_per_provider=request.limit_per_provider,
            subject_area=request.subject_area
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Search failed: {str(e)}")
    
    # Convert to response format
    response_resources = []
    for resource in resources:
        tags = [tag.tag for tag in resource.tags] if resource.tags else []
        response_resources.append(ResourceResponse(
            id=resource.id,
            title=resource.title,
            description=resource.description,
            author=resource.author,
            resource_type=resource.resource_type,
            provider=resource.provider,
            external_url=resource.external_url,
            thumbnail_url=resource.thumbnail_url,
            download_url=resource.download_url,
            duration_minutes=resource.duration_minutes,
            page_count=resource.page_count,
            subject_area=resource.subject_area,
            difficulty_level=resource.difficulty_level,
            quality_score=resource.quality_score,
            language=resource.language,
            isbn=resource.isbn,
            tags=tags
        ))
    
    return response_resources

@router.post("/curate-for-course", response_model=List[ResourceResponse])
async def curate_resources_for_course(
    request: CourseCurationRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """AI-powered curation of resources for a specific course"""
    
    service = ResourceAggregationService(db)
    
    try:
        resources = await service.curate_resources_for_course(
            course_topic=request.course_topic,
            learning_objectives=request.learning_objectives,
            difficulty_level=request.difficulty_level,
            max_resources=request.max_resources
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Curation failed: {str(e)}")
    
    # Convert to response format
    response_resources = []
    for resource in resources:
        tags = [tag.tag for tag in resource.tags] if resource.tags else []
        response_resources.append(ResourceResponse(
            id=resource.id,
            title=resource.title,
            description=resource.description,
            author=resource.author,
            resource_type=resource.resource_type,
            provider=resource.provider,
            external_url=resource.external_url,
            thumbnail_url=resource.thumbnail_url,
            download_url=resource.download_url,
            duration_minutes=resource.duration_minutes,
            page_count=resource.page_count,
            subject_area=resource.subject_area,
            difficulty_level=resource.difficulty_level,
            quality_score=resource.quality_score,
            language=resource.language,
            isbn=resource.isbn,
            tags=tags
        ))
    
    return response_resources

@router.get("/trending", response_model=List[ResourceResponse])
async def get_trending_resources(
    resource_type: Optional[ResourceType] = Query(None),
    subject_area: Optional[str] = Query(None),
    limit: int = Query(20, le=100),
    db: AsyncSession = Depends(get_db)
):
    """Get trending educational resources"""
    
    service = ResourceAggregationService(db)
    
    try:
        resources = await service.get_trending_resources(
            resource_type=resource_type,
            subject_area=subject_area,
            limit=limit
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to get trending resources: {str(e)}")
    
    # Convert to response format
    response_resources = []
    for resource in resources:
        tags = [tag.tag for tag in resource.tags] if resource.tags else []
        response_resources.append(ResourceResponse(
            id=resource.id,
            title=resource.title,
            description=resource.description,
            author=resource.author,
            resource_type=resource.resource_type,
            provider=resource.provider,
            external_url=resource.external_url,
            thumbnail_url=resource.thumbnail_url,
            download_url=resource.download_url,
            duration_minutes=resource.duration_minutes,
            page_count=resource.page_count,
            subject_area=resource.subject_area,
            difficulty_level=resource.difficulty_level,
            quality_score=resource.quality_score,
            language=resource.language,
            isbn=resource.isbn,
            tags=tags
        ))
    
    return response_resources

@router.get("/providers", response_model=List[str])
async def get_available_providers():
    """Get list of available resource providers"""
    return [provider.value for provider in ResourceProvider]

@router.get("/resource-types", response_model=List[str])
async def get_resource_types():
    """Get list of available resource types"""
    return [resource_type.value for resource_type in ResourceType]

@router.get("/health")
async def health_check():
    """Health check endpoint for the resources service"""
    return {"status": "healthy", "service": "educational_resources"}
