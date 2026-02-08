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

logger = logging.getLogger(__name__)


def _get_gemini_model():
    """Lazy-initialise a Gemini model for text generation."""
    api_key = getattr(settings, "google_api_key", None) or getattr(settings, "gemini_api_key", None)
    if not api_key:
        logger.warning("No Gemini API key available for executor text generation")
        return None
    genai.configure(api_key=api_key)
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
Be concise but thorough. Use examples when they aid understanding.
If reference material is provided, incorporate it into your answer.
If conversation history is provided, maintain context and continuity with previous messages.
Do NOT repeat yourself or re-introduce topics already discussed.
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
            
        return UnifiedChatResponse(
            answer_block=answer_block,
            artifact_block=artifact_block,
            next_actions=[UIBlock(type=UIBlockType.CTA_ROW, content={"actions": ["Continue", "More info"]})],
            metadata={"latency_ms": 100} # Mock
        )
