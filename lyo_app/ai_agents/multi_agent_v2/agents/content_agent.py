"""
Content Creator Agent - Generates full lesson content.
Third agent in the Multi-Agent Course Generation Pipeline.

MIT Architecture Engineering - Content Generation Agent

This agent operates in PARALLEL mode - it can generate multiple lessons concurrently.
"""

from typing import Optional, Dict, Any, List
import asyncio
from dataclasses import dataclass

from lyo_app.ai_agents.multi_agent_v2.agents.base_agent import BaseAgent
from lyo_app.ai_agents.multi_agent_v2.schemas.course_schemas import (
    LessonOutline,
    LessonContent,
    ContentBlock,
    TextBlock,
    CodeBlock,
    ExerciseBlock,
    MediaBlock,
    LessonType
)


@dataclass
class LessonGenerationContext:
    """Context for generating a single lesson"""
    lesson_outline: LessonOutline
    module_title: str
    module_description: str
    course_topic: str
    difficulty_level: str
    previous_lessons: List[str]  # Titles of prerequisite lessons


class ContentCreatorAgent(BaseAgent[LessonContent]):
    """
    Third agent in the pipeline.
    Generates complete lesson content with multiple content blocks.
    
    Responsibilities:
    - Generate structured lesson content
    - Create code examples with proper explanations
    - Design exercises with hints and solutions
    - Include media references where appropriate
    - Adapt content to lesson type (concept, tutorial, exercise, etc.)
    
    Parallelization:
    - This agent can process multiple lessons in parallel
    - Use generate_lessons_parallel() for batch processing
    """
    
    def __init__(self):
        super().__init__(
            name="content_creator",  # Matches ModelManager task name for STANDARD tier
            output_schema=LessonContent,
            temperature=0.7,  # Higher creativity for content
            max_tokens=8192,
            timeout_seconds=90.0
        )
    
    def get_system_prompt(self) -> str:
        return """You are an expert educational content creator with deep experience in:
- Technical writing for developers
- Interactive tutorial design
- Code example creation
- Exercise and challenge design

## Your Expertise

You create content that is:
- Clear and concise
- Properly scaffolded (simple → complex)
- Rich with practical examples
- Engaging and motivating

## Content Creation Guidelines

### Text Blocks
- Use headers to structure content (h1, h2, h3)
- Keep paragraphs focused (3-5 sentences)
- Include bullet points for lists
- Add notes and tips in callout style
- Explain concepts before showing code

### Code Blocks
- Always specify the language
- Include descriptive filenames
- Add line-by-line comments for complex code
- Show realistic, production-quality code
- Explain WHY, not just WHAT

### Exercise Blocks
- Clear, specific instructions
- Difficulty appropriate to lesson level
- Provide 2-3 helpful hints
- Include complete solution code
- Expected output for verification

### Media Blocks
- Suggest diagrams for complex concepts
- Use alt_text for accessibility
- Caption should explain the media

## Lesson Type Specific Guidelines

### "concept" lessons
- Focus on explanation and understanding
- 60% text, 30% code examples, 10% exercises
- Include diagrams/visuals for complex ideas

### "tutorial" lessons
- Step-by-step guided implementation
- 40% text, 50% code blocks, 10% exercises
- Each step should build on the previous

### "exercise" lessons
- Hands-on practice focus
- 20% text (setup/context), 20% code (starter), 60% exercises
- Multiple small challenges building to larger ones

### "project" lessons
- Open-ended application
- 30% text (requirements/guidance), 20% code (examples), 50% exercise (the project)
- Include evaluation criteria

### "quiz" lessons
- Create as review content
- 40% text (key concepts recap), 60% exercises (quiz questions as exercises)
- Include self-assessment guidance

### "review" lessons
- Summarize module content
- 70% text (summaries, key takeaways), 30% code (key examples recap)
- Connect concepts together"""
    
    def build_prompt(
        self, 
        context: LessonGenerationContext
    ) -> str:
        lesson = context.lesson_outline
        prereq_section = ""
        if context.previous_lessons:
            prereq_section = f"""
### Prerequisite Content (the learner has already covered)
{chr(10).join(f"- {title}" for title in context.previous_lessons)}
"""
        
        objectives_list = "\n".join(f"- {obj}" for obj in lesson.objectives)
        
        return f"""## Lesson Content Generation

Generate complete, high-quality content for this lesson:

### Course Context
**Topic:** {context.course_topic}
**Difficulty:** {context.difficulty_level}
**Module:** {context.module_title}
**Module Description:** {context.module_description}
{prereq_section}

### Lesson Details
**Lesson ID:** {lesson.lesson_id}
**Title:** {lesson.title}
**Type:** {lesson.lesson_type.value}
**Duration:** {lesson.duration_minutes} minutes
**Description:** {lesson.description}

**Objectives:**
{objectives_list}

## Your Task

Generate the lesson content with these elements:

1. **lesson_id**: "{lesson.lesson_id}"
2. **title**: "{lesson.title}"
3. **lesson_type**: "{lesson.lesson_type.value}"
4. **introduction**: 2-3 paragraphs setting up the lesson

5. **content_blocks** (array of blocks in order):
   For each block, specify the "block_type" as one of:
   - "text": For explanatory content
   - "code": For code examples
   - "exercise": For practice challenges
   - "media": For diagrams/images (describe what should be there)

   **Text Block Structure:**
   - block_type: "text"
   - title: Section heading
   - content: The text content (can include markdown)
   - order: Position in sequence

   **Code Block Structure:**
   - block_type: "code"
   - title: What this code demonstrates
   - language: Programming language
   - code: The actual code
   - explanation: What the code does and why
   - filename: Optional filename
   - order: Position in sequence

   **Exercise Block Structure:**
   - block_type: "exercise"
   - title: Exercise name
   - instructions: What to do
   - difficulty: "easy", "medium", or "hard"
   - hints: Array of helpful hints
   - solution: Complete solution code
   - expected_output: What the solution produces
   - order: Position in sequence

   **Media Block Structure:**
   - block_type: "media"
   - title: What it shows
   - media_type: "diagram", "image", or "video"
   - url: Leave as "placeholder" (will be generated later)
   - alt_text: Accessibility description
   - caption: Explanation of the media
   - order: Position in sequence

6. **summary**: 1-2 paragraphs summarizing key takeaways

7. **key_takeaways**: Array of 3-5 bullet points

8. **next_steps**: Brief text on what comes next

## Content Volume Guidelines

Based on {lesson.duration_minutes} minute duration:
- 5-10 min: 2-4 content blocks
- 10-20 min: 4-6 content blocks
- 20-30 min: 6-8 content blocks
- 30-45 min: 8-12 content blocks
- 45+ min: 12+ content blocks

Respond with the complete JSON structure only."""
    
    async def generate_lesson(
        self,
        context: LessonGenerationContext
    ) -> LessonContent:
        """Generate content for a single lesson"""
        prompt = self.build_prompt(context)
        return await self.execute(prompt)
    
    async def generate_lessons_parallel(
        self,
        contexts: List[LessonGenerationContext],
        max_concurrent: int = 3
    ) -> List[LessonContent]:
        """
        Generate multiple lessons in parallel with concurrency limit.
        
        This is the key optimization - we don't need to wait for
        sequential lesson generation.
        
        Args:
            contexts: List of lesson generation contexts
            max_concurrent: Maximum concurrent generations
            
        Returns:
            List of generated lesson contents (in same order as contexts)
        """
        semaphore = asyncio.Semaphore(max_concurrent)
        
        async def generate_with_semaphore(ctx: LessonGenerationContext) -> LessonContent:
            async with semaphore:
                return await self.generate_lesson(ctx)
        
        tasks = [generate_with_semaphore(ctx) for ctx in contexts]
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        # Handle any exceptions
        processed_results = []
        for i, result in enumerate(results):
            if isinstance(result, Exception):
                # Re-raise with context about which lesson failed
                raise RuntimeError(
                    f"Failed to generate lesson {contexts[i].lesson_outline.lesson_id}: {result}"
                ) from result
            processed_results.append(result)
        
        return processed_results
    
    def get_fallback_prompt(
        self, 
        context: LessonGenerationContext, 
        **kwargs
    ) -> str:
        """Simpler prompt for retry attempts"""
        lesson = context.lesson_outline
        return f"""Create lesson content for:

Topic: {context.course_topic}
Lesson: {lesson.title}
Type: {lesson.lesson_type.value}
Duration: {lesson.duration_minutes} minutes
Objectives: {', '.join(lesson.objectives)}

Provide:
- lesson_id: "{lesson.lesson_id}"
- title: "{lesson.title}"
- lesson_type: "{lesson.lesson_type.value}"
- introduction: 2 paragraphs
- content_blocks: Array of 3-5 blocks, each with:
  - block_type: "text" or "code" or "exercise"
  - title
  - content/code/instructions as appropriate
  - order: 1, 2, 3, etc.
- summary: 1 paragraph
- key_takeaways: 3 bullet points
- next_steps: 1 sentence

Respond with JSON only."""


class ContentEnhancerAgent(BaseAgent[LessonContent]):
    """
    Specialized agent to enhance and improve existing lesson content.
    Used for quality improvements without full regeneration.
    """
    
    def __init__(self):
        super().__init__(
            name="content_creator",  # Matches ModelManager task name
            output_schema=LessonContent,
            timeout_seconds=90.0  # Model config from ModelManager
        )
    
    def get_system_prompt(self) -> str:
        return """You are an expert at enhancing and improving educational content.

Your role is to take existing lesson content and improve its quality based on feedback.

Maintain the core teaching objectives while enhancing clarity, engagement, and depth."""
    
    def build_prompt(
        self,
        current_content: Dict[str, Any],
        enhancement_feedback: str
    ) -> str:
        return f"""## Content Enhancement Task

### Current Lesson Content
```json
{current_content}
```

### Enhancement Feedback
{enhancement_feedback}

## Your Task

Enhance the lesson content to:
1. Address the specific feedback
2. Improve clarity and engagement
3. Add depth where needed
4. Ensure code examples are correct and well-explained
5. Make exercises more helpful

Return the complete enhanced lesson content as JSON."""
