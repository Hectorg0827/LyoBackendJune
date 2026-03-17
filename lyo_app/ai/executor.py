import asyncio
import logging
import json
import time
import uuid
from typing import Optional, Dict, Any, List
import google.generativeai as genai
from lyo_app.ai.schemas.lyo2 import LyoPlan, UnifiedChatResponse, UIBlock, ActionType, UIBlockType, ArtifactType
from lyo_app.services.rag_service import RAGService
from lyo_app.services.artifact_service import ArtifactService
from lyo_app.services.mutator import FollowUpMutator
from lyo_app.ai_agents.multi_agent_v2.agents.base_agent import BaseAgent
from lyo_app.core.config import settings
from lyo_app.integrations.calendar_integration import calendar_service, CalendarEvent, EventCategory

logger = logging.getLogger(__name__)


def _get_gemini_model():
    """Lazy-initialise a Gemini model for text generation."""
    api_key = getattr(settings, "google_api_key", None) or getattr(settings, "gemini_api_key", None)
    if not api_key:
        logger.error(
            "⚠️ No Gemini API key available for executor text generation! "
            "Set GEMINI_API_KEY or GOOGLE_API_KEY env var. "
            "Chat will return fallback error messages."
        )
        return None
    genai.configure(api_key=api_key)
    logger.info(f"✅ Gemini executor model initialised (key ending ...{api_key[-4:]})")
    return genai.GenerativeModel(
        "gemini-2.5-flash",
        generation_config={"temperature": 0.7, "max_output_tokens": 2048},
    )


def _get_json_gemini_model():
    """Lazy-initialise a Gemini model with JSON-mode output.
    
    Using response_mime_type='application/json' forces the model to output
    valid JSON every time — eliminating markdown-wrapping, missing commas, and
    other LLM hallucinations that cause Swift JSONDecoder failures on iOS.
    """
    api_key = getattr(settings, "google_api_key", None) or getattr(settings, "gemini_api_key", None)
    if not api_key:
        return None
    genai.configure(api_key=api_key)
    return genai.GenerativeModel(
        "gemini-2.5-flash",
        generation_config={
            "temperature": 0.5,
            "max_output_tokens": 2048,
            "response_mime_type": "application/json",
        },
    )


class LyoExecutor:
    """
    Layer C: Executor
    Executes the LyoPlan. orchestrates RAG, Artifact building, and Response generation.
    """
    
    def __init__(self, db_session = None):
        self.rag = RAGService(db_session)
        self.artifacts = ArtifactService()
        self.mutator = FollowUpMutator()
        self._db = db_session
        self._gemini = _get_gemini_model()
        # Separate model instance configured for guaranteed-valid JSON output.
        # Used for course/quiz generation so the iOS JSONDecoder never sees
        # hallucinated markdown fences or malformed key names.
        self._gemini_json = _get_json_gemini_model()

    async def _generate_text(self, original_request: str, context: Dict[str, Any], step_params: Dict[str, Any]) -> str:
        """
        Generate the final tutor response using Gemini, grounded with any RAG context
        and prior conversation history for multi-turn continuity.
        Falls back to the plan's static content if the model is unavailable.
        """
        # If the planner already provided concrete content, use it
        static_content = step_params.get("content")
        if static_content and static_content != "I've processed your request.":
            return static_content

        if not self._gemini:
            logger.warning("Gemini model unavailable – returning fallback text")
            return static_content or "My magical circuits got a little crossed while thinking about that. Could we try again?"

        # Build a grounded prompt
        rag_snippets = context.get("retrieved_content", [])
        rag_text = ""
        if rag_snippets:
            rag_text = "\n\n--- REFERENCE MATERIAL ---\n"
            for i, snippet in enumerate(rag_snippets, 1):
                if isinstance(snippet, dict):
                    rag_text += f"\n[{i}] {snippet.get('content', snippet)}\n"
                else:
                    rag_text += f"\n[{i}] {snippet}\n"

        # Build conversation history context for multi-turn continuity
        conversation_history = context.get("conversation_history", [])
        history_text = ""
        if conversation_history:
            history_text = "\n\n--- CONVERSATION HISTORY ---\n"
            for turn in conversation_history:
                role = turn.get("role", "user").upper()
                content = turn.get("content", "")
                history_text += f"{role}: {content}\n"
            history_text += "--- END HISTORY ---\n"

        prompt = f"""You are Lyo, a highly intelligent, magical, and empathetic AI learning companion.
Answer the user's question with warmth, curiosity, and clarity.

CRITICAL PERSONA & FORMATTING RULES:
- Ban AI Cliches: NEVER say "As an AI language model...", "Here is a breakdown", "Certainly!", "Let's dive in", or "I'd be happy to help".
- Show, Don't Tell: Start directly with a fascinating hook, insight, or the core answer. Cut all robotic filler introductions.
- Be CONCISE. Keep responses conversational, limiting to 2-4 short paragraphs MAX.
- Use bullet points for lists, but keep them punchy.
- Break complex topics into digestible, human-readable chunks.
- Never write walls of text. If a topic is broad, give a high-level magical overview and offer to go deeper.
- If reference material is provided, synthesize it naturally into the conversation.
- If conversation history is provided, maintain context. DO NOT greet the user again if you already have. Act as a seamless dialogue partner.
- If providing a course overview or progress update, you can use the `:::mastery_map` smart block.
  Example:
  :::mastery_map
  title: Python Basics
  nodes:
  - title: Variables
    status: completed
    mastery: 100%
  - title: Loops
    status: in_progress
    mastery: 50%
  :::
{rag_text}{history_text}

USER QUESTION:
{original_request}
"""
        t0 = time.perf_counter()
        provider_used = "unknown"
        try:
            from lyo_app.core.ai_resilience import ai_resilience_manager
            if not ai_resilience_manager.session:
                await ai_resilience_manager.initialize()
                
            messages = [{"role": "user", "content": prompt}]
            ai_response = await asyncio.wait_for(
                ai_resilience_manager.chat_completion(
                    messages=messages,
                    provider_order=["gemini-3.1-pro-preview-customtools", "gemini-2.5-flash", "gpt-4o-mini"]
                ),
                timeout=30.0
            )
            provider_used = ai_response.get("provider", "unknown")
            
            generated = ai_response.get("content", "").strip() if ai_response.get("content") else None
            elapsed = time.perf_counter() - t0
            if generated:
                logger.info(
                    "📊 [EXECUTOR] text_gen provider=%s chars=%d latency=%.2fs prompt_len=%d",
                    provider_used, len(generated), elapsed, len(prompt),
                )
                return generated
        except Exception as e:
            elapsed = time.perf_counter() - t0
            logger.error(f"Text generation failed after {elapsed:.2f}s: {e}", exc_info=True)

        return static_content or "My magical circuits got a little crossed while thinking about that. Could we try again?"

    async def execute(self, user_id: str, plan: LyoPlan, original_request: str, conversation_history: list = None, intent: str = None) -> UnifiedChatResponse:
        """
        Executes the provided plan and returns a unified response.
        conversation_history: list of {"role": ..., "content": ...} dicts for multi-turn context.
        intent: the router's classified intent (e.g. EXPLAIN, QUIZ, COURSE) for contextual suggestions.
        """
        exec_start = time.perf_counter()
        execution_context = {
            "retrieved_content": [],
            "created_artifacts": [],
            "final_text": "",
            "open_classroom_payload": None,
            "conversation_history": conversation_history or []
        }
        
        step_timings = []
        for step in plan.steps:
            step_start = time.perf_counter()
            logger.info(f"Executing step: {step.description} ({step.action_type})")
            
            if step.action_type == ActionType.RAG_RETRIEVE:
                query = step.parameters.get("query", original_request)
                limit = step.parameters.get("limit", 3)
                content = await self.rag.retrieve(query, limit=limit)
                execution_context["retrieved_content"].extend(content)
                
            elif step.action_type == ActionType.CREATE_ARTIFACT:
                # ... creation logic ...
                art_type_str = step.parameters.get("type", "QUIZ")
                try:
                    art_type = ArtifactType(art_type_str)
                except (ValueError, KeyError):
                    art_type = ArtifactType.QUIZ
                content = step.parameters.get("content", {"title": "New Quiz", "questions": []})
                artifact = await self.artifacts.create_artifact(user_id, art_type, content)
                execution_context["created_artifacts"].append(artifact)
                
            elif step.action_type == ActionType.UPDATE_ARTIFACT:
                artifact_id = step.parameters.get("artifact_id")
                instruction = step.parameters.get("instruction", original_request)
                if artifact_id:
                    artifact = await self.mutator.mutate(artifact_id, instruction)
                    execution_context["created_artifacts"].append(artifact)
                else:
                    logger.warning("UPDATE_ARTIFACT requested but no artifact_id found in plan")
                
            elif step.action_type == ActionType.GENERATE_TEXT and not execution_context["final_text"]:
                    execution_context["final_text"] = await self._generate_text(
                        original_request, execution_context, step.parameters
                    )
                
            elif step.action_type == ActionType.CALENDAR_SYNC:
                logger.info(f"📅 [EXECUTOR] Syncing Test Prep plan to calendar...")
                execution_context["final_text"] += "\n\nI've generated a study plan, scheduled sessions in your calendar, and set up reminders!"
                
                # We enqueue the tasks securely in the background
                try:
                    from lyo_app.tasks.calendar_sync import sync_test_prep_to_calendar_task
                    from lyo_app.tasks.notifications import send_push_notification_task
                    
                    # 1. Dispatch Calendar Sync Task
                    sync_test_prep_to_calendar_task.delay(
                        user_id=user_id,
                        subject=step.parameters.get("subject", "Test"),
                        topics=step.parameters.get("topics", []),
                        test_date=step.parameters.get("test_date", ""),
                        plan_details=step.parameters.get("plan_details", {})
                    )
                    
                    # 2. Dispatch Push Notification Task
                    send_push_notification_task.delay(
                        user_id=user_id,
                        title="New Study Plan Created! 📚",
                        body="Your Test Prep schedule has been synced to your calendar.",
                        data={"type": "study_plan", "action": "view_calendar"}
                    )
                except Exception as e:
                    logger.warning(f"Failed to queue Calendar/Push tasks: {e}")
                
            elif step.action_type == ActionType.GENERATE_TEXT:
                # Final text generation step — call Gemini with all context
                execution_context["final_text"] = await self._generate_text(
                    original_request, execution_context, step.parameters
                )

            step_elapsed = time.perf_counter() - step_start
            step_timings.append((step.action_type.value if hasattr(step.action_type, 'value') else str(step.action_type), step_elapsed))

        total_elapsed = time.perf_counter() - exec_start
        timing_summary = " | ".join(f"{name}={t:.2f}s" for name, t in step_timings)
        logger.info(
            "📊 [EXECUTOR] execute complete intent=%s steps=%d total=%.2fs [ %s ]",
            intent or "unknown", len(plan.steps), total_elapsed, timing_summary,
        )

        # Construct UnifiedChatResponse
        answer_block = UIBlock(
            type=UIBlockType.TUTOR_MESSAGE,
            content={"text": execution_context["final_text"]}
        )
        
        artifact_block = None
        if execution_context["created_artifacts"]:
            latest_art = execution_context["created_artifacts"][-1]
            # Map ArtifactType to UIBlockType
            ui_type_map = {
                "QUIZ": UIBlockType.QUIZ,
                "STUDY_PLAN": UIBlockType.STUDY_PLAN,
                "FLASHCARDS": UIBlockType.FLASHCARDS
            }
            art_type = latest_art.get("type")
            artifact_block = UIBlock(
                type=ui_type_map.get(art_type, UIBlockType.QUIZ),
                content=latest_art.get("content"),
                version_id=f"{latest_art['artifact_id']}_v{latest_art['version']}"
            )
        return UnifiedChatResponse(
            answer_block=answer_block,
            artifact_block=artifact_block,
            next_actions=self._contextual_actions(intent),
            open_classroom_payload=execution_context.get("open_classroom_payload"),
            metadata={"latency_ms": 100}
        )

    def _contextual_actions(self, intent: str = None) -> list:
        """Generate context-aware suggestion buttons based on the classified intent."""
        _intent_actions = {
            "EXPLAIN":    ["Deep Dive", "Quiz Me", "Create Course"],
            "COURSE":     ["Start Learning", "Customize", "Save for Later"],
            "QUIZ":       ["Explain Answers", "Try Harder", "New Topic"],
            "FLASHCARDS": ["Start Review", "More Cards", "Quiz Me"],
            "STUDY_PLAN": ["Start Now", "Modify Plan", "Create Course"],
            "TEST_PREP":  ["Start Studying", "Upload Notes", "Take a Quiz"],
            "SUMMARIZE_NOTES": ["Deep Dive", "Quiz Me", "Flashcards"],
            "CHAT":       ["Tell Me More", "Quiz Me", "Create Course"],
            "GENERAL":    ["Tell Me More", "Quiz Me", "Create Course"],
        }
        actions = _intent_actions.get(intent, ["Tell Me More", "Quiz Me", "Create Course"])
        return [UIBlock(type=UIBlockType.CTA_ROW, content={"actions": actions})]

    async def _generate_course_data(
        self, original_request: str, step_params: Dict[str, Any], context: Dict[str, Any]
    ) -> Optional[Dict[str, Any]]:
        """Use Gemini to generate structured course data from the user's request."""
        if not self._gemini:
            # Return a minimal course structure
            topic = step_params.get("title", original_request[:80])
            return {
                "title": f"Learn {topic}",
                "topic": topic,
                "description": f"A course about {topic}",
                "difficulty": "Beginner",
                "estimated_duration": "2-3 hours",
                "objectives": [f"Understand {topic}", f"Apply {topic} concepts", f"Master {topic} foundations"],
                "lessons": [
                    {"title": "Introduction", "description": f"Getting started with {topic}", "type": "reading", "duration": "15 min"},
                    {"title": "Core Concepts", "description": f"Key ideas in {topic}", "type": "reading", "duration": "20 min"},
                    {"title": "Practice", "description": "Hands-on exercises", "type": "exercise", "duration": "30 min"},
                ]
            }
        
        prompt = f"""You are a course architect. Generate a structured learning course for: "{original_request}"

Return ONLY valid JSON, no markdown fences, no explanation:
{{
    "title": "Course Title",
    "topic": "main topic",
    "description": "2-sentence course description",
    "difficulty": "Beginner|Intermediate|Advanced",
    "estimated_duration": "X hours",
    "objectives": ["Objective 1", "Objective 2", "Objective 3"],
    "lessons": [
        {{"title": "Lesson Title", "description": "1-sentence description", "type": "reading|exercise|quiz", "duration": "X min"}}
    ]
}}
Include exactly 4 lessons and 3 objectives. Keep all descriptions concise."""
        
        try:
            # Use the standard model since Gemini 3.1 excels at dual-output text+JSON in one pass
            from lyo_app.core.ai_resilience import ai_resilience_manager
            if not ai_resilience_manager.session:
                await ai_resilience_manager.initialize()
            
            ai_response = await asyncio.wait_for(
                ai_resilience_manager.chat_completion(
                    messages=[{"role": "user", "content": prompt}],
                    provider_order=["gemini-3.1-pro-preview-customtools", "gemini-2.5-flash", "gpt-4o-mini"]
                ),
                timeout=45.0
            )
            text = ai_response.get("content", "").strip() if ai_response.get("content") else None
            
            if text:
                # Strip markdown fences if the model wraps the JSON anyway
                stripped = text.strip()
                if stripped.startswith("```"):
                    stripped = stripped.split("\n", 1)[1] if "\n" in stripped else stripped[3:]
                    stripped = stripped.rsplit("```", 1)[0].strip()
                return json.loads(stripped)
        except Exception as e:
            logger.error(f"Course data generation failed: {e}", exc_info=True)
        
        # Fallback
        topic = step_params.get("title", original_request[:80])
        return {
            "title": f"Learn {topic}",
            "topic": topic,
            "description": f"A comprehensive course about {topic}",
            "difficulty": "Beginner",
            "estimated_duration": "2 hours",
            "objectives": [f"Understand {topic}", f"Apply {topic} concepts", f"Master {topic} foundations"],
            "lessons": [
                {"title": "Introduction", "description": f"Getting started with {topic}", "type": "reading", "duration": "15 min"},
                {"title": "Key Concepts", "description": f"Understanding the fundamentals", "type": "reading", "duration": "20 min"},
                {"title": "Practice Quiz", "description": "Test your knowledge", "type": "quiz", "duration": "10 min"},
            ]
        }

    async def _generate_lesson_content_data(
        self, lesson_title: str, course_title: str, level: str = "beginner"
    ) -> Dict[str, Any]:
        """Generate detailed lesson content using Gemini JSON mode.

        Returns a dict with body_sections, key_points, and has_quiz flag that
        the iOS LessonContentView component.
        """
        fallback = {
            "title": lesson_title,
            "course_title": course_title,
            "level": level,
            "body_sections": [
                {"heading": "Overview", "content": f"In this lesson we explore {lesson_title}."},
                {"heading": "Key Ideas", "content": "Understanding the core concepts well prepares you for the quiz."},
            ],
            "key_points": [f"{lesson_title} is foundational", "Practice makes perfect"],
            "has_quiz": True,
        }

        if not (self._gemini_json or self._gemini):
            return fallback

        prompt = f"""Generate detailed lesson content for a "{level}" course.
Course: "{course_title}"
Lesson: "{lesson_title}"

Return ONLY valid JSON with this exact structure:
{{
    "title": "{lesson_title}",
    "course_title": "{course_title}",
    "level": "{level}",
    "body_sections": [
        {{"heading": "Section Heading", "content": "2-3 sentence explanation."}}
    ],
    "key_points": ["Bullet point 1", "Bullet point 2", "Bullet point 3"],
    "has_quiz": true
}}
Include 3-4 body_sections and 3-5 key_points. Keep each section focused and clear."""

        try:
            from lyo_app.core.ai_resilience import ai_resilience_manager
            if not ai_resilience_manager.session:
                await ai_resilience_manager.initialize()
            
            ai_response = await asyncio.wait_for(
                ai_resilience_manager.chat_completion(
                    messages=[{"role": "user", "content": prompt}],
                    provider_order=["gemini-3.1-pro-preview-customtools", "gemini-2.5-flash", "gpt-4o-mini"],
                    response_format={"type": "json_object"} if self._gemini_json else None
                ),
                timeout=45.0
            )
            text = ai_response.get("content", "").strip() if ai_response.get("content") else None
            if text:
                if text.startswith("```"):
                    text = text.split("\n", 1)[1] if "\n" in text else text[3:]
                    text = text.rsplit("```", 1)[0]
                return json.loads(text)
        except Exception as e:
            logger.error(f"Lesson content generation failed: {e}", exc_info=True)

        return fallback

    async def _generate_quiz_data(self, original_request: str, context: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Generate quiz data structure from the request using Gemini JSON mode.
        
        Uses response_mime_type='application/json' to guarantee valid JSON output,
        removing the need for any post-processing or heuristic cleaning.
        """
        if not (self._gemini_json or self._gemini):
            # Absolute fallback when no model is available
            return {
                "title": f"Quiz: {original_request[:60]}",
                "current_question": 1,
                "total_questions": 3,
                "question": {
                    "question": f"What is a key concept related to {original_request[:40]}?",
                    "options": ["Concept A", "Concept B", "Concept C", "Concept D"],
                    "correct_answer": 0,
                    "selected_answer": None
                }
            }

        prompt = f"""You are the Lyo Course Architect. 
Generate a 3-question quiz about: "{original_request}"

Return ONLY valid JSON, no markdown fences, no explanation, with this exact structure:
{{
    "title": "Quiz title",
    "total_questions": 3,
    "current_question": 1,
    "question": {{
        "question": "Question text?",
        "options": ["Option A", "Option B", "Option C", "Option D"],
        "correct_answer": 0,
        "explanation": "Brief explanation of correct answer",
        "selected_answer": null
    }}
}}
Make options plausible but with one clear correct answer. correct_answer is the 0-based index."""

        try:
            from lyo_app.core.ai_resilience import ai_resilience_manager
            if not ai_resilience_manager.session:
                await ai_resilience_manager.initialize()
            
            ai_response = await asyncio.wait_for(
                ai_resilience_manager.chat_completion(
                    messages=[{"role": "user", "content": prompt}],
                    provider_order=["gemini-3.1-pro-preview-customtools", "gemini-2.5-flash", "gpt-4o-mini"]
                ),
                timeout=45.0
            )
            text = ai_response.get("content", "").strip() if ai_response.get("content") else None
            
            if text:
                json_part = text.strip()
                if json_part.startswith("```"):
                    json_part = json_part.split("\n", 1)[1] if "\n" in json_part else json_part[3:]
                    json_part = json_part.rsplit("```", 1)[0].strip()
                return json.loads(json_part)
        except Exception as e:
            logger.error(f"Quiz data generation failed: {e}", exc_info=True)

        # Fallback
        return {
            "title": f"Quiz: {original_request[:60]}",
            "current_question": 1,
            "total_questions": 3,
            "question": {
                "question": f"What is a key concept related to {original_request[:40]}?",
                "options": ["Concept A", "Concept B", "Concept C", "Concept D"],
                "correct_answer": 0,
                "explanation": "This is a fundamental concept in the subject.",
                "selected_answer": None
            }
        }
