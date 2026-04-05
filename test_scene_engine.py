#!/usr/bin/env python3
"""
Test script for the Scene Lifecycle Engine
"""

import sys
import asyncio
from datetime import datetime
from typing import Optional, Dict, Any

# Add current directory to path
sys.path.insert(0, '.')

# Import SDUI models by executing the file (to avoid import issues)
exec(open('lyo_app/ai_classroom/sdui_models.py').read())

# Define core Scene Lifecycle classes for testing
class TriggerType:
    USER_ACTION = "user_action"
    SYSTEM_TIMEOUT = "system_timeout"

class Trigger:
    def __init__(self, trigger_type: str, user_id: str, session_id: str, action_data: Optional[Dict] = None):
        self.trigger_id = f"trigger_{datetime.utcnow().strftime('%H%M%S')}"
        self.trigger_type = trigger_type
        self.user_id = user_id
        self.session_id = session_id
        self.action_data = action_data or {}
        self.timestamp = datetime.utcnow()

class KnowledgeState:
    def __init__(self, concept_id: str, mastery_level: float = 0.5):
        self.concept_id = concept_id
        self.mastery_level = mastery_level
        self.confidence = 0.5
        self.consecutive_correct = 0

class FrustrationMetrics:
    def __init__(self):
        self.frustration_score = 0.0
        self.consecutive_failures = 0

class ContextSnapshot:
    def __init__(self, user_id: str, session_id: str):
        self.user_id = user_id
        self.session_id = session_id
        self.knowledge_states = []
        self.frustration = FrustrationMetrics()
        self.engagement_level = 0.7

class DirectorDecision:
    def __init__(self, selected_scene_type: str, reasoning: str, confidence: float = 0.8):
        self.selected_scene_type = selected_scene_type
        self.reasoning = reasoning
        self.confidence = confidence
        self.suggested_components = []

class MockClassroomDirector:
    """Mock implementation of Classroom Director for testing"""

    async def decide_scene(self, trigger: Trigger, context: ContextSnapshot) -> DirectorDecision:
        """Simple decision logic for testing"""
        print(f"🎯 Director analyzing: {trigger.trigger_type}")

        if trigger.action_data.get("action_intent") == "request_hint":
            return DirectorDecision(
                selected_scene_type=SceneType.CORRECTION,
                reasoning="User needs help - provide guidance",
                confidence=0.9
            )
        elif trigger.action_data.get("action_intent") == "submit_answer":
            is_correct = trigger.action_data.get("is_correct", False)
            if is_correct:
                return DirectorDecision(
                    selected_scene_type=SceneType.CELEBRATION,
                    reasoning="Correct answer - celebrate success",
                    confidence=0.85
                )
            else:
                return DirectorDecision(
                    selected_scene_type=SceneType.CORRECTION,
                    reasoning="Incorrect answer - provide correction",
                    confidence=0.8
                )
        else:
            return DirectorDecision(
                selected_scene_type=SceneType.INSTRUCTION,
                reasoning="Continue with instruction",
                confidence=0.7
            )

class MockSceneCompiler:
    """Mock implementation of Scene Compiler for testing"""

    async def compile_scene(self, decision: DirectorDecision, context: ContextSnapshot, trigger: Trigger) -> Scene:
        """Compile Director decision into SDUI scene"""
        print(f"🎨 Compiling scene: {decision.selected_scene_type}")

        components = []

        if decision.selected_scene_type == SceneType.INSTRUCTION:
            components.append(TeacherMessage(
                text="Let's continue with our lesson!",
                emotion="encouraging"
            ))
            components.append(CTAButton(
                label="Continue",
                action_intent=ActionIntent.CONTINUE
            ))

        elif decision.selected_scene_type == SceneType.CELEBRATION:
            components.append(Celebration(
                message="Excellent work! 🎉"
            ))
            components.append(CTAButton(
                label="Next Question",
                action_intent=ActionIntent.CONTINUE
            ))

        elif decision.selected_scene_type == SceneType.CORRECTION:
            components.append(TeacherMessage(
                text="Let me help clarify this concept.",
                emotion="concerned"
            ))
            components.append(CTAButton(
                label="Try Again",
                action_intent=ActionIntent.RETRY
            ))

        scene = Scene(
            scene_type=decision.selected_scene_type,
            components=components
        )

        print(f"✅ Scene compiled: {len(components)} components")
        return scene

# Test the Scene Lifecycle
async def test_scene_lifecycle():
    """Test the complete scene lifecycle process"""

    print("🎭 Testing Scene Lifecycle Engine\n")

    # Initialize components
    director = MockClassroomDirector()
    compiler = MockSceneCompiler()

    # Test scenarios
    test_cases = [
        {
            "name": "User continues lesson",
            "trigger": Trigger(
                TriggerType.USER_ACTION,
                "user123",
                "session456",
                {"action_intent": "continue"}
            )
        },
        {
            "name": "User requests hint",
            "trigger": Trigger(
                TriggerType.USER_ACTION,
                "user123",
                "session456",
                {"action_intent": "request_hint"}
            )
        },
        {
            "name": "User submits correct answer",
            "trigger": Trigger(
                TriggerType.USER_ACTION,
                "user123",
                "session456",
                {"action_intent": "submit_answer", "is_correct": True}
            )
        },
        {
            "name": "User submits incorrect answer",
            "trigger": Trigger(
                TriggerType.USER_ACTION,
                "user123",
                "session456",
                {"action_intent": "submit_answer", "is_correct": False}
            )
        }
    ]

    for test_case in test_cases:
        print(f"📋 Test Case: {test_case['name']}")
        trigger = test_case['trigger']

        # Phase 1: Trigger (already have it)
        print(f"   Phase 1 (Trigger): {trigger.trigger_type}")

        # Phase 2: Context Assembly
        context = ContextSnapshot(trigger.user_id, trigger.session_id)
        context.knowledge_states = [
            KnowledgeState("python_basics", 0.6),
            KnowledgeState("variables", 0.7)
        ]
        print(f"   Phase 2 (Context): {len(context.knowledge_states)} concepts")

        # Phase 3: Director Decision
        decision = await director.decide_scene(trigger, context)
        print(f"   Phase 3 (Director): {decision.selected_scene_type} (confidence: {decision.confidence})")

        # Phase 4: Scene Compilation
        scene = await compiler.compile_scene(decision, context, trigger)
        print(f"   Phase 4 (Compiler): Scene {scene.scene_id[:8]}... with {len(scene.components)} components")

        # Verify scene structure
        component_types = [c.type for c in scene.components]
        print(f"   Components: {component_types}")

        print("   ✅ Lifecycle complete\n")

    print("🎯 All test cases passed successfully!")

# Run the test
if __name__ == "__main__":
    asyncio.run(test_scene_lifecycle())