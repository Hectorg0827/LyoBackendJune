import pytest
import pytest_asyncio
from unittest.mock import AsyncMock, patch, MagicMock
from sqlalchemy.ext.asyncio import AsyncSession
from fastapi.testclient import TestClient
from datetime import datetime

from lyo_app.enhanced_main import app
from lyo_app.core.database import Base, get_db
from lyo_app.auth.models import User
from lyo_app.personalization.models import LearnerState, LearnerMastery, AffectState
from lyo_app.chat.models import ChatConversation, ChatMessage, ChatMode
from lyo_app.personalization.service import personalization_engine
from lyo_app.auth.security import create_access_token

# Use db_session from conftest.py

@pytest.fixture
def client(db_session):
    async def override_get_db():
        yield db_session
        
    app.dependency_overrides[get_db] = override_get_db
    yield TestClient(app)
    del app.dependency_overrides[get_db]

@pytest.mark.asyncio
async def test_build_prompt_context(db_session):
    # 1. Setup Data
    user = User(
        email="test@example.com", 
        hashed_password="hash", 
        username="testuser",
        first_name="Test",
        last_name="User",
        is_active=True
    )
    db_session.add(user)
    await db_session.commit()
    await db_session.refresh(user)
    
    # Learner State
    state = LearnerState(
        user_id=user.id,
        current_affect=AffectState.FRUSTRATED,
        fatigue_level=0.8,
        prefers_visual=True
    )
    db_session.add(state)
    
    # Mastery
    m1 = LearnerMastery(user_id=user.id, skill_id="python_loops", mastery_level=0.9) # Strength
    m2 = LearnerMastery(user_id=user.id, skill_id="python_recursion", mastery_level=0.1) # Weakness
    db_session.add(m1)
    db_session.add(m2)
    
    # Chat History
    conv = ChatConversation(
        user_id=str(user.id),
        session_id="sess1",
        current_mode=ChatMode.GENERAL.value,
        initial_mode=ChatMode.GENERAL.value,
        topic="Recursion Help"
    )
    db_session.add(conv)
    await db_session.commit()
    await db_session.refresh(conv)
    
    msg1 = ChatMessage(
        conversation_id=conv.id,
        role="user",
        content="I don't understand recursion at all."
    )
    msg2 = ChatMessage(
        conversation_id=conv.id,
        role="assistant",
        content="Recursion is when a function calls itself."
    )
    db_session.add(msg1)
    db_session.add(msg2)
    await db_session.commit()
    
    # 2. Test Context Builder
    context = await personalization_engine.build_prompt_context(db_session, str(user.id))
    
    print(f"Generated Context:\n{context}")
    
    # 3. Assertions
    assert "visual=True" in context
    assert "affect=frustrated" in context
    assert "Strengths (mastered): python_loops" in context
    assert "Struggling with: python_recursion" in context
    assert "Topic: Recursion Help" in context
    assert "I don't understand recursion" in context

@pytest.mark.asyncio
async def test_greeting_endpoint(client, db_session):
    # 1. Setup User
    user = User(email="greet@example.com", username="greetuser", hashed_password="hash", is_active=True)
    db_session.add(user)
    await db_session.commit()
    await db_session.refresh(user)
    
    # 2. Mock AI Response
    with patch("lyo_app.core.ai_resilience.ai_resilience_manager.chat_completion", new_callable=AsyncMock) as mock_ai:
        mock_ai.return_value = {"content": "Welcome back, master of loops!"}
        
        # 3. Call Endpoint
        # Mock get_optional_current_user
        from lyo_app.auth.jwt_auth import get_optional_current_user
        app.dependency_overrides[get_optional_current_user] = lambda: user
        
        response = client.get("/api/v1/chat/greeting")
        
        assert response.status_code == 200
        data = response.json()
        
        assert data["greeting"] == "Welcome back, master of loops!"
        
        # Add personalization data to verify context_used=True
        state = LearnerState(user_id=user.id, current_affect=AffectState.FLOW)
        db_session.add(state)
        await db_session.commit()
        
        response = client.get("/api/v1/chat/greeting")
        data = response.json()
        assert data["context_used"] is True
        
        del app.dependency_overrides[get_optional_current_user]

