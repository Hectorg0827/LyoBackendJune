"""
Living Classroom Stream Enhancement
==================================

Enhances the existing stream_lyo2.py with Living Classroom capabilities.
Provides backward compatibility while enabling real-time scene streaming.
"""

import asyncio
import json
import logging
import time
import uuid
from datetime import datetime
from typing import AsyncGenerator, Dict, Any, Optional, List

from fastapi import HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from lyo_app.auth.schemas import UserRead
from lyo_app.ai.schemas.lyo2 import RouterRequest

# Import Living Classroom components
from lyo_app.ai_classroom.scene_lifecycle_engine import SceneLifecycleEngine, TriggerType, Trigger
from lyo_app.ai_classroom.websocket_manager import get_websocket_manager
from lyo_app.ai_classroom.sdui_models import Scene, SceneType, Component

logger = logging.getLogger(__name__)


class LivingClassroomStreamEnhancer:
    """Enhances existing SSE streams with Living Classroom capabilities"""

    def __init__(self):
        self.scene_cache = {}
        self.conversion_metrics = {
            "scenes_converted": 0,
            "components_generated": 0,
            "sse_bricks_created": 0
        }

    async def enhance_stream_lyo2(
        self,
        request: RouterRequest,
        current_user: UserRead,
        db: AsyncSession,
        existing_stream_function: callable
    ) -> AsyncGenerator[str, None]:
        """Enhanced stream that can output both Living Classroom and SSE formats"""

        trace_id = str(uuid.uuid4())
        logger.info(f"🎭 Living Classroom Enhanced Stream: {trace_id}")

        try:
            # Check if user should get Living Classroom experience
            use_living_classroom = await self._should_use_living_classroom(current_user)

            if use_living_classroom:
                logger.info(f"✅ Using Living Classroom for user {current_user.id}")
                async for event in self._living_classroom_stream(request, current_user, db, trace_id):
                    yield event
            else:
                logger.info(f"📄 Using legacy SSE for user {current_user.id}")
                # Use existing stream function
                async for event in existing_stream_function():
                    yield event

        except Exception as e:
            logger.error(f"❌ Stream enhancement error: {e}")
            # Fallback to existing stream
            async for event in existing_stream_function():
                yield event

    async def _should_use_living_classroom(self, user: UserRead) -> bool:
        """Determine if user should get Living Classroom experience"""
        import os

        # Feature flag
        if not os.getenv("LIVING_CLASSROOM_ENABLED", "false").lower() == "true":
            return False

        # User percentage rollout
        rollout_percentage = float(os.getenv("LIVING_CLASSROOM_PERCENTAGE", "0.1"))
        user_hash = hash(str(user.id)) % 100

        return user_hash < (rollout_percentage * 100)

    async def _living_classroom_stream(
        self,
        request: RouterRequest,
        current_user: UserRead,
        db: AsyncSession,
        trace_id: str
    ) -> AsyncGenerator[str, None]:
        """Generate Living Classroom stream"""

        start_time = time.time()

        # Initialize Scene Lifecycle Engine
        ws_manager = await get_websocket_manager()
        lifecycle_engine = SceneLifecycleEngine(db, ws_manager)

        # Create trigger from HTTP request
        trigger = Trigger(
            trigger_type=TriggerType.USER_ACTION,
            user_id=str(current_user.id),
            session_id=trace_id,
            action_data={
                "action_intent": "continue",
                "request_text": request.text,
                "forced_intent": request.forced_intent.value if request.forced_intent else None
            }
        )

        try:
            # Process through Scene Lifecycle Engine
            scene = await lifecycle_engine.process_trigger(trigger)
            logger.info(f"🎬 Scene generated: {scene.scene_id} with {len(scene.components)} components")

            # Convert scene to SSE events for backward compatibility
            async for sse_event in self._scene_to_sse_stream(scene, trace_id):
                yield sse_event

            # Add Living Classroom metadata
            metadata_event = {
                "type": "living_classroom_metadata",
                "data": {
                    "scene_id": scene.scene_id,
                    "scene_type": scene.scene_type.value,
                    "generation_time_ms": (time.time() - start_time) * 1000,
                    "components_count": len(scene.components)
                }
            }

            yield f"data: {json.dumps(metadata_event)}\n\n"
            yield "data: [DONE]\n\n"

        except Exception as e:
            logger.error(f"❌ Living Classroom stream error: {e}")
            # Return error event
            error_event = {
                "type": "error",
                "message": "Scene generation failed, falling back to standard response"
            }
            yield f"data: {json.dumps(error_event)}\n\n"

    async def _scene_to_sse_stream(self, scene: Scene, trace_id: str) -> AsyncGenerator[str, None]:
        """Convert Living Classroom scene to SSE brick format"""

        # Send skeleton first (existing pattern)
        skeleton_brick = {"type": "skeleton", "blocks": ["answer", "actions"]}
        yield f"data: {json.dumps(skeleton_brick)}\n\n"

        # Brief delay for realism
        await asyncio.sleep(0.1)

        # Convert scene components to SSE bricks
        for component in scene.components:
            brick = await self._component_to_sse_brick(component)
            if brick:
                yield f"data: {json.dumps(brick)}\n\n"
                self.conversion_metrics["sse_bricks_created"] += 1

                # Add small delay between components for progressive feel
                await asyncio.sleep(0.05)

        self.conversion_metrics["scenes_converted"] += 1

    async def _component_to_sse_brick(self, component: Component) -> Optional[Dict[str, Any]]:
        """Convert SDUI component to SSE brick format"""

        component_type = component.type

        if component_type == "TeacherMessage":
            return {
                "type": "answer",
                "block": {
                    "type": "TutorMessageBlock",
                    "content": {"text": component.text},
                    "priority": component.priority,
                    "metadata": {
                        "emotion": getattr(component, "emotion", "neutral"),
                        "audio_mood": getattr(component, "audio_mood", "calm"),
                        "living_classroom": True
                    }
                }
            }

        elif component_type == "CTAButton":
            return {
                "type": "actions",
                "blocks": [{
                    "type": "CTARow",
                    "content": {"actions": [component.label]},
                    "priority": component.priority,
                    "metadata": {
                        "action_intent": component.action_intent.value,
                        "living_classroom": True
                    }
                }]
            }

        elif component_type == "QuizCard":
            return {
                "type": "quiz",
                "block": {
                    "type": "QuizBlock",
                    "content": {
                        "question": component.question,
                        "options": [
                            {
                                "id": opt.id,
                                "label": opt.label,
                                "is_correct": opt.is_correct
                            }
                            for opt in component.options
                        ]
                    },
                    "priority": component.priority,
                    "metadata": {
                        "concept_id": getattr(component, "concept_id", None),
                        "living_classroom": True
                    }
                }
            }

        elif component_type == "Celebration":
            return {
                "type": "celebration",
                "block": {
                    "type": "CelebrationBlock",
                    "content": {
                        "message": component.message,
                        "celebration_type": component.celebration_type,
                        "particle_effect": component.particle_effect
                    },
                    "priority": component.priority,
                    "metadata": {
                        "living_classroom": True
                    }
                }
            }

        elif component_type == "StudentPrompt":
            return {
                "type": "peer_message",
                "block": {
                    "type": "PeerMessageBlock",
                    "content": {
                        "student_name": component.student_name,
                        "text": component.text,
                        "purpose": component.purpose
                    },
                    "priority": component.priority,
                    "metadata": {
                        "living_classroom": True
                    }
                }
            }

        # Unknown component type
        logger.warning(f"⚠️ Unknown component type for SSE conversion: {component_type}")
        return None

    def get_metrics(self) -> Dict[str, Any]:
        """Get conversion metrics"""
        return {
            **self.conversion_metrics,
            "cache_size": len(self.scene_cache)
        }


# Global enhancer instance
_stream_enhancer = LivingClassroomStreamEnhancer()


async def get_stream_enhancer() -> LivingClassroomStreamEnhancer:
    """Get stream enhancer instance"""
    return _stream_enhancer


def create_enhanced_stream_function(original_stream_function):
    """Decorator to enhance existing stream functions with Living Classroom"""

    async def enhanced_stream(
        request: RouterRequest,
        current_user: UserRead,
        db: AsyncSession
    ):
        enhancer = await get_stream_enhancer()

        # Create wrapper for original function
        async def original_wrapper():
            async for event in original_stream_function(request, current_user, db):
                yield event

        # Use enhancer
        async for event in enhancer.enhance_stream_lyo2(
            request, current_user, db, original_wrapper
        ):
            yield event

    return enhanced_stream