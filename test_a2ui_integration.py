#!/usr/bin/env python3
"""
Comprehensive A2UI Integration Tests
Tests the complete A2UI system from backend generation to iOS rendering
"""

import asyncio
import json
import requests
import time
from typing import Dict, Any, List
import subprocess
import sys

# Test configuration
BASE_URL = "https://lyo-backend-production-830162750094.us-central1.run.app"
LOCAL_URL = "http://localhost:8000"

class A2UIIntegrationTester:
    def __init__(self, use_local=False):
        self.base_url = LOCAL_URL if use_local else BASE_URL
        self.test_results = []
        self.session = requests.Session()

    def log_result(self, test_name: str, success: bool, details: str = ""):
        self.test_results.append({
            "test": test_name,
            "success": success,
            "details": details,
            "timestamp": time.time()
        })
        status = "✅ PASS" if success else "❌ FAIL"
        print(f"{status} {test_name}: {details}")

    def test_backend_health(self):
        """Test 1: Backend Health Check"""
        try:
            response = self.session.get(f"{self.base_url}/a2ui/health", timeout=10)
            if response.status_code == 200:
                data = response.json()
                self.log_result("Backend Health", True, f"Service: {data.get('service', 'unknown')}")
                return True
            else:
                self.log_result("Backend Health", False, f"HTTP {response.status_code}")
                return False
        except Exception as e:
            self.log_result("Backend Health", False, str(e))
            return False

    def test_component_generation(self):
        """Test 2: A2UI Component Generation"""
        try:
            response = self.session.get(f"{self.base_url}/a2ui/components/test", timeout=15)
            if response.status_code == 200:
                data = response.json()
                components = data.get("components", {})

                # Check if all expected components are generated
                expected_components = ["welcome", "course", "quiz", "text", "button"]
                missing_components = [c for c in expected_components if c not in components]

                if not missing_components:
                    self.log_result("Component Generation", True,
                                  f"Generated {len(components)} components")
                    return True
                else:
                    self.log_result("Component Generation", False,
                                  f"Missing: {missing_components}")
                    return False
            else:
                self.log_result("Component Generation", False, f"HTTP {response.status_code}")
                return False
        except Exception as e:
            self.log_result("Component Generation", False, str(e))
            return False

    def test_screen_endpoints(self):
        """Test 3: Screen Generation Endpoints"""
        screens = ["dashboard", "course", "quiz", "chat", "settings"]
        all_passed = True

        for screen in screens:
            try:
                payload = {
                    "screen_id": screen,
                    "user_id": "test_user",
                    "context": {"test": True}
                }

                response = self.session.post(
                    f"{self.base_url}/a2ui/screen/{screen}",
                    json=payload,
                    timeout=15
                )

                if response.status_code == 200:
                    data = response.json()
                    component = data.get("component")

                    # Validate component structure
                    if component and "type" in component:
                        self.log_result(f"Screen: {screen}", True,
                                      f"Type: {component['type']}")
                    else:
                        self.log_result(f"Screen: {screen}", False, "Invalid component structure")
                        all_passed = False
                else:
                    self.log_result(f"Screen: {screen}", False, f"HTTP {response.status_code}")
                    all_passed = False

            except Exception as e:
                self.log_result(f"Screen: {screen}", False, str(e))
                all_passed = False

        return all_passed

    def test_action_handling(self):
        """Test 4: Action Handling"""
        test_actions = [
            {"action_id": "quick_learn", "component_id": "test", "action_type": "tap"},
            {"action_id": "create_course", "component_id": "test", "action_type": "tap"},
            {"action_id": "quiz_answer", "component_id": "test", "action_type": "selection",
             "params": {"selectedAnswer": 1}},
            {"action_id": "send_message", "component_id": "test", "action_type": "tap",
             "params": {"message": "Hello world"}}
        ]

        all_passed = True

        for action in test_actions:
            try:
                response = self.session.post(
                    f"{self.base_url}/a2ui/action",
                    json=action,
                    timeout=10
                )

                if response.status_code == 200:
                    data = response.json()
                    success = data.get("success", False)

                    if success:
                        self.log_result(f"Action: {action['action_id']}", True,
                                      data.get("message", "No message"))
                    else:
                        self.log_result(f"Action: {action['action_id']}", False,
                                      data.get("message", "Action failed"))
                        all_passed = False
                else:
                    self.log_result(f"Action: {action['action_id']}", False,
                                  f"HTTP {response.status_code}")
                    all_passed = False

            except Exception as e:
                self.log_result(f"Action: {action['action_id']}", False, str(e))
                all_passed = False

        return all_passed

    def test_chat_integration(self):
        """Test 5: Chat A2UI Integration"""
        try:
            # Test chat with A2UI request
            chat_payload = {
                "message": "Create a course about machine learning",
                "include_ui": True,
                "mode_hint": "course_planner"
            }

            response = self.session.post(
                f"{self.base_url}/chat",
                json=chat_payload,
                timeout=30
            )

            if response.status_code == 200:
                data = response.json()
                ui_component = data.get("ui_component") or data.get("uiComponent")

                if ui_component:
                    self.log_result("Chat A2UI Integration", True,
                                  f"Generated UI component: {ui_component.get('type', 'unknown')}")
                    return True
                else:
                    self.log_result("Chat A2UI Integration", False, "No UI component in response")
                    return False
            else:
                self.log_result("Chat A2UI Integration", False, f"HTTP {response.status_code}")
                return False

        except Exception as e:
            self.log_result("Chat A2UI Integration", False, str(e))
            return False

    def test_component_validation(self):
        """Test 6: Component Structure Validation"""
        try:
            # Get a dashboard component
            response = self.session.get(f"{self.base_url}/a2ui/screen/dashboard")

            if response.status_code == 200:
                data = response.json()
                component = data.get("component")

                # Validate required fields
                validation_results = self._validate_component_structure(component)

                if validation_results["valid"]:
                    self.log_result("Component Validation", True,
                                  f"Validated {validation_results['components_count']} components")
                    return True
                else:
                    self.log_result("Component Validation", False,
                                  f"Errors: {validation_results['errors']}")
                    return False
            else:
                self.log_result("Component Validation", False, f"HTTP {response.status_code}")
                return False

        except Exception as e:
            self.log_result("Component Validation", False, str(e))
            return False

    def _validate_component_structure(self, component: Dict[str, Any], path="root") -> Dict[str, Any]:
        """Recursively validate A2UI component structure"""
        errors = []
        components_count = 0

        if not component:
            errors.append(f"{path}: Component is None or empty")
            return {"valid": False, "errors": errors, "components_count": 0}

        # Check required fields
        required_fields = ["id", "type"]
        for field in required_fields:
            if field not in component:
                errors.append(f"{path}: Missing required field '{field}'")

        components_count += 1

        # Validate children recursively
        if "children" in component and component["children"]:
            for i, child in enumerate(component["children"]):
                child_result = self._validate_component_structure(child, f"{path}.children[{i}]")
                errors.extend(child_result["errors"])
                components_count += child_result["components_count"]

        return {
            "valid": len(errors) == 0,
            "errors": errors,
            "components_count": components_count
        }

    def test_performance(self):
        """Test 7: Performance Benchmarks"""
        try:
            # Test response times for different operations
            operations = [
                ("Dashboard Load", lambda: self.session.get(f"{self.base_url}/a2ui/screen/dashboard")),
                ("Quiz Load", lambda: self.session.get(f"{self.base_url}/a2ui/screen/quiz")),
                ("Action Handle", lambda: self.session.post(f"{self.base_url}/a2ui/action", json={
                    "action_id": "test", "component_id": "test", "action_type": "tap"
                }))
            ]

            all_passed = True

            for op_name, operation in operations:
                start_time = time.time()
                try:
                    response = operation()
                    end_time = time.time()

                    response_time_ms = int((end_time - start_time) * 1000)

                    if response.status_code == 200 and response_time_ms < 5000:  # 5 second limit
                        self.log_result(f"Performance: {op_name}", True, f"{response_time_ms}ms")
                    else:
                        self.log_result(f"Performance: {op_name}", False,
                                      f"{response_time_ms}ms (HTTP {response.status_code})")
                        all_passed = False

                except Exception as e:
                    self.log_result(f"Performance: {op_name}", False, str(e))
                    all_passed = False

            return all_passed

        except Exception as e:
            self.log_result("Performance Tests", False, str(e))
            return False

    def test_swift_model_compatibility(self):
        """Test 8: Swift Model Compatibility"""
        try:
            # Get a complex component and verify it matches Swift model expectations
            response = self.session.get(f"{self.base_url}/a2ui/screen/dashboard")

            if response.status_code == 200:
                data = response.json()
                component = data.get("component")

                # Convert to JSON string and back to simulate iOS parsing
                json_str = json.dumps(component)
                parsed_component = json.loads(json_str)

                # Check Swift-compatible structure
                compatibility_issues = self._check_swift_compatibility(parsed_component)

                if not compatibility_issues:
                    self.log_result("Swift Compatibility", True, "All fields compatible")
                    return True
                else:
                    self.log_result("Swift Compatibility", False,
                                  f"Issues: {compatibility_issues}")
                    return False
            else:
                self.log_result("Swift Compatibility", False, f"HTTP {response.status_code}")
                return False

        except Exception as e:
            self.log_result("Swift Compatibility", False, str(e))
            return False

    def _check_swift_compatibility(self, component: Dict[str, Any]) -> List[str]:
        """Check if component structure is compatible with Swift models"""
        issues = []

        # Check for unsupported types or structures
        if "props" in component and component["props"]:
            for key, value in component["props"].items():
                if isinstance(value, dict) and "type" not in value:
                    # Props should be simple values or have a type field for UIValue
                    if not isinstance(value, (str, int, float, bool, list)):
                        issues.append(f"Complex prop without type: {key}")

        # Recursively check children
        if "children" in component and component["children"]:
            for child in component["children"]:
                issues.extend(self._check_swift_compatibility(child))

        return issues

    def run_all_tests(self):
        """Run all integration tests"""
        print("🚀 Starting A2UI Integration Tests")
        print("=" * 50)

        tests = [
            ("Backend Health Check", self.test_backend_health),
            ("Component Generation", self.test_component_generation),
            ("Screen Endpoints", self.test_screen_endpoints),
            ("Action Handling", self.test_action_handling),
            ("Chat Integration", self.test_chat_integration),
            ("Component Validation", self.test_component_validation),
            ("Performance Tests", self.test_performance),
            ("Swift Compatibility", self.test_swift_model_compatibility)
        ]

        passed_tests = 0
        total_tests = len(tests)

        for test_name, test_func in tests:
            print(f"\n📋 Running {test_name}...")
            try:
                if test_func():
                    passed_tests += 1
            except Exception as e:
                self.log_result(test_name, False, f"Test crashed: {e}")

        # Print summary
        print("\n" + "=" * 50)
        print("🎉 A2UI Integration Test Results")
        print("=" * 50)

        success_rate = (passed_tests / total_tests) * 100

        print(f"✅ Passed: {passed_tests}/{total_tests}")
        print(f"📊 Success Rate: {success_rate:.1f}%")

        if success_rate >= 90:
            print("🚀 A2UI Integration: READY FOR PRODUCTION")
        elif success_rate >= 75:
            print("⚠️  A2UI Integration: MOSTLY FUNCTIONAL - Minor issues")
        else:
            print("❌ A2UI Integration: NEEDS ATTENTION - Major issues")

        # Detailed results
        print("\n📝 Detailed Results:")
        for result in self.test_results:
            status = "✅" if result["success"] else "❌"
            print(f"  {status} {result['test']}: {result['details']}")

        return success_rate >= 90


def main():
    """Main test execution"""
    import argparse

    parser = argparse.ArgumentParser(description="A2UI Integration Tests")
    parser.add_argument("--local", action="store_true", help="Test against local server")
    parser.add_argument("--quick", action="store_true", help="Run quick tests only")

    args = parser.parse_args()

    tester = A2UIIntegrationTester(use_local=args.local)

    if args.quick:
        # Quick tests
        print("🏃‍♂️ Running Quick Tests...")
        tester.test_backend_health()
        tester.test_component_generation()
        tester.test_screen_endpoints()
    else:
        # Full test suite
        success = tester.run_all_tests()
        sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()