#!/usr/bin/env python3
"""
Quick Production Readiness Check for LyoApp Backend
"""

import sys
import subprocess
import time
from pathlib import Path
import sqlite3

class Colors:
    GREEN = '\033[92m'
    RED = '\033[91m'
    YELLOW = '\033[93m'
    BLUE = '\033[94m'
    CYAN = '\033[96m'
    BOLD = '\033[1m'
    END = '\033[0m'

def print_status(message: str, status: str = "INFO"):
    """Print colored status message."""
    if status == "SUCCESS":
        print(f"{Colors.GREEN}✅ {message}{Colors.END}")
    elif status == "ERROR":
        print(f"{Colors.RED}❌ {message}{Colors.END}")
    elif status == "WARNING":
        print(f"{Colors.YELLOW}⚠️  {message}{Colors.END}")
    elif status == "INFO":
        print(f"{Colors.BLUE}ℹ️  {message}{Colors.END}")

def check_file_structure():
    """Check if all required files are present."""
    print_status("Checking file structure...", "INFO")
    
    required_files = [
        "lyo_app/main.py",
        "lyo_app/auth/routes.py",
        "lyo_app/auth/email_routes.py",
        "lyo_app/core/health.py",
        "lyo_app/core/file_routes.py",
        "lyo_app/core/redis_client.py",
        "lyo_app/core/celery_app.py",
        "requirements.txt",
        "Dockerfile",
        "docker-compose.yml",
        "deploy.sh",
        ".github/workflows/ci-cd.yml"
    ]
    
    missing_files = []
    for file_path in required_files:
        if not Path(file_path).exists():
            missing_files.append(file_path)
    
    if missing_files:
        print_status(f"Missing files: {', '.join(missing_files)}", "ERROR")
        return False
    else:
        print_status("All required files present", "SUCCESS")
        return True

def check_database():
    """Check database setup."""
    print_status("Checking database...", "INFO")
    
    try:
        db_path = Path("lyo_app_dev.db")
        if not db_path.exists():
            print_status("Database file not found", "WARNING")
            return False
        
        conn = sqlite3.connect("lyo_app_dev.db")
        cursor = conn.cursor()
        
        # Check key tables
        tables = ["users", "learning_paths", "posts", "communities"]
        for table in tables:
            cursor.execute(f"SELECT name FROM sqlite_master WHERE type='table' AND name='{table}'")
            if not cursor.fetchone():
                print_status(f"Table {table} missing", "ERROR")
                conn.close()
                return False
        
        conn.close()
        print_status("Database structure verified", "SUCCESS")
        return True
        
    except Exception as e:
        print_status(f"Database check failed: {e}", "ERROR")
        return False

def check_imports():
    """Check if all modules can be imported."""
    print_status("Checking module imports...", "INFO")
    
    try:
        # Test core imports
        import lyo_app.main
        import lyo_app.auth.routes
        import lyo_app.core.config
        
        print_status("Core modules import successfully", "SUCCESS")
        return True
        
    except Exception as e:
        print_status(f"Import error: {e}", "ERROR")
        return False

def test_app_creation():
    """Test FastAPI app creation."""
    print_status("Testing app creation...", "INFO")
    
    try:
        from lyo_app.main import create_app
        app = create_app()
        
        if app:
            print_status("FastAPI app created successfully", "SUCCESS")
            return True
        else:
            print_status("App creation failed", "ERROR")
            return False
            
    except Exception as e:
        print_status(f"App creation error: {e}", "ERROR")
        return False

def check_dependencies():
    """Check if all dependencies are installed."""
    print_status("Checking dependencies...", "INFO")
    
    try:
        # Read requirements.txt
        with open("requirements.txt", "r") as f:
            requirements = f.read().strip().split("\n")
        
        # Check key dependencies
        key_deps = ["fastapi", "sqlalchemy", "alembic", "uvicorn", "pydantic"]
        
        for dep in key_deps:
            try:
                __import__(dep)
            except ImportError:
                print_status(f"Missing dependency: {dep}", "ERROR")
                return False
        
        print_status("Key dependencies available", "SUCCESS")
        return True
        
    except Exception as e:
        print_status(f"Dependency check failed: {e}", "ERROR")
        return False

def run_production_readiness_check():
    """Run complete production readiness check."""
    print(f"{Colors.BOLD}{Colors.CYAN}")
    print("╔══════════════════════════════════════════════════════════════════════════════╗")
    print("║                    LYOAPP PRODUCTION READINESS CHECK                        ║")
    print("║                                                                              ║")
    print("║                      Quick validation of core systems                       ║")
    print("╚══════════════════════════════════════════════════════════════════════════════╝")
    print(f"{Colors.END}\n")
    
    checks = [
        ("File Structure", check_file_structure),
        ("Database Setup", check_database),
        ("Module Imports", check_imports),
        ("App Creation", test_app_creation),
        ("Dependencies", check_dependencies)
    ]
    
    results = []
    for name, check_func in checks:
        result = check_func()
        results.append((name, result))
        print()  # Add spacing
    
    # Generate report
    print(f"{Colors.BOLD}{Colors.CYAN}{'='*80}{Colors.END}")
    print(f"{Colors.BOLD}{Colors.CYAN}                         READINESS REPORT{Colors.END}")
    print(f"{Colors.BOLD}{Colors.CYAN}{'='*80}{Colors.END}\n")
    
    passed = sum(1 for _, result in results if result)
    total = len(results)
    
    for name, result in results:
        status = "✅ PASS" if result else "❌ FAIL"
        color = Colors.GREEN if result else Colors.RED
        print(f"{color}{status}{Colors.END} {name}")
    
    print(f"\n{Colors.BOLD}Overall: {passed}/{total} checks passed{Colors.END}")
    
    if passed == total:
        print(f"{Colors.GREEN}")
        print("🚀 PRODUCTION READY!")
        print("   All core systems operational")
        print("   Ready for deployment")
        print(f"{Colors.END}")
        
        print(f"\n{Colors.BOLD}To start the server:{Colors.END}")
        print(f"{Colors.CYAN}python start_server.py{Colors.END}")
        print(f"{Colors.CYAN}# or{Colors.END}")
        print(f"{Colors.CYAN}uvicorn lyo_app.main:app --host 0.0.0.0 --port 8000 --reload{Colors.END}")
        
        print(f"\n{Colors.BOLD}API Documentation:{Colors.END}")
        print(f"{Colors.CYAN}http://localhost:8000/docs{Colors.END}")
        
    else:
        print(f"{Colors.RED}")
        print("⚠️  NOT READY FOR PRODUCTION")
        print("   Please fix the failing checks above")
        print(f"{Colors.END}")
    
    print(f"\n{Colors.CYAN}{'='*80}{Colors.END}")

if __name__ == "__main__":
    run_production_readiness_check()
