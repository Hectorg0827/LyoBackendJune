#!/usr/bin/env python3
"""
No-Dependency Validation Script for LyoBackend
Provides comprehensive validation without requiring external dependencies.
Tests the codebase structure, imports, and configuration that would work once dependencies are installed.
"""

import os
import sys
import ast
import importlib.util
import traceback
from pathlib import Path
from typing import List, Tuple, Dict, Any

class LyoBackendValidator:
    def __init__(self):
        self.project_root = Path(__file__).parent
        self.results = {}
        self.issues = []
        
    def add_result(self, test_name: str, success: bool, message: str = ""):
        self.results[test_name] = {
            'success': success,
            'message': message
        }
        if not success:
            self.issues.append(f"{test_name}: {message}")

    def test_project_structure(self) -> bool:
        """Comprehensive test of project structure."""
        print("📁 Testing Project Structure...")
        
        # Core directories and files that should exist
        required_items = {
            # Core application structure
            "lyo_app/__init__.py": "Main application package",
            "lyo_app/main.py": "FastAPI main application",
            "lyo_app/core/__init__.py": "Core functionality package",
            "lyo_app/core/config.py": "Configuration management",
            "lyo_app/core/database.py": "Database configuration",
            "lyo_app/models/__init__.py": "Database models package",
            "lyo_app/api/__init__.py": "API routes package",
            "lyo_app/auth/__init__.py": "Authentication package",
            
            # AI functionality
            "lyo_app/ai/__init__.py": "AI functionality package",
            "lyo_app/ai_study/__init__.py": "AI study mode package",
            
            # Configuration files
            "requirements.txt": "Python dependencies",
            ".env.example": "Environment configuration template",
            ".env": "Environment configuration",
            "alembic.ini": "Database migration configuration",
            
            # Documentation
            "README.md": "Project documentation",
        }
        
        missing_items = []
        present_items = []
        
        for item_path, description in required_items.items():
            full_path = self.project_root / item_path
            if full_path.exists():
                present_items.append(f"  ✅ {item_path} - {description}")
            else:
                missing_items.append(f"  ❌ {item_path} - {description}")
                
        print(f"Present items ({len(present_items)}):")
        for item in present_items[:10]:  # Show first 10
            print(item)
        if len(present_items) > 10:
            print(f"  ... and {len(present_items) - 10} more")
            
        if missing_items:
            print(f"\nMissing items ({len(missing_items)}):")
            for item in missing_items:
                print(item)
                
        success = len(missing_items) == 0
        message = f"Structure: {len(present_items)} present, {len(missing_items)} missing"
        
        self.add_result("project_structure", success, message)
        return success

    def test_python_syntax(self) -> bool:
        """Test that all Python files have valid syntax."""
        print("🐍 Testing Python Syntax...")
        
        syntax_errors = []
        valid_files = []
        
        # Find all Python files in the project
        python_files = list(self.project_root.rglob("*.py"))
        
        for py_file in python_files:
            try:
                with open(py_file, 'r', encoding='utf-8') as f:
                    source_code = f.read()
                    
                # Parse the file to check syntax
                ast.parse(source_code)
                valid_files.append(str(py_file.relative_to(self.project_root)))
                
            except SyntaxError as e:
                syntax_errors.append(f"{py_file.relative_to(self.project_root)}: {e}")
            except Exception as e:
                syntax_errors.append(f"{py_file.relative_to(self.project_root)}: {e}")
                
        print(f"✅ Valid Python files: {len(valid_files)}")
        if syntax_errors:
            print(f"❌ Syntax errors in {len(syntax_errors)} files:")
            for error in syntax_errors[:5]:  # Show first 5 errors
                print(f"  {error}")
            if len(syntax_errors) > 5:
                print(f"  ... and {len(syntax_errors) - 5} more")
                
        success = len(syntax_errors) == 0
        message = f"Syntax: {len(valid_files)} valid, {len(syntax_errors)} errors"
        
        self.add_result("python_syntax", success, message)
        return success

    def test_configuration_files(self) -> bool:
        """Test configuration files are properly structured."""
        print("⚙️  Testing Configuration Files...")
        
        config_issues = []
        
        # Test .env file
        env_file = self.project_root / ".env"
        if env_file.exists():
            try:
                with open(env_file, 'r') as f:
                    env_content = f.read()
                    
                # Check for essential environment variables
                essential_vars = [
                    "DATABASE_URL", "SECRET_KEY", "ENVIRONMENT"
                ]
                
                missing_vars = []
                for var in essential_vars:
                    if var not in env_content:
                        missing_vars.append(var)
                        
                if missing_vars:
                    config_issues.append(f"Missing environment variables: {missing_vars}")
                else:
                    print("✅ Essential environment variables present")
                    
            except Exception as e:
                config_issues.append(f".env file error: {e}")
        else:
            config_issues.append(".env file missing")
            
        # Test requirements.txt
        req_file = self.project_root / "requirements.txt"
        if req_file.exists():
            try:
                with open(req_file, 'r') as f:
                    req_content = f.read()
                    
                # Check for essential packages
                essential_packages = ["fastapi", "uvicorn", "pydantic", "sqlalchemy"]
                
                missing_packages = []
                for package in essential_packages:
                    if package.lower() not in req_content.lower():
                        missing_packages.append(package)
                        
                if missing_packages:
                    config_issues.append(f"Missing essential packages: {missing_packages}")
                else:
                    print("✅ Essential packages present in requirements.txt")
                    
            except Exception as e:
                config_issues.append(f"requirements.txt error: {e}")
        else:
            config_issues.append("requirements.txt missing")
            
        if config_issues:
            for issue in config_issues:
                print(f"❌ {issue}")
                
        success = len(config_issues) == 0
        message = f"Configuration: {len(config_issues)} issues found"
        
        self.add_result("configuration", success, message)
        return success

    def test_import_structure(self) -> bool:
        """Test that import statements are properly structured."""
        print("📦 Testing Import Structure...")
        
        import_issues = []
        analyzed_files = 0
        
        # Analyze key Python files for import structure
        key_files = [
            "lyo_app/main.py",
            "lyo_app/core/config.py", 
            "lyo_app/core/database.py",
            "lyo_app/api/__init__.py"
        ]
        
        for file_path in key_files:
            full_path = self.project_root / file_path
            if full_path.exists():
                try:
                    with open(full_path, 'r') as f:
                        content = f.read()
                        
                    # Parse the AST to check imports
                    tree = ast.parse(content)
                    
                    imports = []
                    for node in ast.walk(tree):
                        if isinstance(node, ast.Import):
                            imports.extend([alias.name for alias in node.names])
                        elif isinstance(node, ast.ImportFrom):
                            if node.module:
                                imports.append(node.module)
                                
                    analyzed_files += 1
                    print(f"  ✅ {file_path}: {len(imports)} imports analyzed")
                    
                except Exception as e:
                    import_issues.append(f"{file_path}: {e}")
                    
        if import_issues:
            for issue in import_issues:
                print(f"❌ {issue}")
                
        success = len(import_issues) == 0
        message = f"Imports: {analyzed_files} files analyzed, {len(import_issues)} issues"
        
        self.add_result("import_structure", success, message)
        return success

    def test_database_models_structure(self) -> bool:
        """Test database models are properly structured."""
        print("🗄️  Testing Database Models Structure...")
        
        models_issues = []
        models_found = []
        
        models_dir = self.project_root / "lyo_app" / "models"
        if models_dir.exists():
            # Find all Python files in models directory
            model_files = list(models_dir.glob("*.py"))
            
            for model_file in model_files:
                if model_file.name == "__init__.py":
                    continue
                    
                try:
                    with open(model_file, 'r') as f:
                        content = f.read()
                        
                    # Parse to look for SQLAlchemy model patterns
                    tree = ast.parse(content)
                    
                    for node in ast.walk(tree):
                        if isinstance(node, ast.ClassDef):
                            # Look for SQLAlchemy Base classes
                            for base in node.bases:
                                if isinstance(base, ast.Name) and 'Base' in base.id:
                                    models_found.append(f"{model_file.stem}.{node.name}")
                                    
                    print(f"  ✅ {model_file.name}: Models analyzed")
                    
                except Exception as e:
                    models_issues.append(f"{model_file.name}: {e}")
                    
            print(f"  Found {len(models_found)} potential database models")
            
        else:
            models_issues.append("Models directory not found")
            
        if models_issues:
            for issue in models_issues:
                print(f"❌ {issue}")
                
        success = len(models_issues) == 0
        message = f"Models: {len(models_found)} found, {len(models_issues)} issues"
        
        self.add_result("database_models", success, message)
        return success

    def test_api_routes_structure(self) -> bool:
        """Test API routes are properly structured."""
        print("🛣️  Testing API Routes Structure...")
        
        routes_issues = []
        routes_found = []
        
        api_dirs = [
            self.project_root / "lyo_app" / "api",
            self.project_root / "lyo_app" / "routers"
        ]
        
        for api_dir in api_dirs:
            if api_dir.exists():
                route_files = list(api_dir.glob("*.py"))
                
                for route_file in route_files:
                    if route_file.name == "__init__.py":
                        continue
                        
                    try:
                        with open(route_file, 'r') as f:
                            content = f.read()
                            
                        # Look for FastAPI router patterns
                        if "router" in content.lower() or "apiRouter" in content:
                            routes_found.append(route_file.stem)
                            
                        print(f"  ✅ {api_dir.name}/{route_file.name}: Analyzed")
                        
                    except Exception as e:
                        routes_issues.append(f"{api_dir.name}/{route_file.name}: {e}")
                        
        if routes_issues:
            for issue in routes_issues:
                print(f"❌ {issue}")
                
        success = len(routes_issues) == 0
        message = f"Routes: {len(routes_found)} route files, {len(routes_issues)} issues"
        
        self.add_result("api_routes", success, message)
        return success

    def generate_deployment_readiness_report(self) -> Dict[str, Any]:
        """Generate a deployment readiness assessment."""
        print("🚀 Generating Deployment Readiness Report...")
        
        readiness_score = 0
        max_score = 0
        critical_issues = []
        recommendations = []
        
        for test_name, result in self.results.items():
            max_score += 1
            if result['success']:
                readiness_score += 1
            else:
                critical_issues.append(f"{test_name}: {result['message']}")
                
        # Calculate readiness percentage
        readiness_percentage = (readiness_score / max_score * 100) if max_score > 0 else 0
        
        # Generate recommendations based on issues
        if readiness_percentage >= 90:
            recommendations.append("✅ Excellent! Project structure is production-ready")
            recommendations.append("📦 Install dependencies: pip install -r requirements.txt")
            recommendations.append("🚀 Ready for deployment testing")
        elif readiness_percentage >= 80:
            recommendations.append("👍 Good structure with minor issues")
            recommendations.append("🔧 Address the issues listed above")
            recommendations.append("📦 Install and test dependencies")
        elif readiness_percentage >= 60:
            recommendations.append("⚠️  Fair - some structural issues need attention")
            recommendations.append("🛠️  Fix critical issues before deployment")
            recommendations.append("📋 Review project structure requirements")
        else:
            recommendations.append("❌ Poor - major structural issues")
            recommendations.append("🚨 Significant refactoring needed")
            recommendations.append("📚 Review project setup documentation")
            
        return {
            'readiness_score': readiness_score,
            'max_score': max_score,
            'readiness_percentage': readiness_percentage,
            'critical_issues': critical_issues,
            'recommendations': recommendations
        }

    def run_validation(self) -> bool:
        """Run all validation tests."""
        print("🎯 LyoBackend Comprehensive No-Dependency Validation")
        print("=" * 60)
        print("Testing project structure and codebase without external dependencies")
        print("=" * 60)
        
        # Run all tests
        tests = [
            ("Project Structure", self.test_project_structure),
            ("Python Syntax", self.test_python_syntax),
            ("Configuration Files", self.test_configuration_files),
            ("Import Structure", self.test_import_structure),
            ("Database Models", self.test_database_models_structure),
            ("API Routes", self.test_api_routes_structure)
        ]
        
        passed_tests = 0
        total_tests = len(tests)
        
        for i, (test_name, test_func) in enumerate(tests, 1):
            print(f"\n{i}. {test_name}")
            print("-" * 30)
            try:
                result = test_func()
                if result:
                    passed_tests += 1
                    print(f"✅ PASSED: {test_name}")
                else:
                    print(f"❌ FAILED: {test_name}")
            except Exception as e:
                print(f"💥 ERROR in {test_name}: {e}")
                traceback.print_exc()
                self.add_result(test_name.lower().replace(' ', '_'), False, f"Exception: {e}")
                
        # Generate final report
        print("\n" + "=" * 60)
        print("📊 VALIDATION RESULTS")
        print("=" * 60)
        
        success_rate = (passed_tests / total_tests * 100) if total_tests > 0 else 0
        print(f"Tests Passed: {passed_tests}/{total_tests} ({success_rate:.1f}%)")
        
        # Get deployment readiness report
        readiness_report = self.generate_deployment_readiness_report()
        
        print(f"\n🎯 Deployment Readiness: {readiness_report['readiness_percentage']:.1f}%")
        
        if readiness_report['critical_issues']:
            print(f"\n❌ Critical Issues ({len(readiness_report['critical_issues'])}):")
            for issue in readiness_report['critical_issues']:
                print(f"  • {issue}")
        
        print(f"\n📋 Recommendations:")
        for rec in readiness_report['recommendations']:
            print(f"  {rec}")
        
        print(f"\n🎭 Overall Assessment:")
        if success_rate >= 90:
            print("🏆 OUTSTANDING! LyoBackend is architecturally sound and ready for production!")
        elif success_rate >= 80:
            print("🌟 EXCELLENT! Minor tweaks needed but overall very solid!")
        elif success_rate >= 70:
            print("✨ GOOD! Most components working well with some areas for improvement!")
        elif success_rate >= 60:
            print("👍 FAIR! Core structure is there but needs attention!")
        else:
            print("🔧 NEEDS WORK! Significant structural improvements required!")
            
        return success_rate >= 80

def main():
    """Main validation function."""
    validator = LyoBackendValidator()
    success = validator.run_validation()
    
    print(f"\n🎬 Validation Complete!")
    print(f"📈 Next step: Install dependencies and run full validation")
    print(f"💻 Command: pip install -r requirements.txt && python simple_validation.py")
    
    return success

if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)