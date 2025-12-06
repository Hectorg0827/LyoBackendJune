"""
AI Agents Module - Multi-Agent Course Creation System

MIT Architecture Engineering - Fail-Proof Course Generation Pipeline

Model Strategy:
- Gemini 2.5 Pro: Orchestrator, Curriculum Architect, QA Agent
- Gemini 1.5 Flash: Content Creator, Assessment Designer

Exports all agents for external use.
"""

from lyo_app.ai_agents.multi_agent_v2.agents.base_agent import BaseAgent, AgentMetrics
from lyo_app.ai_agents.multi_agent_v2.agents.orchestrator_agent import (
    OrchestratorAgent,
    IntentRefinerAgent
)
from lyo_app.ai_agents.multi_agent_v2.agents.curriculum_agent import (
    CurriculumArchitectAgent,
    CurriculumRebalancerAgent
)
from lyo_app.ai_agents.multi_agent_v2.agents.content_agent import (
    ContentCreatorAgent,
    ContentEnhancerAgent,
    LessonGenerationContext
)
from lyo_app.ai_agents.multi_agent_v2.agents.assessment_agent import (
    AssessmentDesignerAgent,
    QuestionRegeneratorAgent
)
from lyo_app.ai_agents.multi_agent_v2.agents.qa_agent import (
    QualityAssuranceAgent,
    TargetedReviewAgent,
    ReviewFocus,
    QAContext
)

# Model Management
from lyo_app.ai_agents.multi_agent_v2.model_manager import (
    ModelManager,
    ModelConfig,
    ModelTier,
    TaskComplexity
)

__all__ = [
    # Base
    "BaseAgent",
    "AgentMetrics",
    
    # Orchestrator
    "OrchestratorAgent",
    "IntentRefinerAgent",
    
    # Curriculum
    "CurriculumArchitectAgent",
    "CurriculumRebalancerAgent",
    
    # Content
    "ContentCreatorAgent",
    "ContentEnhancerAgent",
    "LessonGenerationContext",
    
    # Assessment
    "AssessmentDesignerAgent",
    "QuestionRegeneratorAgent",
    
    # QA
    "QualityAssuranceAgent",
    "TargetedReviewAgent",
    "ReviewFocus",
    "QAContext",
    
    # Model Management
    "ModelManager",
    "ModelConfig",
    "ModelTier",
    "TaskComplexity"
]
