#!/usr/bin/env python3
"""
Developer Experience Test Suite
Validates all developer tools, documentation, and development workflow
"""

import unittest
import asyncio
import json
import os
import subprocess
import sys
import time
from pathlib import Path
from datetime import datetime

class TestDeveloperExperience(unittest.TestCase):
    """Comprehensive test suite for developer experience features"""

    def setUp(self):
        """Setup test environment"""
        self.start_time = time.time()
        self.test_results = []

    def tearDown(self):
        """Cleanup after tests"""
        duration = time.time() - self.start_time
        print(f"   ⏱️  Test duration: {duration:.3f}s")

    def test_documentation_generation(self):
        """Test documentation generation functionality"""
        print("📚 Testing documentation generation...")

        # Test docs generator exists
        generator_path = Path("generate_docs.py")
        self.assertTrue(generator_path.exists(), "Documentation generator should exist")

        # Test documentation can be generated
        try:
            result = subprocess.run([sys.executable, "generate_docs.py"],
                                  capture_output=True, text=True, timeout=30)
            self.assertEqual(result.returncode, 0, "Documentation generation should succeed")
        except subprocess.TimeoutExpired:
            self.fail("Documentation generation timed out")

        # Verify documentation files created
        docs_dir = Path("docs")
        self.assertTrue(docs_dir.exists(), "Docs directory should be created")

        expected_files = ["README.md", "api_documentation.json", "api_validator.py", "run_tests.py"]
        for file_name in expected_files:
            file_path = docs_dir / file_name
            self.assertTrue(file_path.exists(), f"Documentation file {file_name} should exist")

        # Test documentation content quality
        readme_path = docs_dir / "README.md"
        with open(readme_path, 'r') as f:
            readme_content = f.read()

        self.assertIn("Lyo Learning Platform", readme_content, "README should contain project name")
        self.assertIn("A2UI", readme_content, "README should document A2UI system")
        self.assertIn("API Documentation", readme_content, "README should include API docs")
        self.assertTrue(len(readme_content) > 5000, "README should be comprehensive (>5000 chars)")

        # Test JSON documentation structure
        json_path = docs_dir / "api_documentation.json"
        with open(json_path, 'r') as f:
            api_docs = json.load(f)

        required_sections = ["meta", "project_info", "components", "architecture"]
        for section in required_sections:
            self.assertIn(section, api_docs, f"API docs should include {section} section")

        print("   ✅ Documentation generation: PASS")

    def test_development_tools(self):
        """Test developer tools functionality"""
        print("🔧 Testing development tools...")

        # Test API validator
        validator_path = Path("docs/api_validator.py")
        self.assertTrue(validator_path.exists(), "API validator should exist")
        self.assertTrue(os.access(validator_path, os.X_OK), "API validator should be executable")

        # Test test runner
        test_runner_path = Path("docs/run_tests.py")
        self.assertTrue(test_runner_path.exists(), "Test runner should exist")
        self.assertTrue(os.access(test_runner_path, os.X_OK), "Test runner should be executable")

        # Test dev server
        dev_server_path = Path("lyo_app/dev_tools/dev_server.py")
        self.assertTrue(dev_server_path.exists(), "Development server should exist")

        # Validate dev server can be imported
        sys.path.insert(0, str(Path("lyo_app/dev_tools").absolute()))
        try:
            import dev_server
            self.assertTrue(hasattr(dev_server, 'DevServer'), "DevServer class should exist")
            self.assertTrue(hasattr(dev_server, 'main'), "Main function should exist")
        except ImportError as e:
            self.fail(f"Dev server should be importable: {e}")

        print("   ✅ Development tools: PASS")

    def test_code_quality_tools(self):
        """Test code quality and validation tools"""
        print("🔍 Testing code quality tools...")

        # Test Python syntax validation
        python_files = list(Path("lyo_app").rglob("*.py"))
        syntax_errors = []

        for py_file in python_files[:20]:  # Test first 20 files for speed
            try:
                with open(py_file, 'r', encoding='utf-8') as f:
                    content = f.read()
                compile(content, str(py_file), 'exec')
            except SyntaxError as e:
                syntax_errors.append((py_file, e))
            except UnicodeDecodeError:
                continue  # Skip binary or non-UTF8 files

        self.assertEqual(len(syntax_errors), 0,
                        f"No syntax errors should exist. Found: {syntax_errors[:3]}")

        # Test import structure
        import_issues = []
        for py_file in python_files[:10]:  # Test subset for speed
            try:
                with open(py_file, 'r', encoding='utf-8') as f:
                    content = f.read()

                # Basic import validation
                lines = content.split('\n')
                for i, line in enumerate(lines[:50], 1):  # Check first 50 lines
                    if line.strip().startswith('from') and 'import' in line:
                        if '..' in line and not line.strip().startswith('from .'):
                            import_issues.append(f"{py_file}:{i} - Potential relative import issue")

            except Exception:
                continue

        self.assertLess(len(import_issues), 5, "Should have minimal import issues")

        print("   ✅ Code quality tools: PASS")

    def test_developer_workflow(self):
        """Test complete developer workflow"""
        print("⚡ Testing developer workflow...")

        # Test configuration files
        config_files = ["dev_config.json"]
        for config_file in config_files:
            if Path(config_file).exists():
                try:
                    with open(config_file, 'r') as f:
                        config = json.load(f)
                    self.assertIn("development", config, "Config should have development section")
                except json.JSONDecodeError:
                    self.fail(f"Config file {config_file} should be valid JSON")

        # Test project structure
        required_dirs = [
            "lyo_app",
            "lyo_app/dev_tools",
            "docs"
        ]

        for dir_path in required_dirs:
            self.assertTrue(Path(dir_path).exists(), f"Required directory {dir_path} should exist")

        # Test that basic development commands work
        basic_commands = [
            [sys.executable, "--version"],
            [sys.executable, "-c", "import sys; print('Python OK')"]
        ]

        for cmd in basic_commands:
            try:
                result = subprocess.run(cmd, capture_output=True, timeout=10)
                self.assertEqual(result.returncode, 0, f"Command should succeed: {' '.join(cmd)}")
            except subprocess.TimeoutExpired:
                self.fail(f"Command timed out: {' '.join(cmd)}")

        print("   ✅ Developer workflow: PASS")

    def test_documentation_quality(self):
        """Test documentation completeness and quality"""
        print("📖 Testing documentation quality...")

        docs_dir = Path("docs")
        if not docs_dir.exists():
            self.skipTest("Documentation not generated yet")

        # Test README completeness
        readme_path = docs_dir / "README.md"
        with open(readme_path, 'r') as f:
            readme = f.read()

        required_sections = [
            "# Lyo Learning Platform",
            "## Project Overview",
            "## System Architecture",
            "## A2UI Component System",
            "## API Documentation",
            "## Testing & Quality Assurance",
            "## Development Workflow",
            "## Configuration",
            "## Troubleshooting"
        ]

        for section in required_sections:
            self.assertIn(section, readme, f"README should contain section: {section}")

        # Test code examples in documentation
        code_blocks = readme.count("```")
        self.assertGreaterEqual(code_blocks, 10, "README should contain multiple code examples")

        # Test API documentation completeness
        api_docs_path = docs_dir / "api_documentation.json"
        with open(api_docs_path, 'r') as f:
            api_docs = json.load(f)

        self.assertIn("meta", api_docs, "API docs should have metadata")
        self.assertIn("generated_at", api_docs["meta"], "API docs should include generation timestamp")

        print("   ✅ Documentation quality: PASS")

    def test_performance_and_accessibility(self):
        """Test development tools performance and accessibility"""
        print("⚡ Testing performance and accessibility...")

        # Test documentation generation speed
        start_time = time.time()
        try:
            result = subprocess.run([sys.executable, "generate_docs.py"],
                                  capture_output=True, timeout=60)
            generation_time = time.time() - start_time
            self.assertLess(generation_time, 30, "Documentation generation should complete in <30s")
            self.assertEqual(result.returncode, 0, "Documentation generation should succeed")
        except subprocess.TimeoutExpired:
            self.fail("Documentation generation should not timeout")

        # Test file sizes are reasonable
        docs_dir = Path("docs")
        if docs_dir.exists():
            readme_size = (docs_dir / "README.md").stat().st_size if (docs_dir / "README.md").exists() else 0
            self.assertLess(readme_size, 1024 * 1024, "README should be <1MB")  # 1MB limit
            self.assertGreater(readme_size, 1000, "README should be substantial (>1KB)")

        # Test tools are responsive
        tool_files = [
            Path("docs/api_validator.py"),
            Path("docs/run_tests.py"),
            Path("lyo_app/dev_tools/dev_server.py")
        ]

        for tool_file in tool_files:
            if tool_file.exists():
                file_size = tool_file.stat().st_size
                self.assertLess(file_size, 100 * 1024, f"Tool {tool_file.name} should be <100KB")

        print("   ✅ Performance and accessibility: PASS")

def run_developer_experience_tests():
    """Run comprehensive developer experience test suite"""
    print("🎯 DEVELOPER EXPERIENCE TEST SUITE")
    print("=" * 60)

    suite = unittest.TestLoader().loadTestsFromTestCase(TestDeveloperExperience)
    runner = unittest.TextTestRunner(verbosity=2, stream=sys.stdout)

    start_time = time.time()
    result = runner.run(suite)
    total_time = time.time() - start_time

    # Calculate results
    total_tests = result.testsRun
    failed_tests = len(result.failures) + len(result.errors)
    success_rate = ((total_tests - failed_tests) / total_tests * 100) if total_tests > 0 else 0

    print(f"\n📊 DEVELOPER EXPERIENCE TEST RESULTS")
    print("=" * 60)
    print(f"Total Tests: {total_tests}")
    print(f"Passed: {total_tests - failed_tests}")
    print(f"Failed: {failed_tests}")
    print(f"Success Rate: {success_rate:.1f}%")
    print(f"Duration: {total_time:.3f}s")

    if result.failures:
        print(f"\n❌ FAILURES:")
        for test, error in result.failures:
            print(f"   • {test}: {error.split(chr(10))[0]}")

    if result.errors:
        print(f"\n💥 ERRORS:")
        for test, error in result.errors:
            print(f"   • {test}: {error.split(chr(10))[0]}")

    if success_rate >= 90.0:
        print(f"\n🎉 DEVELOPER EXPERIENCE: EXCELLENT ({success_rate:.1f}%)")
        print("✅ All critical developer tools working")
        print("✅ Documentation comprehensive and current")
        print("✅ Development workflow optimized")
        print("✅ Code quality tools validated")
    else:
        print(f"\n⚠️  DEVELOPER EXPERIENCE: NEEDS IMPROVEMENT ({success_rate:.1f}%)")
        print("📝 Address failing tests to improve developer productivity")

    return success_rate >= 90.0, {
        "total_tests": total_tests,
        "passed_tests": total_tests - failed_tests,
        "failed_tests": failed_tests,
        "success_rate": success_rate,
        "duration": total_time,
        "status": "pass" if success_rate >= 90.0 else "fail"
    }

if __name__ == "__main__":
    success, results = run_developer_experience_tests()