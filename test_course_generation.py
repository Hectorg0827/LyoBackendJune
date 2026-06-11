import asyncio
import os
import sys

# Add the project directory to path
sys.path.insert(0, '/Users/hectorgarcia/Desktop/LyoBackendJune')

# Set environment variable to force using local .env
os.environ["ENVIRONMENT"] = "development"
os.environ["GOOGLE_API_KEY"] = "AIzaSyAXqRkBk_PUuiy8WKCQ66v447NmTE_tCK0"
os.environ["GEMINI_API_KEY"] = "AIzaSyAXqRkBk_PUuiy8WKCQ66v447NmTE_tCK0"

# Import after setting env vars
from lyo_app.ai_agents.multi_agent_v2 import CourseGenerationPipeline, PipelineConfig, QualityTier

async def main():
    print("Initializing pipeline...")
    config = PipelineConfig(
        quality_tier=QualityTier.BALANCED,
        parallel_lesson_batch_size=1
    )
    pipeline = CourseGenerationPipeline(config=config)
    
    topic = "Introduction to Photosynthesis"
    print(f"Generating course for topic: {topic}")
    
    try:
        course = await pipeline.generate_course(
            user_request=f"Create a comprehensive course about {topic}",
            user_context={"source": "test_script"}
        )
        print("🎉 SUCCESS! Generated course:")
        print(f"ID: {course.course_id}")
        print(f"Title: {course.curriculum.course_title}")
        print(f"Modules: {len(course.curriculum.modules)}")
        print(f"Lessons: {len(course.lessons)}")
    except Exception as e:
        print("❌ FAILED!")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    asyncio.run(main())
