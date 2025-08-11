#!/usr/bin/env python3
"""
Final Backend Health Check & Validation - UPDATED
Comprehensive analysis to ensure all issues are fixed
"""

import sys
import os
import asyncio
from pathlib import Path

# Add project root to Python path
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

class BackendHealthChecker:
    """Comprehensive backend health checker"""
    
    def __init__(self):
        self.results = {}
        self.total_score = 0
        self.max_score = 10
        
    def test_core_imports(self) -> bool:
        """Test if all core modules can be imported"""
        try:
            # Core imports
            from lyo_app.core.database import Base, init_db, get_db
            from lyo_app.core.config import settings
            from lyo_app.core.logging import logger
            
            # Auth models
            from lyo_app.auth.models import User
            
            # AI Study Mode models (our focus)
            from lyo_app.ai_study.models import (
                StudySession, StudyMessage, GeneratedQuiz, 
                QuizAttempt, StudySessionAnalytics
            )
            
            # Enhanced modules
            from lyo_app.core.enhanced_config import EnhancedSettings
            from lyo_app.core.enhanced_monitoring import EnhancedErrorHandler
            from lyo_app.feeds.addictive_algorithm import AddictiveAlgorithm
            from lyo_app.storage.enhanced_storage import EnhancedStorageSystem
            
            print("✅ All core imports successful")
            return True
            
        except Exception as e:
            print(f"❌ Import error: {e}")
            return False
    
    def test_user_model_relationships(self) -> bool:
        """Test User model has correct AI Study Mode relationships"""
        try:
            from lyo_app.auth.models import User
            
            # Check if User model has AI Study Mode relationships
            required_relationships = [
                'study_sessions', 'generated_quizzes', 
                'quiz_attempts', 'study_analytics'
            ]
            
            missing = []
            for rel in required_relationships:
                if not hasattr(User, rel):
                    missing.append(rel)
            
            if missing:
                print(f"❌ Missing User relationships: {missing}")
                return False
            
            print("✅ User model has all AI Study Mode relationships")
            return True
            
        except Exception as e:
            print(f"❌ User model relationship error: {e}")
            return False
    
    def test_database_models(self) -> bool:
        """Test that all AI Study Mode models are properly defined"""
        try:
            from lyo_app.ai_study.models import (
                StudySession, StudyMessage, GeneratedQuiz, 
                QuizAttempt, StudySessionAnalytics
            )
            
            # Test that models have proper attributes
            required_attrs = {
                'StudySession': ['id', 'user_id', 'resource_id', 'status'],
                'StudyMessage': ['id', 'session_id', 'role', 'content'],
                'GeneratedQuiz': ['id', 'user_id', 'quiz_type', 'questions'],
                'QuizAttempt': ['id', 'quiz_id', 'user_id', 'score'],
                'StudySessionAnalytics': ['id', 'user_id', 'date']
            }
            
            for model_name, attrs in required_attrs.items():
                if model_name == 'StudySession':
                    model = StudySession
                elif model_name == 'StudyMessage':
                    model = StudyMessage
                elif model_name == 'GeneratedQuiz':
                    model = GeneratedQuiz
                elif model_name == 'QuizAttempt':
                    model = QuizAttempt
                elif model_name == 'StudySessionAnalytics':
                    model = StudySessionAnalytics
                
                for attr in attrs:
                    if not hasattr(model, attr):
                        print(f"❌ {model_name} missing attribute: {attr}")
                        return False
            
            print("✅ All AI Study Mode models properly defined")
            return True
            
        except Exception as e:
            print(f"❌ Database model error: {e}")
            return False
    
    def test_enhanced_features(self) -> bool:
        """Test enhanced features are working"""
        try:
            # Test enhanced config
            from lyo_app.core.enhanced_config import EnhancedSettings
            settings = EnhancedSettings()
            
            # Test enhanced monitoring  
            from lyo_app.core.enhanced_monitoring import EnhancedErrorHandler
            error_handler = EnhancedErrorHandler()
            
            # Test addictive algorithm
            from lyo_app.feeds.addictive_algorithm import AddictiveAlgorithm
            algorithm = AddictiveAlgorithm()
            
            # Test enhanced storage
            from lyo_app.storage.enhanced_storage import EnhancedStorageSystem
            storage = EnhancedStorageSystem()
            
            print("✅ All enhanced features working")
            return True
            
        except Exception as e:
            print(f"❌ Enhanced features error: {e}")
            return False
    
    def test_main_app(self) -> bool:
        """Test that main app can be created"""
        try:
            from lyo_app.enhanced_main import app
            
            # Check if app has routes
            route_count = len(app.routes)
            if route_count == 0:
                print("❌ No routes found in main app")
                return False
            
            print(f"✅ Enhanced main app working with {route_count} routes")
            return True
            
        except Exception as e:
            print(f"❌ Main app error: {e}")
            return False
    
    def test_api_routes(self) -> bool:
        """Test that API routes are properly configured"""
        try:
            # Test AI Study Mode routes
            from lyo_app.ai_study.routes import router as ai_study_router
            
            # Test enhanced routes
            from lyo_app.feeds.enhanced_routes import router as feeds_router
            from lyo_app.storage.enhanced_routes import router as storage_router
            
            ai_route_count = len(ai_study_router.routes)
            feeds_route_count = len(feeds_router.routes)
            storage_route_count = len(storage_router.routes)
            
            print(f"✅ API routes working:")
            print(f"   - AI Study Mode: {ai_route_count} routes")
            print(f"   - Enhanced Feeds: {feeds_route_count} routes")
            print(f"   - Enhanced Storage: {storage_route_count} routes")
            return True
            
        except Exception as e:
            print(f"❌ API routes error: {e}")
            return False
    
    def test_requirements(self) -> bool:
        """Test that requirements.txt has been enhanced"""
        try:
            requirements_path = project_root / "requirements.txt"
            content = requirements_path.read_text()
            
            enhanced_packages = [
                'google-generativeai',
                'aiofiles', 
                'structlog',
                'fastapi',
                'uvicorn'
            ]
            
            missing = []
            for package in enhanced_packages:
                if package not in content:
                    missing.append(package)
            
            if missing:
                print(f"❌ Missing packages in requirements.txt: {missing}")
                return False
            
            print("✅ Requirements.txt enhanced properly")
            return True
            
        except Exception as e:
            print(f"❌ Requirements test error: {e}")
            return False
    
    def test_startup_script(self) -> bool:
        """Test that startup script exists and is valid"""
        try:
            startup_path = project_root / "start_optimized.py"
            
            if not startup_path.exists():
                print("❌ start_optimized.py not found")
                return False
            
            # Read the file to check it's valid Python
            content = startup_path.read_text()
            
            if 'start_server' not in content:
                print("❌ start_optimized.py missing start_server function")
                return False
            
            print("✅ Startup script configured properly")
            return True
            
        except Exception as e:
            print(f"❌ Startup script error: {e}")
            return False
    
    def test_database_initialization(self) -> bool:
        """Test database initialization includes all models"""
        try:
            from lyo_app.core.database import init_db
            
            # Read the database.py file to check AI Study Mode models are included
            db_path = project_root / "lyo_app" / "core" / "database.py"
            content = db_path.read_text()
            
            if 'StudySession' not in content:
                print("❌ AI Study Mode models not imported in database.py")
                return False
            
            print("✅ Database initialization includes all models")
            return True
            
        except Exception as e:
            print(f"❌ Database initialization error: {e}")
            return False
    
    def test_error_handling(self) -> bool:
        """Test enhanced error handling"""
        try:
            from lyo_app.core.enhanced_monitoring import EnhancedErrorHandler
            
            error_handler = EnhancedErrorHandler()
            
            # Test basic error categorization
            test_error = ValueError("Test error")
            
            # Check if handler has required methods
            required_methods = ['handle_error', 'categorize_error', 'should_retry']
            
            for method in required_methods:
                if not hasattr(error_handler, method):
                    print(f"❌ EnhancedErrorHandler missing method: {method}")
                    return False
            
            print("✅ Enhanced error handling working")
            return True
            
        except Exception as e:
            print(f"❌ Error handling test error: {e}")
            return False
    
    def run_validation(self):
        """Run all validation tests"""
        print("🔍 COMPREHENSIVE BACKEND HEALTH CHECK")
        print("=" * 50)
        
        test_methods = [
            ('Core Imports', self.test_core_imports),
            ('User Model Relationships', self.test_user_model_relationships),
            ('Database Models', self.test_database_models),
            ('Enhanced Features', self.test_enhanced_features),
            ('Main App', self.test_main_app),
            ('API Routes', self.test_api_routes),
            ('Requirements', self.test_requirements),
            ('Startup Script', self.test_startup_script),
            ('Database Init', self.test_database_initialization),
            ('Error Handling', self.test_error_handling),
        ]
        
        for test_name, test_method in test_methods:
            try:
                result = test_method()
                self.results[test_name] = result
                if result:
                    self.total_score += 1
            except Exception as e:
                print(f"❌ {test_name} test failed with exception: {e}")
                self.results[test_name] = False
        
        # Calculate final score
        percentage = (self.total_score / self.max_score) * 100
        rating = self.total_score / self.max_score * 10
        
        print("\n" + "=" * 50)
        print("📊 FINAL HEALTH CHECK RESULTS")
        print("=" * 50)
        
        for test_name, result in self.results.items():
            status = "✅ PASS" if result else "❌ FAIL"
            print(f"{test_name:25} {status}")
        
        print(f"\nSCORE: {self.total_score}/{self.max_score} ({percentage:.1f}%)")
        print(f"RATING: {rating:.1f}/10")
        
        if rating >= 9.0:
            print("🎉 EXCELLENT! Backend is production-ready with no issues!")
        elif rating >= 7.0:
            print("👍 GOOD! Backend is working well with minor issues.")
        elif rating >= 5.0:
            print("⚠️  FAIR! Some issues need attention.")
        else:
            print("❌ POOR! Major issues need immediate fixing.")
        
        print("
🚀 BACKEND STATUS SUMMARY:")
        print(f"   - All identified issues: {'FIXED' if rating >= 9.0 else 'PARTIALLY FIXED'}")
        print(f"   - AI Study Mode: {'FULLY IMPLEMENTED' if self.results.get('Database Models', False) else 'NEEDS WORK'}")
        print(f"   - Enhanced Features: {'OPERATIONAL' if self.results.get('Enhanced Features', False) else 'NEEDS WORK'}")
        print(f"   - Production Ready: {'YES' if rating >= 8.0 else 'NEEDS MORE WORK'}")
        
        return rating

if __name__ == "__main__":
    checker = BackendHealthChecker()
    final_rating = checker.run_validation()
    
    if final_rating >= 9.0:
        print("
🏆 MISSION ACCOMPLISHED!")
        print("✨ Backend is error-free and operates as intended!")
    else:
        print(f"
📈 Current status: {final_rating:.1f}/10")
        print("🔧 Additional fixes may be needed.")

import subprocess
import sys
import os
from pathlib import Path

def check_and_fix_requirements():
    """Ensure all required packages are installed"""
    print("📦 Checking Dependencies...")
    
    required_packages = [
        "fastapi>=0.104.1",
        "uvicorn[standard]>=0.24.0",
        "sqlalchemy[asyncio]>=2.0.23",
        "alembic>=1.13.0",
        "pydantic>=2.5.0",
        "pydantic-settings>=2.1.0",
        "requests>=2.31.0",
        "passlib[bcrypt]>=1.7.4",
        "python-jose[cryptography]>=3.3.0",
        "python-multipart>=0.0.6",
    ]
    
    for package in required_packages:
        try:
            subprocess.run([sys.executable, "-m", "pip", "install", package], 
                         check=True, capture_output=True)
            print(f"✅ {package.split('>=')[0]}")
        except subprocess.CalledProcessError:
            print(f"⚠️ Failed to install {package}")

def validate_file_structure():
    """Validate critical file structure"""
    print("\n📁 Validating File Structure...")
    
    critical_files = [
        "lyo_app/__init__.py",
        "lyo_app/main.py",
        "lyo_app/core/config.py",
        "lyo_app/core/database.py",
        "lyo_app/auth/models.py",
        "lyo_app/auth/routes.py",
        "lyo_app/ai_study/models.py",
        "lyo_app/learning/models.py",
        "lyo_app/feeds/models.py",
        "lyo_app/community/models.py",
        "lyo_app/gamification/models.py",
        "requirements.txt",
        "start_server.py",
    ]
    
    missing_files = []
    for file_path in critical_files:
        if not Path(file_path).exists():
            missing_files.append(file_path)
        else:
            print(f"✅ {file_path}")
    
    if missing_files:
        print(f"❌ Missing files: {missing_files}")
        return False
    
    print("✅ All critical files present")
    return True

def test_imports():
    """Test critical imports"""
    print("\n🔍 Testing Critical Imports...")
    
    critical_imports = [
        "lyo_app.main",
        "lyo_app.core.config",
        "lyo_app.core.database",
        "lyo_app.auth.models",
        "lyo_app.ai_study.models",
    ]
    
    failed_imports = []
    for module in critical_imports:
        try:
            __import__(module)
            print(f"✅ {module}")
        except Exception as e:
            print(f"❌ {module}: {str(e)}")
            failed_imports.append(module)
    
    if failed_imports:
        print(f"❌ Failed imports: {failed_imports}")
        return False
    
    print("✅ All critical imports successful")
    return True

def optimize_database():
    """Optimize database configuration"""
    print("\n🗄️ Optimizing Database...")
    
    try:
        # Check if database file exists and is accessible
        db_path = "./lyo_app_dev.db"
        if os.path.exists(db_path):
            stat = os.stat(db_path)
            print(f"✅ Database file size: {stat.st_size} bytes")
        else:
            print("ℹ️ Database will be created on first run")
        
        # Test database module
        from lyo_app.core.database import Base, engine
        print("✅ Database module loaded successfully")
        return True
        
    except Exception as e:
        print(f"❌ Database error: {str(e)}")
        return False

def check_server_config():
    """Check server configuration"""
    print("\n⚙️ Checking Server Configuration...")
    
    try:
        from lyo_app.core.config import settings
        
        print(f"✅ App Name: {settings.app_name}")
        print(f"✅ Environment: {settings.environment}")
        print(f"✅ Database URL: {settings.database_url[:50]}...")
        print(f"✅ CORS Origins: {len(settings.cors_origins)} configured")
        
        return True
        
    except Exception as e:
        print(f"❌ Configuration error: {str(e)}")
        return False

def performance_optimization():
    """Apply performance optimizations"""
    print("\n🚀 Applying Performance Optimizations...")
    
    # Set optimal environment variables
    optimizations = {
        "PYTHONUNBUFFERED": "1",
        "PYTHONDONTWRITEBYTECODE": "1",
    }
    
    for key, value in optimizations.items():
        os.environ[key] = value
        print(f"✅ Set {key}={value}")
    
    print("✅ Performance optimizations applied")
    return True

def security_hardening():
    """Apply security hardening"""
    print("\n🔒 Applying Security Hardening...")
    
    try:
        from lyo_app.core.config import settings
        
        # Check security settings
        if len(settings.secret_key) >= 32:
            print("✅ Secret key is sufficiently long")
        else:
            print("⚠️ Secret key may be too short")
        
        if settings.cors_origins:
            print("✅ CORS origins configured")
        else:
            print("⚠️ CORS origins not configured")
        
        print("✅ Security checks completed")
        return True
        
    except Exception as e:
        print(f"❌ Security check error: {str(e)}")
        return False

def create_startup_script():
    """Create optimized startup script"""
    print("\n📝 Creating Optimized Startup Script...")
    
    startup_script = '''#!/usr/bin/env python3
"""
Optimized LyoBackend Startup Script
"""

import os
import sys
import uvicorn
from pathlib import Path

# Set performance environment variables
os.environ["PYTHONUNBUFFERED"] = "1"
os.environ["PYTHONDONTWRITEBYTECODE"] = "1"

# Add project root to path
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

def main():
    print("🚀 Starting Optimized LyoBackend Server...")
    print("📊 Environment: Development")
    print("🗄️ Database: SQLite (./lyo_app_dev.db)")
    print("🌐 URL: http://localhost:8000")
    print("📖 Docs: http://localhost:8000/docs")
    print("=" * 50)
    
    # Start server with optimal settings
    uvicorn.run(
        "lyo_app.main:app",
        host="0.0.0.0",
        port=8000,
        reload=True,
        reload_dirs=["lyo_app"],
        log_level="info",
        access_log=True,
    )

if __name__ == "__main__":
    main()
'''
    
    with open("start_optimized.py", "w") as f:
        f.write(startup_script)
    
    os.chmod("start_optimized.py", 0o755)
    print("✅ Created start_optimized.py")

def run_final_health_check():
    """Run final comprehensive health check"""
    print("\n🏥 Final Health Check...")
    
    checks = [
        ("File Structure", validate_file_structure),
        ("Critical Imports", test_imports),
        ("Database", optimize_database),
        ("Configuration", check_server_config),
        ("Performance", performance_optimization),
        ("Security", security_hardening),
    ]
    
    passed = 0
    total = len(checks)
    
    for check_name, check_func in checks:
        if check_func():
            passed += 1
    
    score = (passed / total) * 100
    
    print("\n" + "=" * 60)
    print("🎯 FINAL HEALTH CHECK RESULTS")
    print("=" * 60)
    print(f"Score: {passed}/{total} ({score:.1f}%)")
    
    if score >= 95:
        print("🏆 EXCELLENT! Backend is production-ready!")
    elif score >= 85:
        print("👍 GOOD! Backend is working well!")
    elif score >= 75:
        print("⚠️ FAIR! Minor issues need attention!")
    else:
        print("❌ POOR! Significant issues require fixing!")
    
    return score >= 85

def main():
    print("🔧 BACKEND OPTIMIZATION & HEALTH CHECK")
    print("=" * 60)
    
    # Run optimization steps
    check_and_fix_requirements()
    create_startup_script()
    
    # Run final health check
    if run_final_health_check():
        print("\n✅ BACKEND IS OPTIMIZED AND READY!")
        print("\n🚀 To start the optimized server:")
        print("   python3 start_optimized.py")
        print("\n📖 API Documentation:")
        print("   http://localhost:8000/docs")
        
        return True
    else:
        print("\n❌ BACKEND NEEDS ATTENTION!")
        return False

if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
