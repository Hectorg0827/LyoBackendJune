"""
Curriculum Architect Agent - Designs course structure with modules and lessons.
Second agent in the Multi-Agent Course Generation Pipeline.

MIT Architecture Engineering - Structure Design Agent
"""

from typing import Optional, Dict, Any, List

from lyo_app.ai_agents.multi_agent_v2.agents.base_agent import BaseAgent
from lyo_app.ai_agents.multi_agent_v2.schemas.course_schemas import (
    CourseIntent, 
    CurriculumStructure,
    ModuleOutline,
    LessonOutline,
    DifficultyLevel
)


class CurriculumArchitectAgent(BaseAgent[CurriculumStructure]):
    """
    Second agent in the pipeline.
    Takes course intent and creates detailed curriculum structure.
    
    Responsibilities:
    - Design logical module progression
    - Create lesson outlines for each module
    - Define lesson types and durations
    - Establish prerequisite DAG (no cycles!)
    - Ensure complete learning objective coverage
    """
    
    def __init__(self):
        super().__init__(
            name="curriculum_architect",  # Matches ModelManager task name for PREMIUM tier
            output_schema=CurriculumStructure,
            temperature=0.6,
            max_tokens=16384,  # Large output for detailed curriculum
            timeout_seconds=120.0
        )
    
    def get_system_prompt(self) -> str:
        return """You are a world-class curriculum architect with expertise in instructional design, learning science, and educational technology.

You have designed curricula for Harvard, MIT, Coursera, and leading bootcamps.

## Your Expertise

- Bloom's Taxonomy application
- Scaffolded learning progressions
- Cognitive load management
- Spaced repetition integration
- Practical skill development

## Design Principles

1. **Progressive Complexity**: Start simple, build toward complexity
2. **Prerequisite Logic**: Each lesson builds on previous ones logically
3. **Module Cohesion**: Each module covers a coherent sub-topic
4. **Lesson Focus**: Each lesson has ONE clear learning outcome
5. **Practice Integration**: Include hands-on lessons regularly (every 2-3 theory lessons)
6. **Assessment Points**: Include checkpoints for knowledge verification

## Module Design Guidelines

- 3-8 modules per course (more for longer courses)
- Each module: 3-7 lessons
- Module names: Clear, descriptive, action-oriented when possible
- Module descriptions: 2-3 sentences explaining scope and outcomes

## Lesson Design Guidelines

- Lesson types:
  - "concept": Theory, explanation, foundational knowledge
  - "tutorial": Step-by-step guided implementation  
  - "exercise": Hands-on practice with guidance
  - "project": Open-ended application
  - "quiz": Knowledge assessment
  - "review": Summary and reinforcement

- Duration guidelines:
  - concept: 10-30 minutes
  - tutorial: 20-45 minutes
  - exercise: 15-40 minutes
  - project: 30-90 minutes
  - quiz: 10-20 minutes
  - review: 10-20 minutes

## Prerequisite Rules (CRITICAL)

- Prerequisites form a DIRECTED ACYCLIC GRAPH (DAG)
- No circular dependencies!
- Each lesson can depend on 0-3 previous lessons
- Prerequisites must be from EARLIER in the curriculum
- Use lesson_id format: "mod{module_number}_les{lesson_number}" (e.g., "mod1_les1")

## Quality Standards

- Total lesson durations must roughly match course estimated duration
- Every learning objective from the intent must be addressed
- Balance theory (40%) and practice (60%)
- Include at least one project or major exercise per module"""
    
    def build_prompt(
        self, 
        intent: CourseIntent,
        constraints: Optional[Dict[str, Any]] = None
    ) -> str:
        constraints_section = ""
        if constraints:
            constraints_section = f"""
## Additional Constraints

- Maximum modules: {constraints.get('max_modules', 8)}
- Maximum lessons per module: {constraints.get('max_lessons_per_module', 7)}
- Must include projects: {constraints.get('require_projects', True)}
- Focus areas: {constraints.get('focus_areas', 'None specified')}
"""
        
        objectives_list = "\n".join(f"  - {obj}" for obj in intent.learning_objectives)
        prerequisites_list = "\n".join(f"  - {pre}" for pre in intent.prerequisites) if intent.prerequisites else "  - None"
        
        return f"""## Curriculum Design Task

Design a complete curriculum structure for this course:

### Course Intent

**Topic:** {intent.topic}
**Target Audience:** {intent.target_audience.value}
**Total Duration:** {intent.estimated_duration_hours} hours
**Teaching Style:** {intent.teaching_style.value}

**Learning Objectives:**
{objectives_list}

**Prerequisites:**
{prerequisites_list}

**Tags:** {', '.join(intent.tags)}
{constraints_section}

## Your Task

Create a comprehensive curriculum with:

1. **Modules** (3-8 depending on course length):
   - module_id: "mod1", "mod2", etc.
   - title: Descriptive, engaging title
   - description: 2-3 sentences on module scope
   - order: 1, 2, 3, etc.
   - estimated_duration_minutes: Sum of lesson durations

2. **Lessons** within each module (3-7 per module):
   - lesson_id: "mod1_les1", "mod1_les2", etc.
   - title: Specific, action-oriented title
   - lesson_type: "concept", "tutorial", "exercise", "project", "quiz", or "review"
   - duration_minutes: Realistic for the content
   - order: 1, 2, 3, etc. within module
   - prerequisites: List of lesson_ids (must be earlier lessons)
   - objectives: List of specific objectives this lesson addresses (use same text as course objectives where applicable)
   - description: What the learner will do/learn

3. **Curriculum Metadata**:
   - title: The course title
   - description: 2-3 sentence course description
   - total_duration_minutes: Sum of all lessons
   - module_count: Number of modules
   - lesson_count: Total lessons

## Critical Rules

1. Prerequisites must form a valid DAG (no cycles!)
2. Lesson IDs must follow format "mod{{n}}_les{{m}}"
3. Every course learning objective must be covered by at least one lesson
4. Include variety in lesson types
5. End each module with a quiz or exercise
6. Include at least one project in the course

Respond with the complete JSON structure only."""
    
    def get_fallback_prompt(
        self, 
        intent: CourseIntent, 
        **kwargs
    ) -> str:
        """Simpler prompt for retry attempts"""
        return f"""Design a curriculum for a {intent.estimated_duration_hours}-hour course on "{intent.topic}".

Target audience: {intent.target_audience.value}

Create:
1. 3-5 modules with titles and descriptions
2. 3-5 lessons per module with:
   - lesson_id (format: "mod1_les1")
   - title
   - lesson_type: "concept", "tutorial", "exercise", "project", or "quiz"
   - duration_minutes (5-60)
   - order
   - prerequisites (list of earlier lesson_ids, can be empty)
   - objectives (1-2 items)
   - description

Include:
- title: Course title
- description: Course description
- total_duration_minutes
- module_count
- lesson_count

Respond with JSON only."""


class CurriculumRebalancerAgent(BaseAgent[CurriculumStructure]):
    """
    Specialized agent to rebalance and optimize an existing curriculum.
    Used when duration needs adjustment or balance is off.
    """
    
    def __init__(self):
        super().__init__(
            name="curriculum_architect",  # Matches ModelManager task name
            output_schema=CurriculumStructure,
            timeout_seconds=120.0  # Model config from ModelManager
        )
    
    def get_system_prompt(self) -> str:
        return """You are an expert at optimizing and rebalancing educational curricula.

Your role is to adjust an existing curriculum to better match time constraints or improve balance.

Maintain the core structure while making targeted adjustments."""
    
    def build_prompt(
        self,
        current_curriculum: Dict[str, Any],
        target_duration_minutes: int,
        adjustment_notes: str = ""
    ) -> str:
        return f"""## Curriculum Rebalancing Task

### Current Curriculum
```json
{current_curriculum}
```

### Target Duration
{target_duration_minutes} minutes

### Adjustment Notes
{adjustment_notes if adjustment_notes else "Rebalance to match target duration while maintaining quality."}

## Your Task

Adjust the curriculum to:
1. Match the target duration (within 10% tolerance)
2. Maintain logical progression and prerequisites
3. Keep essential content, trim or expand as needed
4. Ensure good lesson type variety

Return the complete adjusted curriculum as JSON."""
