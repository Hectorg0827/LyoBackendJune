"""
Course Generator Agent (v2)
Responsible for orchestrating the creation of a strictly typed LyoCourse.
"""
import json
import logging
import asyncio
from typing import Optional, List, Dict

from lyo_app.api.v2.course_schemas import (
    LyoCourse, LyoModule, LyoLesson, LyoArtifact, 
    ArtifactType, RenderTarget, ArtifactAIMetadata,
    ConceptExplainerPayload, QuizArtifactPayload,
    FlashcardsPayload, Flashcard, QuizQuestion, QuizOption
)
from lyo_app.core.ai_resilience import ai_resilience_manager

logger = logging.getLogger(__name__)

class CourseGeneratorV2:
    # Limit concurrent AI calls to avoid rate-limiting / overload
    _hydration_semaphore = asyncio.Semaphore(3)
    
    async def generate_course(self, topic: str, target_audience: str, learning_objectives: List[str]) -> LyoCourse:
        """
        Generates a full LyoCourse object using a multi-step prompt strategy.
        1. Generate Skeleton (Modules + Lessons)
        2. Hydrate Artifacts (parallelized with bounded concurrency)
        """
        
        # Step 1: Generate Structure
        structure = await self._generate_structure(topic, target_audience, learning_objectives)
        
        # Step 2: Hydrate Lessons (parallel per module, bounded by semaphore)
        hydrated_modules = []
        for module in structure.modules:
            hydrated_lessons = await self._hydrate_module_lessons(module.lessons, topic)
                
            hydrated_modules.append(
                LyoModule(
                    module_id=module.module_id,
                    title=module.title,
                    goal=module.goal,
                    lessons=list(hydrated_lessons)
                )
            )
            
        return LyoCourse(
            course_id=f"lyo.course.{topic.replace(' ', '').lower()[:10]}",
            title=structure.title,
            target_audience=structure.target_audience,
            learning_objectives=structure.learning_objectives,
            modules=hydrated_modules,
            generation_source="ai_v2_lily"
        )

    async def _hydrate_module_lessons(self, lessons: List[LyoLesson], topic: str) -> List[LyoLesson]:
        """Hydrate all lessons in a module concurrently, bounded by semaphore."""
        async def _throttled(lesson):
            async with self._hydration_semaphore:
                return await self._hydrate_lesson(lesson, topic)
        return list(await asyncio.gather(*[_throttled(l) for l in lessons]))

    async def _generate_structure(self, topic: str, audience: str, objectives: List[str]) -> LyoCourse:
        """Generates the skeleton (Modules & Lessons) without heavy artifact content."""
        
        system_prompt = """
        You are the Course Architect for Lyo. 
        Create a structured course plan.
        Output MUST be valid JSON matching the LyoCourse schema, but with empty 'artifacts' lists.
        Focus on flow, pacing, and logical progression.
        """
        
        user_prompt = f"""
        Topic: {topic}
        Audience: {audience}
        Objectives: {json.dumps(objectives)}
        
        Return a JSON object with 'modules' and 'lessons'.
        """
        
        # Call AI (Mocking the response structure for resilience/simplicity of this example)
        # In prod, use structured output mode
        response = await ai_resilience_manager.chat_completion(
            messages=[{"role": "system", "content": system_prompt}, {"role": "user", "content": user_prompt}],
            provider_order=["gemini-3.1-pro-preview-customtools", "gpt-4o-mini"]
        )
        
        # Allow AI to do the work, but for this "executable plan" I'll enforce the schema parsing
        # For the "Spanish 101" validation step, we will likely hardcode the skeleton generation 
        # or rely on the LLM's strict adherence.
        try:
             # Heuristic clean up
            content = response.get("content", "{}")
            if "```json" in content:
                content = content.split("```json")[1].split("```")[0]
            
            data = json.loads(content)
            # Validate with Pydantic (partial)
            return LyoCourse(**data)
        except Exception as e:
            logger.error(f"Failed to generate structure: {e}. Fallback to template.")
            return self._get_fallback_structure(topic)

    async def _hydrate_lesson(self, lesson: LyoLesson, topic: str) -> LyoLesson:
        """Generates specific artifacts for a lesson based on its goal."""
        
        # Decide which artifacts to create (The "Brain" part)
        # For MVP: 1 Concept, 1 Quiz, 1 Flashcard set
        
        artifacts = []
        
        # 1. Concept Explainer
        concept = await self._generate_artifact(ArtifactType.CONCEPT_EXPLAINER, lesson.title, lesson.goal)
        artifacts.append(concept)
        
        # 2. Flashcards
        flashcards = await self._generate_artifact(ArtifactType.FLASHCARDS, lesson.title, lesson.goal)
        artifacts.append(flashcards)
        
        # 3. Quiz
        quiz = await self._generate_artifact(ArtifactType.QUIZ, lesson.title, lesson.goal)
        artifacts.append(quiz)
        
        return LyoLesson(
            lesson_id=lesson.lesson_id,
            title=lesson.title,
            goal=lesson.goal,
            duration_minutes=lesson.duration_minutes,
            artifacts=artifacts
        )

    async def _generate_artifact(self, type: ArtifactType, title: str, goal: str) -> LyoArtifact:
        """Generate a real AI-powered artifact for a lesson."""

        # Build type-specific prompt for the AI
        if type == ArtifactType.CONCEPT_EXPLAINER:
            user_prompt = f"""Generate a detailed concept explainer for the lesson "{title}".
Learning goal: {goal}

Return ONLY valid JSON with this exact structure:
{{
  "markdown": "# {title}\\n\\n(Full, detailed markdown explanation — at least 3 paragraphs covering the concept, examples, and how it connects to the broader topic. Use headers, bullet points, and bold text for emphasis.)",
  "key_takeaways": ["Takeaway 1", "Takeaway 2", "Takeaway 3"]
}}
Make the explanation thorough, engaging, and educational. Use real examples and analogies."""

        elif type == ArtifactType.QUIZ:
            user_prompt = f"""Generate a quiz for the lesson "{title}".
Learning goal: {goal}

Return ONLY valid JSON with this exact structure:
{{
  "questions": [
    {{
      "id": "q1",
      "text": "Question text here?",
      "options": [
        {{"id": "a", "text": "Option A"}},
        {{"id": "b", "text": "Option B"}},
        {{"id": "c", "text": "Option C"}},
        {{"id": "d", "text": "Option D"}}
      ],
      "correct_option_id": "b"
    }}
  ]
}}
Include 3 questions. Each question must have exactly 4 options. Questions should test real understanding, not just recall."""

        elif type == ArtifactType.FLASHCARDS:
            user_prompt = f"""Generate flashcards for the lesson "{title}".
Learning goal: {goal}

Return ONLY valid JSON with this exact structure:
{{
  "topic": "{title}",
  "cards": [
    {{"front": "Term or question", "back": "Definition or answer"}}
  ]
}}
Include 5-8 flashcards covering the key concepts. Make them useful for spaced repetition."""

        else:
            user_prompt = f"Generate content for a {type.value} artifact about '{title}'. Goal: {goal}. Return valid JSON."

        system_prompt = f"""You are a world-class educational content creator for the Lyo learning platform.
Generate a high-quality {type.value} for the lesson '{title}'.
Goal: {goal}.
Output ONLY strict valid JSON — no markdown fences, no extra text."""

        # Call the AI
        try:
            response = await ai_resilience_manager.chat_completion(
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt}
                ],
                provider_order=["gemini-2.5-flash", "gpt-4o-mini"]
            )

            raw = response.get("content", "").strip()

            # Strip markdown code fences if present
            if "```json" in raw:
                raw = raw.split("```json")[1].split("```")[0].strip()
            elif raw.startswith("```"):
                raw = raw.split("\n", 1)[1] if "\n" in raw else raw[3:]
                raw = raw.rsplit("```", 1)[0].strip()

            content = json.loads(raw)

            # Validate with Pydantic models to ensure schema compliance
            if type == ArtifactType.CONCEPT_EXPLAINER:
                validated = ConceptExplainerPayload(**content)
                content = validated.dict()
            elif type == ArtifactType.QUIZ:
                validated = QuizArtifactPayload(**content)
                content = validated.dict()
            elif type == ArtifactType.FLASHCARDS:
                validated = FlashcardsPayload(**content)
                content = validated.dict()

            logger.info(f"✅ AI-generated {type.value} artifact for '{title}'")

            return LyoArtifact(
                artifact_id=f"art_{type.value}_{title[:5]}",
                type=type,
                render_target=RenderTarget.NATIVE,
                content=content,
                ai_metadata=ArtifactAIMetadata(confidence=0.92)
            )

        except Exception as e:
            logger.warning(f"⚠️ AI artifact generation failed for {type.value}/{title}: {e} — using fallback")

        # Fallback: return minimal valid content so the course isn't broken
        content = {}
        if type == ArtifactType.CONCEPT_EXPLAINER:
            content = ConceptExplainerPayload(
                markdown=f"# {title}\n\nThis lesson covers {goal}. Content is being generated — check back shortly for the full explanation.",
                key_takeaways=[f"Understanding {title} is essential", f"The goal is: {goal}"]
            ).dict()
        elif type == ArtifactType.QUIZ:
            content = QuizArtifactPayload(
                questions=[QuizQuestion(id="q1", text=f"What is the main purpose of {title}?",
                    options=[QuizOption(id="a", text="To understand the basics"), QuizOption(id="b", text="To apply the concept"), QuizOption(id="c", text="To evaluate outcomes"), QuizOption(id="d", text="All of the above")],
                    correct_option_id="d")]
            ).dict()
        elif type == ArtifactType.FLASHCARDS:
            content = FlashcardsPayload(topic=title, cards=[Flashcard(front=title, back=goal)]).dict()

        return LyoArtifact(
            artifact_id=f"art_{type.value}_{title[:5]}",
            type=type,
            render_target=RenderTarget.NATIVE,
            content=content,
            ai_metadata=ArtifactAIMetadata(confidence=0.5)
        )

    def _get_fallback_structure(self, topic: str) -> LyoCourse:
        # Emergency fallback
        return LyoCourse(
            course_id="fallback",
            title=topic,
            target_audience="beginner",
            learning_objectives=[],
            modules=[LyoModule(module_id="m1", title="Basics", goal="Intro", lessons=[])]
        )
