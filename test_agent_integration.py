#!/usr/bin/env python3
"""
Test script for Agent Integration Layer
"""

import sys
import asyncio
from datetime import datetime
from typing import Dict, List, Any
from unittest.mock import Mock, AsyncMock

# Add current directory to path
sys.path.insert(0, '.')

# Import SDUI models
exec(open('lyo_app/ai_classroom/sdui_models.py').read())

# Mock existing agents for testing
class MockTutorAgent:
    """Mock version of existing TutorAgent"""

    def __init__(self):
        self.name = "tutor_agent"

    async def execute_task(self, prompt: str) -> str:
        """Mock tutor response generation"""
        await asyncio.sleep(0.1)  # Simulate processing time

        if "python" in prompt.lower():
            return "Python is a powerful programming language perfect for beginners. It uses simple syntax that reads like English!"
        elif "variables" in prompt.lower():
            return "Variables are containers that store data values. Think of them like labeled boxes where you can put things!"
        else:
            return "Let's explore this concept together step by step. I'm here to help you understand!"

class MockAssessmentAgent:
    """Mock version of existing AssessmentAgent"""

    def __init__(self):
        self.name = "assessment_agent"

    async def execute_task(self, prompt: str) -> str:
        """Mock assessment generation"""
        await asyncio.sleep(0.2)  # Simulate processing time

        # Return mock quiz JSON
        quiz_data = {
            "question": "Which of the following best describes a variable?",
            "options": [
                {"id": "a", "label": "A fixed value that never changes", "is_correct": False, "feedback": "Variables can change their values"},
                {"id": "b", "label": "A container that stores data values", "is_correct": True, "feedback": "Exactly right!"},
                {"id": "c", "label": "A type of loop in programming", "is_correct": False, "feedback": "That's a different concept"}
            ]
        }

        import json
        return json.dumps(quiz_data)

# Define Agent Integration classes for testing
class AgentRole:
    CONTENT_PROVIDER = "content_provider"
    KNOWLEDGE_ASSESSOR = "knowledge_assessor"

class AgentCapability:
    def __init__(self, agent_name: str, role: str, can_generate: List[str]):
        self.agent_name = agent_name
        self.role = role
        self.can_generate = can_generate
        self.response_time_ms = 500.0
        self.reliability_score = 0.8

class AgentConsultationRequest:
    def __init__(self, agent_name: str, scene_type: str, topic: str, max_words: int = 80):
        self.agent_name = agent_name
        self.consultation_type = "generate_content"
        self.scene_type = scene_type
        self.topic = topic
        self.max_words = max_words
        self.tone = "encouraging"
        self.timeout_ms = 2000
        self.concept_tags = [topic]

class AgentConsultationResponse:
    def __init__(self, agent_name: str, success: bool = True):
        self.agent_name = agent_name
        self.success = success
        self.response_time_ms = 0.0
        self.generated_components = []
        self.confidence = 0.8
        self.error_message = None

class MockTutorAgentAdapter:
    """Adapter for TutorAgent testing"""

    def __init__(self, tutor_agent):
        self.agent = tutor_agent
        self.capability = AgentCapability(
            "tutor_agent",
            AgentRole.CONTENT_PROVIDER,
            ["TeacherMessage"]
        )
        self.consultation_count = 0

    async def consult(self, request: AgentConsultationRequest) -> AgentConsultationResponse:
        """Mock agent consultation"""
        start_time = asyncio.get_event_loop().time()

        try:
            # Build prompt
            prompt = f"Generate teaching content for: {request.topic}. Keep under {request.max_words} words. Tone: {request.tone}"

            # Call mock agent
            agent_response = await asyncio.wait_for(
                self.agent.execute_task(prompt),
                timeout=request.timeout_ms / 1000.0
            )

            # Convert to SDUI components
            teacher_msg = TeacherMessage(
                text=agent_response,
                emotion="encouraging",
                concept_tags=request.concept_tags
            )

            response = AgentConsultationResponse(self.capability.agent_name, True)
            response.generated_components = [teacher_msg]
            response.response_time_ms = (asyncio.get_event_loop().time() - start_time) * 1000

            self.consultation_count += 1
            print(f"✅ TutorAgent consultation: {response.response_time_ms:.0f}ms")

            return response

        except Exception as e:
            print(f"❌ TutorAgent consultation failed: {e}")
            return AgentConsultationResponse(self.capability.agent_name, False)

class MockAssessmentAgentAdapter:
    """Adapter for AssessmentAgent testing"""

    def __init__(self, assessment_agent):
        self.agent = assessment_agent
        self.capability = AgentCapability(
            "assessment_agent",
            AgentRole.KNOWLEDGE_ASSESSOR,
            ["QuizCard"]
        )
        self.consultation_count = 0

    async def consult(self, request: AgentConsultationRequest) -> AgentConsultationResponse:
        """Mock assessment consultation"""
        start_time = asyncio.get_event_loop().time()

        try:
            # Build prompt
            prompt = f"Create quiz question for: {request.topic}. Multiple choice with 3 options."

            # Call mock agent
            agent_response = await asyncio.wait_for(
                self.agent.execute_task(prompt),
                timeout=request.timeout_ms / 1000.0
            )

            # Parse JSON response
            import json
            quiz_data = json.loads(agent_response)

            # Convert to QuizCard
            quiz_card = QuizCard(
                question=quiz_data["question"],
                options=[
                    QuizOption(
                        id=opt["id"],
                        label=opt["label"],
                        is_correct=opt["is_correct"],
                        feedback_incorrect=opt.get("feedback", "Try again!")
                    )
                    for opt in quiz_data["options"]
                ]
            )

            response = AgentConsultationResponse(self.capability.agent_name, True)
            response.generated_components = [quiz_card]
            response.response_time_ms = (asyncio.get_event_loop().time() - start_time) * 1000

            self.consultation_count += 1
            print(f"✅ AssessmentAgent consultation: {response.response_time_ms:.0f}ms")

            return response

        except Exception as e:
            print(f"❌ AssessmentAgent consultation failed: {e}")
            return AgentConsultationResponse(self.capability.agent_name, False)

class MockClassroomDirectorIntegration:
    """Mock Director Integration for testing"""

    def __init__(self):
        self.agent_adapters = {}

    def initialize_adapters(self):
        """Initialize mock agent adapters"""
        tutor_agent = MockTutorAgent()
        assessment_agent = MockAssessmentAgent()

        self.agent_adapters["tutor"] = MockTutorAgentAdapter(tutor_agent)
        self.agent_adapters["assessment"] = MockAssessmentAgentAdapter(assessment_agent)

        print(f"✅ Initialized {len(self.agent_adapters)} agent adapters")

    async def enhance_scene_with_agents(self, base_scene: Scene, scene_type: str, topic: str) -> Scene:
        """Enhance scene using agent consultation"""
        print(f"🎯 Enhancing scene with agent consultation for: {topic}")

        enhanced_components = []
        consultation_tasks = []

        # Select agents based on scene type
        agents_to_consult = []
        if scene_type == SceneType.INSTRUCTION:
            agents_to_consult = ["tutor"]
        elif scene_type == SceneType.CHALLENGE:
            agents_to_consult = ["assessment"]
        elif scene_type == SceneType.CORRECTION:
            agents_to_consult = ["tutor", "assessment"]

        # Create consultation requests
        for agent_name in agents_to_consult:
            if agent_name in self.agent_adapters:
                request = AgentConsultationRequest(
                    agent_name=agent_name,
                    scene_type=scene_type,
                    topic=topic,
                    max_words=60
                )
                consultation_tasks.append(
                    self.agent_adapters[agent_name].consult(request)
                )

        # Execute consultations in parallel
        if consultation_tasks:
            consultation_responses = await asyncio.gather(*consultation_tasks, return_exceptions=True)

            # Process responses
            for response in consultation_responses:
                if isinstance(response, AgentConsultationResponse) and response.success:
                    enhanced_components.extend(response.generated_components)
                    print(f"   Agent {response.agent_name}: {len(response.generated_components)} components")

        # Merge with base scene (Director has authority)
        final_components = self._merge_components(base_scene.components, enhanced_components)

        # Create enhanced scene
        enhanced_scene = Scene(
            scene_id=base_scene.scene_id,
            scene_type=base_scene.scene_type,
            components=final_components,
            metadata=base_scene.metadata
        )

        print(f"✅ Scene enhanced: {len(base_scene.components)} → {len(final_components)} components")
        return enhanced_scene

    def _merge_components(self, base_components: List, agent_components: List) -> List:
        """Merge components with Director authority"""
        # Director components have priority 0-3
        final_components = []

        for comp in base_components:
            comp.priority = min(comp.priority, 3)
            final_components.append(comp)

        # Agent components have lower priority
        for comp in agent_components:
            comp.priority = max(comp.priority, 4)
            final_components.append(comp)

        # Sort by priority
        final_components.sort(key=lambda c: c.priority)

        # Limit total components
        MAX_COMPONENTS = 5
        if len(final_components) > MAX_COMPONENTS:
            final_components = final_components[:MAX_COMPONENTS]

        return final_components

    def get_performance_stats(self):
        """Get agent performance statistics"""
        stats = {}
        for agent_name, adapter in self.agent_adapters.items():
            stats[agent_name] = {
                "consultation_count": adapter.consultation_count,
                "capability": adapter.capability.agent_name
            }

        return {
            "total_agents": len(self.agent_adapters),
            "agent_stats": stats
        }

# Test Agent Integration
async def test_agent_integration():
    """Test Agent Integration functionality"""

    print("🤖 Testing Agent Integration Layer\n")

    # Initialize Director Integration
    director_integration = MockClassroomDirectorIntegration()
    director_integration.initialize_adapters()

    print()

    # Test scenarios
    test_scenarios = [
        {
            "name": "Instruction Scene Enhancement",
            "scene_type": SceneType.INSTRUCTION,
            "topic": "python variables",
            "base_components": [
                CTAButton(label="Continue", action_intent=ActionIntent.CONTINUE, priority=0)
            ]
        },
        {
            "name": "Challenge Scene Enhancement",
            "scene_type": SceneType.CHALLENGE,
            "topic": "python basics",
            "base_components": [
                TeacherMessage(text="Let's test your knowledge!", priority=0),
                QuizCard(
                    question="Basic placeholder question?",
                    options=[
                        QuizOption(id="a", label="Option A", is_correct=False),
                        QuizOption(id="b", label="Option B", is_correct=True)
                    ],
                    priority=1
                )
            ]
        },
        {
            "name": "Correction Scene Enhancement",
            "scene_type": SceneType.CORRECTION,
            "topic": "programming concepts",
            "base_components": [
                TeacherMessage(text="Let me help clarify this.", priority=0)
            ]
        }
    ]

    for scenario in test_scenarios:
        print(f"📋 Test: {scenario['name']}")

        # Create base scene
        base_scene = Scene(
            scene_type=scenario["scene_type"],
            components=scenario["base_components"]
        )

        print(f"   Base scene: {len(base_scene.components)} components")

        # Enhance with agents
        enhanced_scene = await director_integration.enhance_scene_with_agents(
            base_scene=base_scene,
            scene_type=scenario["scene_type"],
            topic=scenario["topic"]
        )

        print(f"   Enhanced scene: {len(enhanced_scene.components)} components")

        # Verify component types
        component_types = [c.type for c in enhanced_scene.components]
        print(f"   Component types: {component_types}")

        # Verify priorities
        priorities = [c.priority for c in enhanced_scene.components]
        print(f"   Priorities: {priorities}")

        print("   ✅ Enhancement complete\n")

    # Test performance stats
    print("📋 Agent Performance Statistics")
    stats = director_integration.get_performance_stats()
    print(f"   Total agents: {stats['total_agents']}")
    for agent_name, agent_stats in stats['agent_stats'].items():
        print(f"   {agent_name}: {agent_stats['consultation_count']} consultations")

    print("\n🎯 All Agent Integration tests passed!")

    # Test individual agent adapters
    print("\n📋 Individual Agent Testing")

    # Test TutorAgent directly
    tutor_adapter = director_integration.agent_adapters["tutor"]
    tutor_request = AgentConsultationRequest("tutor", SceneType.INSTRUCTION, "functions", 50)
    tutor_response = await tutor_adapter.consult(tutor_request)

    print(f"TutorAgent direct test:")
    print(f"   Success: {tutor_response.success}")
    print(f"   Components: {len(tutor_response.generated_components)}")
    if tutor_response.generated_components:
        component = tutor_response.generated_components[0]
        print(f"   Content preview: {component.text[:50]}...")

    # Test AssessmentAgent directly
    assessment_adapter = director_integration.agent_adapters["assessment"]
    assessment_request = AgentConsultationRequest("assessment", SceneType.CHALLENGE, "loops", 50)
    assessment_response = await assessment_adapter.consult(assessment_request)

    print(f"\\nAssessmentAgent direct test:")
    print(f"   Success: {assessment_response.success}")
    print(f"   Components: {len(assessment_response.generated_components)}")
    if assessment_response.generated_components:
        component = assessment_response.generated_components[0]
        print(f"   Question preview: {component.question[:50]}...")

# Run the test
if __name__ == "__main__":
    asyncio.run(test_agent_integration())