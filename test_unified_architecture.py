#!/usr/bin/env python3
"""
test_unified_architecture.py
Test script for validating the unified architecture implementation.
"""
import os
import sys
import argparse
import logging
from typing import Dict, Any, List, Optional

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger("unified-architecture-test")

# Define test categories
TEST_CATEGORIES = [
    "database", 
    "config", 
    "error", 
    "api", 
    "plugin",
    "all"
]

def test_database_enforcement() -> Dict[str, Any]:
    """Test PostgreSQL enforcement in production environment."""
    logger.info("Testing PostgreSQL enforcement in production...")
    
    # Save original environment variables
    original_env = os.environ.get("ENV")
    original_db_url = os.environ.get("DATABASE_URL")
    
    # Set test environment variables
    os.environ["ENV"] = "production"
    os.environ["DATABASE_URL"] = "sqlite:///./test.db"
    
    try:
        # Import here to ensure we test with the modified environment
        from lyo_app.core.database import get_engine
        
        try:
            # This should raise an exception in production with SQLite
            engine = get_engine()
            result = {
                "status": "failed",
                "message": "PostgreSQL enforcement failed: SQLite was accepted in production"
            }
        except Exception as e:
            # This is expected behavior
            if "SQLite is not allowed in production" in str(e):
                result = {
                    "status": "passed",
                    "message": "PostgreSQL enforcement working correctly"
                }
            else:
                result = {
                    "status": "error",
                    "message": f"Unexpected error: {str(e)}"
                }
    except ImportError as e:
        result = {
            "status": "error",
            "message": f"Failed to import database module: {str(e)}"
        }
    finally:
        # Restore original environment variables
        if original_env:
            os.environ["ENV"] = original_env
        else:
            os.environ.pop("ENV", None)
            
        if original_db_url:
            os.environ["DATABASE_URL"] = original_db_url
        else:
            os.environ.pop("DATABASE_URL", None)
    
    return result

def test_unified_config() -> Dict[str, Any]:
    """Test unified configuration system."""
    logger.info("Testing unified configuration system...")
    
    try:
        from lyo_app.core.unified_config import config
        
        # Test basic config functionality
        try:
            # Access some configuration values
            app_name = config.app_name
            env = config.environment
            
            # Test environment-specific configuration
            is_dev = config.is_development
            is_prod = config.is_production
            
            result = {
                "status": "passed",
                "message": f"Configuration system working correctly. App: {app_name}, Env: {env}",
                "details": {
                    "is_development": is_dev,
                    "is_production": is_prod
                }
            }
        except Exception as e:
            result = {
                "status": "failed",
                "message": f"Configuration system error: {str(e)}"
            }
    except ImportError as e:
        result = {
            "status": "error",
            "message": f"Failed to import unified_config module: {str(e)}"
        }
    
    return result

def test_error_handling() -> Dict[str, Any]:
    """Test standardized error handling."""
    logger.info("Testing standardized error handling...")
    
    try:
        from lyo_app.core.unified_errors import ErrorHandler, ErrorCategory
        
        try:
            # Test error category enum
            categories = [c.name for c in ErrorCategory]
            
            # Test error handler methods
            try:
                # This should raise an HTTPException
                ErrorHandler.raise_bad_request("Test error")
                result = {
                    "status": "failed",
                    "message": "Error handler did not raise exception"
                }
            except Exception as e:
                if "Test error" in str(e):
                    result = {
                        "status": "passed",
                        "message": "Error handling system working correctly",
                        "details": {
                            "categories": categories
                        }
                    }
                else:
                    result = {
                        "status": "failed",
                        "message": f"Unexpected error message: {str(e)}"
                    }
        except Exception as e:
            result = {
                "status": "failed",
                "message": f"Error handling system error: {str(e)}"
            }
    except ImportError as e:
        result = {
            "status": "error",
            "message": f"Failed to import unified_errors module: {str(e)}"
        }
    
    return result

def test_api_schemas() -> Dict[str, Any]:
    """Test API response schemas."""
    logger.info("Testing API response schemas...")
    
    try:
        from lyo_app.core.api_schemas import APIResponse
        
        try:
            # Test success response
            success_response = APIResponse.success(data={"test": "value"})
            
            # Test error response
            error_response = APIResponse.error(message="Test error")
            
            # Test pagination
            paginated_response = APIResponse.paginated(
                data=[{"id": 1}, {"id": 2}],
                total=100,
                page=1,
                page_size=10
            )
            
            result = {
                "status": "passed",
                "message": "API schema system working correctly",
                "details": {
                    "success_response": success_response,
                    "error_response": error_response
                }
            }
        except Exception as e:
            result = {
                "status": "failed",
                "message": f"API schema system error: {str(e)}"
            }
    except ImportError as e:
        result = {
            "status": "error",
            "message": f"Failed to import api_schemas module: {str(e)}"
        }
    
    return result

def test_plugin_system() -> Dict[str, Any]:
    """Test plugin system."""
    logger.info("Testing plugin system...")
    
    try:
        from lyo_app.core.plugin_system import PluginManager, Plugin
        
        try:
            # Create a simple test plugin
            class TestPlugin(Plugin):
                name = "test_plugin"
                version = "1.0.0"
                
                async def on_startup(self):
                    return True
                
                async def on_shutdown(self):
                    return True
            
            # Test plugin manager
            manager = PluginManager()
            manager.register_plugin(TestPlugin())
            
            # Get registered plugins
            plugins = manager.get_plugins()
            
            result = {
                "status": "passed",
                "message": "Plugin system working correctly",
                "details": {
                    "registered_plugins": len(plugins)
                }
            }
        except Exception as e:
            result = {
                "status": "failed",
                "message": f"Plugin system error: {str(e)}"
            }
    except ImportError as e:
        result = {
            "status": "error",
            "message": f"Failed to import plugin_system module: {str(e)}"
        }
    
    return result

def run_tests(categories: List[str]) -> Dict[str, Dict[str, Any]]:
    """Run tests for the specified categories."""
    results = {}
    
    # If "all" is specified, run all tests
    if "all" in categories:
        categories = [c for c in TEST_CATEGORIES if c != "all"]
    
    # Run tests for each category
    for category in categories:
        if category == "database":
            results["database"] = test_database_enforcement()
        elif category == "config":
            results["config"] = test_unified_config()
        elif category == "error":
            results["error"] = test_error_handling()
        elif category == "api":
            results["api"] = test_api_schemas()
        elif category == "plugin":
            results["plugin"] = test_plugin_system()
    
    return results

def format_results(results: Dict[str, Dict[str, Any]]) -> str:
    """Format test results for display."""
    output = "\n" + "=" * 60 + "\n"
    output += "UNIFIED ARCHITECTURE TEST RESULTS\n"
    output += "=" * 60 + "\n\n"
    
    # Count test results
    total = len(results)
    passed = sum(1 for r in results.values() if r["status"] == "passed")
    failed = sum(1 for r in results.values() if r["status"] == "failed")
    errors = sum(1 for r in results.values() if r["status"] == "error")
    
    # Display summary
    output += f"Total Tests: {total}\n"
    output += f"Passed: {passed}\n"
    output += f"Failed: {failed}\n"
    output += f"Errors: {errors}\n\n"
    
    # Display individual test results
    for category, result in results.items():
        status = result["status"].upper()
        if status == "PASSED":
            status_str = f"\033[92m{status}\033[0m"  # Green
        elif status == "FAILED":
            status_str = f"\033[91m{status}\033[0m"  # Red
        else:
            status_str = f"\033[93m{status}\033[0m"  # Yellow
            
        output += f"{category.upper()}: {status_str}\n"
        output += f"  {result['message']}\n"
        
        # Display details if available
        if "details" in result:
            for key, value in result["details"].items():
                output += f"  - {key}: {value}\n"
        
        output += "\n"
    
    return output

def main():
    """Main function."""
    parser = argparse.ArgumentParser(description="Test unified architecture implementation")
    parser.add_argument(
        "--category", 
        "-c", 
        choices=TEST_CATEGORIES, 
        default="all",
        help="Test category to run"
    )
    
    args = parser.parse_args()
    
    # Run tests
    results = run_tests([args.category])
    
    # Display results
    print(format_results(results))
    
    # Exit with appropriate code
    failed = sum(1 for r in results.values() if r["status"] in ["failed", "error"])
    sys.exit(1 if failed > 0 else 0)

if __name__ == "__main__":
    main()
