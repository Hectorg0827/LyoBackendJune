"""
Lyo AI Classroom - Multi-Agent Integration Layer
===============================================

Bridge between the existing multi-agent system and the new Scene Lifecycle Engine.
Transforms the current monolithic course generation into real-time, scene-by-scene streaming.

Architecture Flow:
Current:  User Request → Multi-Agent Pipeline → Full Course → iOS (60-120s latency)
New:     User Action → Scene Lifecycle → Agent Consultation → SDUI Scene → iOS (<1s latency)

Integration Strategy:
1. Preserve existing agents as knowledge sources
2. Convert batch generation to scene-by-scene streaming
3. Classroom Director has authority over final SDUI output
4. Existing agents provide content, Director compiles scenes
"""

import asyncio
import json
import logging
from datetime import datetime
from typing import Dict, List, Optional, Any, Union
from enum import Enum

from sqlalchemy.ext.asyncio import AsyncSession
from pydantic import BaseModel, Field

# Import existing multi-agent system
from lyo_app.ai_agents.multi_agent_v2.agents.base_agent import BaseAgent
from lyo_app.ai_agents.multi_agent_v2.agents.orchestrator_agent import OrchestratorAgent
from lyo_app.ai_agents.multi_agent_v2.agents.content_agent import ContentCreatorAgent
from lyo_app.ai_agents.multi_agent_v2.agents.tutor_agent import TutorAgent
from lyo_app.ai_agents.multi_agent_v2.agents.assessment_agent import AssessmentAgent
from lyo_app.ai_agents.multi_agent_v2.model_manager import ModelManager

# Import existing schemas
from lyo_app.ai_agents.multi_agent_v2.schemas.course_schemas import CourseIntent

# Import new SDUI architecture
from lyo_app.ai_classroom.sdui_models import (
    Scene, SceneType, Component, ComponentType,
    TeacherMessage, StudentPrompt, QuizCard, CTAButton,
    AudioMood, SceneMetadata
)
from lyo_app.ai_classroom.scene_lifecycle_engine import ContextSnapshot, DirectorDecision

logger = logging.getLogger(__name__)


# ═══════════════════════════════════════════════════════════════════════════════════
# 🎯 AGENT CONSULTATION SYSTEM
# ═══════════════════════════════════════════════════════════════════════════════════

class AgentRole(str, Enum):
    """Roles of existing agents in the new architecture"""
    CONTENT_PROVIDER = "content_provider"    # Generate educational content
    KNOWLEDGE_ASSESSOR = "knowledge_assessor" # Evaluate user understanding
    PEDAGOGICAL_ADVISOR = "pedagogical_advisor" # Educational strategy advice
    SUBJECT_MATTER_EXPERT = "subject_matter_expert" # Domain knowledge


class AgentCapability(BaseModel):
    """Describes what an existing agent can contribute to scene generation"""
    agent_name: str
    role: AgentRole
    can_generate: List[ComponentType] = Field(default_factory=list)
    response_time_ms: float = Field(default=500.0, description="Expected response time")
    reliability_score: float = Field(default=0.8, ge=0.0, le=1.0)

    # Context requirements
    requires_user_context: bool = True
    requires_content_history: bool = False
    requires_mastery_state: bool = False

    # Output constraints
    max_content_length: int = 1000
    supported_languages: List[str] = Field(default_factory=lambda: ["en-US"])


class AgentConsultationRequest(BaseModel):
    """Request to consult existing agent for scene content"""
    agent_name: str
    consultation_type: str  # "generate_content", "assess_understanding", "provide_feedback"

    # Scene context
    scene_type: SceneType
    target_components: List[ComponentType]

    # Educational context
    user_context: Optional[ContextSnapshot] = None
    topic: str
    difficulty_level: str = "beginner"
    concept_tags: List[str] = Field(default_factory=list)

    # Content constraints
    max_words: int = 100
    tone: str = "encouraging"
    include_audio_hints: bool = True

    # Timing constraints
    timeout_ms: int = 2000  # Fast response required
    priority: int = Field(default=5, ge=1, le=10)


class AgentConsultationResponse(BaseModel):
    """Response from existing agent consultation"""
    agent_name: str
    success: bool = True
    response_time_ms: float = 0.0

    # Generated content
    generated_components: List[Component] = Field(default_factory=list)
    content_suggestions: Dict[str, Any] = Field(default_factory=dict)

    # Educational insights
    difficulty_assessment: Optional[float] = None
    prerequisite_concepts: List[str] = Field(default_factory=list)
    suggested_followup: List[str] = Field(default_factory=list)

    # Metadata
    confidence: float = Field(default=0.8, ge=0.0, le=1.0)
    fallback_used: bool = False
    error_message: Optional[str] = None


# ═══════════════════════════════════════════════════════════════════════════════════
# 🤖 AGENT ADAPTER SYSTEM
# ═══════════════════════════════════════════════════════════════════════════════════

class BaseAgentAdapter:
    """Base adapter to integrate existing agents with Scene Lifecycle Engine"""

    def __init__(self, agent: BaseAgent, capability: AgentCapability):
        self.agent = agent
        self.capability = capability
        self.consultation_count = 0
        self.average_response_time = 0.0

    async def consult(self, request: AgentConsultationRequest) -> AgentConsultationResponse:
        """Consult the existing agent for scene content"""
        start_time = asyncio.get_event_loop().time()

        try:
            response = await self._execute_consultation(request)
            response.response_time_ms = (asyncio.get_event_loop().time() - start_time) * 1000

            # Update metrics
            self._update_metrics(response.response_time_ms)

            logger.info(f"✅ Agent consultation: {self.capability.agent_name} → "
                       f"{len(response.generated_components)} components in {response.response_time_ms:.0f}ms")

            return response

        except asyncio.TimeoutError:
            logger.warning(f"⏰ Agent consultation timeout: {self.capability.agent_name}")
            return self._create_fallback_response(request, "Consultation timeout")

        except Exception as e:
            logger.error(f"❌ Agent consultation error: {self.capability.agent_name} - {e}")
            return self._create_fallback_response(request, str(e))

    async def _execute_consultation(self, request: AgentConsultationRequest) -> AgentConsultationResponse:
        """Execute the actual agent consultation (to be overridden)"""
        raise NotImplementedError("Subclasses must implement _execute_consultation")

    def _create_fallback_response(self, request: AgentConsultationRequest, error: str) -> AgentConsultationResponse:
        """Create fallback response when agent fails"""
        return AgentConsultationResponse(
            agent_name=self.capability.agent_name,
            success=False,
            error_message=error,
            fallback_used=True,
            confidence=0.1
        )

    def _update_metrics(self, response_time_ms: float):
        """Update performance metrics"""
        self.consultation_count += 1
        self.average_response_time = (
            (self.average_response_time * (self.consultation_count - 1) + response_time_ms)
            / self.consultation_count
        )


# ═══════════════════════════════════════════════════════════════════════════════════
# 🎓 SPECIFIC AGENT ADAPTERS
# ═══════════════════════════════════════════════════════════════════════════════════

class TutorAgentAdapter(BaseAgentAdapter):
    """Adapter for the existing TutorAgent"""

    def __init__(self, tutor_agent: TutorAgent):
        capability = AgentCapability(
            agent_name="tutor_agent",
            role=AgentRole.CONTENT_PROVIDER,
            can_generate=[ComponentType.TEACHER_MESSAGE, ComponentType.EXAMPLE_BLOCK],
            response_time_ms=800.0,
            reliability_score=0.9
        )
        super().__init__(tutor_agent, capability)

    async def _execute_consultation(self, request: AgentConsultationRequest) -> AgentConsultationResponse:
        """Generate teaching content using TutorAgent"""

        # Build prompt for the tutor agent
        tutor_prompt = self._build_tutor_prompt(request)

        try:
            # Call existing tutor agent
            # Note: This adapts to your existing TutorAgent interface
            tutor_response = await asyncio.wait_for(
                self.agent.execute_task(tutor_prompt),
                timeout=request.timeout_ms / 1000.0
            )

            # Convert tutor response to SDUI components
            components = await self._convert_tutor_response_to_components(tutor_response, request)

            return AgentConsultationResponse(
                agent_name=self.capability.agent_name,
                success=True,
                generated_components=components,
                confidence=0.85
            )

        except asyncio.TimeoutError:
            raise
        except Exception as e:
            logger.error(f"TutorAgent execution failed: {e}")
            raise

    def _build_tutor_prompt(self, request: AgentConsultationRequest) -> str:
        """Build prompt for TutorAgent in scene context"""
        context_info = ""
        if request.user_context:
            frustration = request.user_context.frustration.frustration_score
            engagement = request.user_context.engagement_level
            context_info = f"\nStudent frustration: {frustration:.1f}, engagement: {engagement:.1f}"

        return f"""You are Lio, the AI teacher in a real-time learning conversation.

Generate a brief teaching response for this scene:
- Topic: {request.topic}
- Scene Type: {request.scene_type}
- Difficulty: {request.difficulty_level}
- Max Words: {request.max_words}
- Tone: {request.tone}
{context_info}

Requirements:
1. Be conversational and encouraging
2. Keep under {request.max_words} words
3. Focus on the specific concept: {', '.join(request.concept_tags) if request.concept_tags else request.topic}
4. End with a natural transition or question if appropriate

Generate ONLY the teaching content, no metadata."""

    async def _convert_tutor_response_to_components(
        self,
        tutor_response: Any,
        request: AgentConsultationRequest
    ) -> List[Component]:
        """Convert TutorAgent response to SDUI components"""

        components = []

        # Extract text from tutor response (adapt to your response format)
        teaching_text = str(tutor_response).strip() if tutor_response else "Let's continue learning together!"

        # Create TeacherMessage component
        teacher_msg = TeacherMessage(
            text=teaching_text,
            emotion="encouraging" if "great" in teaching_text.lower() else "neutral",
            audio_mood=AudioMood.CALM,
            concept_tags=request.concept_tags,
            difficulty_level=request.difficulty_level
        )

        components.append(teacher_msg)

        return components


class AssessmentAgentAdapter(BaseAgentAdapter):
    """Adapter for the existing AssessmentAgent"""

    def __init__(self, assessment_agent: AssessmentAgent):
        capability = AgentCapability(
            agent_name="assessment_agent",
            role=AgentRole.KNOWLEDGE_ASSESSOR,
            can_generate=[ComponentType.QUIZ_CARD, ComponentType.REFLECTION_PROMPT],
            response_time_ms=1200.0,
            reliability_score=0.85,
            requires_mastery_state=True
        )
        super().__init__(assessment_agent, capability)

    async def _execute_consultation(self, request: AgentConsultationRequest) -> AgentConsultationResponse:
        """Generate assessment content using AssessmentAgent"""

        # Build assessment request
        assessment_prompt = self._build_assessment_prompt(request)

        try:
            # Call existing assessment agent
            assessment_response = await asyncio.wait_for(
                self.agent.execute_task(assessment_prompt),
                timeout=request.timeout_ms / 1000.0
            )

            # Convert to SDUI components
            components = await self._convert_assessment_to_components(assessment_response, request)

            return AgentConsultationResponse(
                agent_name=self.capability.agent_name,
                success=True,
                generated_components=components,
                confidence=0.8
            )

        except asyncio.TimeoutError:
            raise
        except Exception as e:
            logger.error(f"AssessmentAgent execution failed: {e}")
            raise

    def _build_assessment_prompt(self, request: AgentConsultationRequest) -> str:
        """Build prompt for AssessmentAgent"""
        mastery_context = ""
        if request.user_context and request.user_context.knowledge_states:
            avg_mastery = sum(k.mastery_level for k in request.user_context.knowledge_states) / len(request.user_context.knowledge_states)
            mastery_context = f"\nStudent mastery level: {avg_mastery:.1f}"

        return f"""Create a quick knowledge check question for real-time assessment.

Topic: {request.topic}
Concepts: {', '.join(request.concept_tags) if request.concept_tags else 'general'}
Difficulty: {request.difficulty_level}
{mastery_context}

Generate a multiple choice question with:
1. Clear, concise question (max 50 words)
2. 3-4 options with exactly ONE correct answer
3. Brief feedback for incorrect answers
4. Focus on understanding, not memorization

Format as JSON with question, options[], and explanations."""

    async def _convert_assessment_to_components(
        self,
        assessment_response: Any,
        request: AgentConsultationRequest
    ) -> List[Component]:
        """Convert AssessmentAgent response to QuizCard"""

        components = []

        try:
            # Parse JSON response (adapt to your AssessmentAgent format)
            if isinstance(assessment_response, str):
                quiz_data = json.loads(assessment_response)
            else:
                quiz_data = assessment_response

            # Import QuizOption here to avoid circular imports
            from lyo_app.ai_classroom.sdui_models import QuizOption

            # Convert to QuizCard
            quiz_card = QuizCard(
                question=quiz_data.get("question", "Quick check: Which is correct?"),
                options=[
                    QuizOption(
                        id=opt.get("id", f"opt_{i}"),
                        label=opt.get("label", f"Option {i+1}"),
                        is_correct=opt.get("is_correct", False),
                        feedback_correct="Great job!" if opt.get("is_correct") else None,
                        feedback_incorrect=opt.get("feedback", "Not quite right, let's try again.")
                    )
                    for i, opt in enumerate(quiz_data.get("options", []))
                ],
                concept_id=request.concept_tags[0] if request.concept_tags else request.topic,
                difficulty_weight=1.0 if request.difficulty_level == "beginner" else 1.5
            )

            components.append(quiz_card)

        except (json.JSONDecodeError, KeyError, IndexError) as e:
            logger.warning(f"Failed to parse assessment response, using fallback: {e}")
            # Fallback quiz
            from lyo_app.ai_classroom.sdui_models import QuizOption
            fallback_quiz = QuizCard(
                question=f"Which statement best describes {request.topic}?",
                options=[
                    QuizOption(id="a", label="It's a fundamental concept", is_correct=True),
                    QuizOption(id="b", label="It's not important", is_correct=False),
                    QuizOption(id="c", label="It's too complex", is_correct=False)
                ]
            )
            components.append(fallback_quiz)

        return components


# ═══════════════════════════════════════════════════════════════════════════════════
# 🎭 CLASSROOM DIRECTOR INTEGRATION
# ═══════════════════════════════════════════════════════════════════════════════════

class ClassroomDirectorIntegration:
    """Integrates Classroom Director with existing multi-agent system"""

    def __init__(self, db: AsyncSession):
        self.db = db
        self.agent_adapters: Dict[str, BaseAgentAdapter] = {}
        self.model_manager = ModelManager()
        self._initialize_adapters()

    def _initialize_adapters(self):
        """Initialize adapters for existing agents"""
        try:
            # Initialize existing agents
            tutor_agent = TutorAgent()
            assessment_agent = AssessmentAgent()

            # Create adapters
            self.agent_adapters["tutor"] = TutorAgentAdapter(tutor_agent)
            self.agent_adapters["assessment"] = AssessmentAgentAdapter(assessment_agent)

            logger.info(f"✅ Initialized {len(self.agent_adapters)} agent adapters")

        except Exception as e:
            logger.error(f"❌ Failed to initialize agent adapters: {e}")

    async def enhance_scene_with_agents(
        self,
        base_scene: Scene,
        director_decision: DirectorDecision,
        context: ContextSnapshot
    ) -> Scene:
        """Enhance a scene using existing multi-agent system"""

        logger.info(f"🎯 Enhancing scene {base_scene.scene_id} with agent consultation")

        enhanced_components = []
        consultation_tasks = []

        # Determine which agents to consult based on scene type
        agents_to_consult = self._select_agents_for_scene(director_decision.selected_scene_type)

        # Create consultation requests
        for agent_name in agents_to_consult:
            if agent_name in self.agent_adapters:
                request = self._create_consultation_request(
                    agent_name=agent_name,
                    scene_type=base_scene.scene_type,
                    decision=director_decision,
                    context=context
                )
                consultation_tasks.append(
                    self.agent_adapters[agent_name].consult(request)
                )

        # Execute consultations in parallel
        if consultation_tasks:
            try:
                consultation_responses = await asyncio.gather(
                    *consultation_tasks,
                    return_exceptions=True
                )

                # Process responses
                for response in consultation_responses:
                    if isinstance(response, AgentConsultationResponse) and response.success:
                        enhanced_components.extend(response.generated_components)
                        logger.debug(f"✅ Agent {response.agent_name} contributed {len(response.generated_components)} components")
                    else:
                        logger.warning(f"⚠️ Agent consultation failed or returned exception: {response}")

            except Exception as e:
                logger.error(f"❌ Agent consultation batch failed: {e}")

        # Merge with base scene components (Director has final authority)
        final_components = self._merge_components_with_director_authority(
            base_components=base_scene.components,
            agent_components=enhanced_components,
            director_decision=director_decision
        )

        # Create enhanced scene
        enhanced_scene = Scene(
            scene_id=base_scene.scene_id,
            scene_type=base_scene.scene_type,
            components=final_components,
            metadata=base_scene.metadata,
            state=base_scene.state
        )

        logger.info(f"✅ Scene enhanced: {len(base_scene.components)} → {len(final_components)} components")

        return enhanced_scene

    def _select_agents_for_scene(self, scene_type: SceneType) -> List[str]:
        """Select appropriate agents based on scene type"""
        agent_selection = {
            SceneType.INSTRUCTION: ["tutor"],
            SceneType.CHALLENGE: ["assessment"],
            SceneType.CORRECTION: ["tutor", "assessment"],
            SceneType.CELEBRATION: [],  # No agent consultation needed
            SceneType.REFLECTION: ["tutor"]
        }

        return agent_selection.get(scene_type, ["tutor"])

    def _create_consultation_request(
        self,
        agent_name: str,
        scene_type: SceneType,
        decision: DirectorDecision,
        context: ContextSnapshot
    ) -> AgentConsultationRequest:
        """Create consultation request for specific agent"""

        # Extract topic from context or use fallback
        topic = "current topic"
        if context.knowledge_states:
            topic = context.knowledge_states[0].concept_id

        return AgentConsultationRequest(
            agent_name=agent_name,
            consultation_type="generate_content",
            scene_type=scene_type,
            target_components=decision.suggested_components,
            user_context=context,
            topic=topic,
            difficulty_level="beginner",  # Could be derived from context
            max_words=80,  # Keep it concise for real-time
            tone="encouraging",
            timeout_ms=1500,  # Fast response required
            priority=7 if scene_type == SceneType.CORRECTION else 5
        )

    def _merge_components_with_director_authority(
        self,
        base_components: List[Component],
        agent_components: List[Component],
        director_decision: DirectorDecision
    ) -> List[Component]:
        """Merge components while respecting Director's authority"""

        # Director has final say - its components have priority 0-3
        final_components = []

        # Add Director components first (highest priority)
        for comp in base_components:
            comp.priority = min(comp.priority, 3)  # Ensure Director components are high priority
            final_components.append(comp)

        # Add agent-generated components with lower priority
        for comp in agent_components:
            comp.priority = max(comp.priority, 4)  # Ensure agent components are lower priority
            final_components.append(comp)

        # Sort by priority (0 = highest priority, rendered first)
        final_components.sort(key=lambda c: c.priority)

        # Limit total components to avoid overwhelming user
        MAX_COMPONENTS = 5
        if len(final_components) > MAX_COMPONENTS:
            logger.info(f"🎯 Director limiting components: {len(final_components)} → {MAX_COMPONENTS}")
            final_components = final_components[:MAX_COMPONENTS]

        return final_components

    async def get_agent_performance_stats(self) -> Dict[str, Any]:
        """Get performance statistics for agent adapters"""
        stats = {}

        for agent_name, adapter in self.agent_adapters.items():
            stats[agent_name] = {
                "consultation_count": adapter.consultation_count,
                "average_response_time_ms": adapter.average_response_time,
                "reliability_score": adapter.capability.reliability_score,
                "can_generate": [ct.value for ct in adapter.capability.can_generate]
            }

        return {
            "total_agents": len(self.agent_adapters),
            "agent_stats": stats,
            "integration_status": "active"
        }


# ═══════════════════════════════════════════════════════════════════════════════════
# 🎯 MIGRATION UTILITIES
# ═══════════════════════════════════════════════════════════════════════════════════

class CourseToSceneConverter:
    """Converts existing full course structures to scene-based streaming"""

    @staticmethod
    async def convert_existing_course_to_scenes(course_data: Any) -> List[Scene]:
        """Convert existing course structure to scene sequence"""
        scenes = []

        # This would implement the conversion logic
        # For now, return a basic scene structure
        logger.info("🔄 Converting existing course to scene sequence (placeholder)")

        return scenes

    @staticmethod
    def extract_learning_objectives_as_scenes(objectives: List[str]) -> List[Scene]:
        """Extract learning objectives and create corresponding scenes"""
        scenes = []

        for i, objective in enumerate(objectives):
            # Create instruction scene for each objective
            instruction_scene = Scene(
                scene_type=SceneType.INSTRUCTION,
                components=[
                    TeacherMessage(
                        text=f"Let's work on: {objective}",
                        concept_tags=["objective"],
                        priority=0
                    )
                ],
                metadata=SceneMetadata(
                    concept_tags=[f"objective_{i}"],
                    estimated_duration_seconds=60
                )
            )
            scenes.append(instruction_scene)

        return scenes


# ═══════════════════════════════════════════════════════════════════════════════════
# 🎯 EXPORTS
# ═══════════════════════════════════════════════════════════════════════════════════

__all__ = [
    "ClassroomDirectorIntegration",
    "TutorAgentAdapter",
    "AssessmentAgentAdapter",
    "AgentConsultationRequest",
    "AgentConsultationResponse",
    "CourseToSceneConverter"
]