import asyncio
from lyo_app.core.celery_app import celery_app
from lyo_app.ai_agents.sentiment_agent import sentiment_engagement_agent
from lyo_app.ai_agents.mentor_agent import AIMentor
from lyo_app.ai_agents.curriculum_agent import curriculum_design_agent
from lyo_app.ai_agents.curation_agent import content_curation_agent
from lyo_app.core.database import get_db_session

@celery_app.task(name="ai.analyze_activity")
def analyze_user_activity_task(user_id: int, action: str, metadata: dict, user_message: str = None):
    """Celery task to analyze user activity asynchronously with AI agents."""
    async def run():
        async with get_db_session() as db:
            # 1. Sentiment & engagement analysis
            await sentiment_engagement_agent.analyze_user_action(
                user_id=user_id,
                action=action,
                metadata=metadata,
                db=db,
                user_message=user_message
            )
            
            # 2. Proactive mentoring if needed
            mentor = AIMentor()
            # Call proactive check-in based on analyzed action
            try:
                await mentor.proactive_check_in(
                    user_id=user_id,
                    reason=action,
                    db=db
                )
            except Exception as e:
                # Log mentor errors but do not fail the task
                print(f"Error in proactive_check_in for user {user_id}: {e}")
    asyncio.run(run())


@celery_app.task(name="ai.generate_course_outline")
def generate_course_outline_task(
    title: str, 
    description: str,
    target_audience: str,
    learning_objectives: list,
    difficulty_level: str,
    estimated_duration_hours: int,
    user_id: int = None
):
    """Celery task to generate a course outline using the curriculum agent."""
    async def run():
        async with get_db_session() as db:
            result = await curriculum_design_agent.generate_course_outline(
                title=title,
                description=description,
                target_audience=target_audience,
                learning_objectives=learning_objectives,
                difficulty_level=difficulty_level,
                estimated_duration_hours=estimated_duration_hours,
                db=db,
                user_id=user_id
            )
            return result
    return asyncio.run(run())


@celery_app.task(name="ai.generate_lesson_content")
def generate_lesson_content_task(
    course_id: int,
    lesson_title: str,
    lesson_description: str,
    learning_objectives: list,
    content_type: str,
    difficulty_level: str,
    user_id: int = None
):
    """Celery task to generate lesson content using the curriculum agent."""
    async def run():
        async with get_db_session() as db:
            result = await curriculum_design_agent.generate_lesson_content(
                course_id=course_id,
                lesson_title=lesson_title,
                lesson_description=lesson_description,
                learning_objectives=learning_objectives,
                content_type=content_type,
                difficulty_level=difficulty_level,
                db=db,
                user_id=user_id
            )
            return result
    return asyncio.run(run())


@celery_app.task(name="ai.evaluate_content_quality")
def evaluate_content_quality_task(
    content_text: str,
    content_type: str,
    topic: str,
    target_audience: str = None,
    difficulty_level: str = None
):
    """Celery task to evaluate content quality using the curation agent."""
    async def run():
        async with get_db_session() as db:
            result = await content_curation_agent.evaluate_content_quality(
                content_text=content_text,
                content_type=content_type,
                topic=topic,
                target_audience=target_audience,
                difficulty_level=difficulty_level,
                db=db
            )
            return result
    return asyncio.run(run())


@celery_app.task(name="ai.tag_and_categorize_content")
def tag_content_task(
    content_text: str,
    content_type: str,
    content_title: str = None
):
    """Celery task to tag and categorize content using the curation agent."""
    async def run():
        async with get_db_session() as db:
            result = await content_curation_agent.tag_and_categorize_content(
                content_text=content_text,
                content_type=content_type,
                content_title=content_title,
                db=db
            )
            return result
    return asyncio.run(run())


@celery_app.task(name="ai.identify_content_gaps")
def identify_content_gaps_task(course_id: int):
    """Celery task to identify content gaps in a course using the curation agent."""
    async def run():
        async with get_db_session() as db:
            result = await content_curation_agent.identify_content_gaps(
                course_id=course_id,
                db=db
            )
            return result
    return asyncio.run(run())
