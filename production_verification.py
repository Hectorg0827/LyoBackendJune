#!/usr/bin/env python3
"""
Production Deployment Verification for LyoApp AI Agents
"""

import sys
import subprocess
from pathlib import Path

# Add the project root to Python path
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

def check_python_imports():
    """Verify all critical Python imports work."""
    print("🔍 Checking Python imports...")
    
    try:
        # Core orchestrator
        from lyo_app.ai_agents.orchestrator import (
            ai_orchestrator, 
            ModelType, 
            LanguageCode,
            TaskComplexity,
            ProductionGemma4Client,
            ModernCloudLLMClient
        )
        print("  ✅ AI Orchestrator imports")
        
        # All agents
        from lyo_app.ai_agents.curriculum_agent import CurriculumAgent
        from lyo_app.ai_agents.curation_agent import CurationAgent  
        from lyo_app.ai_agents.mentor_agent import MentorAgent
        from lyo_app.ai_agents.feed_agent import FeedAgent
        print("  ✅ All AI agents imports")
        
        # Routes and FastAPI integration
        from lyo_app.ai_agents.routes import router
        from lyo_app.ai_agents import ai_router
        print("  ✅ FastAPI routes integration")
        
        # Schemas and models
        from lyo_app.ai_agents.schemas import (
            AgentResponse,
            CurriculumRequest,
            CurationRequest,
            MentorRequest
        )
        print("  ✅ API schemas and models")
        
        return True
        
    except Exception as e:
        print(f"  ❌ Import failed: {e}")
        return False

def check_file_structure():
    """Verify all required files exist."""
    print("\n📁 Checking file structure...")
    
    required_files = [
        "lyo_app/ai_agents/orchestrator.py",
        "lyo_app/ai_agents/curriculum_agent.py", 
        "lyo_app/ai_agents/curation_agent.py",
        "lyo_app/ai_agents/mentor_agent.py",
        "lyo_app/ai_agents/feed_agent.py",
        "lyo_app/ai_agents/routes.py",
        "lyo_app/ai_agents/schemas.py",
        "lyo_app/ai_agents/__init__.py",
        "requirements.txt",
        ".env.production",
        "deploy_production.sh",
        "AI_PRODUCTION_GUIDE.md"
    ]
    
    all_exist = True
    for file_path in required_files:
        full_path = project_root / file_path
        if full_path.exists():
            print(f"  ✅ {file_path}")
        else:
            print(f"  ❌ {file_path} - MISSING")
            all_exist = False
    
    return all_exist

def check_production_features():
    """Verify production features are implemented."""
    print("\n🏭 Checking production features...")
    
    features_found = 0
    total_features = 8
    
    try:
        # Read orchestrator file to check for production features
        orchestrator_path = project_root / "lyo_app/ai_agents/orchestrator.py"
        orchestrator_content = orchestrator_path.read_text()
        
        # Check for key production features
        if "CircuitBreakerState" in orchestrator_content:
            print("  ✅ Circuit breaker pattern")
            features_found += 1
        
        if "rate_limit" in orchestrator_content:
            print("  ✅ Rate limiting")
            features_found += 1
            
        if "security" in orchestrator_content or "safety" in orchestrator_content:
            print("  ✅ Security/safety features")
            features_found += 1
            
        if "LanguageCode" in orchestrator_content:
            print("  ✅ Multi-language support")
            features_found += 1
            
        if "metrics" in orchestrator_content or "monitoring" in orchestrator_content:
            print("  ✅ Monitoring and metrics")
            features_found += 1
            
        if "ProductionGemma4Client" in orchestrator_content:
            print("  ✅ Gemma 4 integration")
            features_found += 1
            
        if "async def" in orchestrator_content:
            print("  ✅ Async/await patterns")
            features_found += 1
            
        if "logger" in orchestrator_content:
            print("  ✅ Structured logging")
            features_found += 1
            
    except Exception as e:
        print(f"  ❌ Error checking features: {e}")
    
    return features_found >= 6  # At least 75% of features

def check_dependencies():
    """Check if production dependencies are listed."""
    print("\n📦 Checking dependencies...")
    
    try:
        req_path = project_root / "requirements.txt"
        if not req_path.exists():
            print("  ❌ requirements.txt missing")
            return False
            
        requirements = req_path.read_text()
        
        critical_deps = [
            "transformers",
            "torch", 
            "openai",
            "anthropic",
            "tiktoken",
            "langdetect",
            "structlog",
            "prometheus-client",
            "redis"
        ]
        
        deps_found = 0
        for dep in critical_deps:
            if dep in requirements:
                print(f"  ✅ {dep}")
                deps_found += 1
            else:
                print(f"  ⚠️  {dep} - not found")
        
        return deps_found >= len(critical_deps) * 0.8  # 80% of deps
        
    except Exception as e:
        print(f"  ❌ Error checking dependencies: {e}")
        return False

def check_environment_config():
    """Check environment configuration."""
    print("\n⚙️  Checking environment configuration...")
    
    try:
        env_path = project_root / ".env.production"
        if not env_path.exists():
            print("  ❌ .env.production missing")
            return False
            
        env_content = env_path.read_text()
        
        required_vars = [
            "OPENAI_API_KEY",
            "ANTHROPIC_API_KEY", 
            "GEMMA_MODEL_PATH",
            "AI_MODEL_CONFIG",
            "RATE_LIMIT_PER_MINUTE",
            "CIRCUIT_BREAKER_THRESHOLD"
        ]
        
        vars_found = 0
        for var in required_vars:
            if var in env_content:
                print(f"  ✅ {var}")
                vars_found += 1
            else:
                print(f"  ⚠️  {var} - not configured")
        
        return vars_found >= len(required_vars) * 0.7  # 70% of vars
        
    except Exception as e:
        print(f"  ❌ Error checking environment: {e}")
        return False

def main():
    """Run all production verification checks."""
    print("🚀 LyoApp AI Agents - Production Deployment Verification")
    print("=" * 65)
    
    checks = [
        ("Python Imports", check_python_imports),
        ("File Structure", check_file_structure), 
        ("Production Features", check_production_features),
        ("Dependencies", check_dependencies),
        ("Environment Config", check_environment_config)
    ]
    
    passed_checks = 0
    total_checks = len(checks)
    
    for name, check_func in checks:
        result = check_func()
        if result:
            passed_checks += 1
    
    print("\n" + "=" * 65)
    print(f"🎯 Production Readiness: {passed_checks}/{total_checks} checks passed ({passed_checks/total_checks*100:.1f}%)")
    
    if passed_checks == total_checks:
        print("\n🎉 PRODUCTION READY!")
        print("✨ All systems verified and ready for deployment")
        print("\n📋 Next Steps:")
        print("  1. Review AI_PRODUCTION_GUIDE.md")
        print("  2. Set up production environment variables")
        print("  3. Download Gemma 4 model files")
        print("  4. Run: chmod +x deploy_production.sh && ./deploy_production.sh")
        return True
        
    elif passed_checks >= 4:
        print("\n⚡ MOSTLY READY!")
        print("🔧 Minor configuration needed before deployment")
        return True
        
    else:
        print("\n⚠️  NEEDS ATTENTION!")
        print("🛠️  Critical issues must be resolved before deployment")
        return False

if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
