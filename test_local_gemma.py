#!/usr/bin/env python3
"""
Test script for local Gemma 3 course generation.
"""

import asyncio
import logging
from lyo_app.models.loading import model_manager
from lyo_app.services.content_curator import ContentCurator
from lyo_app.core.settings import settings

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

async def test_gemma_generation():
    """
    Test the full local course generation process.
    """
    print("="*60)
    print("🚀 TESTING LOCAL GEMMA COURSE GENERATION")
    print("="*60)

    # 1. Ensure the model is loaded
    try:
        logger.info("Ensuring Gemma model is available...")
        model_info = model_manager.ensure_model()
        logger.info(f"✅ Model ready: {model_info.name} ({model_info.size_bytes / 1e9:.2f} GB)")
    except Exception as e:
        logger.error(f"❌ Failed to load model: {e}")
        return

    # 2. Initialize the content curator
    curator = ContentCurator(
        model_manager=model_manager,
        youtube_api_key=settings.YOUTUBE_API_KEY,
        openai_api_key=settings.OPENAI_API_KEY
    )
    logger.info("✅ ContentCurator initialized.")

    # 3. Define test course parameters
    test_params = {
        "topic": "Introduction to Quantum Computing",
        "interests": ["Physics", "Algorithms", "Cryptography"],
        "difficulty_level": "Beginner",
        "target_duration_hours": 4.0,
        "locale": "en"
    }
    logger.info(f"📝 Generating course for topic: '{test_params['topic']}'")

    # 4. Run the course curation
    try:
        def progress_callback(percent, message):
            logger.info(f"[{percent}%] {message}")

        logger.info("\n" + "-"*60)
        logger.info("🏃‍♂️ Starting course curation...")
        
        course_data = await curator.curate_course(
            **test_params,
            progress_callback=progress_callback
        )
        
        logger.info("🏁 Course curation finished.")
        logger.info("-" * 60 + "\n")

        # 5. Print the results
        print("="*60)
        print("✅ COURSE GENERATION SUCCESSFUL!")
        print("="*60)
        print(f"Title: {course_data.get('title')}")
        print(f"Summary: {course_data.get('summary')}")
        print(f"Tags: {', '.join(course_data.get('tags', []))}")
        print(f"Estimated Duration: {course_data.get('estimated_duration_hours')} hours")
        
        print("\n--- Lessons ---")
        for i, lesson in enumerate(course_data.get('lessons', [])):
            print(f"  {i+1}. {lesson.get('title')} ({lesson.get('duration_minutes', 0)} mins)")
            print(f"     Summary: {lesson.get('summary')}")
            print(f"     Objectives: {', '.join(lesson.get('objectives', []))}")
        
        print("\n" + "="*60)

    except Exception as e:
        logger.error(f"❌ An error occurred during course generation: {e}", exc_info=True)

if __name__ == "__main__":
    # To run this test, ensure you have your environment set up, e.g.,
    # by running from the root of your project with the correct PYTHONPATH.
    # Example:
    # export PYTHONPATH=.
    # python test_local_gemma.py
    
    # For simplicity, we'll add the project root to the path here.
    import sys
    from pathlib import Path
    project_root = Path(__file__).parent.parent
    sys.path.insert(0, str(project_root))

    asyncio.run(test_gemma_generation())
