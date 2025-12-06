"""
Orchestrator Agent - Parses user intent and creates course plan.
First agent in the Multi-Agent Course Generation Pipeline.

MIT Architecture Engineering - Intent Analysis Agent
"""

from typing import Optional, Dict, Any

from lyo_app.ai_agents.multi_agent_v2.agents.base_agent import BaseAgent
from lyo_app.ai_agents.multi_agent_v2.schemas.course_schemas import CourseIntent, DifficultyLevel


class OrchestratorAgent(BaseAgent[CourseIntent]):
    """
    First agent in the pipeline.
    Analyzes user request and extracts structured course intent.
    
    Responsibilities:
    - Parse natural language course requests
    - Determine topic, difficulty, duration
    - Define learning objectives
    - Identify prerequisites
    """
    
    def __init__(self):
        super().__init__(
            name="orchestrator",  # Matches ModelManager task name
            output_schema=CourseIntent,
            timeout_seconds=90.0  # Model config from ModelManager
        )
    
    def get_system_prompt(self) -> str:
        return """You are an expert educational course designer and curriculum architect with 20+ years of experience creating courses for top universities and ed-tech platforms.

Your role is to analyze a user's request for a course and extract a precise, structured plan.

## Your Expertise

You excel at:
- Understanding what users want to learn, even from vague or incomplete requests
- Determining appropriate difficulty levels based on topic complexity and user hints
- Estimating realistic course durations based on industry standards
- Defining clear, actionable, measurable learning objectives
- Identifying necessary prerequisites

## Analysis Guidelines

When analyzing a course request:

1. **Topic Extraction**: Identify the core subject. If vague (e.g., "programming"), infer the most likely specific topic (e.g., "Python Programming Fundamentals").

2. **Difficulty Assessment**:
   - beginner: No prior knowledge required, foundational concepts
   - intermediate: Some experience expected, deeper exploration
   - advanced: Significant experience required, specialized topics

3. **Duration Estimation** (be realistic):
   - 1-5 hours: Single focused skill or concept
   - 5-15 hours: Comprehensive introduction to a topic
   - 15-40 hours: In-depth mastery of a subject area
   - 40+ hours: Professional/certification level depth

4. **Learning Objectives**: Must be SMART:
   - Specific: Clearly defined outcome
   - Measurable: Can verify achievement
   - Actionable: Uses action verbs (build, create, implement, analyze)
   - Relevant: Directly supports the course goal
   - Time-bound: Achievable within the course duration

5. **Prerequisites**: Only include truly necessary prior knowledge.

## Quality Standards

- Never use generic objectives like "understand programming"
- Always include practical, hands-on objectives
- Balance theory and practice objectives
- Consider real-world application"""
    
    def build_prompt(
        self, 
        user_request: str, 
        user_context: Optional[Dict[str, Any]] = None
    ) -> str:
        context_section = ""
        if user_context:
            context_section = f"""
## User Context (use this to personalize the course plan)

- Previous courses completed: {user_context.get('completed_courses', 'None')}
- Current skill level: {user_context.get('skill_level', 'Not specified')}
- Learning goals: {user_context.get('goals', 'Not specified')}
- Available time per week: {user_context.get('time_per_week', 'Not specified')}
- Preferred learning style: {user_context.get('learning_style', 'Not specified')}
"""
        
        return f"""## Course Request Analysis

Analyze this course request and create a structured course intent:

**User's Request:** "{user_request}"
{context_section}

## Your Task

Create a comprehensive course intent that includes:

1. **Topic**: The specific subject matter (be precise, not vague)
2. **Target Audience**: beginner, intermediate, or advanced
3. **Estimated Duration**: Realistic hours needed (1-100)
4. **Learning Objectives**: 3-10 specific, measurable outcomes using action verbs like:
   - "Build a working..."
   - "Implement X from scratch"
   - "Design and deploy..."
   - "Analyze and optimize..."
   - "Create production-ready..."
5. **Prerequisites**: What learners should already know (empty list for beginner courses)
6. **Tags**: Relevant categorization tags for discovery
7. **Teaching Style**: "interactive", "project-based", "lecture", or "hands-on"

## Important

- Be specific and practical in learning objectives
- Duration should match the depth implied by objectives
- Consider what a motivated learner could realistically achieve
- If the request is vague, make reasonable assumptions and be more specific

Respond with the JSON object only."""
    
    def get_fallback_prompt(
        self, 
        user_request: str, 
        **kwargs
    ) -> str:
        """Simpler prompt for retry attempts"""
        return f"""Create a course plan for: "{user_request}"

Provide:
- topic: The main subject (be specific)
- target_audience: "beginner", "intermediate", or "advanced"
- estimated_duration_hours: Number between 1-100
- learning_objectives: 3-5 specific skills the learner will gain
- prerequisites: List of required prior knowledge (can be empty)
- tags: 2-5 relevant tags
- teaching_style: "interactive"

Keep it practical and achievable. Respond with JSON only."""


class IntentRefinerAgent(BaseAgent[CourseIntent]):
    """
    Specialized agent to refine and improve an existing course intent.
    Used when the initial intent needs adjustment based on user feedback.
    """
    
    def __init__(self):
        super().__init__(
            name="IntentRefiner",
            output_schema=CourseIntent,
            temperature=0.4,
            max_tokens=4096,
            timeout_seconds=45.0
        )
    
    def get_system_prompt(self) -> str:
        return """You are an expert at refining and improving educational course plans based on feedback.

Your role is to take an existing course intent and adjust it based on user feedback or system requirements.

Maintain the core essence of the course while making targeted improvements."""
    
    def build_prompt(
        self,
        original_intent: Dict[str, Any],
        feedback: str,
        adjustment_type: str = "general"
    ) -> str:
        return f"""## Course Intent Refinement

### Original Course Intent
```json
{original_intent}
```

### Feedback/Adjustment Required
{feedback}

### Adjustment Type
{adjustment_type}

## Your Task

Refine the course intent based on the feedback while:
1. Maintaining the core topic and purpose
2. Adjusting difficulty/duration if requested
3. Improving learning objectives to be more specific
4. Ensuring all changes are educationally sound

Return the complete refined course intent as JSON."""
