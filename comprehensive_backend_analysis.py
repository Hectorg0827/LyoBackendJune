#!/usr/bin/env python3
"""
Comprehensive Backend Analysis and Validation
Deep analysis to ensure error-free operation
"""

import asyncio
import importlib
import sys
import traceback
import requests
from pathlib import Path
from typing import Dict, List, Any, Optional

# Add project root to path
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

class BackendAnalyzer:
    """Comprehensive backend analysis tool"""
    
    def __init__(self):
        self.results = {}
        self.errors = []
        self.warnings = []
        self.total_tests = 0
        self.passed_tests = 0
        
    def test_imports(self) -> Dict[str, bool]:
        """Test all critical imports"""
        print("🔍 Phase 1: Testing Core Imports")
        print("-" * 50)
        
        imports_to_test = [
            # Core modules
            ("lyo_app.main", "Main application"),
            ("lyo_app.core.config", "Core configuration"),
            ("lyo_app.core.database", "Database configuration"),
            ("lyo_app.core.logging", "Logging system"),
            
            # Authentication
            ("lyo_app.auth.models", "Auth models"),
            ("lyo_app.auth.routes", "Auth routes"),
            ("lyo_app.auth.service", "Auth service"),
            
            # AI Study Mode
            ("lyo_app.ai_study.models", "AI Study models"),
            
            # Learning system
            ("lyo_app.learning.models", "Learning models"),
            ("lyo_app.learning.routes", "Learning routes"),
            
            # Feeds system
            ("lyo_app.feeds.models", "Feeds models"),
            ("lyo_app.feeds.routes", "Feeds routes"),
            
            # Community system
            ("lyo_app.community.models", "Community models"),
            ("lyo_app.community.routes", "Community routes"),
            
            # Gamification
            ("lyo_app.gamification.models", "Gamification models"),
            ("lyo_app.gamification.routes", "Gamification routes"),
            
            # Enhanced modules (optional)
            ("lyo_app.enhanced_main", "Enhanced main app"),
            ("lyo_app.feeds.addictive_algorithm", "Addictive algorithm"),
            ("lyo_app.storage.enhanced_storage", "Enhanced storage"),
        ]
        
        results = {}
        for module_name, description in imports_to_test:
            self.total_tests += 1
            try:
                importlib.import_module(module_name)
                print(f"✅ {description}")
                results[module_name] = True
                self.passed_tests += 1
            except Exception as e:
                print(f"❌ {description} - Error: {str(e)}")
                results[module_name] = False
                self.errors.append(f"Import error in {module_name}: {str(e)}")
        
        return results
    
    def test_database_models(self) -> bool:
        """Test database model integrity"""
        print("\n🗄️ Phase 2: Testing Database Models")
        print("-" * 50)
        
        self.total_tests += 1
        try:
            from lyo_app.core.database import Base
            from lyo_app.auth.models import User
            from lyo_app.ai_study.models import StudySession, StudyMessage, GeneratedQuiz
            from lyo_app.learning.models import Course, Lesson
            from lyo_app.feeds.models import Post, Comment
            from lyo_app.community.models import StudyGroup
            from lyo_app.gamification.models import UserXP, Achievement
            
            # Test model relationships
            user_model = User.__table__
            study_session_model = StudySession.__table__
            
            print(f"✅ User model has {len(user_model.columns)} columns")
            print(f"✅ StudySession model has {len(study_session_model.columns)} columns")
            print("✅ All database models loaded successfully")
            
            self.passed_tests += 1
            return True
            
        except Exception as e:
            print(f"❌ Database model error: {str(e)}")
            self.errors.append(f"Database model error: {str(e)}")
            return False
    
    def test_api_routes(self) -> Dict[str, bool]:
        """Test API route registration"""
        print("\n🛣️ Phase 3: Testing API Routes")
        print("-" * 50)
        
        route_modules = [
            ("lyo_app.auth.routes", "Authentication routes"),
            ("lyo_app.learning.routes", "Learning routes"),
            ("lyo_app.feeds.routes", "Feeds routes"),
            ("lyo_app.community.routes", "Community routes"),
            ("lyo_app.gamification.routes", "Gamification routes"),
            ("lyo_app.core.health", "Health check routes"),
        ]
        
        results = {}
        for module_name, description in route_modules:
            self.total_tests += 1
            try:
                module = importlib.import_module(module_name)
                if hasattr(module, 'router'):
                    router = module.router
                    route_count = len(router.routes)
                    print(f"✅ {description} - {route_count} routes")
                    results[module_name] = True
                    self.passed_tests += 1
                else:
                    print(f"⚠️ {description} - No router found")
                    results[module_name] = False
                    self.warnings.append(f"{module_name} has no router attribute")
            except Exception as e:
                print(f"❌ {description} - Error: {str(e)}")
                results[module_name] = False
                self.errors.append(f"Route error in {module_name}: {str(e)}")
        
        return results
    
    def test_server_health(self) -> bool:
        """Test if server is running and healthy"""
        print("\n🏥 Phase 4: Testing Server Health")
        print("-" * 50)
        
        self.total_tests += 1
        try:
            # Test basic connectivity
            response = requests.get("http://localhost:8000/api/v1/health", timeout=5)
            if response.status_code == 200:
                print("✅ Server is running and responding")
                health_data = response.json()
                print(f"✅ Health check status: {health_data.get('status', 'Unknown')}")
                self.passed_tests += 1
                return True
            else:
                print(f"❌ Server returned status code: {response.status_code}")
                self.errors.append(f"Server health check failed with status {response.status_code}")
                return False
                
        except requests.exceptions.ConnectionError:
            print("❌ Server is not running on localhost:8000")
            self.errors.append("Server connection failed - server may not be running")
            return False
        except Exception as e:
            print(f"❌ Health check error: {str(e)}")
            self.errors.append(f"Health check error: {str(e)}")
            return False
    
    def test_configuration(self) -> bool:
        """Test configuration integrity"""
        print("\n⚙️ Phase 5: Testing Configuration")
        print("-" * 50)
        
        self.total_tests += 1
        try:
            from lyo_app.core.config import settings
            
            # Test critical settings
            required_settings = [
                'app_name',
                'database_url',
                'secret_key',
                'cors_origins'
            ]
            
            for setting in required_settings:
                if hasattr(settings, setting):
                    value = getattr(settings, setting)
                    print(f"✅ {setting}: {str(value)[:50]}{'...' if len(str(value)) > 50 else ''}")
                else:
                    print(f"❌ Missing setting: {setting}")
                    self.errors.append(f"Missing configuration setting: {setting}")
                    return False
            
            print("✅ All critical settings present")
            self.passed_tests += 1
            return True
            
        except Exception as e:
            print(f"❌ Configuration error: {str(e)}")
            self.errors.append(f"Configuration error: {str(e)}")
            return False
    
    async def test_database_connection(self) -> bool:
        """Test database connectivity"""
        print("\n🔌 Phase 6: Testing Database Connection")
        print("-" * 50)
        
        self.total_tests += 1
        try:
            from lyo_app.core.database import engine
            
            # Test connection
            async with engine.begin() as conn:
                result = await conn.execute("SELECT 1 as test")
                row = result.fetchone()
                if row and row[0] == 1:
                    print("✅ Database connection successful")
                    self.passed_tests += 1
                    return True
                else:
                    print("❌ Database query failed")
                    self.errors.append("Database query test failed")
                    return False
                    
        except Exception as e:
            print(f"❌ Database connection error: {str(e)}")
            self.errors.append(f"Database connection error: {str(e)}")
            return False
    
    def test_enhanced_features(self) -> Dict[str, bool]:
        """Test enhanced features (optional)"""
        print("\n🚀 Phase 7: Testing Enhanced Features")
        print("-" * 50)
        
        enhanced_features = [
            ("lyo_app.feeds.addictive_algorithm", "TikTok-style addictive algorithm"),
            ("lyo_app.storage.enhanced_storage", "Enhanced storage system"),
            ("lyo_app.core.enhanced_monitoring", "Enhanced monitoring"),
            ("lyo_app.feeds.enhanced_routes", "Enhanced feed routes"),
            ("lyo_app.storage.enhanced_routes", "Enhanced storage routes"),
        ]
        
        results = {}
        for module_name, description in enhanced_features:
            self.total_tests += 1
            try:
                module = importlib.import_module(module_name)
                print(f"✅ {description}")
                results[module_name] = True
                self.passed_tests += 1
            except Exception as e:
                print(f"⚠️ {description} - {str(e)[:50]}...")
                results[module_name] = False
                self.warnings.append(f"Enhanced feature {module_name} not available: {str(e)}")
        
        return results
    
    async def run_comprehensive_analysis(self):
        """Run all tests and provide comprehensive report"""
        print("🔍 COMPREHENSIVE BACKEND ANALYSIS")
        print("=" * 60)
        
        # Run all test phases
        import_results = self.test_imports()
        model_result = self.test_database_models()
        route_results = self.test_api_routes()
        server_result = self.test_server_health()
        config_result = self.test_configuration()
        db_result = await self.test_database_connection()
        enhanced_results = self.test_enhanced_features()
        
        # Generate comprehensive report
        print("\n" + "=" * 60)
        print("📊 COMPREHENSIVE ANALYSIS REPORT")
        print("=" * 60)
        
        print(f"\n📈 OVERALL SCORE: {self.passed_tests}/{self.total_tests} ({(self.passed_tests/self.total_tests)*100:.1f}%)")
        
        if self.passed_tests / self.total_tests >= 0.9:
            print("🎉 EXCELLENT! Backend is in excellent condition")
        elif self.passed_tests / self.total_tests >= 0.8:
            print("👍 GOOD! Backend is working well with minor issues")
        elif self.passed_tests / self.total_tests >= 0.7:
            print("⚠️ FAIR! Backend has some issues that need attention")
        else:
            print("❌ POOR! Backend has significant issues requiring immediate attention")
        
        # Error summary
        if self.errors:
            print(f"\n❌ ERRORS FOUND ({len(self.errors)}):")
            for i, error in enumerate(self.errors, 1):
                print(f"  {i}. {error}")
        
        # Warning summary
        if self.warnings:
            print(f"\n⚠️ WARNINGS ({len(self.warnings)}):")
            for i, warning in enumerate(self.warnings, 1):
                print(f"  {i}. {warning}")
        
        # Recommendations
        print("\n💡 RECOMMENDATIONS:")
        if not self.errors:
            print("  ✅ No critical errors found - backend is ready for production!")
        else:
            print("  🔧 Fix the identified errors to improve backend stability")
        
        if self.warnings:
            print("  📦 Install optional dependencies for enhanced features:")
            print("      pip install scikit-learn opencv-python psutil boto3 redis")
        
        print("\n🔗 API Documentation: http://localhost:8000/docs")
        print("🔗 Health Check: http://localhost:8000/api/v1/health")
        
        return {
            'score': self.passed_tests / self.total_tests,
            'passed': self.passed_tests,
            'total': self.total_tests,
            'errors': self.errors,
            'warnings': self.warnings
        }

async def main():
    analyzer = BackendAnalyzer()
    results = await analyzer.run_comprehensive_analysis()
    
    # Exit with appropriate code
    if results['score'] >= 0.8:
        print("\n✅ Backend analysis completed successfully!")
        sys.exit(0)
    else:
        print("\n❌ Backend analysis found significant issues!")
        sys.exit(1)

if __name__ == "__main__":
    asyncio.run(main())
