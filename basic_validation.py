#!/usr/bin/env python3
"""
Basic Validation Script for LyoBackend
Tests core functionality that works without external dependencies
"""

import os
import sys
import importlib
import traceback
from pathlib import Path

def test_basic_python_environment():
    """Test basic Python environment."""
    print("🐍 Testing Python Environment...")
    
    # Check Python version
    version = sys.version_info
    if version.major != 3 or version.minor < 9:
        print(f"❌ Python version: {version.major}.{version.minor}.{version.micro} (need 3.9+)")
        return False
    
    print(f"✅ Python version: {version.major}.{version.minor}.{version.micro}")
    return True

def test_project_structure():
    """Test that required project files exist."""
    print("📁 Testing Project Structure...")
    
    required_files = [
        "lyo_app/__init__.py",
        "lyo_app/main.py", 
        "lyo_app/core/__init__.py",
        "requirements.txt",
        ".env.example"
    ]
    
    missing_files = []
    for file_path in required_files:
        if not Path(file_path).exists():
            missing_files.append(file_path)
    
    if missing_files:
        print(f"❌ Missing files: {missing_files}")
        return False
    
    print("✅ All required files present")
    return True

def test_configuration_files():
    """Test configuration files."""
    print("⚙️  Testing Configuration Files...")
    
    # Check .env file exists (created by setup)
    env_file = Path(".env")
    if not env_file.exists():
        print("❌ .env file not found - run setup.py first")
        return False
    
    # Check basic structure
    try:
        with open(".env", "r") as f:
            content = f.read()
            
        required_vars = ["DATABASE_URL", "SECRET_KEY", "GEMINI_API_KEY"]
        missing_vars = []
        
        for var in required_vars:
            if var not in content:
                missing_vars.append(var)
        
        if missing_vars:
            print(f"⚠️  Missing environment variables: {missing_vars}")
        else:
            print("✅ Configuration file structure looks good")
        
        return True
        
    except Exception as e:
        print(f"❌ Error reading .env: {e}")
        return False

def test_basic_imports():
    """Test basic Python imports that should work without dependencies."""
    print("📦 Testing Basic Imports...")
    
    # Test standard library imports used by the project
    basic_modules = [
        "json",
        "os", 
        "sys",
        "pathlib",
        "datetime",
        "asyncio",
        "typing",
        "dataclasses"
    ]
    
    failed_imports = []
    for module in basic_modules:
        try:
            importlib.import_module(module)
        except ImportError as e:
            failed_imports.append(f"{module}: {e}")
    
    if failed_imports:
        print(f"❌ Failed basic imports: {failed_imports}")
        return False
    
    print("✅ Basic imports working")
    return True

def test_project_modules_structure():
    """Test that lyo_app modules have correct structure."""
    print("🏗️  Testing Project Module Structure...")
    
    try:
        # Test that we can at least import the package structure
        lyo_app_path = Path("lyo_app")
        
        # Check key directories exist
        key_dirs = ["core", "auth", "ai", "models", "api"]
        missing_dirs = []
        
        for dir_name in key_dirs:
            dir_path = lyo_app_path / dir_name
            if not dir_path.exists():
                missing_dirs.append(str(dir_path))
        
        if missing_dirs:
            print(f"⚠️  Missing directories: {missing_dirs}")
        else:
            print("✅ Core module structure present")
        
        return True
        
    except Exception as e:
        print(f"❌ Error checking module structure: {e}")
        return False

def test_requirements_file():
    """Test requirements.txt has basic content."""
    print("📋 Testing Requirements File...")
    
    try:
        with open("requirements.txt", "r") as f:
            content = f.read()
        
        # Check for key requirements
        key_requirements = ["fastapi", "uvicorn", "sqlalchemy", "pydantic"]
        missing_reqs = []
        
        for req in key_requirements:
            if req.lower() not in content.lower():
                missing_reqs.append(req)
        
        if missing_reqs:
            print(f"⚠️  Missing key requirements: {missing_reqs}")
        else:
            print("✅ Requirements file looks comprehensive")
        
        return True
        
    except Exception as e:
        print(f"❌ Error reading requirements.txt: {e}")
        return False

def main():
    """Run all basic validation tests."""
    print("🎯 LyoBackend Basic Validation")
    print("=" * 50)
    print("Testing core functionality without external dependencies")
    print("=" * 50)
    
    tests = [
        ("Python Environment", test_basic_python_environment),
        ("Project Structure", test_project_structure),
        ("Configuration Files", test_configuration_files),
        ("Basic Imports", test_basic_imports),
        ("Module Structure", test_project_modules_structure),
        ("Requirements File", test_requirements_file)
    ]
    
    passed = 0
    total = len(tests)
    
    for i, (test_name, test_func) in enumerate(tests, 1):
        try:
            print(f"\n{i}. {test_name}")
            result = test_func()
            if result:
                passed += 1
        except Exception as e:
            print(f"❌ {test_name} failed with exception: {e}")
            traceback.print_exc()
    
    print("\n" + "=" * 50)
    print("📊 BASIC VALIDATION RESULTS")
    print("=" * 50)
    
    success_rate = (passed / total) * 100
    rating = (passed / total) * 10
    
    print(f"Tests Passed: {passed}/{total} ({success_rate:.1f}%)")
    print(f"Basic Rating: {rating:.1f}/10")
    
    if passed == total:
        print("\n🎉 EXCELLENT! Core project structure is solid!")
        print("✅ Ready for dependency installation and full validation")
    elif passed >= total * 0.8:
        print("\n👍 GOOD! Most basic checks passed")
        print("🔧 Minor issues but core structure looks good")
    elif passed >= total * 0.6:
        print("\n⚠️  FAIR! Some issues but fixable")
        print("🛠️  Check the failed tests above")
    else:
        print("\n❌ NEEDS WORK! Major structural issues")
        print("🚨 Project structure needs attention")
    
    print(f"\n📝 Next Steps:")
    print(f"1. Fix any issues shown above")
    print(f"2. Install dependencies: pip install -r requirements.txt")
    print(f"3. Run full validation: python simple_validation.py")
    print(f"4. Start server: python start_server.py")
    
    return passed == total

if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)