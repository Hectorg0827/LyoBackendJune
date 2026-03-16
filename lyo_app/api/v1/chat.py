"""
Chat API endpoint for iOS app
Handles conversational AI interactions with user profile personalization
"""

import logging
import time
import asyncio
import re
from typing import List, Dict, Any, Optional
from pydantic import BaseModel, Field
from fastapi import APIRouter, HTTPException, status, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from lyo_app.core.ai_resilience import ai_resilience_manager
from lyo_app.core.config import settings
from lyo_app.auth.dependencies import get_current_user, get_db
from lyo_app.auth.models import User
from lyo_app.personalization.service import PersonalizationEngine
from lyo_app.ai_agents.a2a.schemas import Artifact, ArtifactType, A2ACourseRequest
from lyo_app.ai_agents.a2a.orchestrator import A2AOrchestrator

logger = logging.getLogger(__name__)

router = APIRouter()


# ============================================================
# AI CLASSROOM INTEGRATION HELPERS
# ============================================================

def detect_ai_classroom_intent(message: str) -> str:
    """Detect AI Classroom specific intents"""
    message_lower = message.lower()

    if any(phrase in message_lower for phrase in ["teach me", "learn about", "course on", "create course"]):
        return "course_creation"
    elif any(phrase in message_lower for phrase in ["continue lesson", "continue my lesson", "resume course", "my progress"]):
        return "continue_learning"
    elif any(phrase in message_lower for phrase in ["show courses", "available courses", "explore courses"]):
        return "course_discovery"
    elif any(phrase in message_lower for phrase in ["complete", "finished", "done with"]):
        return "course_completion"
    else:
        return "general_learning"

async def generate_ai_classroom_course(message: str, user) -> Optional[Dict[str, Any]]:
    """Generate course using real AI pipeline and return structured course data"""
    try:
        # Extract topic from message
        topic = extract_learning_topic(message)
        if not topic:
            return None

        logger.info(f"🚀 Generating real AI course for topic: {topic}")

        # Use the AI resilience manager to generate a structured course outline
        prompt = f"""You are the Lyo Course Architect. Generate a structured course outline.

Topic: {topic}
Return ONLY valid JSON with this exact structure:
{{
    "id": "course_<unique_number>",
    "title": "Course Title",
    "description": "2-3 sentence description of the course",
    "subject": "{topic}",
    "grade_band": "Beginner|Intermediate|Advanced",
    "estimated_minutes": <number>,
    "total_nodes": <number between 8 and 20>,
    "thumbnail_url": null,
    "learning_objectives": [
        "Objective 1",
        "Objective 2",
        "Objective 3"
    ],
    "lessons": [
        {{"title": "Lesson Title", "description": "What this lesson covers", "duration_minutes": <number>}}
    ]
}}
Include 4-8 lessons. Make the course comprehensive and engaging."""

        response = await ai_resilience_manager.chat_completion(
            messages=[
                {"role": "system", "content": "You are a world-class course designer. Output ONLY valid JSON."},
                {"role": "user", "content": prompt}
            ],
            provider_order=["gemini-2.5-flash", "gpt-4o-mini"]
        )

        raw = response.get("content", "").strip()

        # Strip markdown code fences
        if "```json" in raw:
            raw = raw.split("```json")[1].split("```")[0].strip()
        elif raw.startswith("```"):
            raw = raw.split("\n", 1)[1] if "\n" in raw else raw[3:]
            raw = raw.rsplit("```", 1)[0].strip()

        import json
        course_data = json.loads(raw)
        logger.info(f"✅ AI generated course: {course_data.get('title', topic)}")
        return course_data

    except Exception as e:
        logger.error(f"AI course generation failed: {e} — using fallback")
        # Minimal fallback so the flow doesn't break
        topic = extract_learning_topic(message) or message[:60]
        return {
            'id': f"course_{hash(topic) % 10000}",
            'title': f"Learn {topic.title()}",
            'description': f"A comprehensive course covering all aspects of {topic}",
            'subject': topic,
            'grade_band': 'Intermediate',
            'estimated_minutes': 90,
            'total_nodes': 12,
            'thumbnail_url': None
        }

def extract_learning_topic(message: str) -> Optional[str]:
    """Extract learning topic from user message"""
    import re

    patterns = [
        r"teach me (?:about )?(.+?)(?:\s+please|\s+pls|\s+today|\s+now|$)",
        r"learn (?:about )?(.+?)(?:\s+please|\s+pls|\s+today|\s+now|$)",
        r"course on (.+?)(?:\s+please|\s+pls|\s+today|\s+now|$)",
        r"study (.+?)(?:\s+please|\s+pls|\s+today|\s+now|$)"
    ]

    for pattern in patterns:
        match = re.search(pattern, message.lower())
        if match:
            topic = match.group(1).strip()
            # Clean up common trailing words
            topic = re.sub(r'\s+(please|pls|today|now)$', '', topic)
            return topic

    return None

async def get_user_learning_progress(user_id: str, course_id: str = None) -> Dict[str, Any]:
    """Get user's learning progress from the database."""
    try:
        from lyo_app.core.database import AsyncSessionLocal
        from lyo_app.ai_classroom.models import GraphCourse, LearningNode
        from sqlalchemy import select, func

        async with AsyncSessionLocal() as db:
            # Find the user's most recent active course
            query = select(GraphCourse).where(
                GraphCourse.created_by == user_id
            ).order_by(GraphCourse.updated_at.desc()).limit(1)

            if course_id:
                query = select(GraphCourse).where(GraphCourse.id == course_id)

            result = await db.execute(query)
            course = result.scalar_one_or_none()

            if not course:
                return {
                    'course_title': 'No active course',
                    'current_node': 0,
                    'total_nodes': 0,
                    'current_node_title': '',
                    'next_node_title': '',
                    'motivation_message': "Start a new course to begin learning!"
                }

            # Count total nodes
            total_result = await db.execute(
                select(func.count(LearningNode.id)).where(
                    LearningNode.course_id == course.id
                )
            )
            total_nodes = int(total_result.scalar() or 0)

            # Get ordered nodes for position info
            nodes_result = await db.execute(
                select(LearningNode).where(
                    LearningNode.course_id == course.id
                ).order_by(LearningNode.sequence_order)
            )
            nodes = nodes_result.scalars().all()

            current_node = max(1, course.version)  # Approximate progress indicator
            current_title = nodes[min(current_node - 1, len(nodes) - 1)].content.get("narration", "")[:60] if nodes else ""
            next_title = nodes[min(current_node, len(nodes) - 1)].content.get("narration", "")[:60] if nodes and current_node < len(nodes) else "Course complete!"

            remaining = max(0, total_nodes - current_node)
            motivation = f"You're doing great! {'Only ' + str(remaining) + ' more lessons to go.' if remaining > 0 else 'Almost there!'}"

            return {
                'course_title': course.title,
                'current_node': current_node,
                'total_nodes': total_nodes,
                'current_node_title': current_title,
                'next_node_title': next_title,
                'motivation_message': motivation
            }

    except Exception as e:
        logger.warning(f"Failed to fetch real progress for user {user_id}: {e}")
        return {
            'course_title': 'Loading...',
            'current_node': 0,
            'total_nodes': 0,
            'current_node_title': '',
            'next_node_title': '',
            'motivation_message': "Keep learning — you're doing great!"
        }


# ============================================================
# INTENT DETECTION
# ============================================================

def detect_course_creation_intent(message: str) -> Optional[Dict[str, str]]:
    """
    Detects if the user is requesting course creation.
    Returns topic if detected, None otherwise.
    """
    message_lower = message.lower()
    
    # Patterns that indicate course creation
    course_patterns = [
        r"create (?:a )?course (?:on|about|for) (.+)",
        r"make (?:a )?course (?:on|about|for) (.+)",
        r"build (?:a )?course (?:on|about|for) (.+)",
        r"generate (?:a )?course (?:on|about|for) (.+)",
        r"design (?:a )?course (?:on|about|for) (.+)",
        r"(?:i want to learn|learn) (?:about )?(.+?)(?:,.*course|.*make.*course)",
        r"(?:teach me|course on|study) (.+)",
        r"can you (?:make|create|build) (?:a )?course.*?(?:on|about|for) (.+)",
    ]
    
    for pattern in course_patterns:
        match = re.search(pattern, message_lower)
        if match:
            topic = match.group(1).strip()
            return {"topic": topic, "intent": "course_creation"}
    
    return None


# ============================================================
# TRANSLATION LAYER (A2A -> Frontend UI)
# ============================================================

def translate_artifact_to_ui_component(artifact: Artifact) -> Optional[Dict[str, Any]]:
    """
    Translates internal A2A Artifacts into Frontend UI Components.
    This acts as the Envelope / Adapter layer.
    
    Returns a dictionary matching iOS ContentType structure:
    {
        "type": "course_roadmap" | "quiz" | "visual_gallery" | ...,
        "course_roadmap": {...},  // For courseRoadmap type
        "quiz": {...},           // For quiz type
        "title": "...",          // For topic_selection type
        "topics": [...]          // For topic_selection type
    }
    """
    # Helper to get generic content regardless of storage field
    # (data dict, text string, or url string)
    def get_content():
        return artifact.data or artifact.text or artifact.url

    # 1. VISUAL_PROMPT -> visual_gallery (not yet supported in iOS, skip for now)
    if artifact.type == ArtifactType.VISUAL_PROMPT:
        # iOS doesn't have visual_gallery yet, so skip
        return None
    
    # 2. ASSESSMENT -> quiz
    elif artifact.type == ArtifactType.ASSESSMENT:
        # Assessments are structured data
        quiz_data = artifact.data or {}
        questions = quiz_data.get("questions", []) if isinstance(quiz_data, dict) else []
        
        return {
            "type": "quiz",
            "quiz": {
                "title": artifact.name or "Quick Check",
                "questions": [
                    {
                        "question": q.get("question", ""),
                        "options": q.get("options", []),
                        "correct_answer": q.get("correct_answer", "")
                    }
                    for q in questions
                ]
            }
        }

    # 3. CURRICULUM_STRUCTURE -> course_roadmap
    elif artifact.type == ArtifactType.CURRICULUM_STRUCTURE:
        # Curriculum is structured data
        course_data = artifact.data or {}
        if not isinstance(course_data, dict):
            return None
            
        modules = course_data.get("modules", [])
        title = artifact.name or course_data.get("title", "Course Roadmap")
        topic = course_data.get("topic", "Learning Path")
        level = course_data.get("level", "beginner")
        
        # Convert modules to iOS format
        formatted_modules = []
        for mod in modules:
            lessons = mod.get("lessons", [])
            formatted_lessons = [
                {
                    "title": les.get("title", "Lesson"),
                    "duration": les.get("duration", "10 min")
                }
                for les in lessons
            ]
            
            formatted_modules.append({
                "title": mod.get("title", "Module"),
                "description": mod.get("description", ""),
                "lessons": formatted_lessons
            })
        
        return {
            "type": "course_roadmap",
            "course_roadmap": {
                "title": title,
                "topic": topic,
                "level": level,
                "modules": formatted_modules
            }
        }

    # 4. Fallback for other types
    return None


# Request/Response Models
class ConversationMessage(BaseModel):
    """Single message in conversation history"""
    role: str = Field(..., description="Message role: 'user' or 'assistant'")
    content: str = Field(..., description="Message content")


class ChatRequest(BaseModel):
    """Chat request from iOS app"""
    message: str = Field(..., min_length=1, max_length=5000)
    conversation_history: Optional[List[ConversationMessage]] = Field(default=[], description="Previous conversation messages")
    context: Optional[str] = Field(None, description="Context or system instruction override")
    include_chips: Optional[int] = Field(default=0, description="Whether to include suggestion chips")
    include_ctas: Optional[int] = Field(default=0, description="Whether to include CTAs")


class ChatResponse(BaseModel):
    """Chat response to iOS app"""
    model_config = {"protected_namespaces": ()}
    
    response: str = Field(..., description="AI generated response")
    conversation_id: Optional[str] = Field(None, description="Conversation ID for tracking")
    conversation_history: Optional[List[ConversationMessage]] = Field(None, description="Updated conversation history")
    model_used: str = Field(default="Google Gemini 2.0 Flash", description="Model used for generation")
    success: bool = Field(default=True, description="Whether request succeeded")
    error: Optional[str] = Field(None, description="Error message if failed")
    user_profile: Optional[Dict[str, Any]] = Field(None, description="User learning profile summary")
    ui_component: Optional[Dict[str, Any]] = Field(None, description="UI component dict for frontend rendering")
    
@router.post("/", response_model=ChatResponse)
async def chat(
    request: ChatRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """
    Primary chat endpoint for iOS app.
    Provides Lyo's conversational AI with personalization.
    """
    start_time = time.time()
    try:
        # Get personalization context
        personalization = PersonalizationEngine()
        
        # Build profile context for AI prompts (Layer 1 & 2 personalization)
        profile_context = await personalization.build_prompt_context(db, str(current_user.id))
        
        # Get profile summary for client response
        user_profile = await personalization.get_mastery_profile(db, str(current_user.id))
        user_profile_summary = user_profile.model_dump() if user_profile else {}
        
        # ============================================================
        # STEP 1: Detect Course Creation Intent
        # ============================================================
        course_intent = detect_course_creation_intent(request.message)
        
        if course_intent:
            logger.info(f"🎓 Course creation detected: {course_intent['topic']}")
            
            # Use A2A Orchestrator for course generation
            try:
                orchestrator = A2AOrchestrator()
                course_request = A2ACourseRequest(
                    topic=course_intent['topic'],
                    user_id=str(current_user.id),
                    level="beginner",  # Could be detected from message or profile
                    duration_minutes=30
                )
                
                # Generate course (non-streaming for now, with safety timeout)
                a2a_response = await asyncio.wait_for(
                    orchestrator.generate_course(course_request),
                    timeout=120.0
                )
                
                # Extract artifacts
                artifacts = a2a_response.output_artifacts
                
                # Build course data from artifacts
                course_data = {
                    "title": f"Learn {course_intent['topic'].title()}",
                    "description": f"A comprehensive course on {course_intent['topic']}",
                    "lessons": []
                }

                # Extract lessons from artifacts
                for artifact in artifacts:
                    if artifact.type == ArtifactType.CURRICULUM_STRUCTURE and artifact.data:
                        modules = artifact.data.get("modules", [])
                        for module in modules:
                            for lesson in module.get("lessons", []):
                                course_data["lessons"].append({
                                    "title": lesson.get("title", "Lesson"),
                                    "type": "reading",
                                    "duration": f"{lesson.get('duration_minutes', 15)} min"
                                })

                # Build course UI component from artifacts
                ui_component_json = None
                for artifact in artifacts:
                    ui_component_json = translate_artifact_to_ui_component(artifact)
                    if ui_component_json:
                        break

                # Build response text
                response_text = f"🎓 **Course Created: {course_intent['topic'].title()}**\n\nI've designed a comprehensive learning experience for you! The course includes {len(course_data['lessons'])} lessons covering all the essential concepts.\n\n✨ *Tap below to explore your personalized course*"

                latency_ms = int((time.time() - start_time) * 1000)
                logger.info(f"A2A Course generated in {latency_ms}ms")

                return ChatResponse(
                    response=response_text,
                    model_used="A2A Multi-Agent Pipeline",
                    success=True,
                    error=None,
                    user_profile=user_profile_summary,
                    ui_component=[{"type": "ui_block", "component": ui_component_json}] if ui_component_json else None
                )
                
            except Exception as e:
                logger.error(f"A2A course generation failed: {e}", exc_info=True)
                # Fall through to regular chat completion
                pass
        
        # ============================================================
        # STEP 2: Regular Chat Completion (Non-course requests)
        # ============================================================
        
        # Build message history for Gemini
        messages = []
        if request.conversation_history:
            for msg in request.conversation_history:
                # Map 'assistant' to 'model' for Gemini if needed, but ai_resilience handles mapping
                messages.append({"role": msg.role, "content": msg.content})
        
        # Add current message
        messages.append({"role": "user", "content": request.message})

        # Add system message for Lyo personality with optional profile context
        # Incorporate client-provided context if available
        client_context = request.context if request.context else ""
        
        system_content = f"""You are Lyo, a friendly and engaging AI learning assistant.
Be conversational, helpful, and educational. Use emojis sparingly for warmth.
Format responses with markdown for readability. Keep responses concise but informative.

### SMART BLOCKS CAPABILITIES
When appropriate, use the following interactive blocks to enhance learning.
ALWAYS use the `:::block_type` syntax. Do NOT use these blocks inside code fences.

1. QUIZ (Check understanding)
:::quiz
question: [The question]
options: [Option A], [Option B], [Option C], [Option D]
answer: [The exact text of the correct option]
explanation: [Brief explanation of why it's correct]
:::

2. FLASHCARD (Define terms or concepts)
:::flashcard
front: [Term or question]
back: [Definition or answer]
:::

3. FLASHCARD SET (Multiple flashcards)
:::flashcard_set
title: [Set Title]
cards:
- front: [Term 1]
  back: [Def 1]
- front: [Term 2]
  back: [Def 2]
:::

4. PROGRESS (Show lesson progress)
:::progress
completed: [Number]
total: [Number]
label: [Context label, e.g., 'Chapter 1 Progress']
:::

5. SUMMARY (Key takeaways)
:::summary
title: [Title]
points: [Point 1], [Point 2], [Point 3]
:::

6. IMAGE (Visualize concepts)
:::image
query: [Search query for the image]
caption: [Description of what the image shows]
:::

7. CINEMATIC HOOK (Narrative Intro & Hype)
:::cinematic_hook
title: [Title]
hook: [A compelling one-sentence narrative hook]
visual_description: [Cinematic visual description]
cta: [Call to Action, e.g., 'EXPLORE NOW']
:::

8. TEST PREP (Exam Setup & Information Collection)
:::test_prep
topic: [Exam Topic]
courses: ["Course A", "Course B"]
date: [ISO8601 Date or null]
description: [Short description of the exam]
:::

9. STUDY PLAN (Structured Reminders & Sessions)
:::study_plan
title: Study Plan for [Topic]
exam_date: [ISO8601 Date]
sessions:
- title: [Session Title]
  desc: [Description]
  duration: [Minutes]
  date: [ISO8601 Date]
:::

When a user asks to create a course, briefly confirm the topic and ask about their preferred level (beginner/intermediate/advanced) if you don't know it yet.

{profile_context}

{client_context}"""

        system_message = {
            "role": "system",
            "content": system_content
        }
        messages.insert(0, system_message)
        
        # Generate response using resilient manager
        result = await ai_resilience_manager.chat_completion(
            messages=messages,
            temperature=0.7,
            max_tokens=1500
        )
        
        # Extract response text
        response_text = result.get("content") or result.get("response") or result.get("text") or ""

        if not response_text:
            raise ValueError("Empty response from AI")

        # ============================================================
        # PROACTIVE ENGAGEMENT: Scan for Study Plans/Lessons
        # ============================================================
        try:
            from lyo_app.services.proactive_dispatcher import proactive_dispatcher
            proactive_dispatcher.extract_and_schedule_from_text(current_user.id, response_text)
        except Exception as e:
            logger.error(f"Proactive dispatcher failed: {e}")

        # ============================================================
        # Translate A2A artifacts to UI components if present
        # ============================================================
        # Check if the AI result contains artifacts (populated by Orchestrator or Agents)
        artifacts_data = result.get("artifacts", [])
        if artifacts_data and isinstance(artifacts_data, list) and not ui_component_json:
            for art_data in artifacts_data:
                try:
                    if isinstance(art_data, dict):
                        artifact = Artifact(**art_data)
                    elif isinstance(art_data, Artifact):
                        artifact = art_data
                    else:
                        continue

                    translated = translate_artifact_to_ui_component(artifact)
                    if translated:
                        ui_component_json = translated
                        break
                except Exception as e:
                    logger.warning(f"Failed to translate artifact: {e}")

        latency_ms = int((time.time() - start_time) * 1000)
        logger.info(f"Chat response generated in {latency_ms}ms")

        return ChatResponse(
            response=response_text,
            model_used=result.get("model", "Google Gemini 2.0 Flash"),
            success=True,
            error=None,
            user_profile=user_profile_summary,
            ui_component=ui_component_json
        )
        
    except Exception as e:
        logger.error(f"Chat endpoint failed: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={
                "error": True,
                "message": f"Request could not be processed: {str(e)}" if not settings.is_production() else "Request could not be processed. Please try again.",
                "category": "business_logic",
                "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S")
            }
        )
