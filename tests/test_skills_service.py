import pytest
from unittest.mock import AsyncMock, patch, MagicMock
from lyo_app.skills.service import create_skill, get_skills_by_domain
from lyo_app.skills.schemas import SkillCreate
from lyo_app.skills.models import SkillDomain, Skill

@pytest.mark.asyncio
async def test_create_skill():
    db_mock = AsyncMock()
    
    skill_in = SkillCreate(name="Python", domain=SkillDomain.CAPABILITY, tags=["Programming"])
    
    db_skill = Skill(id=1, name="Python", domain=SkillDomain.CAPABILITY)
    
    # Let create_skill do its thing, it adds to session and commits
    result = await create_skill(db_mock, skill_in)
    
    assert db_mock.add.called
    assert db_mock.commit.called
    assert result.name == "Python"
    assert result.domain == SkillDomain.CAPABILITY

@pytest.mark.asyncio
async def test_get_skills_by_domain():
    db_mock = AsyncMock()
    
    mock_result = MagicMock()
    mock_result.scalars().all.return_value = [
        Skill(id=1, name="Math", domain=SkillDomain.ACADEMIC),
        Skill(id=2, name="Physics", domain=SkillDomain.ACADEMIC)
    ]
    db_mock.execute.return_value = mock_result
    
    results = await get_skills_by_domain(db_mock, SkillDomain.ACADEMIC)
    
    assert db_mock.execute.called
    assert len(results) == 2
    assert results[0].name == "Math"
