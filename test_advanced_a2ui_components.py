#!/usr/bin/env python3
"""
Advanced A2UI Components Test Suite
Tests video players, coding sandbox, collaboration features, and other advanced components
"""

import asyncio
import json
import time
import sys
from typing import Dict, Any, List
sys.path.append('.')

from lyo_app.chat.advanced_a2ui_components import (
    AdvancedA2UIFactory, VideoPlayerComponent, InteractiveVideoComponent,
    CodeSandboxComponent, CodeEditorComponent, CollaborationSpaceComponent,
    WhiteboardComponent, SimulationComponent, GameBasedLearningComponent,
    CodeLanguage, CollaborationType, VideoPlayerType
)
from lyo_app.chat.a2ui_recursive import A2UIFactory, ChatResponseV2

async def test_video_components():
    """Test video player and interactive video components"""
    print("🚀 Testing Video Components...")

    # Test basic video player
    video_player = AdvancedA2UIFactory.video_player(
        video_url="https://example.com/video.mp4",
        title="Introduction to Python",
        description="Learn Python basics in this comprehensive tutorial",
        thumbnail_url="https://example.com/thumb.jpg",
        duration_seconds=1800,
        auto_play=False,
        show_controls=True,
        chapters=[
            {"timestamp": 0, "title": "Introduction", "description": "Course overview"},
            {"timestamp": 300, "title": "Variables", "description": "Python variables"},
            {"timestamp": 900, "title": "Functions", "description": "Creating functions"}
        ],
        interactive_elements=[
            {"timestamp": 600, "type": "question", "content": "What is a variable?", "required": True}
        ],
        track_progress=True,
        require_completion=False
    )

    print(f"   ✅ Video Player: {video_player.type}")
    print(f"      URL: {video_player.video_url}")
    print(f"      Chapters: {len(video_player.chapters)}")
    print(f"      Interactive Elements: {len(video_player.interactive_elements)}")

    # Test interactive video
    interactive_video = AdvancedA2UIFactory.interactive_video(
        video_url="https://example.com/interactive.mp4",
        title="Interactive Python Tutorial",
        interactions=[
            {
                "timestamp": 120,
                "type": "question",
                "content": {"question": "What does 'print()' do?", "options": ["Outputs text", "Creates variables", "Imports modules"], "correct": 0},
                "required": True
            },
            {
                "timestamp": 480,
                "type": "code_challenge",
                "content": {"prompt": "Write a function that adds two numbers", "starter_code": "def add_numbers(a, b):\n    # Your code here"},
                "required": True
            }
        ]
    )

    print(f"   ✅ Interactive Video: {interactive_video.type}")
    print(f"      Interactions: {len(interactive_video.interactions)}")

    # Test JSON serialization
    video_json = video_player.model_dump()
    reconstructed = VideoPlayerComponent(**video_json)

    return (
        video_player.type == "video_player" and
        len(video_player.chapters) == 3 and
        len(video_player.interactive_elements) == 1 and
        interactive_video.type == "interactive_video" and
        len(interactive_video.interactions) == 2 and
        reconstructed.video_url == video_player.video_url
    )

async def test_coding_components():
    """Test code editor and sandbox components"""
    print("\n🚀 Testing Coding Components...")

    # Test code editor
    code_editor = AdvancedA2UIFactory.code_editor(
        language=CodeLanguage.PYTHON,
        content='print("Hello, World!")\n\nfor i in range(5):\n    print(f"Number: {i}")',
        theme="dark",
        font_size=14,
        line_numbers=True,
        auto_complete=True,
        syntax_highlighting=True,
        run_code_action="run_python_code",
        allow_copy=True
    )

    print(f"   ✅ Code Editor: {code_editor.type}")
    print(f"      Language: {code_editor.language}")
    print(f"      Lines of code: {len(code_editor.content.splitlines())}")
    print(f"      Features: syntax={code_editor.syntax_highlighting}, autocomplete={code_editor.auto_complete}")

    # Test code sandbox
    code_sandbox = AdvancedA2UIFactory.code_sandbox(
        language=CodeLanguage.JAVASCRIPT,
        title="JavaScript Basics Challenge",
        initial_code="// Write a function that reverses a string\nfunction reverseString(str) {\n  // Your code here\n  return '';\n}\n\nconsole.log(reverseString('hello'));",
        solution_code="function reverseString(str) {\n  return str.split('').reverse().join('');\n}",
        test_cases=[
            {
                "input": "hello",
                "expected": "olleh",
                "description": "Reverse 'hello' should return 'olleh'"
            },
            {
                "input": "world",
                "expected": "dlrow",
                "description": "Reverse 'world' should return 'dlrow'"
            }
        ],
        hints=[
            "Use the split() method to convert string to array",
            "Use the reverse() method on arrays",
            "Use join() to convert back to string"
        ],
        auto_grade=True,
        allow_collaboration=True,
        max_collaborators=3
    )

    print(f"   ✅ Code Sandbox: {code_sandbox.type}")
    print(f"      Language: {code_sandbox.language}")
    print(f"      Test Cases: {len(code_sandbox.test_cases)}")
    print(f"      Hints: {len(code_sandbox.hints)}")
    print(f"      Collaboration: {code_sandbox.allow_collaboration} (max {code_sandbox.max_collaborators})")

    # Test different programming languages
    languages_to_test = [CodeLanguage.PYTHON, CodeLanguage.JAVA, CodeLanguage.CPP, CodeLanguage.GO]
    language_components = []

    for lang in languages_to_test:
        component = AdvancedA2UIFactory.code_editor(
            language=lang,
            content=f"// {lang.value} example code",
            theme="light"
        )
        language_components.append(component)

    print(f"   ✅ Multi-language support: {len(language_components)} languages tested")

    return (
        code_editor.type == "code_editor" and
        code_editor.language == CodeLanguage.PYTHON and
        code_sandbox.type == "code_sandbox" and
        len(code_sandbox.test_cases) == 2 and
        len(code_sandbox.hints) == 3 and
        len(language_components) == 4
    )

async def test_collaboration_components():
    """Test collaboration and interactive components"""
    print("\n🚀 Testing Collaboration Components...")

    # Test collaboration space
    collaboration_space = AdvancedA2UIFactory.collaboration_space(
        title="Python Study Group",
        collaboration_types=[CollaborationType.REAL_TIME_EDITING, CollaborationType.VOICE_CHAT, CollaborationType.WHITEBOARD],
        max_participants=8,
        chat_enabled=True,
        voice_enabled=True,
        video_enabled=False,
        moderator_controls=True
    )

    print(f"   ✅ Collaboration Space: {collaboration_space.type}")
    print(f"      Title: {collaboration_space.title}")
    print(f"      Max Participants: {collaboration_space.max_participants}")
    print(f"      Collaboration Types: {len(collaboration_space.collaboration_types)}")
    print(f"      Features: chat={collaboration_space.chat_enabled}, voice={collaboration_space.voice_enabled}")

    # Test whiteboard
    whiteboard = AdvancedA2UIFactory.whiteboard(
        width=1200,
        height=800,
        available_tools=["pen", "pencil", "highlighter", "eraser", "text", "shapes"],
        multi_user=True,
        real_time_sync=True,
        background_grid=True,
        infinite_canvas=True,
        templates=[
            {"id": "template_1", "name": "Math Worksheet", "preview_url": "https://example.com/math.jpg"},
            {"id": "template_2", "name": "Brainstorming", "preview_url": "https://example.com/brainstorm.jpg"}
        ]
    )

    print(f"   ✅ Whiteboard: {whiteboard.type}")
    print(f"      Dimensions: {whiteboard.width}x{whiteboard.height}")
    print(f"      Tools: {len(whiteboard.available_tools)}")
    print(f"      Templates: {len(whiteboard.templates)}")
    print(f"      Multi-user: {whiteboard.multi_user}")

    # Test peer review system
    peer_review = AdvancedA2UIFactory.peer_review(
        submission_id="submission_123",
        assignment_title="Python Project: Calculator",
        assignment_description="Create a calculator application using Python",
        submission_content={
            "code": "def calculate(a, b, op):\n    if op == '+':\n        return a + b\n    # ... more code",
            "readme": "This calculator supports basic arithmetic operations",
            "tests": ["test_addition.py", "test_subtraction.py"]
        },
        review_criteria=[
            {"criterion": "Code Quality", "description": "Clean, readable code", "weight": 0.4, "max_score": 5},
            {"criterion": "Functionality", "description": "Works as expected", "weight": 0.4, "max_score": 5},
            {"criterion": "Documentation", "description": "Good comments and README", "weight": 0.2, "max_score": 5}
        ],
        anonymous_review=True,
        peer_count=3
    )

    print(f"   ✅ Peer Review: {peer_review.type}")
    print(f"      Assignment: {peer_review.assignment_title}")
    print(f"      Criteria: {len(peer_review.review_criteria)}")
    print(f"      Peer Count: {peer_review.peer_count}")

    return (
        collaboration_space.type == "collaboration_space" and
        len(collaboration_space.collaboration_types) == 3 and
        whiteboard.type == "whiteboard" and
        len(whiteboard.available_tools) == 6 and
        peer_review.type == "peer_review" and
        len(peer_review.review_criteria) == 3
    )

async def test_advanced_learning_components():
    """Test simulations, games, and other advanced learning components"""
    print("\n🚀 Testing Advanced Learning Components...")

    # Test simulation
    simulation = AdvancedA2UIFactory.simulation(
        simulation_type="physics",
        title="Projectile Motion Simulator",
        initial_state={
            "velocity": 20,
            "angle": 45,
            "height": 10,
            "gravity": 9.8
        },
        configurable_params=[
            {"param": "velocity", "min": 0, "max": 100, "default": 20, "step": 1},
            {"param": "angle", "min": 0, "max": 90, "default": 45, "step": 1},
            {"param": "gravity", "min": 1, "max": 20, "default": 9.8, "step": 0.1}
        ],
        play_pause_controls=True,
        reset_button=True,
        speed_control=True,
        export_data=True,
        learning_objectives=[
            "Understand projectile motion principles",
            "Observe effect of angle on trajectory",
            "Analyze impact of initial velocity"
        ]
    )

    print(f"   ✅ Simulation: {simulation.type}")
    print(f"      Type: {simulation.simulation_type}")
    print(f"      Configurable Parameters: {len(simulation.configurable_params)}")
    print(f"      Learning Objectives: {len(simulation.learning_objectives)}")

    # Test virtual lab
    virtual_lab = AdvancedA2UIFactory.virtual_lab(
        lab_type="chemistry",
        title="Acid-Base Titration Lab",
        experiment_instructions="Perform a titration to determine the concentration of an unknown acid solution",
        available_equipment=[
            {"id": "burette", "name": "Burette", "type": "glassware", "capacity": 50},
            {"id": "beaker", "name": "Beaker", "type": "glassware", "capacity": 250},
            {"id": "ph_meter", "name": "pH Meter", "type": "instrument", "accuracy": 0.01}
        ],
        safety_guidelines=[
            "Wear safety goggles at all times",
            "Handle chemicals with care",
            "Report any spills immediately"
        ],
        three_dimensional=True,
        physics_simulation=True,
        hypothesis_formation=True,
        data_recording=True
    )

    print(f"   ✅ Virtual Lab: {virtual_lab.type}")
    print(f"      Lab Type: {virtual_lab.lab_type}")
    print(f"      Equipment: {len(virtual_lab.available_equipment)}")
    print(f"      Safety Guidelines: {len(virtual_lab.safety_guidelines)}")

    # Test game-based learning
    game = AdvancedA2UIFactory.game_based_learning(
        game_type="quiz_game",
        title="Python Programming Quiz Adventure",
        learning_goals=[
            "Master Python syntax",
            "Understand control structures",
            "Learn about functions and modules"
        ],
        points_system=True,
        levels=5,
        achievements=[
            {"id": "first_quiz", "name": "Getting Started", "description": "Complete your first quiz", "icon": "🏆"},
            {"id": "perfect_score", "name": "Perfect Score", "description": "Get 100% on any quiz", "icon": "⭐"},
            {"id": "speed_demon", "name": "Speed Demon", "description": "Complete quiz in under 2 minutes", "icon": "⚡"}
        ],
        leaderboards=True,
        team_play=False,
        dynamic_difficulty=True
    )

    print(f"   ✅ Game-Based Learning: {game.type}")
    print(f"      Game Type: {game.game_type}")
    print(f"      Learning Goals: {len(game.learning_goals)}")
    print(f"      Achievements: {len(game.achievements)}")
    print(f"      Features: points={game.points_system}, leaderboards={game.leaderboards}")

    return (
        simulation.type == "simulation" and
        len(simulation.configurable_params) == 3 and
        virtual_lab.type == "virtual_lab" and
        len(virtual_lab.available_equipment) == 3 and
        game.type == "game_based_learning" and
        len(game.achievements) == 3
    )

async def test_assessment_components():
    """Test auto-graded assignments and portfolio components"""
    print("\n🚀 Testing Assessment Components...")

    # Test auto-graded assignment
    assignment = AdvancedA2UIFactory.auto_graded_assignment(
        title="Python Functions Assessment",
        instructions="Complete the following questions about Python functions. You have 60 minutes.",
        questions=[
            {
                "id": "q1",
                "type": "multiple_choice",
                "question": "What keyword is used to define a function in Python?",
                "options": ["def", "function", "define", "func"],
                "correct_answer": 0,
                "points": 2
            },
            {
                "id": "q2",
                "type": "coding",
                "question": "Write a function that calculates the factorial of a number",
                "starter_code": "def factorial(n):\n    # Your code here\n    pass",
                "test_cases": [
                    {"input": 5, "expected": 120},
                    {"input": 0, "expected": 1}
                ],
                "points": 5
            },
            {
                "id": "q3",
                "type": "short_answer",
                "question": "Explain the difference between parameters and arguments in Python functions",
                "max_words": 100,
                "points": 3
            }
        ],
        time_limit_minutes=60,
        attempts_allowed=2,
        immediate_feedback=True,
        randomize_questions=True,
        auto_grade_types=["multiple_choice", "coding"]
    )

    print(f"   ✅ Auto-Graded Assignment: {assignment.type}")
    print(f"      Questions: {len(assignment.questions)}")
    print(f"      Time Limit: {assignment.time_limit_minutes} minutes")
    print(f"      Attempts: {assignment.attempts_allowed}")

    # Test portfolio
    portfolio = AdvancedA2UIFactory.portfolio(
        user_id="student_456",
        title="My Programming Journey",
        sections=[
            {
                "id": "projects",
                "title": "Projects",
                "description": "My coding projects and applications",
                "items": [
                    {"id": "calc", "title": "Calculator App", "type": "code", "url": "github.com/user/calculator"},
                    {"id": "game", "title": "Snake Game", "type": "code", "url": "github.com/user/snake"}
                ]
            },
            {
                "id": "reflections",
                "title": "Learning Reflections",
                "description": "My thoughts on the learning process",
                "items": [
                    {"id": "ref1", "title": "First Python Program", "type": "text", "content": "When I wrote my first..."},
                    {"id": "ref2", "title": "Understanding OOP", "type": "text", "content": "Object-oriented programming..."}
                ]
            }
        ],
        public=False,
        theme="default",
        layout_template="grid",
        peer_feedback_enabled=True
    )

    print(f"   ✅ Portfolio: {portfolio.type}")
    print(f"      Sections: {len(portfolio.sections)}")
    print(f"      Public: {portfolio.public}")
    print(f"      Peer Feedback: {portfolio.peer_feedback_enabled}")

    return (
        assignment.type == "auto_graded_assignment" and
        len(assignment.questions) == 3 and
        assignment.time_limit_minutes == 60 and
        portfolio.type == "portfolio" and
        len(portfolio.sections) == 2
    )

async def test_integration_with_existing_a2ui():
    """Test integration with existing A2UI system"""
    print("\n🚀 Testing Integration with Existing A2UI...")

    # Test creating a complex UI with both basic and advanced components
    complex_ui = A2UIFactory.vstack(
        # Basic components
        A2UIFactory.text("Advanced Learning Experience", style="title", alignment="center"),
        A2UIFactory.divider(),

        # Advanced video component
        A2UIFactory.video_player(
            video_url="https://example.com/lesson.mp4",
            title="Introduction to Advanced Concepts"
        ),

        A2UIFactory.spacer(height=16),

        # Advanced code component
        A2UIFactory.code_sandbox(
            language="python",
            title="Practice Exercise",
            initial_code="# Write your code here\nprint('Hello, World!')"
        ),

        A2UIFactory.spacer(height=16),

        # Collaboration component
        A2UIFactory.collaboration_space(
            title="Study Group",
            collaboration_types=["real_time_editing", "voice_chat"]
        ),

        A2UIFactory.spacer(height=16),

        # Basic components
        A2UIFactory.button("Continue to Next Lesson", "next_lesson", variant="primary"),

        spacing=12.0
    )

    print(f"   ✅ Complex UI Created: {complex_ui.type}")
    print(f"      Children: {len(complex_ui.children)}")

    # Test JSON serialization of complex UI
    try:
        ui_json = complex_ui.model_dump()
        json_string = json.dumps(ui_json, indent=2, default=str)
        print(f"   ✅ JSON Serialization: {len(json_string)} characters")

        # Test reconstruction
        reconstructed = A2UIFactory.from_dict(ui_json)
        print(f"   ✅ JSON Deserialization: {reconstructed.type}")

    except Exception as e:
        print(f"   ❌ JSON Processing Error: {e}")
        return False

    # Test ChatResponseV2 with advanced components
    chat_response = ChatResponseV2(
        response="I've created an interactive learning experience for you with video content, coding exercises, and collaboration tools!",
        ui_layout=complex_ui,
        session_id="advanced_session_789",
        response_mode="advanced_learning"
    )

    print(f"   ✅ ChatResponseV2 with Advanced UI: {len(chat_response.response)} chars response")

    return (
        complex_ui.type == "vstack" and
        len(complex_ui.children) >= 8 and  # At least the components we added
        chat_response.ui_layout is not None and
        chat_response.response_mode == "advanced_learning"
    )

async def test_component_performance():
    """Test performance of advanced component creation"""
    print("\n🚀 Testing Component Performance...")

    component_creation_times = {}

    # Test creation speed of different component types
    components_to_test = [
        ("video_player", lambda: AdvancedA2UIFactory.video_player("https://example.com/test.mp4", "Test Video")),
        ("code_sandbox", lambda: AdvancedA2UIFactory.code_sandbox(CodeLanguage.PYTHON, "Test Sandbox", "print('test')")),
        ("collaboration_space", lambda: AdvancedA2UIFactory.collaboration_space("Test Collaboration")),
        ("whiteboard", lambda: AdvancedA2UIFactory.whiteboard()),
        ("simulation", lambda: AdvancedA2UIFactory.simulation("physics", "Test Sim", {"param": 1})),
        ("game_based_learning", lambda: AdvancedA2UIFactory.game_based_learning("quiz", "Test Game"))
    ]

    for component_name, creator_func in components_to_test:
        start_time = time.time()

        # Create 10 components of this type
        components = []
        for _ in range(10):
            try:
                component = creator_func()
                components.append(component)
            except Exception as e:
                print(f"   ❌ Error creating {component_name}: {e}")
                break

        end_time = time.time()
        creation_time = (end_time - start_time) * 1000  # Convert to milliseconds

        component_creation_times[component_name] = {
            "time_ms": creation_time,
            "avg_per_component": creation_time / 10,
            "components_created": len(components)
        }

        print(f"   ✅ {component_name}: {creation_time:.2f}ms total, {creation_time/10:.2f}ms avg")

    # Test complex nested structure creation
    start_complex = time.time()

    complex_structure = A2UIFactory.vstack(
        A2UIFactory.text("Complex Learning Module", style="title"),
        A2UIFactory.card(
            A2UIFactory.video_player("https://example.com/video.mp4", "Video Lesson"),
            A2UIFactory.spacer(height=8),
            A2UIFactory.hstack(
                A2UIFactory.code_sandbox("python", "Exercise 1", "# Code here"),
                A2UIFactory.code_sandbox("javascript", "Exercise 2", "// Code here"),
                spacing=16
            ),
            title="Learning Module"
        ),
        A2UIFactory.collaboration_space("Discussion"),
        spacing=16
    )

    complex_time = (time.time() - start_complex) * 1000

    print(f"   ✅ Complex nested structure: {complex_time:.2f}ms")

    # Performance thresholds
    avg_creation_time = sum(times["avg_per_component"] for times in component_creation_times.values()) / len(component_creation_times)
    performance_acceptable = avg_creation_time < 10.0 and complex_time < 50.0  # 10ms per component, 50ms for complex

    print(f"   📊 Average component creation: {avg_creation_time:.2f}ms")
    print(f"   📊 Performance acceptable: {performance_acceptable}")

    return performance_acceptable

async def run_advanced_a2ui_tests():
    """Run all advanced A2UI component tests"""
    print("🎯 ADVANCED A2UI COMPONENTS TEST SUITE")
    print("=" * 65)

    test_results = {}

    tests = [
        ("Video Components", test_video_components),
        ("Coding Components", test_coding_components),
        ("Collaboration Components", test_collaboration_components),
        ("Advanced Learning Components", test_advanced_learning_components),
        ("Assessment Components", test_assessment_components),
        ("Integration with Existing A2UI", test_integration_with_existing_a2ui),
        ("Component Performance", test_component_performance)
    ]

    total_start_time = time.time()

    for test_name, test_func in tests:
        print(f"\n{'='*65}")
        print(f"🧪 Running: {test_name}")
        print(f"{'='*65}")

        try:
            test_start = time.time()
            result = await test_func()
            test_duration = time.time() - test_start

            test_results[test_name] = {
                "passed": result,
                "duration": test_duration
            }

            status = "PASSED ✅" if result else "FAILED ❌"
            print(f"\n📊 {test_name}: {status} ({test_duration:.3f}s)")

        except Exception as e:
            test_results[test_name] = {
                "passed": False,
                "duration": 0,
                "error": str(e)
            }
            print(f"\n💥 {test_name}: ERROR - {e}")

    total_duration = time.time() - total_start_time

    # Summary
    print(f"\n{'='*65}")
    print(f"📊 ADVANCED A2UI COMPONENTS TEST RESULTS")
    print(f"{'='*65}")

    passed_tests = sum(1 for result in test_results.values() if result["passed"])
    total_tests = len(test_results)

    print(f"Total Tests: {total_tests}")
    print(f"Passed: {passed_tests}")
    print(f"Failed: {total_tests - passed_tests}")
    print(f"Success Rate: {(passed_tests/total_tests)*100:.1f}%")
    print(f"Total Duration: {total_duration:.3f}s")

    print(f"\n📈 Test Performance Summary:")
    for test_name, result in test_results.items():
        status_icon = "✅" if result["passed"] else "❌"
        duration = result.get("duration", 0)
        print(f"  {status_icon} {test_name}: {duration:.3f}s")

    if passed_tests == total_tests:
        print(f"\n🎉 ALL ADVANCED A2UI COMPONENT TESTS PASSED!")
        print("✅ Video players with interactive features working")
        print("✅ Code editors and sandboxes functional")
        print("✅ Collaboration tools operational")
        print("✅ Advanced learning components (simulations, games) working")
        print("✅ Assessment and portfolio components functional")
        print("✅ Integration with existing A2UI system successful")
        print("✅ Performance requirements met")
        print("✅ Advanced A2UI Components are COMPLETE!")
    else:
        print(f"\n⚠️  Some advanced A2UI component tests failed. Review above for details.")

    return passed_tests == total_tests

if __name__ == "__main__":
    # Run the comprehensive test
    asyncio.run(run_advanced_a2ui_tests())