"""
AI Mentor Agent - Intelligent Educational Mentoring

Advanced AI mentor providing personalized educational guidance:
- Contextual conversation management
- Proactive intervention and support
- Adaptive communication based on user state
- Educational content generation and explanation
- Progress tracking and encouragement
"""

import asyncio
import json
import logging
import uuid
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any, Tuple
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_, desc
from sqlalchemy.orm import selectinload

from .models import MentorInteraction, UserEngagementState, UserEngagementStateEnum, AIConversationLog, AIModelTypeEnum
from .orchestrator import ai_orchestrator, ModelType, TaskComplexity
from .websocket_manager import connection_manager
from lyo_app.models.enhanced import User
from lyo_app.stack.schemas import StackCardPayload, StackItemType
from lyo_app.services.memory_synthesis import memory_synthesis_service

logger = logging.getLogger(__name__)


class ConversationContext:
    """
    Manages conversation context and memory for personalized interactions.
    """
    
    def __init__(self, user_id: int):
        self.user_id = user_id
        self.session_id = str(uuid.uuid4())
        self.conversation_history: List[Dict] = []
        self.user_profile: Optional[Dict] = None
        self.current_topic: Optional[str] = None
        self.learning_objectives: List[str] = []
        self.preferences: Dict[str, Any] = {}
        
    def add_message(self, role: str, content: str, metadata: Optional[Dict] = None):
        """Add a message to conversation history."""
        self.conversation_history.append({
            "role": role,
            "content": content,
            "timestamp": datetime.utcnow().isoformat(),
            "metadata": metadata or {}
        })
        
        # Keep conversation history manageable
        if len(self.conversation_history) > 20:
            self.conversation_history = self.conversation_history[-15:]  # Keep last 15 messages
    
    def get_context_summary(self) -> str:
        """Generate a context summary for the AI model."""
        if not self.conversation_history:
            return "No previous conversation."
        
        # Get last few messages for context
        recent_messages = self.conversation_history[-5:]
        context_parts = []
        
        if self.current_topic:
            context_parts.append(f"Current topic: {self.current_topic}")
        
        if self.user_profile:
            context_parts.append(f"User background: {self.user_profile.get('learning_level', 'unknown')}")
        
        context_parts.append("Recent conversation:")
        for msg in recent_messages:
            role_label = "Student" if msg["role"] == "user" else "Mentor"
            context_parts.append(f"{role_label}: {msg['content'][:100]}...")
        
        return "\n".join(context_parts)


class MentorPersonality:
    """
    Defines the AI mentor's personality and communication style.
    """
    
    def __init__(self):
        self.base_personality = {
            "tone": "encouraging and supportive",
            "style": "conversational yet educational",
            "approach": "socratic questioning and guided discovery",
            "empathy_level": "high",
            "humor_usage": "light and appropriate"
        }
        
        # Different personas for different situations
        self.personas = {
            "struggling_student": {
                "tone": "patient and reassuring",
                "approach": "break down complex concepts into simple steps",
                "encouragement": "high",
                "examples": "concrete and relatable"
            },
            "advanced_learner": {
                "tone": "intellectually stimulating",
                "approach": "challenge with deeper questions",
                "encouragement": "moderate",
                "examples": "complex and thought-provoking"
            },
            "frustrated_learner": {
                "tone": "calm and understanding",
                "approach": "address emotions first, then learning",
                "encouragement": "very high",
                "examples": "simple and stress-reducing"
            },
            "curious_explorer": {
                "tone": "enthusiastic and explorative",
                "approach": "encourage discovery and experimentation",
                "encouragement": "moderate",
                "examples": "diverse and inspiring"
            }
        }
    
    def get_persona_prompt(self, user_state: str, context: Dict) -> str:
        """Generate personality prompt based on user state."""
        persona = self.personas.get(user_state, self.base_personality)
        
        prompt_parts = [
            "You are an AI mentor on an educational platform. Your personality and approach:",
            f"- Tone: {persona.get('tone', self.base_personality['tone'])}",
            f"- Teaching approach: {persona.get('approach', self.base_personality['approach'])}",
            f"- Encouragement level: {persona.get('encouragement', 'moderate')}",
            f"- Example style: {persona.get('examples', 'clear and relevant')}"
        ]
        
        # Add specific context-based instructions
        if user_state == "struggling":
            prompt_parts.extend([
                "- Be extra patient and break concepts into very small steps",
                "- Use lots of encouragement and positive reinforcement",
                "- Avoid overwhelming the student with too much information"
            ])
        elif user_state == "bored":
            prompt_parts.extend([
                "- Introduce more challenging and interesting concepts",
                "- Use engaging questions and thought experiments",
                "- Connect learning to real-world applications"
            ])
        
        return "\n".join(prompt_parts)


class AIMentor:
    """
    Main AI Mentor agent providing intelligent educational guidance.
    
    Features:
    - Contextual conversation management
    - Adaptive personality based on user state
    - Proactive intervention and support
    - Educational content generation
    - Progress tracking and encouragement
    """
    
    def __init__(self):
        self.personality = MentorPersonality()
        self.active_conversations: Dict[int, ConversationContext] = {}
        
        # Response templates for common scenarios
        self.response_templates = {
            "greeting": [
                "Hello! I'm your AI mentor. How can I help you with your learning today?",
                "Hi there! Ready to dive into some learning? What would you like to explore?",
                "Welcome! I'm here to support your educational journey. What's on your mind?"
            ],
            "struggling_support": [
                "I can see you're finding this challenging. That's completely normal! Let's break it down together.",
                "Learning can be tough sometimes. You're doing great by persisting! Let me help you approach this differently.",
                "I notice you might be struggling with this concept. No worries - we'll work through it step by step."
            ],
            "encouragement": [
                "You're making excellent progress! Keep up the great work!",
                "I can see your understanding is really developing. Well done!",
                "That's a fantastic insight! You're really getting the hang of this."
            ],
            "curiosity_support": [
                "Great question! I love seeing your curiosity. Let's explore this together.",
                "Your eagerness to learn is wonderful! Here's an interesting way to think about it...",
                "That's exactly the kind of thinking that leads to deep understanding!"
            ]
        }
        
        # Educational strategies
        self.teaching_strategies = {
            "explain_concept": "Break down the concept into fundamental parts and build understanding step by step",
            "provide_examples": "Give concrete, relatable examples that illustrate the concept clearly",
            "ask_questions": "Use Socratic questioning to guide the student to discover the answer",
            "analogies": "Use analogies and metaphors to connect new concepts to familiar ideas",
            "practice_problems": "Provide practice exercises to reinforce understanding",
            "real_world_connections": "Show how the concept applies in real-world situations"
        }
        
        logger.info("AIMentor initialized with adaptive personality system")
    
    async def get_response(
        self,
        user_id: int,
        message: str,
        db: AsyncSession,
        context: Optional[Dict] = None
    ) -> Dict[str, Any]:
        """Handle incoming user message, generate AI response, log interaction, and return structured data.

        This method now includes persistent memory to make the AI feel like it truly knows the user.
        """
        # Get or create conversation context
        convo = self._get_conversation_context(user_id)
        convo.add_message("user", message)

        # Fetch user profile for additional context
        user_profile = await self._get_user_profile(user_id, db)
        if user_profile:
            convo.user_profile = user_profile

        # Get persistent memory - THE KEY TO FEELING INDISPENSABLE
        persistent_memory = await memory_synthesis_service.get_memory_for_prompt(user_id, db)

        # Get user's engagement state for adaptive response
        engagement_state = await self._get_engagement_state(user_id, db)
        user_state = engagement_state.state.value if engagement_state else "neutral"

        # Build memory-aware prompt
        persona_prompt = self.personality.get_persona_prompt(user_state, {})
        context_summary = convo.get_context_summary()

        # Construct the full prompt with persistent memory
        full_prompt = f"""
{persona_prompt}

{persistent_memory}

## Current Session Context:
{context_summary}

## Student's Message:
"{message}"

## Instructions:
Respond naturally as their AI mentor. Reference their history and preferences when relevant.
Keep your response helpful, educational, and personalized to who they are.
"""

        # Generate response using orchestrator
        model_resp = await ai_orchestrator.generate_response(
            prompt=full_prompt,
            task_complexity=TaskComplexity.MEDIUM,
            model_preference=ModelType.GEMMA_4_ON_DEVICE,
            max_tokens=512,
            user_context={
                "user_id": user_id,
                "engagement_state": user_state,
                "has_memory": bool(persistent_memory)
            }
        )

        # Extract response content
        response_content = model_resp.content if hasattr(model_resp, 'content') else str(model_resp)

        # Record AI response in conversation context
        convo.add_message("assistant", response_content)

        # Build response
        response = {
            "response": response_content,
            "interaction_id": None,
            "model_used": model_resp.model_used if hasattr(model_resp, 'model_used') else ModelType.GEMMA_ON_DEVICE,
            "response_time_ms": model_resp.response_time_ms if hasattr(model_resp, 'response_time_ms') else 0.0,
            "strategy_used": TaskComplexity.MEDIUM,
            "conversation_id": convo.session_id,
            "engagement_state": UserEngagementStateEnum.IDLE,
            "timestamp": datetime.utcnow(),
            "stack_card": None,
            "memory_used": bool(persistent_memory)  # Flag to indicate memory was used
        }

        # Demo heuristic: If user asks to save or mentions stack, provide a card
        if "save" in message.lower() or "stack" in message.lower():
            response["stack_card"] = StackCardPayload(
                title="Conversation Summary",
                description="Save this conversation point to your stack.",
                type=StackItemType.SESSION,
                ref_id=convo.session_id,
                action_label="Save to Stack",
                context_data={"summary": response["response"][:50] + "..."}
            ).model_dump()

        # Persist interaction
        interaction = MentorInteraction(
            user_id=user_id,
            session_id=convo.session_id,
            user_message=message,
            mentor_response=response["response"],
            interaction_type="conversation",
            model_used=response["model_used"],
            response_time_ms=response["response_time_ms"],
            sentiment_detected=None,
            context_metadata=context
        )
        db.add(interaction)
        await db.commit()
        await db.refresh(interaction)

        # Update response with DB id
        response["interaction_id"] = interaction.id

        # Get updated engagement state
        eng_state = await db.get(UserEngagementState, user_id)
        if eng_state:
            response["engagement_state"] = eng_state.state

        # Queue memory synthesis for this session (async, non-blocking)
        # This happens in background after response is sent
        self._queue_memory_synthesis(user_id, convo.session_id)

        return response

    def _queue_memory_synthesis(self, user_id: int, session_id: str):
        """Queue memory synthesis as a background task."""
        try:
            from lyo_app.tasks.memory_synthesis import trigger_session_memory_synthesis
            # Delay synthesis by 30 seconds to allow session to accumulate more messages
            trigger_session_memory_synthesis(user_id, session_id, delay_seconds=30)
        except Exception as e:
            # Don't fail the response if memory synthesis queueing fails
            logger.warning(f"Failed to queue memory synthesis for user {user_id}: {e}")

    async def proactive_check_in(
        self, 
        user_id: int, 
        reason: str, 
        db: AsyncSession
    ):
        """Send a proactive check-in message to struggling or frustrated users via WebSocket."""
        # Generate proactive message
        msg = f"I noticed you might be {reason}. How can I help?"
        # Log interaction
        inter = MentorInteraction(
            user_id=user_id,
            session_id=str(uuid.uuid4()),
            user_message=None,
            mentor_response=msg,
            interaction_type="proactive_check_in",
            model_used=ModelType.GEMMA_ON_DEVICE,
            response_time_ms=0.0,
            sentiment_detected=None,
            context_metadata={"reason": reason}
        )
        db.add(inter)
        await db.commit()
        await db.refresh(inter)

        # Send via WebSocket
        await connection_manager.send_personal_message(
            message=msg,
            user_id=user_id
        )

    async def get_conversation_history(self, user_id: int, db: AsyncSession, limit: int = 20) -> List[Dict[str, Any]]:
        """Fetch recent mentor interactions for the user."""
        result = await db.execute(
            select(MentorInteraction)
                .where(MentorInteraction.user_id == user_id)
                .order_by(MentorInteraction.timestamp.desc())
                .limit(limit)
        )
        interactions = result.scalars().all()
        history = []
        for inter in interactions:
            history.append({
                "interaction_id": inter.id,
                "type": inter.interaction_type,
                "message": inter.user_message,
                "response": inter.mentor_response,
                "model_used": inter.model_used,
                "timestamp": inter.timestamp
            })
        return history

    async def rate_interaction(self, interaction_id: int, was_helpful: bool, db: AsyncSession) -> bool:
        """Allow users to rate past interactions."""
        inter = await db.get(MentorInteraction, interaction_id)
        if not inter:
            return False
        inter.was_helpful = was_helpful
        await db.commit()
        return True
    
    def _get_conversation_context(self, user_id: int) -> ConversationContext:
        """Get or create conversation context for user."""
        if user_id not in self.active_conversations:
            self.active_conversations[user_id] = ConversationContext(user_id)
        return self.active_conversations[user_id]
    
    async def _get_user_profile(self, user_id: int, db: AsyncSession) -> Optional[Dict]:
        """Get user profile information."""
        try:
            result = await db.execute(
                select(User).where(User.id == user_id)
            )
            user = result.scalar_one_or_none()
            
            if user:
                return {
                    "username": user.username,
                    "full_name": f"{user.first_name} {user.last_name}".strip(),
                    "learning_level": "intermediate",  # Would be determined from actual data
                    "interests": [],  # Would be extracted from user activities
                    "learning_style": "mixed"  # Would be inferred from behavior
                }
            return None
            
        except Exception as e:
            logger.error(f"Error getting user profile for {user_id}: {e}")
            return None
    
    async def _get_engagement_state(self, user_id: int, db: AsyncSession) -> Optional[UserEngagementState]:
        """Get current user engagement state."""
        try:
            result = await db.execute(
                select(UserEngagementState).where(UserEngagementState.user_id == user_id)
            )
            return result.scalar_one_or_none()
            
        except Exception as e:
            logger.error(f"Error getting engagement state for {user_id}: {e}")
            return None
    
    async def _determine_response_strategy(
        self,
        message: str,
        engagement_state: Optional[UserEngagementState],
        conversation: ConversationContext,
        context: Optional[Dict]
    ) -> str:
        """Determine the best response strategy based on context."""
        
        message_lower = message.lower()
        
        # Check for specific question types
        if any(word in message_lower for word in ["explain", "what is", "how does", "why"]):
            return "explain_concept"
        
        if any(word in message_lower for word in ["example", "show me", "demonstrate"]):
            return "provide_examples"
        
        if any(word in message_lower for word in ["help", "stuck", "confused", "don't understand"]):
            return "guided_support"
        
        # Base strategy on engagement state
        if engagement_state:
            state = engagement_state.state
            
            if state == UserEngagementStateEnum.STRUGGLING:
                return "patient_explanation"
            elif state == UserEngagementStateEnum.FRUSTRATED:
                return "calming_support"
            elif state == UserEngagementStateEnum.BORED:
                return "engaging_challenge"
            elif state == UserEngagementStateEnum.CURIOUS:
                return "exploration_encouragement"
        
        # Default conversational strategy
        return "conversational_support"
    
    async def _generate_ai_response(
        self,
        user_id: int,
        message: str,
        conversation: ConversationContext,
        engagement_state: Optional[UserEngagementState],
        strategy: str
    ) -> Any:  # ModelResponse type
        """Generate AI response using the orchestrator."""
        
        # Build context prompt
        context_summary = conversation.get_context_summary()
        
        # Get appropriate persona
        user_state = engagement_state.state.value if engagement_state else "neutral"
        persona_prompt = self.personality.get_persona_prompt(user_state, {})
        
        # Build strategy-specific prompt
        strategy_instruction = self._get_strategy_instruction(strategy)
        
        # Combine into final prompt
        full_prompt = f"""
{persona_prompt}

Strategy for this response: {strategy_instruction}

Conversation context:
{context_summary}

Student's current message: "{message}"

Provide a helpful, educational response that matches your personality and the specified strategy. Keep responses conversational, encouraging, and appropriately detailed for the context.
"""
        
        # Determine task complexity based on strategy
        complexity_mapping = {
            "explain_concept": "medium",
            "provide_examples": "medium", 
            "guided_support": "simple",
            "patient_explanation": "simple",
            "calming_support": "simple",
            "engaging_challenge": "complex",
            "exploration_encouragement": "medium",
            "conversational_support": "simple"
        }
        
        task_type = complexity_mapping.get(strategy, "simple")
        
        # Generate response using orchestrator
        complexity = TaskComplexity.SIMPLE
        if task_type == "medium":
            complexity = TaskComplexity.MEDIUM
        elif task_type == "complex":
            complexity = TaskComplexity.COMPLEX
            
        response = await ai_orchestrator.generate_response(
            prompt=full_prompt,
            task_complexity=complexity,
            model_preference=ModelType.GEMMA_4_ON_DEVICE,
            max_tokens=512,
            user_context={
                "user_id": user_id,
                "engagement_state": user_state,
                "strategy": strategy
            }
        )
        
        return response
    
    def _get_strategy_instruction(self, strategy: str) -> str:
        """Get specific instruction for response strategy."""
        instructions = {
            "explain_concept": "Provide a clear, step-by-step explanation of the concept. Use simple language and build understanding gradually.",
            "provide_examples": "Give concrete, relatable examples that illustrate the concept clearly. Use real-world applications when possible.",
            "guided_support": "Help the student work through their confusion by asking guiding questions and providing hints rather than direct answers.",
            "patient_explanation": "Be extra patient and break down complex ideas into very simple steps. Use lots of encouragement.",
            "calming_support": "Address any frustration or stress first, then gently guide back to learning. Be very supportive and understanding.",
            "engaging_challenge": "Provide more stimulating content that challenges the student intellectually. Introduce advanced concepts or interesting applications.",
            "exploration_encouragement": "Encourage the student's curiosity by expanding on their interests and suggesting related topics to explore.",
            "conversational_support": "Provide a natural, conversational response that addresses the student's message directly and helpfully."
        }
        
        return instructions.get(strategy, "Provide a helpful and educational response.")
    
    async def _generate_proactive_message(
        self,
        user_id: int,
        reason: str,
        context: Dict,
        conversation: ConversationContext
    ) -> Any:  # ModelResponse type
        """Generate proactive message based on reason."""
        
        # Build context for proactive message
        engagement_state = context.get("engagement_state", "unknown")
        confidence = context.get("confidence", 0.0)
        recommendations = context.get("recommendations", [])
        
        # Create reason-specific prompts
        reason_prompts = {
            "struggling_detected": f"""
The student appears to be struggling (confidence: {confidence:.1f}). 
Generate a supportive, encouraging message that offers help without being overwhelming.
Focus on reassurance and offering specific assistance.
""",
            "frustrated_detected": f"""
The student seems frustrated (confidence: {confidence:.1f}).
Generate a calming, empathetic message that acknowledges their feelings and offers gentle support.
Help them refocus and provide a different approach.
""",
            "bored_detected": f"""
The student appears to be bored or disengaged (confidence: {confidence:.1f}).
Generate an engaging message that introduces more interesting content or challenges.
Spark their curiosity and motivation.
""",
            "curious_detected": f"""
The student is showing curiosity and engagement (confidence: {confidence:.1f}).
Generate an encouraging message that feeds their curiosity and suggests interesting directions to explore.
"""
        }
        
        base_prompt = reason_prompts.get(reason, f"The student needs a check-in based on: {reason}")
        
        # Get conversation context
        context_summary = conversation.get_context_summary()
        persona_prompt = self.personality.get_persona_prompt(engagement_state, context)
        
        full_prompt = f"""
{persona_prompt}

Context: You are proactively reaching out to a student based on AI analysis of their learning behavior.

{base_prompt}

Previous conversation context:
{context_summary}

Recommendations from AI analysis: {', '.join(recommendations) if recommendations else 'None'}

Generate a brief, caring, proactive message (2-3 sentences) that feels natural and helpful, not robotic. 
The student hasn't asked for help - you're reaching out because you care about their learning.
"""
        
        # Generate response
        response = await ai_orchestrator.generate_response(
            prompt=full_prompt,
            task_complexity=TaskComplexity.MEDIUM,
            model_preference=ModelType.GEMMA_4_ON_DEVICE,
            max_tokens=256,
            user_context={
                "user_id": user_id,
                "reason": reason,
                "proactive": True
            }
        )
        
        return response
    
    async def _log_interaction(
        self,
        user_id: int,
        user_message: Optional[str],
        mentor_response: str,
        interaction_type: str,
        model_used: ModelType,
        response_time: float,
        context: Optional[Dict],
        db: AsyncSession
    ) -> MentorInteraction:
        """Log mentor interaction to database."""
        
        # Convert ModelType to AIModelTypeEnum
        model_enum_mapping = {
            ModelType.GEMMA_ON_DEVICE: AIModelTypeEnum.GEMMA_ON_DEVICE,
            ModelType.CLOUD_LLM: AIModelTypeEnum.CLOUD_LLM,
            ModelType.HYBRID: AIModelTypeEnum.HYBRID
        }
        
        interaction = MentorInteraction(
            user_id=user_id,
            session_id=self.active_conversations.get(user_id, ConversationContext(user_id)).session_id,
            user_message=user_message,
            mentor_response=mentor_response,
            interaction_type=interaction_type,
            model_used=model_enum_mapping.get(model_used, AIModelTypeEnum.GEMMA_ON_DEVICE),
            response_time_ms=response_time,
            context_metadata=context,
            timestamp=datetime.utcnow()
        )
        
        db.add(interaction)
        await db.commit()
        await db.refresh(interaction)
        
        return interaction
    
    async def _send_websocket_response(self, user_id: int, message: str, message_type: str) -> bool:
        """Send response via WebSocket if user is connected."""
        try:
            success = await connection_manager.send_personal_message(
                json.dumps({
                    "type": message_type,
                    "content": message,
                    "from": "ai_mentor",
                    "timestamp": datetime.utcnow().isoformat()
                }),
                user_id,
                message_type
            )
            
            if success:
                logger.debug(f"WebSocket message sent to user {user_id}")
            else:
                logger.debug(f"User {user_id} not connected, message queued")
            
            return success
            
        except Exception as e:
            logger.error(f"Error sending WebSocket message to user {user_id}: {e}")
            return False
    
    async def get_conversation_history(self, user_id: int, db: AsyncSession, limit: int = 20) -> List[Dict]:
        """Get conversation history for a user."""
        try:
            result = await db.execute(
                select(MentorInteraction)
                .where(MentorInteraction.user_id == user_id)
                .order_by(desc(MentorInteraction.timestamp))
                .limit(limit)
            )
            interactions = result.scalars().all()
            
            history = []
            for interaction in reversed(interactions):  # Reverse to get chronological order
                history.append({
                    "id": interaction.id,
                    "user_message": interaction.user_message,
                    "mentor_response": interaction.mentor_response,
                    "interaction_type": interaction.interaction_type,
                    "model_used": interaction.model_used.value,
                    "response_time_ms": interaction.response_time_ms,
                    "was_helpful": interaction.was_helpful,
                    "timestamp": interaction.timestamp.isoformat()
                })
            
            return history
            
        except Exception as e:
            logger.error(f"Error getting conversation history for user {user_id}: {e}")
            return []
    
    async def rate_interaction(self, interaction_id: int, was_helpful: bool, db: AsyncSession) -> bool:
        """Allow user to rate mentor interaction."""
        try:
            result = await db.execute(
                select(MentorInteraction).where(MentorInteraction.id == interaction_id)
            )
            interaction = result.scalar_one_or_none()
            
            if interaction:
                interaction.was_helpful = was_helpful
                await db.commit()
                logger.info(f"Interaction {interaction_id} rated as {'helpful' if was_helpful else 'not helpful'}")
                return True
            
            return False
            
        except Exception as e:
            logger.error(f"Error rating interaction {interaction_id}: {e}")
            return False
    
    def cleanup_inactive_conversations(self, max_age_hours: int = 24):
        """Clean up inactive conversation contexts."""
        cutoff_time = datetime.utcnow() - timedelta(hours=max_age_hours)
        
        inactive_users = []
        for user_id, conversation in self.active_conversations.items():
            if conversation.conversation_history:
                last_message_time = datetime.fromisoformat(
                    conversation.conversation_history[-1]["timestamp"].replace('Z', '+00:00')
                )
                if last_message_time < cutoff_time:
                    inactive_users.append(user_id)
        
        for user_id in inactive_users:
            del self.active_conversations[user_id]
            logger.debug(f"Cleaned up inactive conversation for user {user_id}")
        
        if inactive_users:
            logger.info(f"Cleaned up {len(inactive_users)} inactive conversations")


# Global mentor instance
ai_mentor = AIMentor()
