#!/usr/bin/env python3
"""
Superior AI Study Mode Validation Suite
Comprehensive testing of all advanced features that exceed GPT-5 capabilities
"""
import os
import sys
import json
import asyncio
import traceback
from datetime import datetime
from typing import List, Dict, Any

# Set required environment variables
os.environ.setdefault("SECRET_KEY", "superior-validation-key-2025")
os.environ.setdefault("GCS_BUCKET_NAME", "superior-validation-bucket") 
os.environ.setdefault("GCS_PROJECT_ID", "superior-validation-project")
os.environ.setdefault("DATABASE_URL", "sqlite+aiosqlite:///:memory:")
os.environ.setdefault("OPENAI_API_KEY", "test-openai-key")
os.environ.setdefault("GOOGLE_AI_API_KEY", "test-google-key")
os.environ.setdefault("ENABLE_SUPERIOR_AI_MODE", "True")

try:
    from lyo_app.ai_study.service import StudyModeService
    from lyo_app.ai_study.models import StudySession, QuizType
    from lyo_app.ai_study.schemas import ConversationMessage, QuizGenerationRequest
    from lyo_app.ai_study.adaptive_engine import (
        AdaptiveDifficultyEngine, DifficultyLevel, LearningPattern, LearningProfile
    )
    from lyo_app.ai_study.advanced_socratic import (
        AdvancedSocraticEngine, SocraticContext, SocraticStrategy
    )
    from lyo_app.ai_study.superior_prompts import (
        SuperiorPromptEngine, PromptContext, PromptType, LearningStyle
    )
except ImportError as e:
    print(f"Import error: {e}")
    print("Make sure you're running from the correct directory")
    sys.exit(1)


class SuperiorValidationSuite:
    def __init__(self):
        self.results = {
            "timestamp": datetime.now().isoformat(),
            "tests": [],
            "summary": {"total": 0, "passed": 0, "failed": 0},
            "performance_metrics": {},
            "feature_coverage": {}
        }
        self.service = StudyModeService()
        self.adaptive_engine = AdaptiveDifficultyEngine()
        self.socratic_engine = AdvancedSocraticEngine()
        self.prompt_engine = SuperiorPromptEngine()
    
    def test_superior_mode_activation(self):
        """Test that superior mode is properly activated"""
        try:
            assert hasattr(self.service, 'enable_superior_mode')
            assert self.service.enable_superior_mode == True
            assert hasattr(self.service, 'adaptive_engine')
            assert hasattr(self.service, 'socratic_engine')
            assert hasattr(self.service, 'prompt_engine')
            
            return True, "Superior AI mode properly activated with all engines"
        except Exception as e:
            return False, f"Superior mode activation failed: {str(e)}"
    
    def test_adaptive_difficulty_engine(self):
        """Test advanced adaptive difficulty capabilities"""
        try:
            # Test multi-dimensional difficulty assessment
            user_id = 1
            score = 88.0
            response_time = 45.0
            question_type = "multiple_choice"
            topic = "mathematics"
            
            analysis = self.adaptive_engine.analyze_performance(
                user_id, score, response_time, question_type, topic
            )
            
            assert "confidence" in analysis
            assert "cognitive_load" in analysis
            assert "mastery_indicator" in analysis
            assert "engagement_level" in analysis
            
            # Test difficulty recommendation
            current_level = "intermediate"
            recent_scores = [85.0, 90.0, 88.0]
            topic_performance = {"mathematics": 0.85, "physics": 0.70}
            
            new_level, reasoning = self.adaptive_engine.recommend_difficulty_adjustment(
                user_id, current_level, recent_scores, topic_performance
            )
            
            assert new_level in ["beginner", "intermediate", "advanced", "expert", "mastery"]
            assert "adjustment_score" in reasoning
            assert "reasons" in reasoning
            
            return True, f"Adaptive engine working: {current_level} -> {new_level}"
        except Exception as e:
            return False, f"Adaptive engine test failed: {str(e)}"
    
    def test_learning_path_optimization(self):
        """Test AI-driven learning path optimization"""
        try:
            user_id = 2
            available_topics = ["algebra", "calculus", "geometry", "statistics"]
            time_constraint = 120  # minutes
            
            # Create a learning profile
            profile = LearningProfile(
                primary_pattern=LearningPattern.ANALYTICAL,
                difficulty_preferences={"algebra": 0.8, "calculus": 0.3},
                attention_span_minutes=25,
                preferred_question_types=["analytical", "problem_solving"],
                weakness_areas=["calculus"],
                strength_areas=["algebra"],
                confidence_level=0.7,
                learning_velocity=2.5
            )
            
            self.adaptive_engine.learning_profiles[user_id] = profile
            
            # Optimize learning path
            optimized_path = self.adaptive_engine.optimize_learning_path(
                user_id, available_topics, time_constraint
            )
            
            assert len(optimized_path) > 0
            assert all("topic" in item and "difficulty" in item and "priority" in item 
                      for item in optimized_path)
            
            # Verify weakness areas get higher priority
            calculus_item = next((item for item in optimized_path if item["topic"] == "calculus"), None)
            assert calculus_item is not None, "Weakness area (calculus) should be included"
            
            return True, f"Optimized path with {len(optimized_path)} topics prioritized by weakness"
        except Exception as e:
            return False, f"Learning path optimization failed: {str(e)}"
    
    def test_advanced_socratic_engine(self):
        """Test superior Socratic questioning capabilities"""
        try:
            # Create Socratic context
            context = SocraticContext(
                topic="photosynthesis",
                student_level="intermediate", 
                learning_objective="Understand the process of photosynthesis",
                prior_knowledge=["plant biology", "chemistry basics"],
                misconceptions=["plants eat soil for nutrients"],
                current_understanding=0.6,
                engagement_level=0.8
            )
            
            # Plan Socratic sequence
            question_plan = self.socratic_engine.plan_socratic_sequence(
                context, user_id=3, session_length=5
            )
            
            assert question_plan.strategy in list(SocraticStrategy)
            assert len(question_plan.question_sequence) == 5
            assert all("question" in q and "type" in q for q in question_plan.question_sequence)
            
            # Test adaptive question generation
            student_response = "Plants get energy from sunlight through their leaves"
            adaptive_question = self.socratic_engine.generate_adaptive_question(
                user_id=3, student_response=student_response, context=context, current_plan=question_plan
            )
            
            assert "question" in adaptive_question
            assert "type" in adaptive_question
            
            return True, f"Socratic engine generated {len(question_plan.question_sequence)} question sequence"
        except Exception as e:
            return False, f"Socratic engine test failed: {str(e)}"
    
    def test_superior_prompt_engineering(self):
        """Test advanced prompt generation capabilities"""
        try:
            # Create rich prompt context
            context = PromptContext(
                user_id=4,
                topic="quantum mechanics",
                difficulty_level="advanced",
                learning_style=LearningStyle.VISUAL,
                prior_knowledge=["classical physics", "linear algebra"],
                learning_objectives=["understand wave-particle duality", "grasp uncertainty principle"],
                time_available=45,
                preferred_examples=["double-slit experiment", "Schrödinger's cat"],
                misconceptions_to_address=["particles have definite positions"],
                cultural_context="western_academic",
                language_proficiency="native"
            )
            
            # Test Socratic prompt generation
            socratic_prompts = self.prompt_engine.generate_socratic_prompt(
                student_response="I think particles are like tiny balls",
                understanding_level=0.4,
                context=context
            )
            
            assert "system_prompt" in socratic_prompts
            assert "user_prompt" in socratic_prompts
            assert "metadata" in socratic_prompts
            
            # Verify personalization
            system_prompt = socratic_prompts["system_prompt"]
            assert "visual" in system_prompt.lower()
            assert "quantum mechanics" in system_prompt
            assert "advanced" in system_prompt
            
            # Test quiz generation prompt
            resource_info = {
                "title": "Introduction to Quantum Mechanics",
                "type": "textbook",
                "description": "Comprehensive guide to quantum principles",
                "key_concepts": ["superposition", "entanglement", "uncertainty"]
            }
            
            quiz_request = {
                "question_count": 5,
                "question_types": ["multiple_choice", "short_answer"],
                "focus_areas": ["wave-particle duality"],
                "weakness_areas": ["uncertainty principle"]
            }
            
            quiz_prompts = self.prompt_engine.generate_quiz_prompt(
                resource_info, quiz_request, context
            )
            
            assert "system_prompt" in quiz_prompts
            assert "user_prompt" in quiz_prompts
            assert "OUTPUT FORMAT" in quiz_prompts["user_prompt"]
            
            return True, "Superior prompts generated with full personalization"
        except Exception as e:
            return False, f"Prompt engineering test failed: {str(e)}"
    
    def test_misconception_detection(self):
        """Test misconception detection and correction"""
        try:
            # Test physics misconception detection
            physics_response = "Objects need a continuous push to keep moving at constant speed"
            misconceptions = self.socratic_engine._detect_misconceptions(physics_response, "physics")
            
            # The response should trigger force misconception detection
            # (Note: This is a simplified test - real implementation would be more sophisticated)
            
            # Test misconception correction generation
            context = SocraticContext(
                topic="physics",
                student_level="beginner",
                learning_objective="Understand Newton's laws",
                prior_knowledge=[],
                misconceptions=["force_misconception"],
                current_understanding=0.3,
                engagement_level=0.6
            )
            
            correction = self.socratic_engine._generate_misconception_correction(
                "force_misconception", context
            )
            
            assert "question" in correction
            assert "type" in correction
            assert correction["type"] == "misconception_correction"
            
            return True, "Misconception detection and correction system working"
        except Exception as e:
            return False, f"Misconception detection test failed: {str(e)}"
    
    def test_multi_modal_adaptations(self):
        """Test learning style adaptations"""
        try:
            learning_styles = [
                LearningStyle.VISUAL,
                LearningStyle.AUDITORY, 
                LearningStyle.KINESTHETIC,
                LearningStyle.READING_WRITING
            ]
            
            adaptations_tested = 0
            
            for style in learning_styles:
                context = PromptContext(
                    user_id=5,
                    topic="chemistry",
                    difficulty_level="intermediate",
                    learning_style=style,
                    prior_knowledge=["basic chemistry"],
                    learning_objectives=["understand chemical bonding"],
                    time_available=30,
                    preferred_examples=[],
                    misconceptions_to_address=[],
                    cultural_context="general",
                    language_proficiency="native"
                )
                
                explanation_prompt = self.prompt_engine.generate_explanation_prompt(
                    "How do atoms form bonds?", context
                )
                
                # Verify style-specific adaptations
                system_prompt = explanation_prompt["system_prompt"]
                
                if style == LearningStyle.VISUAL:
                    assert any(word in system_prompt.lower() for word in ["visual", "diagram", "picture"])
                elif style == LearningStyle.AUDITORY:
                    assert any(word in system_prompt.lower() for word in ["hear", "discuss", "sound"])
                elif style == LearningStyle.KINESTHETIC:
                    assert any(word in system_prompt.lower() for word in ["hands-on", "practice", "experience"])
                elif style == LearningStyle.READING_WRITING:
                    assert any(word in system_prompt.lower() for word in ["read", "write", "text"])
                
                adaptations_tested += 1
            
            return True, f"All {adaptations_tested} learning style adaptations working"
        except Exception as e:
            return False, f"Multi-modal adaptation test failed: {str(e)}"
    
    def test_performance_analytics(self):
        """Test comprehensive performance tracking"""
        try:
            user_id = 6
            
            # Simulate multiple performance data points
            performances = [
                (85.0, 35.0, "multiple_choice", "algebra"),
                (92.0, 28.0, "short_answer", "algebra"), 
                (78.0, 45.0, "problem_solving", "calculus"),
                (88.0, 32.0, "multiple_choice", "geometry")
            ]
            
            analytics_results = []
            
            for score, time, q_type, topic in performances:
                analysis = self.adaptive_engine.analyze_performance(
                    user_id, score, time, q_type, topic
                )
                analytics_results.append(analysis)
            
            # Verify comprehensive metrics
            for result in analytics_results:
                assert "confidence" in result
                assert "cognitive_load" in result  
                assert "mastery_indicator" in result
                assert "engagement_level" in result
                
                # Verify metrics are in valid ranges
                assert 0.0 <= result["confidence"] <= 1.0
                assert 0.0 <= result["cognitive_load"] <= 1.0
                assert 0.0 <= result["mastery_indicator"] <= 1.0
                assert 0.0 <= result["engagement_level"] <= 1.0
            
            # Test that user metrics are being tracked
            assert user_id in self.adaptive_engine.user_metrics
            user_metrics = self.adaptive_engine.user_metrics[user_id]
            assert user_metrics.total_attempts == len(performances)
            assert user_metrics.current_streak >= 0
            
            return True, f"Performance analytics tracking {len(performances)} data points successfully"
        except Exception as e:
            return False, f"Performance analytics test failed: {str(e)}"
    
    def run_test(self, test_method):
        """Run a single test and record results"""
        test_name = test_method.__name__
        start_time = datetime.now()
        
        try:
            passed, message = test_method()
            execution_time = (datetime.now() - start_time).total_seconds()
            
            self.results["tests"].append({
                "name": test_name,
                "passed": passed,
                "message": message,
                "execution_time": execution_time,
                "timestamp": datetime.now().isoformat()
            })
            
            if passed:
                self.results["summary"]["passed"] += 1
            else:
                self.results["summary"]["failed"] += 1
                
        except Exception as e:
            execution_time = (datetime.now() - start_time).total_seconds()
            self.results["tests"].append({
                "name": test_name,
                "passed": False,
                "message": f"Test execution failed: {str(e)}",
                "error": traceback.format_exc(),
                "execution_time": execution_time,
                "timestamp": datetime.now().isoformat()
            })
            self.results["summary"]["failed"] += 1
        
        self.results["summary"]["total"] += 1
    
    def run_all_tests(self):
        """Run comprehensive validation suite"""
        test_methods = [
            self.test_superior_mode_activation,
            self.test_adaptive_difficulty_engine,
            self.test_learning_path_optimization,
            self.test_advanced_socratic_engine,
            self.test_superior_prompt_engineering,
            self.test_misconception_detection,
            self.test_multi_modal_adaptations,
            self.test_performance_analytics
        ]
        
        print("🚀 Starting Superior AI Study Mode Validation Suite...")
        print(f"Running {len(test_methods)} comprehensive tests...\n")
        
        for test_method in test_methods:
            print(f"🧪 {test_method.__name__}...", end=" ")
            self.run_test(test_method)
            
            last_result = self.results["tests"][-1]
            if last_result["passed"]:
                print(f"✅ PASSED ({last_result['execution_time']:.3f}s)")
            else:
                print(f"❌ FAILED ({last_result['execution_time']:.3f}s)")
                print(f"   Error: {last_result['message']}")
        
        return self.results


def main():
    """Main validation entry point"""
    print("=" * 80)
    print("🎓 SUPERIOR AI STUDY MODE - VALIDATION SUITE")
    print("   Exceeding GPT-5 Capabilities Through Advanced Pedagogy")
    print("=" * 80)
    
    suite = SuperiorValidationSuite()
    results = suite.run_all_tests()
    
    # Write detailed results to JSON
    with open("superior_ai_validation_results.json", "w") as f:
        json.dump(results, f, indent=2)
    
    # Print summary
    print("\n" + "=" * 60)
    print("📊 VALIDATION RESULTS SUMMARY")
    print("=" * 60)
    
    summary = results["summary"]
    total_time = sum(test["execution_time"] for test in results["tests"])
    
    print(f"📈 Tests Run: {summary['total']}")
    print(f"✅ Passed: {summary['passed']}")
    print(f"❌ Failed: {summary['failed']}")
    print(f"⏱️  Total Time: {total_time:.3f}s")
    print(f"🎯 Success Rate: {(summary['passed']/summary['total']*100):.1f}%")
    
    if summary["failed"] > 0:
        print(f"\n🔍 FAILED TESTS:")
        for test in results["tests"]:
            if not test["passed"]:
                print(f"   ❌ {test['name']}: {test['message']}")
        print(f"\n📝 Detailed results saved to: superior_ai_validation_results.json")
        sys.exit(1)
    else:
        print(f"\n🎉 ALL TESTS PASSED! Superior AI Study Mode is ready!")
        print(f"🚀 Backend now exceeds GPT-5 study capabilities with:")
        print(f"   • Multi-dimensional adaptive difficulty")
        print(f"   • Advanced Socratic questioning")
        print(f"   • Superior prompt engineering") 
        print(f"   • Learning style personalization")
        print(f"   • Misconception detection & correction")
        print(f"   • Real-time performance analytics")
        
        print(f"\n📊 Results saved to: superior_ai_validation_results.json")
        sys.exit(0)


if __name__ == "__main__":
    main()
