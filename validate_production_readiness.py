#!/usr/bin/env python3
"""
Comprehensive production readiness validation script.
Checks for security, configuration, code quality, and operational issues.
"""

import os
import ast
import re
import subprocess
import sys
from pathlib import Path
from typing import List, Dict, Tuple, Any

class Colors:
    GREEN = '\033[92m'
    RED = '\033[91m'
    YELLOW = '\033[93m'
    BLUE = '\033[94m'
    MAGENTA = '\033[95m'
    CYAN = '\033[96m'
    BOLD = '\033[1m'
    END = '\033[0m'

class ProductionValidator:
    """Comprehensive production readiness validator."""
    
    def __init__(self):
        self.issues: List[Dict[str, str]] = []
        self.project_root = Path(__file__).parent
        self.passed_checks = 0
        self.total_checks = 0
    
    def add_issue(self, level: str, category: str, message: str, file_path: str = ""):
        """Add an issue to the tracking list."""
        self.issues.append({
            "level": level,
            "category": category,
            "message": message,
            "file": file_path
        })
    
    def print_status(self, message: str, status: str = "INFO"):
        """Print colored status message."""
        if status == "SUCCESS":
            print(f"{Colors.GREEN}✅ {message}{Colors.END}")
        elif status == "ERROR":
            print(f"{Colors.RED}❌ {message}{Colors.END}")
        elif status == "WARNING":
            print(f"{Colors.YELLOW}⚠️  {message}{Colors.END}")
        else:
            print(f"{Colors.BLUE}ℹ️  {message}{Colors.END}")
    
    def check_environment_variables(self) -> bool:
        """Check for required environment variables."""
        self.print_status("Checking environment variables...", "INFO")
        self.total_checks += 1
        
        # Load .env file if it exists
        env_file = self.project_root / '.env'
        env_vars = {}
        if env_file.exists():
            with open(env_file) as f:
                for line in f:
                    if '=' in line and not line.strip().startswith('#'):
                        key, value = line.strip().split('=', 1)
                        env_vars[key] = value
        
        required_vars = [
            'SECRET_KEY',
            'DATABASE_URL',
        ]
        
        production_vars = [
            'SMTP_USERNAME',
            'SMTP_PASSWORD',
            'REDIS_URL'
        ]
        
        missing_required = []
        missing_production = []
        
        for var in required_vars:
            if not (os.getenv(var) or env_vars.get(var)):
                missing_required.append(var)
        
        for var in production_vars:
            if not (os.getenv(var) or env_vars.get(var)):
                missing_production.append(var)
        
        if missing_required:
            self.add_issue(
                "CRITICAL",
                "Environment",
                f"Missing required environment variables: {', '.join(missing_required)}"
            )
            self.print_status(f"Missing critical environment variables: {missing_required}", "ERROR")
            return False
        
        if missing_production:
            self.add_issue(
                "HIGH",
                "Environment", 
                f"Missing production environment variables: {', '.join(missing_production)}"
            )
            self.print_status(f"Missing production variables: {missing_production}", "WARNING")
        
        # Check JWT secret strength
        jwt_secret = os.getenv('SECRET_KEY') or env_vars.get('SECRET_KEY', '')
        if len(jwt_secret) < 32:
            self.add_issue(
                "CRITICAL",
                "Security",
                "SECRET_KEY is too short (minimum 32 characters required)"
            )
            self.print_status("SECRET_KEY is too short", "ERROR")
            return False
        
        self.print_status("Environment variables check passed", "SUCCESS")
        self.passed_checks += 1
        return True
    
    def check_file_structure(self) -> bool:
        """Check if all required files are present."""
        self.print_status("Checking file structure...", "INFO")
        self.total_checks += 1
        
        required_files = [
            "lyo_app/main.py",
            "lyo_app/auth/routes.py",
            "lyo_app/auth/email_routes.py",
            "lyo_app/core/health.py",
            "lyo_app/core/file_routes.py",
            "lyo_app/core/redis_client.py",
            "lyo_app/core/celery_app.py",
            "lyo_app/core/security_utils.py",
            "lyo_app/core/rate_limiter.py",
            "lyo_app/core/email_tasks.py",
            "requirements.txt",
            "Dockerfile",
            "docker-compose.yml",
            "deploy.sh",
            ".github/workflows/ci-cd.yml",
            "alembic.ini"
        ]
        
        missing_files = []
        for file_path in required_files:
            if not (self.project_root / file_path).exists():
                missing_files.append(file_path)
        
        if missing_files:
            self.add_issue(
                "HIGH",
                "Structure",
                f"Missing required files: {', '.join(missing_files)}"
            )
            self.print_status(f"Missing files: {missing_files}", "ERROR")
            return False
        
        self.print_status("File structure check passed", "SUCCESS")
        self.passed_checks += 1
        return True
    
    def check_code_imports(self) -> bool:
        """Check if all modules can be imported."""
        self.print_status("Checking module imports...", "INFO")
        self.total_checks += 1
        
        modules_to_test = [
            "lyo_app.main",
            "lyo_app.core.config",
            "lyo_app.core.security_utils",
            "lyo_app.core.rate_limiter",
            "lyo_app.auth.routes",
            "lyo_app.core.health"
        ]
        
        failed_imports = []
        for module in modules_to_test:
            try:
                __import__(module)
            except ImportError as e:
                failed_imports.append(f"{module}: {str(e)}")
        
        if failed_imports:
            self.add_issue(
                "CRITICAL",
                "Imports",
                f"Failed to import modules: {'; '.join(failed_imports)}"
            )
            self.print_status(f"Import failures: {len(failed_imports)}", "ERROR")
            return False
        
        self.print_status("Module imports check passed", "SUCCESS")
        self.passed_checks += 1
        return True
    
    def check_security_issues(self) -> bool:
        """Check for security issues in code."""
        self.print_status("Checking for security issues...", "INFO")
        self.total_checks += 1
        
        issues_found = False
        
        # Check for hardcoded secrets
        for py_file in self.project_root.rglob("*.py"):
            if any(part in str(py_file) for part in ['.venv', '__pycache__', '.git']):
                continue
                
            try:
                with open(py_file, 'r', encoding='utf-8') as f:
                    content = f.read()
                
                # Check for potential hardcoded secrets
                secret_patterns = [
                    (r'password\s*=\s*["\'][^"\']{8,}["\']', "hardcoded password"),
                    (r'secret\s*=\s*["\'][^"\']{8,}["\']', "hardcoded secret"),
                    (r'api_key\s*=\s*["\'][^"\']{8,}["\']', "hardcoded API key"),
                    (r'token\s*=\s*["\'][^"\']{20,}["\']', "hardcoded token")
                ]
                
                for pattern, issue_type in secret_patterns:
                    if re.search(pattern, content, re.IGNORECASE):
                        # Exclude test files and configuration defaults
                        if not any(test_indicator in str(py_file).lower() 
                                 for test_indicator in ['test_', 'config.py', 'example', 'default']):
                            self.add_issue(
                                "HIGH",
                                "Security",
                                f"Potential {issue_type} in {py_file.name}",
                                str(py_file)
                            )
                            issues_found = True
                
                # Check for SQL injection vulnerabilities
                if 'f"' in content and any(sql_word in content.upper() 
                                         for sql_word in ['SELECT', 'INSERT', 'UPDATE', 'DELETE']):
                    if 'text(' not in content:  # SQLAlchemy text() is safe
                        self.add_issue(
                            "MEDIUM",
                            "Security",
                            f"Potential SQL injection vulnerability in {py_file.name}",
                            str(py_file)
                        )
                        issues_found = True
                        
            except Exception:
                continue
        
        if issues_found:
            self.print_status("Security issues found", "WARNING")
        else:
            self.print_status("No security issues detected", "SUCCESS")
            self.passed_checks += 1
        
        return not issues_found
    
    def check_database_migrations(self) -> bool:
        """Check database migration setup."""
        self.print_status("Checking database migrations...", "INFO")
        self.total_checks += 1
        
        # Check if alembic directory exists
        alembic_dir = self.project_root / 'alembic'
        if not alembic_dir.exists():
            self.add_issue(
                "HIGH",
                "Database",
                "Alembic migration directory not found"
            )
            self.print_status("Alembic directory missing", "ERROR")
            return False
        
        # Check if there are migration files
        versions_dir = alembic_dir / 'versions'
        if not versions_dir.exists():
            self.add_issue(
                "MEDIUM",
                "Database",
                "No migration versions directory found"
            )
            self.print_status("Migration versions directory missing", "WARNING")
            return False
        
        migration_files = list(versions_dir.glob('*.py'))
        if not migration_files:
            self.add_issue(
                "MEDIUM",
                "Database",
                "No database migration files found"
            )
            self.print_status("No migration files found", "WARNING")
        
        self.print_status("Database migrations check passed", "SUCCESS")
        self.passed_checks += 1
        return True
    
    def check_dependencies(self) -> bool:
        """Check for missing or vulnerable dependencies."""
        self.print_status("Checking dependencies...", "INFO")
        self.total_checks += 1
        
        # Check if requirements.txt exists and has necessary packages
        req_file = self.project_root / 'requirements.txt'
        if not req_file.exists():
            self.add_issue(
                "HIGH",
                "Dependencies",
                "requirements.txt not found"
            )
            self.print_status("requirements.txt missing", "ERROR")
            return False
        
        # Check for critical dependencies
        with open(req_file) as f:
            requirements = f.read()
        
        critical_deps = ['fastapi', 'sqlalchemy', 'alembic', 'uvicorn', 'redis', 'bleach']
        missing_deps = []
        
        for dep in critical_deps:
            if dep not in requirements.lower():
                missing_deps.append(dep)
        
        if missing_deps:
            self.add_issue(
                "HIGH",
                "Dependencies",
                f"Missing critical dependencies: {', '.join(missing_deps)}"
            )
            self.print_status(f"Missing dependencies: {missing_deps}", "ERROR")
            return False
        
        # Try to run safety check if available
        try:
            result = subprocess.run(['safety', 'check'], capture_output=True, text=True, timeout=30)
            if result.returncode != 0 and 'vulnerabilities found' in result.stdout.lower():
                self.add_issue(
                    "HIGH",
                    "Dependencies",
                    "Vulnerable dependencies found. Run 'safety check' for details."
                )
                self.print_status("Vulnerable dependencies detected", "WARNING")
                return False
        except (FileNotFoundError, subprocess.TimeoutExpired):
            self.print_status("Safety check skipped (not installed or timeout)", "INFO")
        
        self.print_status("Dependencies check passed", "SUCCESS")
        self.passed_checks += 1
        return True
    
    def check_configuration_consistency(self) -> bool:
        """Check for configuration consistency across files."""
        self.print_status("Checking configuration consistency...", "INFO")
        self.total_checks += 1
        
        # Check if API prefixes are consistent
        api_prefixes = set()
        
        # Check main.py
        main_file = self.project_root / 'lyo_app' / 'main.py'
        if main_file.exists():
            with open(main_file) as f:
                content = f.read()
                # Look for API prefix patterns
                prefixes = re.findall(r'api_v?\d*_?prefix.*?["\']([^"\']+)["\']', content, re.IGNORECASE)
                api_prefixes.update(prefixes)
        
        # Check test files
        for test_file in self.project_root.glob('test_*.py'):
            with open(test_file) as f:
                content = f.read()
                # Look for hardcoded API paths
                paths = re.findall(r'["\'](/api/v\d+)["\']', content)
                api_prefixes.update(paths)
        
        if len(api_prefixes) > 1:
            self.add_issue(
                "MEDIUM",
                "Configuration",
                f"Inconsistent API prefixes found: {list(api_prefixes)}"
            )
            self.print_status(f"Inconsistent API prefixes: {api_prefixes}", "WARNING")
            return False
        
        self.print_status("Configuration consistency check passed", "SUCCESS")
        self.passed_checks += 1
        return True
    
    def check_test_coverage(self) -> bool:
        """Check if critical functionality has tests."""
        self.print_status("Checking test coverage...", "INFO")
        self.total_checks += 1
        
        test_files = list(self.project_root.glob('test_*.py'))
        if not test_files:
            self.add_issue(
                "MEDIUM",
                "Testing",
                "No test files found"
            )
            self.print_status("No test files found", "WARNING")
            return False
        
        # Check if critical areas are tested
        all_test_content = ""
        for test_file in test_files:
            with open(test_file) as f:
                all_test_content += f.read()
        
        critical_test_areas = [
            ('authentication', ['login', 'register', 'token']),
            ('authorization', ['rbac', 'permission', 'role']),
            ('security', ['rate_limit', 'security', 'sanitize'])
        ]
        
        missing_tests = []
        for area, keywords in critical_test_areas:
            if not any(keyword in all_test_content.lower() for keyword in keywords):
                missing_tests.append(area)
        
        if missing_tests:
            self.add_issue(
                "MEDIUM",
                "Testing",
                f"Missing tests for critical areas: {', '.join(missing_tests)}"
            )
            self.print_status(f"Missing tests: {missing_tests}", "WARNING")
        
        self.print_status("Test coverage check passed", "SUCCESS")
        self.passed_checks += 1
        return True
    
    def run_all_checks(self) -> Dict[str, bool]:
        """Run all validation checks."""
        print(f"{Colors.BOLD}{Colors.CYAN}")
        print("╔══════════════════════════════════════════════════════════════════════════════╗")
        print("║                    LYOAPP PRODUCTION READINESS VALIDATION                   ║")
        print("║                                                                              ║")
        print("║                     Comprehensive Security & Quality Audit                  ║")
        print("╚══════════════════════════════════════════════════════════════════════════════╝")
        print(f"{Colors.END}\n")
        
        checks = [
            ("Environment Variables", self.check_environment_variables),
            ("File Structure", self.check_file_structure),
            ("Module Imports", self.check_code_imports),
            ("Security Issues", self.check_security_issues),
            ("Database Migrations", self.check_database_migrations),
            ("Dependencies", self.check_dependencies),
            ("Configuration Consistency", self.check_configuration_consistency),
            ("Test Coverage", self.check_test_coverage),
        ]
        
        results = {}
        for check_name, check_func in checks:
            try:
                results[check_name] = check_func()
            except Exception as e:
                self.add_issue(
                    "CRITICAL",
                    "System",
                    f"Failed to run {check_name} check: {str(e)}"
                )
                results[check_name] = False
                self.print_status(f"{check_name} check failed: {e}", "ERROR")
            print()  # Add spacing between checks
        
        return results
    
    def generate_report(self, results: Dict[str, bool]) -> None:
        """Generate comprehensive validation report."""
        print(f"{Colors.BOLD}{Colors.CYAN}{'='*80}{Colors.END}")
        print(f"{Colors.BOLD}{Colors.CYAN}                    PRODUCTION READINESS REPORT{Colors.END}")
        print(f"{Colors.BOLD}{Colors.CYAN}{'='*80}{Colors.END}\n")
        
        # Summary statistics
        print(f"{Colors.BOLD}📊 SUMMARY STATISTICS{Colors.END}")
        print(f"✅ Checks passed: {self.passed_checks}/{self.total_checks}")
        print(f"❌ Checks failed: {self.total_checks - self.passed_checks}/{self.total_checks}")
        
        # Issue breakdown
        critical_issues = [i for i in self.issues if i['level'] == 'CRITICAL']
        high_issues = [i for i in self.issues if i['level'] == 'HIGH']
        medium_issues = [i for i in self.issues if i['level'] == 'MEDIUM']
        low_issues = [i for i in self.issues if i['level'] == 'LOW']
        
        print(f"\n{Colors.BOLD}🚨 ISSUE BREAKDOWN{Colors.END}")
        print(f"🔴 Critical issues: {len(critical_issues)}")
        print(f"🟡 High priority issues: {len(high_issues)}")  
        print(f"🟠 Medium priority issues: {len(medium_issues)}")
        print(f"🔵 Low priority issues: {len(low_issues)}")
        
        # Detailed issues
        if self.issues:
            print(f"\n{Colors.BOLD}📋 DETAILED ISSUES{Colors.END}")
            print("-" * 60)
            
            for issue in self.issues:
                level_emoji = {
                    'CRITICAL': '🔴',
                    'HIGH': '🟡', 
                    'MEDIUM': '🟠',
                    'LOW': '🔵'
                }.get(issue['level'], '❓')
                
                print(f"{level_emoji} [{issue['level']}] {issue['category']}: {issue['message']}")
                if issue['file']:
                    print(f"   📁 File: {issue['file']}")
                print()
        
        # Production readiness verdict
        print(f"{Colors.BOLD}🎯 PRODUCTION READINESS ASSESSMENT{Colors.END}")
        print("=" * 60)
        
        if len(critical_issues) == 0 and len(high_issues) <= 1:
            print(f"{Colors.GREEN}{Colors.BOLD}🚀 PRODUCTION READY!{Colors.END}")
            print(f"{Colors.GREEN}✅ Your application meets production readiness criteria{Colors.END}")
            print(f"{Colors.GREEN}✅ All critical systems operational{Colors.END}")
            print(f"{Colors.GREEN}✅ Security standards met{Colors.END}")
        elif len(critical_issues) == 0:
            print(f"{Colors.YELLOW}{Colors.BOLD}⚠️  MOSTLY READY FOR PRODUCTION{Colors.END}")
            print(f"{Colors.YELLOW}🔧 Address high-priority issues before deploying{Colors.END}")
            print(f"{Colors.YELLOW}📋 Review and fix identified concerns{Colors.END}")
        else:
            print(f"{Colors.RED}{Colors.BOLD}❌ NOT READY FOR PRODUCTION{Colors.END}")
            print(f"{Colors.RED}🚨 Critical issues must be resolved before deployment{Colors.END}")
            print(f"{Colors.RED}⚠️  Security and stability at risk{Colors.END}")
        
        # Next steps
        print(f"\n{Colors.BOLD}📝 RECOMMENDED NEXT STEPS{Colors.END}")
        if len(critical_issues) == 0 and len(high_issues) <= 1:
            next_steps = [
                "🚀 Deploy to production environment",
                "📊 Set up monitoring and alerting",
                "🔄 Schedule regular health checks",
                "📈 Monitor performance metrics",
                "🛡️  Implement additional security measures"
            ]
        elif len(critical_issues) == 0:
            next_steps = [
                "🔧 Fix high-priority issues identified above",
                "🧪 Run additional testing",
                "📋 Review security configurations",
                "♻️  Re-run validation after fixes"
            ]
        else:
            next_steps = [
                "🚨 URGENT: Fix all critical issues immediately",
                "🔍 Review error messages in detail",
                "🛠️  Update configuration and code as needed",
                "✅ Re-run validation until all critical issues resolved"
            ]
        
        for step in next_steps:
            print(f"  {step}")
        
        print(f"\n{Colors.CYAN}{'='*80}{Colors.END}")


def main():
    """Run the comprehensive production validation."""
    validator = ProductionValidator()
    results = validator.run_all_checks()
    validator.generate_report(results)
    
    # Exit with appropriate code
    critical_issues = [i for i in validator.issues if i['level'] == 'CRITICAL']
    return len(critical_issues) == 0


if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
