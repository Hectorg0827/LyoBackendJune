"""
Pedagogy Agent - Expert in learning science and instructional design.

A2A-compliant agent responsible for:
- Analyzing learning objectives (Bloom's Taxonomy)
- Designing cognitive scaffolding
- Creating prerequisite graphs
- Applying learning science principles
- Personalizing for learner profiles

MIT Architecture Engineering - Pedagogy Specialist Agent
"""

from typing import Optional, Dict, Any, List
from pydantic import BaseModel, Field
from enum import Enum

from .base import A2ABaseAgent
from .schemas import (
    AgentCapability,
    AgentSkill,
    TaskInput,
    ArtifactType,
)
from lyo_app.ai_agents.multi_agent_v2.model_manager import ModelTier


# ============================================================
# PEDAGOGY-SPECIFIC SCHEMAS
# ============================================================

class BloomLevel(str, Enum):
    """Bloom's Taxonomy cognitive levels"""
    REMEMBER = "remember"
    UNDERSTAND = "understand"
    APPLY = "apply"
    ANALYZE = "analyze"
    EVALUATE = "evaluate"
    CREATE = "create"


class LearnerProfile(str, Enum):
    """Types of learner profiles"""
    VISUAL = "visual"
    AUDITORY = "auditory"
    KINESTHETIC = "kinesthetic"
    READING_WRITING = "reading_writing"


class CognitiveLoadLevel(str, Enum):
    """Cognitive load management"""
    LOW = "low"          # Simple, foundational
    MEDIUM = "medium"    # Building complexity
    HIGH = "high"        # Challenging, synthesis
    PEAK = "peak"        # Maximum difficulty


class LearningObjective(BaseModel):
    """Structured learning objective"""
    id: str
    description: str
    bloom_level: BloomLevel
    measurable_outcome: str
    assessment_criteria: List[str]
    estimated_time_minutes: int


class PrerequisiteNode(BaseModel):
    """Node in the prerequisite graph"""
    id: str
    title: str
    description: str
    required_for: List[str]  # IDs of objectives that depend on this
    bloom_level: BloomLevel
    is_optional: bool = False


class CognitiveChunk(BaseModel):
    """A chunk of content optimized for working memory"""
    id: str
    title: str
    concepts: List[str]  # 3-5 concepts max (Miller's Law)
    bloom_level: BloomLevel
    cognitive_load: CognitiveLoadLevel
    duration_minutes: int
    practice_activities: List[str]
    rest_after: bool = False  # Suggest break after this chunk


class ScaffoldingStep(BaseModel):
    """A step in the scaffolding progression"""
    step_number: int
    title: str
    description: str
    support_level: str  # full, partial, minimal, independent
    example_count: int
    practice_type: str  # guided, semi-guided, independent
    feedback_frequency: str  # immediate, delayed, self-check


class PedagogyOutput(BaseModel):
    """Output from the Pedagogy Agent"""
    # Course analysis
    topic: str
    difficulty_level: str
    estimated_total_hours: float
    
    # Learning objectives
    learning_objectives: List[LearningObjective]
    bloom_distribution: Dict[str, int]  # Count per Bloom level
    
    # Prerequisite graph
    prerequisites: List[PrerequisiteNode]
    prerequisite_dag: Dict[str, List[str]]  # Directed acyclic graph
    
    # Cognitive structure
    cognitive_chunks: List[CognitiveChunk]
    recommended_session_length_minutes: int
    total_chunks: int
    
    # Scaffolding plan
    scaffolding_steps: List[ScaffoldingStep]
    
    # Personalization hints
    visual_learner_suggestions: List[str]
    auditory_learner_suggestions: List[str]
    kinesthetic_learner_suggestions: List[str]
    
    # Assessment strategy
    formative_assessment_points: List[str]
    summative_assessment_strategy: str
    mastery_threshold: float  # e.g., 0.8 for 80%
    
    # Pedagogical notes
    key_misconceptions: List[str]
    difficulty_spikes: List[str]
    engagement_risks: List[str]


# ============================================================
# PEDAGOGY AGENT
# ============================================================

class PedagogyAgent(A2ABaseAgent[PedagogyOutput]):
    """
    Expert agent in learning science and instructional design.
    
    First agent in the cinematic pipeline - provides the pedagogical
    foundation that other agents build upon.
    
    Capabilities:
    - Bloom's Taxonomy analysis
    - Cognitive load optimization
    - Prerequisite graph construction
    - Scaffolding design
    - Multi-modal learning support
    """
    
    def __init__(self):
        super().__init__(
            name="pedagogy_agent",
            description="Expert in learning science, instructional design, and cognitive scaffolding",
            output_schema=PedagogyOutput,
            capabilities=[
                AgentCapability.COURSE_DESIGN,
                AgentCapability.CURRICULUM_PLANNING,
            ],
            skills=[
                AgentSkill(
                    id="bloom_analysis",
                    name="Bloom's Taxonomy Analysis",
                    description="Classifies learning objectives by cognitive level"
                ),
                AgentSkill(
                    id="scaffolding_design",
                    name="Scaffolding Design",
                    description="Creates progressive support structures for learning"
                ),
                AgentSkill(
                    id="cognitive_chunking",
                    name="Cognitive Chunking",
                    description="Optimizes content for working memory limits"
                ),
                AgentSkill(
                    id="prerequisite_mapping",
                    name="Prerequisite Mapping",
                    description="Builds dependency graphs for learning paths"
                ),
            ],
            temperature=0.4,  # Lower temperature for structured analysis
            max_tokens=16384,
            timeout_seconds=120.0,
            force_model_tier=ModelTier.PREMIUM  # Use best model for pedagogy
        )
    
    def get_output_artifact_type(self) -> ArtifactType:
        return ArtifactType.COURSE_INTENT
    
    def get_system_prompt(self) -> str:
        return """You are a world-renowned expert in learning science and instructional design with:

## Your Credentials
- PhD in Educational Psychology from Stanford
- Former Head of Curriculum at Coursera
- Author of "The Science of Effective Learning"
- Consultant for MIT OpenCourseWare, Khan Academy, and Duolingo
- Expert in cognitive load theory, scaffolding, and mastery-based learning

## Your Expertise

### Bloom's Taxonomy
You classify every learning objective using Bloom's revised taxonomy:
1. REMEMBER: Recall facts and basic concepts
2. UNDERSTAND: Explain ideas or concepts
3. APPLY: Use information in new situations
4. ANALYZE: Draw connections among ideas
5. EVALUATE: Justify decisions or course of action
6. CREATE: Produce new or original work

### Cognitive Load Theory
You design content that respects working memory limits:
- 7±2 items (Miller's Law) per cognitive chunk
- Intrinsic load: Core complexity of the material
- Extraneous load: Unnecessary complexity (minimize!)
- Germane load: Effort toward schema construction (maximize!)

### Scaffolding Principles
You design progressive support that fades over time:
1. Full Support: Worked examples, step-by-step guidance
2. Partial Support: Hints, partial solutions
3. Minimal Support: Prompts only
4. Independent: No support needed

### Prerequisite Design
You create DIRECTED ACYCLIC GRAPHS (DAGs) for prerequisites:
- No circular dependencies
- Clear learning pathways
- Multiple valid sequences when possible
- Essential vs. optional prerequisites

### Spacing & Interleaving
You recommend:
- Spaced repetition for retention
- Interleaved practice for discrimination
- Varied contexts for transfer

## Output Quality Standards

Your output MUST:
1. Cover ALL learning objectives with measurable outcomes
2. Respect cognitive load limits (3-5 concepts per chunk)
3. Include diverse practice types
4. Address common misconceptions
5. Support multiple learning styles
6. Create valid prerequisite DAGs (no cycles!)

CRITICAL: Return valid JSON matching the schema exactly."""
    
    def build_prompt(
        self, 
        task_input: TaskInput,
        topic: Optional[str] = None,
        difficulty: Optional[str] = None,
        context: Optional[Dict[str, Any]] = None,
        **kwargs
    ) -> str:
        # Extract topic from task input or kwargs
        course_topic = topic or task_input.user_message
        course_difficulty = difficulty or "intermediate"
        
        context_section = ""
        if context:
            context_section = f"""
## Additional Context
{chr(10).join(f"- {k}: {v}" for k, v in context.items())}
"""
        
        return f"""## Pedagogical Analysis Task

Analyze and design the pedagogical foundation for this course:

### Course Request
**Topic:** {course_topic}
**Difficulty Level:** {course_difficulty}
**Language:** {task_input.language}
{context_section}

## Your Task

Create a comprehensive pedagogical analysis including:

### 1. Learning Objectives (5-10 objectives)
For each objective:
- id: "obj_1", "obj_2", etc.
- description: Clear, action-oriented statement
- bloom_level: remember, understand, apply, analyze, evaluate, or create
- measurable_outcome: How we'll know the learner achieved this
- assessment_criteria: 2-4 specific criteria
- estimated_time_minutes: Time to achieve this objective

### 2. Prerequisite Graph
Create nodes for knowledge prerequisites:
- id: "prereq_1", etc.
- title: Short name
- description: What this knowledge includes
- required_for: List of objective IDs that need this
- bloom_level: At what level this prereq should be mastered
- is_optional: true/false

Include a prerequisite_dag as an adjacency list (node_id -> [dependent_ids])

### 3. Cognitive Chunks
Break content into working-memory-friendly chunks:
- id: "chunk_1", etc.
- title: Chunk name
- concepts: 3-5 concepts MAX (Miller's Law!)
- bloom_level: Primary cognitive level
- cognitive_load: low, medium, high, or peak
- duration_minutes: 5-20 minutes typically
- practice_activities: 1-3 activities
- rest_after: true if a break is recommended

### 4. Scaffolding Plan
Design progressive support reduction:
- step_number: 1, 2, 3...
- title: Step name
- description: What happens in this step
- support_level: full, partial, minimal, or independent
- example_count: How many examples to provide
- practice_type: guided, semi-guided, or independent
- feedback_frequency: immediate, delayed, or self-check

### 5. Multi-Modal Support
Provide suggestions for different learner types:
- visual_learner_suggestions: Diagrams, infographics, videos
- auditory_learner_suggestions: Explanations, discussions, podcasts
- kinesthetic_learner_suggestions: Hands-on activities, simulations

### 6. Assessment Strategy
- formative_assessment_points: When to check understanding
- summative_assessment_strategy: Final assessment approach
- mastery_threshold: e.g., 0.8 for 80%

### 7. Pedagogical Notes
- key_misconceptions: Common misunderstandings to address
- difficulty_spikes: Points where learners struggle
- engagement_risks: Where attention might wane

## Bloom Distribution
Provide counts: {{"remember": N, "understand": N, ...}}

Aim for higher-order thinking:
- Beginner courses: More remember/understand (60%), some apply (30%), little analyze+ (10%)
- Intermediate: Balance of understand/apply (50%), analyze/evaluate (40%), create (10%)
- Advanced: Less lower levels (20%), more analyze/evaluate/create (80%)

## Output Format
Return a valid JSON object matching the PedagogyOutput schema.
Do NOT include markdown code blocks or extra text."""
    
    def extract_intent_from_artifacts(
        self,
        artifacts: List
    ) -> Optional[Dict[str, Any]]:
        """Extract course intent from previous artifacts"""
        for artifact in artifacts:
            if artifact.type == ArtifactType.COURSE_INTENT:
                return artifact.data
        return None
