"""
Test Educational Resources System
"""
import asyncio
import sys
import os

# Add the project root to the Python path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from lyo_app.resources.service import ResourceAggregationService
from lyo_app.resources.models import ResourceType, ResourceProvider
from lyo_app.core.database import get_db_session, init_db
from sqlalchemy.ext.asyncio import AsyncSession

async def test_educational_resources():
    """Test the educational resources functionality"""
    
    print("🧪 Starting Educational Resources System Test")
    print("=" * 60)
    
    # Initialize database
    await init_db()
    
    # Get database session
    async with get_db_session() as db:
        service = ResourceAggregationService(db)
        
        # Test 1: Search for programming resources
        print("\n📚 Test 1: Searching for 'Python programming' resources")
        try:
            resources = await service.search_and_aggregate_resources(
                query="Python programming",
                resource_types=[ResourceType.VIDEO, ResourceType.COURSE, ResourceType.EBOOK],
                limit_per_provider=3
            )
            
            print(f"✅ Found {len(resources)} resources")
            for i, resource in enumerate(resources[:3], 1):
                print(f"  {i}. {resource.title}")
                print(f"     Type: {resource.resource_type.value}")
                print(f"     Provider: {resource.provider.value}")
                print(f"     Author: {resource.author}")
                print(f"     Quality Score: {resource.quality_score}")
                print(f"     URL: {resource.external_url}")
                print()
                
        except Exception as e:
            print(f"❌ Test 1 failed: {e}")
        
        # Test 2: Course curation
        print("\n🎯 Test 2: AI-powered course curation for 'Data Science'")
        try:
            curated_resources = await service.curate_resources_for_course(
                course_topic="Data Science",
                learning_objectives=["Python basics", "Data analysis", "Machine learning"],
                difficulty_level="beginner",
                max_resources=5
            )
            
            print(f"✅ Curated {len(curated_resources)} resources")
            for i, resource in enumerate(curated_resources, 1):
                print(f"  {i}. {resource.title}")
                print(f"     Subject: {resource.subject_area}")
                print(f"     Difficulty: {resource.difficulty_level}")
                print(f"     Quality Score: {resource.quality_score}")
                print()
                
        except Exception as e:
            print(f"❌ Test 2 failed: {e}")
        
        # Test 3: Provider availability
        print("\n🔧 Test 3: Testing available providers")
        providers = service.providers
        print(f"✅ Available providers: {len(providers)}")
        for provider_enum, provider_instance in providers.items():
            print(f"  - {provider_enum.value}: {provider_instance.__class__.__name__}")
        
        # Test 4: Get trending resources
        print("\n📈 Test 4: Getting trending resources")
        try:
            trending = await service.get_trending_resources(
                resource_type=ResourceType.VIDEO,
                limit=3
            )
            
            print(f"✅ Found {len(trending)} trending resources")
            for i, resource in enumerate(trending, 1):
                print(f"  {i}. {resource.title}")
                print(f"     Quality Score: {resource.quality_score}")
                print()
                
        except Exception as e:
            print(f"❌ Test 4 failed: {e}")
    
    print("🎉 Educational Resources System Test Complete!")

if __name__ == "__main__":
    asyncio.run(test_educational_resources())
