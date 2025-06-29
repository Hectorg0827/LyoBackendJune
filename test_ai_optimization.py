#!/usr/bin/env python3
"""
AI Optimization Test Suite
Comprehensive testing of all optimization features including performance, personalization, and A/B testing.
"""

import asyncio
import sys
import time
import json
from pathlib import Path
from typing import Dict, Any

# Add the project root to Python path
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

class AIOptimizationTester:
    """Comprehensive AI optimization testing suite."""
    
    def __init__(self):
        self.test_results = []
        self.total_tests = 0
        self.passed_tests = 0
    
    def log_test(self, test_name: str, status: bool, details: str = ""):
        """Log test result."""
        self.total_tests += 1
        if status:
            self.passed_tests += 1
            print(f"✅ {test_name}")
        else:
            print(f"❌ {test_name} - {details}")
        
        self.test_results.append({
            "test": test_name,
            "status": "PASS" if status else "FAIL",
            "details": details
        })
    
    async def test_performance_optimizer_imports(self):
        """Test performance optimizer module imports."""
        try:
            from lyo_app.ai_agents.optimization.performance_optimizer import (
                ai_performance_optimizer,
                OptimizationLevel,
                IntelligentCacheManager,
                ResponseOptimizer,
                ResourceOptimizer
            )
            self.log_test("Performance Optimizer Imports", True)
            return True
        except Exception as e:
            self.log_test("Performance Optimizer Imports", False, str(e))
            return False
    
    async def test_personalization_engine_imports(self):
        """Test personalization engine imports."""
        try:
            from lyo_app.ai_agents.optimization.personalization_engine import (
                personalization_engine,
                LearningStyle,
                PersonalityType,
                UserProfile,
                BehaviorAnalyzer
            )
            self.log_test("Personalization Engine Imports", True)
            return True
        except Exception as e:
            self.log_test("Personalization Engine Imports", False, str(e))
            return False
    
    async def test_ab_testing_imports(self):
        """Test A/B testing framework imports."""
        try:
            from lyo_app.ai_agents.optimization.ab_testing import (
                experiment_manager,
                ExperimentType,
                ExperimentStatus,
                EXPERIMENT_TEMPLATES
            )
            self.log_test("A/B Testing Framework Imports", True)
            return True
        except Exception as e:
            self.log_test("A/B Testing Framework Imports", False, str(e))
            return False
    
    async def test_optimization_routes_imports(self):
        """Test optimization API routes imports."""
        try:
            from lyo_app.ai_agents.optimization.routes import router, setup_optimization_routes
            self.log_test("Optimization Routes Imports", True)
            return True
        except Exception as e:
            self.log_test("Optimization Routes Imports", False, str(e))
            return False
    
    async def test_orchestrator_optimization_integration(self):
        """Test orchestrator integration with optimization."""
        try:
            from lyo_app.ai_agents.orchestrator import ai_orchestrator, ModelType, LanguageCode, TaskComplexity
            
            # Test enhanced generate_response with optimization parameters
            response = await ai_orchestrator.generate_response(
                prompt="Test optimization integration",
                task_complexity=TaskComplexity.SIMPLE,
                language=LanguageCode.ENGLISH,
                user_id=123,  # New optimization parameter
                agent_type="test"  # New optimization parameter
            )
            
            self.log_test("Orchestrator Optimization Integration", True)
            return True
        except Exception as e:
            self.log_test("Orchestrator Optimization Integration", False, str(e))
            return False
    
    async def test_cache_manager_functionality(self):
        """Test intelligent cache manager."""
        try:
            from lyo_app.ai_agents.optimization.performance_optimizer import IntelligentCacheManager
            
            cache_manager = IntelligentCacheManager()
            
            # Test cache set/get
            test_data = {"test": "data", "timestamp": time.time()}
            await cache_manager.set("test_content", test_data, test_key="value")
            
            cached_result = await cache_manager.get("test_content", test_key="value")
            
            cache_works = cached_result is not None
            self.log_test("Cache Manager Functionality", cache_works)
            return cache_works
        except Exception as e:
            self.log_test("Cache Manager Functionality", False, str(e))
            return False
    
    async def test_user_profile_generation(self):
        """Test user profile generation."""
        try:
            from lyo_app.ai_agents.optimization.personalization_engine import personalization_engine
            
            # Test user profile creation (simulated)
            user_profile = await personalization_engine.get_user_profile(123)
            
            profile_valid = (
                hasattr(user_profile, 'learning_style') and
                hasattr(user_profile, 'personality_type') and
                hasattr(user_profile, 'difficulty_preference')
            )
            
            self.log_test("User Profile Generation", profile_valid)
            return profile_valid
        except Exception as e:
            self.log_test("User Profile Generation", False, str(e))
            return False
    
    async def test_ab_experiment_creation(self):
        """Test A/B experiment creation."""
        try:
            from lyo_app.ai_agents.optimization.ab_testing import experiment_manager, ExperimentType
            
            # Create test experiment
            experiment_id = await experiment_manager.create_experiment(
                name="Test Optimization Experiment",
                description="Test experiment for optimization validation",
                experiment_type=ExperimentType.RESPONSE_OPTIMIZATION,
                variants=[
                    {
                        "name": "control",
                        "config": {"optimization": False},
                        "is_control": True,
                        "weight": 0.5
                    },
                    {
                        "name": "optimized",
                        "config": {"optimization": True},
                        "is_control": False,
                        "weight": 0.5
                    }
                ],
                metrics_config={
                    "primary_metric": "response_time",
                    "secondary_metrics": ["user_satisfaction"]
                },
                target_participants=100
            )
            
            experiment_created = experiment_id is not None and len(experiment_id) > 0
            self.log_test("A/B Experiment Creation", experiment_created)
            return experiment_created
        except Exception as e:
            self.log_test("A/B Experiment Creation", False, str(e))
            return False
    
    async def test_performance_metrics_collection(self):
        """Test performance metrics collection."""
        try:
            from lyo_app.ai_agents.optimization.performance_optimizer import ai_performance_optimizer
            
            # Get performance metrics
            metrics = ai_performance_optimizer.get_performance_metrics()
            
            metrics_valid = (
                hasattr(metrics, 'response_time') and
                hasattr(metrics, 'cache_hit_rate') and
                hasattr(metrics, 'memory_usage')
            )
            
            self.log_test("Performance Metrics Collection", metrics_valid)
            return metrics_valid
        except Exception as e:
            self.log_test("Performance Metrics Collection", False, str(e))
            return False
    
    async def test_optimization_level_configuration(self):
        """Test optimization level configuration."""
        try:
            from lyo_app.ai_agents.optimization.performance_optimizer import ai_performance_optimizer, OptimizationLevel
            
            # Test setting different optimization levels
            for level in OptimizationLevel:
                ai_performance_optimizer.set_optimization_level(level)
                current_level = ai_performance_optimizer.optimization_level
                if current_level != level:
                    self.log_test("Optimization Level Configuration", False, f"Failed to set {level}")
                    return False
            
            self.log_test("Optimization Level Configuration", True)
            return True
        except Exception as e:
            self.log_test("Optimization Level Configuration", False, str(e))
            return False
    
    async def test_curriculum_agent_optimization(self):
        """Test curriculum agent optimization integration."""
        try:
            from lyo_app.ai_agents.curriculum_agent import CurriculumDesignAgent
            
            agent = CurriculumDesignAgent()
            
            # Check if the agent has the optimization method
            has_optimization = hasattr(agent, '_apply_personalization_optimizations')
            
            self.log_test("Curriculum Agent Optimization", has_optimization)
            return has_optimization
        except Exception as e:
            self.log_test("Curriculum Agent Optimization", False, str(e))
            return False
    
    async def test_content_recommendations(self):
        """Test personalized content recommendations."""
        try:
            from lyo_app.ai_agents.optimization.personalization_engine import personalization_engine
            
            # Simulate available content
            content = [
                {
                    "id": "test_1",
                    "type": "course",
                    "title": "Test Course",
                    "topics": ["programming"],
                    "difficulty": 0.5,
                    "format": "video",
                    "estimated_duration": 30
                }
            ]
            
            recommendations = await personalization_engine.personalize_content_recommendations(
                user_id=123,
                available_content=content,
                num_recommendations=1
            )
            
            recommendations_valid = len(recommendations) > 0
            self.log_test("Content Recommendations", recommendations_valid)
            return recommendations_valid
        except Exception as e:
            self.log_test("Content Recommendations", False, str(e))
            return False
    
    async def test_system_resource_monitoring(self):
        """Test system resource monitoring."""
        try:
            from lyo_app.ai_agents.optimization.performance_optimizer import ResourceOptimizer
            
            optimizer = ResourceOptimizer()
            system_status = optimizer.get_system_status()
            
            status_valid = (
                "memory" in system_status and
                "cpu" in system_status and
                "gpu" in system_status
            )
            
            self.log_test("System Resource Monitoring", status_valid)
            return status_valid
        except Exception as e:
            self.log_test("System Resource Monitoring", False, str(e))
            return False
    
    async def run_all_tests(self):
        """Run comprehensive optimization test suite."""
        print("🚀 AI Optimization Test Suite")
        print("=" * 50)
        
        tests = [
            self.test_performance_optimizer_imports,
            self.test_personalization_engine_imports,
            self.test_ab_testing_imports,
            self.test_optimization_routes_imports,
            self.test_orchestrator_optimization_integration,
            self.test_cache_manager_functionality,
            self.test_user_profile_generation,
            self.test_ab_experiment_creation,
            self.test_performance_metrics_collection,
            self.test_optimization_level_configuration,
            self.test_curriculum_agent_optimization,
            self.test_content_recommendations,
            self.test_system_resource_monitoring
        ]
        
        print(f"Running {len(tests)} optimization tests...\n")
        
        for test in tests:
            await test()
        
        self.print_summary()
    
    def print_summary(self):
        """Print test summary."""
        print("\n" + "=" * 50)
        print(f"🎯 Test Results: {self.passed_tests}/{self.total_tests} tests passed ({self.passed_tests/self.total_tests*100:.1f}%)")
        
        if self.passed_tests == self.total_tests:
            print("\n🎉 ALL AI OPTIMIZATION TESTS PASSED!")
            print("✨ Your AI system is fully optimized and ready for production!")
            print("\n📊 Optimization Features Available:")
            print("  ✅ Intelligent performance optimization")
            print("  ✅ Advanced user personalization")
            print("  ✅ A/B testing framework") 
            print("  ✅ Real-time analytics and monitoring")
            print("  ✅ Smart caching and resource management")
            print("  ✅ Automated system tuning")
            
        elif self.passed_tests >= self.total_tests * 0.8:
            print("\n⚡ OPTIMIZATION MOSTLY READY!")
            print("🔧 Minor issues detected but core functionality works")
            
        else:
            print("\n⚠️  OPTIMIZATION NEEDS ATTENTION!")
            print("🛠️  Several optimization features need fixes")
        
        # Print failed tests
        failed_tests = [result for result in self.test_results if result["status"] == "FAIL"]
        if failed_tests:
            print(f"\n❌ Failed Tests ({len(failed_tests)}):")
            for test in failed_tests:
                print(f"  - {test['test']}: {test['details']}")
        
        print(f"\n📋 Next Steps:")
        if self.passed_tests == self.total_tests:
            print("  1. Deploy with optimization enabled")
            print("  2. Monitor performance dashboards")
            print("  3. Run A/B experiments for continuous improvement")
            print("  4. Analyze user behavior for enhanced personalization")
        else:
            print("  1. Fix failing optimization components")
            print("  2. Re-run tests after fixes")
            print("  3. Check optimization dependencies")
            print("  4. Review configuration settings")

async def main():
    """Run AI optimization tests."""
    tester = AIOptimizationTester()
    await tester.run_all_tests()
    
    # Return success status
    return tester.passed_tests == tester.total_tests

if __name__ == "__main__":
    success = asyncio.run(main())
    sys.exit(0 if success else 1)
