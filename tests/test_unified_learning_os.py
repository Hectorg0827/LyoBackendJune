import pytest
from unittest.mock import MagicMock, AsyncMock, patch
from lyo_app.ai_classroom.routes import analyze_soft_skills_task
from lyo_app.learning.proofs import ProofEngine
from lyo_app.personalization.soft_skills import SoftSkillType

# Import models to ensure they are registered with SQLAlchemy
import lyo_app.auth.models
import lyo_app.ai_study.models
import lyo_app.ai_agents.models
import lyo_app.learning.proofs
import lyo_app.personalization.soft_skills

@pytest.mark.asyncio
async def test_unified_flow_soft_skills_trigger():
    """
    Verifies that a chat message triggers the soft skills analysis and recording.
    """
    # Setup
    user_id = 1
    # Use a phrase that definitely matches the regex r"why\s+is\s+that"
    message = "Why is that happening? I want to understand."

    # Mocks
    db_mock = AsyncMock()
    
    # Fix for 'coroutine object has no attribute score'
    # We need db.execute to return a result object that has a synchronous scalar_one_or_none method
    result_mock = MagicMock()
    result_mock.scalar_one_or_none.return_value = None # Simulate no existing record
    db_mock.execute.return_value = result_mock

    # Mock the session context manager used in the background task
    session_ctx_mock = AsyncMock()
    session_ctx_mock.__aenter__.return_value = db_mock
    session_ctx_mock.__aexit__.return_value = None

    with patch("lyo_app.ai_classroom.routes.AsyncSessionLocal", return_value=session_ctx_mock):
        # Execute the background task function directly
        await analyze_soft_skills_task(user_id, message)

        # Verification
        # 1. Check if DB execute was called (to find existing skill)
        assert db_mock.execute.called

        # 2. Check if DB commit was called (to save new skill evidence)
        assert db_mock.commit.called

@pytest.mark.asyncio
async def test_proof_engine_integration():
    """
    Verifies Proof Engine generation.
    """
    engine = ProofEngine()
    db = AsyncMock()

    proof = await engine.generate_proof(
        db,
        user_id=99,
        course_id="course-uuid-123",
        course_title="Advanced AI Architecture",
        skills=["System Design", "Python"]
    )

    assert proof.user_id == 99
    assert proof.proof_hash is not None
    assert proof.issuer == "Lyo Learning OS"
