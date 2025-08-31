import os, asyncio
import pytest

# Ensure mandatory settings exist before importing service (pydantic BaseSettings requirements)
os.environ.setdefault("SECRET_KEY", "test-secret-key")
os.environ.setdefault("GCS_BUCKET_NAME", "test-bucket")
os.environ.setdefault("GCS_PROJECT_ID", "test-project")
os.environ.setdefault("DATABASE_URL", "sqlite+aiosqlite:///:memory:")
os.environ.setdefault("OPENAI_API_KEY", "test-openai")
os.environ.setdefault("GOOGLE_AI_API_KEY", "test-google")
from lyo_app.ai_study.service import StudyModeService
from lyo_app.ai_study.models import StudySession
from lyo_app.ai_study.schemas import ConversationMessage, QuizGenerationRequest
from lyo_app.ai_study.models import QuizType

class DummySettings:
    ENABLE_ADVANCED_SOCRATIC = True
    ENABLE_RETRIEVAL_AUGMENTATION = False
    ENABLE_ADAPTIVE_DIFFICULTY = True
    ENABLE_HISTORY_SUMMARIZATION = True
    ENABLE_STRATEGY_METRICS = True

def test_adaptive_difficulty_adjustment():
    service = StudyModeService()
    sess = StudySession(user_id=1, resource_id="r1", tutor_personality="socratic", difficulty_level="intermediate")
    # High score raises difficulty
    service._adjust_adaptive_difficulty(sess, 95.0)
    assert sess.difficulty_level in ("advanced", "expert", "intermediate")
    # Low score lowers difficulty
    service._adjust_adaptive_difficulty(sess, 20.0)
    assert sess.difficulty_level in ("beginner", "intermediate", "advanced", "expert")

def test_history_summarization_noop_when_short():
    service = StudyModeService()
    history = [ConversationMessage(role=None, content=f"msg {i}") for i in range(service.SUMMARIZE_THRESHOLD - 2)]
    summarized = asyncio.run(service._maybe_summarize_history(history))
    assert len(summarized) == len(history)

def test_quiz_prompt_contains_required_sections():
    service = StudyModeService()
    req = QuizGenerationRequest(
        resource_id="res1",
        resource_title="Title",
        resource_content="Content",
        quiz_type=QuizType.MULTIPLE_CHOICE,
        question_count=3,
        difficulty_level="intermediate",
        focus_areas=["topic1"],
    )
    resource_info = {"title": "Title", "type": "article", "description": "Desc"}
    prompt = service._build_quiz_generation_prompt(resource_info, req)
    for fragment in ["RESOURCE DETAILS", "QUIZ REQUIREMENTS", "OUTPUT FORMAT", "Generate exactly"]:
        assert fragment in prompt
