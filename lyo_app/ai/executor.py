import logging
import json
from typing import Optional, Dict, Any, List
import google.generativeai as genai
from lyo_app.ai.schemas.lyo2 import LyoPlan, UnifiedChatResponse, UIBlock, ActionType, UIBlockType, ArtifactType
from lyo_app.services.rag_service import RAGService
from lyo_app.services.artifact_service import ArtifactService
from lyo_app.services.mutator import FollowUpMutator
from lyo_app.ai_agents.multi_agent_v2.agents.base_agent import BaseAgent
from lyo_app.core.config import settings
from lyo_app.chat.a2ui_integration import ChatA2UIService

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
        "gemini-2.0-flash",
        generation_config={"temperature": 0.7, "max_output_tokens": 2048},
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
        self.a2ui_service = ChatA2UIService()
        self._db = db_session
        self._gemini = _get_gemini_model()

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
            return static_content or "I'm sorry, I couldn't generate a response right now. Please try again."

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

        prompt = f"""You are Lyo, a friendly and knowledgeable AI tutor.
Answer the user's question clearly and helpfully.

CRITICAL FORMATTING RULES:
- Be CONCISE. Keep responses to 2-4 short paragraphs MAX.
- Use bullet points for lists instead of long paragraphs.
- Break complex topics into digestible chunks with clear headers.
- Never write walls of text. If a topic is broad, give a high-level overview and offer to go deeper.
- If reference material is provided, synthesize it — don't dump it verbatim.
- If conversation history is provided, maintain context. Don't repeat yourself.
{rag_text}{history_text}

USER QUESTION:
{original_request}
"""
        try:
            response = await self._gemini.generate_content_async(prompt)
            generated = response.text.strip() if response.text else None
            if generated:
                return generated
        except Exception as e:
            logger.error(f"Gemini text generation failed: {e}", exc_info=True)

        return static_content or "I'm sorry, I encountered an issue generating a response. Please try again."

    async def execute(self, user_id: str, plan: LyoPlan, original_request: str, conversation_history: list = None) -> UnifiedChatResponse:
        """
        Executes the provided plan and returns a unified response.
        conversation_history: list of {"role": ..., "content": ...} dicts for multi-turn context.
        """
        execution_context = {
            "retrieved_content": [],
            "created_artifacts": [],
            "final_text": "",
            "a2ui_blocks": [],
            "open_classroom_payload": None,
            "conversation_history": conversation_history or []
        }
        
        for step in plan.steps:
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
                
            elif step.action_type == ActionType.GENERATE_A2UI:
                # Generate rich A2UI components based on the ui_type parameter
                ui_type = step.parameters.get("ui_type", "explanation")
                a2ui_result = await self._generate_a2ui(
                    ui_type=ui_type,
                    original_request=original_request,
                    step_params=step.parameters,
                    context=execution_context
                )
                if a2ui_result:
                    if a2ui_result.get("type") == "open_classroom":
                        execution_context["open_classroom_payload"] = a2ui_result["payload"]
                    elif a2ui_result.get("component"):
                        execution_context["a2ui_blocks"].append(a2ui_result["component"])
                
            elif step.action_type == ActionType.GENERATE_TEXT:
                # Final text generation step — call Gemini with all context
                execution_context["final_text"] = await self._generate_text(
                    original_request, execution_context, step.parameters
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
        # Build A2UI blocks list
        a2ui_ui_blocks = []
        for comp in execution_context.get("a2ui_blocks", []):
            a2ui_ui_blocks.append(UIBlock(
                type=UIBlockType.A2UI_COMPONENT,
                content={"component": comp.to_dict() if hasattr(comp, 'to_dict') else comp}
            ))
            
        return UnifiedChatResponse(
            answer_block=answer_block,
            artifact_block=artifact_block,
            next_actions=[UIBlock(type=UIBlockType.CTA_ROW, content={"actions": ["Continue", "More info"]})],
            a2ui_blocks=a2ui_ui_blocks,
            open_classroom_payload=execution_context.get("open_classroom_payload"),
            metadata={"latency_ms": 100} # Mock
        )

    async def _generate_a2ui(
        self,
        ui_type: str,
        original_request: str,
        step_params: Dict[str, Any],
        context: Dict[str, Any]
    ) -> Optional[Dict[str, Any]]:
        """
        Generate A2UI components or open_classroom payloads based on ui_type.
        
        Returns dict with either:
          {"type": "open_classroom", "payload": {...}}  — for course creation
          {"component": A2UIComponent}                  — for rich UI blocks
          None on failure
        """
        try:
            if ui_type == "course":
                # Generate course data via Gemini, then build an open_classroom payload
                course_data = await self._generate_course_data(original_request, step_params, context)
                if course_data:
                    # Also generate an A2UI card for it
                    a2ui_comp = self.a2ui_service.generate_course_creation_ui(course_data)
                    return {
                        "type": "open_classroom",
                        "payload": course_data,
                        "component": a2ui_comp
                    }
                    
            elif ui_type == "quiz":
                quiz_data = step_params.get("quiz_data") or await self._generate_quiz_data(original_request, context)
                if quiz_data:
                    a2ui_comp = self.a2ui_service.generate_quiz_ui(quiz_data)
                    return {"component": a2ui_comp}
                    
            elif ui_type == "study_plan":
                plan_data = step_params.get("plan_data") or {
                    "title": step_params.get("title", original_request[:80]),
                    "milestones": [],
                    "duration": "2 weeks"
                }
                # Use explanation UI as a rich container for study plans
                topic = step_params.get("title", original_request[:80])
                content = context.get("final_text", f"Here's your study plan for {topic}")
                a2ui_comp = self.a2ui_service.generate_explanation_ui(content, f"📋 Study Plan: {topic}")
                return {"component": a2ui_comp}
                
            elif ui_type == "explanation":
                topic = step_params.get("title", original_request[:80])
                # If we already have generated text, use it; otherwise generate concise content
                content = context.get("final_text", "")
                if not content:
                    content = await self._generate_text(original_request, context, step_params)
                    context["final_text"] = content
                a2ui_comp = self.a2ui_service.generate_explanation_ui(content, topic)
                return {"component": a2ui_comp}
                
            else:
                logger.warning(f"Unknown A2UI ui_type: {ui_type}, falling back to explanation")
                topic = step_params.get("title", original_request[:80])
                content = context.get("final_text", original_request)
                a2ui_comp = self.a2ui_service.generate_explanation_ui(content, topic)
                return {"component": a2ui_comp}
                
        except Exception as e:
            logger.error(f"A2UI generation failed for ui_type={ui_type}: {e}", exc_info=True)
            return None

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
                "lessons": [
                    {"title": "Introduction", "description": f"Getting started with {topic}", "type": "reading", "duration": "15 min"},
                    {"title": "Core Concepts", "description": f"Key ideas in {topic}", "type": "reading", "duration": "20 min"},
                    {"title": "Practice", "description": "Hands-on exercises", "type": "exercise", "duration": "30 min"},
                ]
            }
        
        prompt = f"""Generate a structured course outline in JSON format for this request: "{original_request}"
Return ONLY valid JSON with this exact structure:
{{
    "title": "Course Title",
    "topic": "main topic",
    "description": "2-sentence description",
    "difficulty": "Beginner|Intermediate|Advanced",
    "estimated_duration": "X hours",
    "lessons": [
        {{"title": "Lesson Title", "description": "1-sentence description", "type": "reading|exercise|quiz", "duration": "X min"}}
    ]
}}
Include 4-6 lessons. Keep descriptions short. Return ONLY JSON, no markdown."""
        
        try:
            response = await self._gemini.generate_content_async(prompt)
            text = response.text.strip() if response.text else None
            if text:
                # Clean markdown wrapping if present
                if text.startswith("```"):
                    text = text.split("\n", 1)[1] if "\n" in text else text[3:]
                    text = text.rsplit("```", 1)[0]
                return json.loads(text)
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
            "lessons": [
                {"title": "Introduction", "description": f"Getting started with {topic}", "type": "reading", "duration": "15 min"},
                {"title": "Key Concepts", "description": f"Understanding the fundamentals", "type": "reading", "duration": "20 min"},
                {"title": "Practice Quiz", "description": "Test your knowledge", "type": "quiz", "duration": "10 min"},
            ]
        }

    async def _generate_quiz_data(self, original_request: str, context: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Generate quiz data structure from the request."""
        return {
            "title": f"Quiz: {original_request[:60]}",
            "current_question": 1,
            "total_questions": 5,
            "question": {
                "question": f"What is a key concept related to {original_request[:40]}?",
                "options": ["Option A", "Option B", "Option C", "Option D"],
                "correct_answer": 0,
                "selected_answer": None
            }
        }
