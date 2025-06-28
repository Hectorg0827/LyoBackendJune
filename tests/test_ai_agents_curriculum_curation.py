"""
Unit tests for curriculum and curation agents.
"""

import pytest
import asyncio
from unittest.mock import AsyncMock, MagicMock, patch
from datetime import datetime, timedelta
from lyo_app.ai_agents.curriculum_agent import curriculum_design_agent, CurriculumDesignAgent
from lyo_app.ai_agents.curation_agent import content_curation_agent, ContentCurationAgent
from lyo_app.learning.models import DifficultyLevel, ContentType


@pytest.fixture
def mock_db():
    """Create a mock database session."""
    db = AsyncMock()
    db.execute = AsyncMock()
    db.commit = AsyncMock()
    return db


@pytest.fixture
def mock_orchestrator():
    """Create a mock AI orchestrator."""
    orchestrator = MagicMock()
    orchestrator.generate_response = AsyncMock()
    response = MagicMock()
    response.content = """
    {
        "title": "Test Course",
        "lessons": [
            {
                "title": "Introduction",
                "description": "An introduction to the topic",
                "content_type": "text",
                "topics": ["overview", "basics"],
                "activities": ["discussion"]
            }
        ]
    }
    """
    response.model_used = MagicMock()
    response.model_used.value = "cloud_llm"
    response.tokens_used = 500
    response.cost_estimate = 0.02
    response.response_time_ms = 1200
    response.error = None
    orchestrator.generate_response.return_value = response
    return orchestrator


class TestCurriculumAgent:
    """Test the curriculum agent functionality."""
    
    @patch('lyo_app.ai_agents.curriculum_agent.ai_orchestrator')
    async def test_generate_course_outline(self, mock_orchestrator, mock_db):
        """Test generating a course outline."""
        # Setup mock response
        mock_response = MagicMock()
        mock_response.content = """
        {
            "lessons": [
                {
                    "title": "Introduction to Python",
                    "description": "An introduction to the Python programming language",
                    "topics": ["Python basics", "installation", "first program"],
                    "content_type": "text",
                    "activities": ["Install Python", "Write hello world"],
                    "outcomes": ["Understand Python basics"]
                }
            ]
        }
        """
        mock_response.model_used.value = "cloud_llm"
        mock_response.tokens_used = 500
        mock_response.cost_estimate = 0.02
        mock_response.response_time_ms = 1200
        mock_response.error = None
        mock_orchestrator.generate_response.return_value = mock_response
        
        # Test function
        result = await curriculum_design_agent.generate_course_outline(
            title="Python Programming",
            description="A comprehensive course on Python programming",
            target_audience="Beginners",
            learning_objectives=["Learn Python syntax", "Write basic programs"],
            difficulty_level=DifficultyLevel.BEGINNER,
            estimated_duration_hours=10,
            db=mock_db,
            user_id=1
        )
        
        # Assertions
        assert result["title"] == "Python Programming"
        assert "outline" in result
        assert "model_used" in result
        assert mock_orchestrator.generate_response.called
        assert mock_db.add.called
        assert mock_db.commit.called
    
    @patch('lyo_app.ai_agents.curriculum_agent.ai_orchestrator')
    async def test_generate_lesson_content(self, mock_orchestrator, mock_db):
        """Test generating lesson content."""
        # Setup mock database response for course
        course = MagicMock()
        course.id = 1
        course.title = "Python Programming"
        course.description = "A comprehensive course on Python programming"
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = course
        mock_db.execute.return_value = mock_result
        
        # Setup mock AI response
        mock_response = MagicMock()
        mock_response.content = """
        # Introduction to Python
        
        ## Introduction
        
        Python is a versatile programming language...
        
        ## Setting up your environment
        
        To get started with Python, you need to install it...
        
        ## Writing your first program
        
        Let's create a simple "Hello, World!" program...
        
        ## Conclusion
        
        In this lesson, we've covered the basics of Python...
        """
        mock_response.model_used.value = "hybrid"
        mock_response.tokens_used = 800
        mock_response.cost_estimate = 0.03
        mock_response.response_time_ms = 1500
        mock_response.error = None
        mock_orchestrator.generate_response.return_value = mock_response
        
        # Test function
        result = await curriculum_design_agent.generate_lesson_content(
            course_id=1,
            lesson_title="Introduction to Python",
            lesson_description="An introduction to the Python programming language",
            learning_objectives=["Understand Python basics", "Set up Python environment"],
            content_type=ContentType.TEXT,
            difficulty_level=DifficultyLevel.BEGINNER,
            db=mock_db,
            user_id=1
        )
        
        # Assertions
        assert result["title"] == "Introduction to Python"
        assert "content" in result
        assert "model_used" in result
        assert mock_orchestrator.generate_response.called
        assert mock_db.execute.called
        assert mock_db.add.called
        assert mock_db.commit.called


class TestCurationAgent:
    """Test the content curation agent functionality."""
    
    @patch('lyo_app.ai_agents.curation_agent.ai_orchestrator')
    async def test_evaluate_content_quality(self, mock_orchestrator, mock_db):
        """Test evaluating content quality."""
        # Setup mock response
        mock_response = MagicMock()
        mock_response.content = """
        {
            "accuracy": {"score": 4, "justification": "Content is mostly accurate"},
            "completeness": {"score": 3, "justification": "Covers main topics but lacks depth"},
            "clarity": {"score": 5, "justification": "Very well-explained"},
            "engagement": {"score": 4, "justification": "Uses good examples"},
            "relevance": {"score": 5, "justification": "Highly relevant to topic"},
            "overall_score": 4.2,
            "strengths": ["Clear explanations", "Good examples"],
            "areas_for_improvement": ["Add more advanced topics"],
            "recommendation": "yes"
        }
        """
        mock_response.model_used.value = "hybrid"
        mock_response.tokens_used = 600
        mock_response.cost_estimate = 0.025
        mock_response.response_time_ms = 800
        mock_response.error = None
        mock_orchestrator.generate_response.return_value = mock_response
        
        # Test function
        result = await content_curation_agent.evaluate_content_quality(
            content_text="Python is a programming language that lets you work quickly and integrate systems more effectively.",
            content_type="article",
            topic="Python Programming",
            target_audience="Beginners",
            difficulty_level=DifficultyLevel.BEGINNER,
            db=mock_db
        )
        
        # Assertions
        assert result["topic"] == "Python Programming"
        assert "evaluation" in result
        assert "overall_score" in result
        assert result["overall_score"] > 0
        assert mock_orchestrator.generate_response.called
        assert mock_db.add.called
        assert mock_db.commit.called
    
    @patch('lyo_app.ai_agents.curation_agent.ai_orchestrator')
    async def test_tag_and_categorize_content(self, mock_orchestrator, mock_db):
        """Test tagging and categorizing content."""
        # Setup mock response
        mock_response = MagicMock()
        mock_response.content = """
        {
            "tags": ["python", "programming", "beginners", "tutorial", "coding"],
            "categories": ["Computer Science", "Software Development"],
            "topics": ["Python", "Programming Basics", "Coding"],
            "difficulty_level": "beginner",
            "estimated_read_time_minutes": 15
        }
        """
        mock_response.model_used.value = "hybrid"
        mock_response.tokens_used = 400
        mock_response.cost_estimate = 0.015
        mock_response.response_time_ms = 600
        mock_response.error = None
        mock_orchestrator.generate_response.return_value = mock_response
        
        # Test function
        result = await content_curation_agent.tag_and_categorize_content(
            content_text="Python is a programming language that lets you work quickly and integrate systems more effectively.",
            content_type="article",
            content_title="Introduction to Python",
            db=mock_db
        )
        
        # Assertions
        assert len(result["tags"]) > 0
        assert len(result["categories"]) > 0
        assert "difficulty_level" in result
        assert "estimated_read_time_minutes" in result
        assert mock_orchestrator.generate_response.called
        assert mock_db.add.called
        assert mock_db.commit.called


# Run tests
if __name__ == "__main__":
    pytest.main(["-v"])
