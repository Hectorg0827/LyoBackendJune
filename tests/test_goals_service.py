import pytest
from unittest.mock import AsyncMock, patch, MagicMock
from lyo_app.evolution.goals_service import create_user_goal, get_user_goals
from lyo_app.evolution.goals_schemas import UserGoalCreate
from lyo_app.evolution.goals_models import UserGoal, GoalStatus

@pytest.mark.asyncio
async def test_create_user_goal():
    db_mock = AsyncMock()
    
    goal_in = UserGoalCreate(user_id=1, target="Become a better programmer", status=GoalStatus.ACTIVE)
    
    result = await create_user_goal(db_mock, goal_in)
    
    assert db_mock.add.called
    assert db_mock.commit.called
    assert result.user_id == 1
    assert result.target == "Become a better programmer"
    assert result.status == GoalStatus.ACTIVE

@pytest.mark.asyncio
async def test_get_user_goals():
    db_mock = AsyncMock()
    
    mock_result = MagicMock()
    mock_result.scalars().all.return_value = [
        UserGoal(id=1, user_id=1, target="Goal 1", status=GoalStatus.ACTIVE),
        UserGoal(id=2, user_id=1, target="Goal 2", status=GoalStatus.PAUSED)
    ]
    db_mock.execute.return_value = mock_result
    
    results = await get_user_goals(db_mock, user_id=1)
    
    assert db_mock.execute.called
    assert len(results) == 2
    assert results[0].target == "Goal 1"
