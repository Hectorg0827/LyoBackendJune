#!/usr/bin/env python3
"""
Comprehensive production validation script for LyoBackend v2
Validates all systems, configurations, and production readiness
"""

import asyncio
import sys
import os
import json
import logging
from datetime import datetime
from typing import Dict, List, Any, Optional
from pathlib import Path
import psutil

# Add the project root to Python path
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

# Set environment for testing
os.environ.setdefault("ENVIRONMENT", "production")

try:
    # Core imports
    from lyo_app.core.settings import settings
    from lyo_app.core.database import get_database_url
    from lyo_app.core.environments import env_manager, get_environment_config
    from lyo_app.core.feature_flags import feature_manager, get_feature_status_summary
    
    # Service imports  
    from lyo_app.services.websocket_manager import websocket_manager
    from lyo_app.workers.celery_app import celery_app
    
    # Model imports
    from lyo_app.models.enhanced import User, Course, Task
    from lyo_app.models.loading import ModelManager
    
    # Database
    from sqlalchemy.ext.asyncio import create_async_engine
    from sqlalchemy import text
    import redis.asyncio as redis
    
except ImportError as e:
    print(f"❌ Import Error: {e}")
    print("Please ensure all dependencies are installed")
    sys.exit(1)

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

class ProductionValidator:
    """Comprehensive production validation system"""
    
    def __init__(self):
        self.validation_results = {}
        self.overall_status = "unknown"
        self.critical_failures = []
        self.warnings = []
        
    async def run_all_validations(self) -> Dict[str, Any]:
        """Run all production validation checks"""
        print("🚀 Starting LyoBackend Production Validation")
        print("=" * 60)
        
        validation_categories = [
            ("Environment Configuration", self.validate_environment),
            ("Database Connectivity", self.validate_database),
            ("Redis Connectivity", self.validate_redis),
            ("API Keys & Secrets", self.validate_api_keys),
            ("Feature Flags", self.validate_features),
            ("Celery Workers", self.validate_celery),
            ("WebSocket System", self.validate_websockets),
            ("Model Management", self.validate_models),
            ("Security Configuration", self.validate_security),
            ("Performance Settings", self.validate_performance),
            ("Monitoring & Logging", self.validate_monitoring),
            ("External Services", self.validate_external_services),
            ("System Resources", self.validate_system_resources)
        ]
        
        for category, validator in validation_categories:
            print(f"\n📋 Validating: {category}")
            try:
                result = await validator()
                self.validation_results[category] = result
                
                if result["status"] == "pass":
                    print(f"✅ {category}: PASSED")
                elif result["status"] == "warning":
                    print(f"⚠️  {category}: WARNING - {result['message']}")
                    self.warnings.append(f"{category}: {result['message']}")
                else:
                    print(f"❌ {category}: FAILED - {result['message']}")
                    self.critical_failures.append(f"{category}: {result['message']}")
                    
            except Exception as e:
                error_msg = f"Validation error: {e}"
                print(f"❌ {category}: ERROR - {error_msg}")
                self.validation_results[category] = {
                    "status": "error",
                    "message": error_msg,
                    "details": {}
                }
                self.critical_failures.append(f"{category}: {error_msg}")
        
        # Determine overall status
        if self.critical_failures:
            self.overall_status = "failed"
        elif self.warnings:
            self.overall_status = "warning"
        else:
            self.overall_status = "passed"
            
        return await self.generate_report()
    
    async def validate_environment(self) -> Dict[str, Any]:
        """Validate environment configuration"""
        try:
            config = get_environment_config()
            # settings already imported at module level
            
            checks = {
                "environment_set": bool(os.getenv("ENVIRONMENT")),
                "config_loaded": config is not None,
                "settings_loaded": settings is not None,
                "production_mode": env_manager.is_production(),
                "debug_disabled": not config.debug,
                "proper_log_level": config.log_level in ["WARNING", "ERROR", "CRITICAL"],
            }
            
            passed = all(checks.values())
            details = {
                "environment": env_manager.current_env,
                "checks": checks,
                "config_summary": {
                    "database_pool_size": config.database_pool_size,
                    "redis_max_connections": config.redis_max_connections,
                    "celery_concurrency": config.celery_worker_concurrency,
                    "api_rate_limit": config.api_rate_limit,
                }
            }
            
            return {
                "status": "pass" if passed else "fail",
                "message": "Environment properly configured" if passed else "Environment configuration issues",
                "details": details
            }
            
        except Exception as e:
            return {
                "status": "error", 
                "message": f"Environment validation failed: {e}",
                "details": {}
            }
    
    async def validate_database(self) -> Dict[str, Any]:
        """Validate database connectivity and configuration"""
        try:
            database_url = get_database_url()
            engine = create_async_engine(database_url)
            
            async with engine.begin() as conn:
                # Test basic connectivity
                result = await conn.execute(text("SELECT 1"))
                connection_ok = result.scalar() == 1
                
                # Check database version
                version_result = await conn.execute(text("SELECT version()"))
                db_version = version_result.scalar()
                
                # Check if our tables exist (basic schema check)
                tables_result = await conn.execute(text(
                    "SELECT table_name FROM information_schema.tables WHERE table_schema='public'"
                ))
                tables = [row[0] for row in tables_result.fetchall()]
                
            await engine.dispose()
            
            expected_tables = ["users", "courses", "tasks", "content_items", "user_progress", "achievements"]
            missing_tables = [table for table in expected_tables if table not in tables]
            
            details = {
                "connection": connection_ok,
                "database_version": db_version,
                "tables_found": len(tables),
                "expected_tables": len(expected_tables),
                "missing_tables": missing_tables,
                "database_url_set": bool(database_url),
            }
            
            if not connection_ok:
                return {"status": "fail", "message": "Database connection failed", "details": details}
            elif missing_tables:
                return {
                    "status": "warning", 
                    "message": f"Missing tables: {missing_tables}", 
                    "details": details
                }
            else:
                return {"status": "pass", "message": "Database connectivity verified", "details": details}
                
        except Exception as e:
            return {
                "status": "error",
                "message": f"Database validation failed: {e}",
                "details": {}
            }
    
    async def validate_redis(self) -> Dict[str, Any]:
        """Validate Redis connectivity"""
        try:
            # settings already imported at module level
            redis_client = redis.from_url(settings.REDIS_URL)
            
            # Test basic connectivity
            await redis_client.ping()
            
            # Test pub/sub functionality
            pubsub = redis_client.pubsub()
            await pubsub.subscribe("test_channel")
            await redis_client.publish("test_channel", "test_message")
            
            # Get Redis info
            info = await redis_client.info()
            
            await pubsub.unsubscribe("test_channel")
            await pubsub.close()
            await redis_client.close()
            
            details = {
                "connection": True,
                "version": info.get("redis_version"),
                "connected_clients": info.get("connected_clients"),
                "used_memory_human": info.get("used_memory_human"),
                "pubsub_tested": True,
            }
            
            return {
                "status": "pass", 
                "message": "Redis connectivity verified", 
                "details": details
            }
            
        except Exception as e:
            return {
                "status": "fail",
                "message": f"Redis validation failed: {e}",
                "details": {"connection": False}
            }
    
    async def validate_api_keys(self) -> Dict[str, Any]:
        """Validate API keys and secrets"""
        try:
            required_keys = [
                "SECRET_KEY",
                "DATABASE_URL", 
                "REDIS_URL"
            ]
            
            optional_keys = [
                "OPENAI_API_KEY",
                "GOOGLE_APPLICATION_CREDENTIALS",
                "ANTHROPIC_API_KEY",
                "FCM_SERVER_KEY",
                "APNS_KEY_ID",
                "SENDGRID_API_KEY",
                "SENTRY_DSN"
            ]
            
            key_status = {}
            missing_required = []
            missing_optional = []
            
            for key in required_keys:
                value = os.getenv(key)
                key_status[key] = {
                    "present": bool(value),
                    "length": len(value) if value else 0,
                    "required": True
                }
                if not value:
                    missing_required.append(key)
            
            for key in optional_keys:
                value = os.getenv(key)
                key_status[key] = {
                    "present": bool(value),
                    "length": len(value) if value else 0,
                    "required": False
                }
                if not value:
                    missing_optional.append(key)
            
            details = {
                "key_status": key_status,
                "missing_required": missing_required,
                "missing_optional": missing_optional,
                "total_keys_checked": len(required_keys) + len(optional_keys),
                "required_keys_present": len(required_keys) - len(missing_required)
            }
            
            if missing_required:
                return {
                    "status": "fail",
                    "message": f"Missing required API keys: {missing_required}",
                    "details": details
                }
            elif missing_optional:
                return {
                    "status": "warning",
                    "message": f"Missing optional API keys (some features may be disabled): {missing_optional}",
                    "details": details
                }
            else:
                return {
                    "status": "pass",
                    "message": "All API keys present",
                    "details": details
                }
                
        except Exception as e:
            return {
                "status": "error",
                "message": f"API key validation failed: {e}",
                "details": {}
            }
    
    async def validate_features(self) -> Dict[str, Any]:
        """Validate feature flags and availability"""
        try:
            # Initialize feature manager if not already done
            await feature_manager.initialize()
            
            feature_summary = await get_feature_status_summary()
            all_features = feature_manager.get_all_feature_status()
            
            details = {
                "feature_summary": feature_summary,
                "total_features": len(all_features),
                "healthy_count": len(feature_summary["healthy_features"]),
                "degraded_count": len(feature_summary["degraded_features"]),
                "disabled_count": len(feature_summary["disabled_features"]),
                "overall_health": feature_summary["overall_health"]
            }
            
            if feature_summary["overall_health"] == "healthy":
                return {
                    "status": "pass",
                    "message": "All features healthy",
                    "details": details
                }
            elif feature_summary["overall_health"] == "degraded":
                return {
                    "status": "warning",
                    "message": f"Some features degraded: {len(feature_summary['degraded_features'])}",
                    "details": details
                }
            else:
                return {
                    "status": "warning",
                    "message": "Limited feature availability",
                    "details": details
                }
                
        except Exception as e:
            return {
                "status": "error",
                "message": f"Feature validation failed: {e}",
                "details": {}
            }
    
    async def validate_celery(self) -> Dict[str, Any]:
        """Validate Celery worker configuration"""
        try:
            # Check if Celery is properly configured
            celery_configured = celery_app is not None
            
            # Try to inspect active workers (this might fail if no workers running)
            try:
                inspect = celery_app.control.inspect()
                active_workers = inspect.active()
                worker_count = len(active_workers) if active_workers else 0
            except Exception:
                worker_count = 0
                active_workers = {}
            
            # Check task routing
            task_routes = celery_app.conf.task_routes or {}
            
            details = {
                "celery_configured": celery_configured,
                "active_workers": worker_count,
                "worker_details": active_workers,
                "task_routes_configured": len(task_routes),
                "broker_url_set": bool(celery_app.conf.broker_url),
                "result_backend_set": bool(celery_app.conf.result_backend),
            }
            
            if not celery_configured:
                return {
                    "status": "fail",
                    "message": "Celery not properly configured",
                    "details": details
                }
            elif worker_count == 0:
                return {
                    "status": "warning",
                    "message": "No active Celery workers detected",
                    "details": details
                }
            else:
                return {
                    "status": "pass",
                    "message": f"Celery configured with {worker_count} workers",
                    "details": details
                }
                
        except Exception as e:
            return {
                "status": "error",
                "message": f"Celery validation failed: {e}",
                "details": {}
            }
    
    async def validate_websockets(self) -> Dict[str, Any]:
        """Validate WebSocket system"""
        try:
            # Check WebSocket manager initialization
            manager_initialized = websocket_manager is not None
            
            # Check Redis connectivity for WebSocket pub/sub
            redis_available = False
            try:
                if hasattr(websocket_manager, 'redis_client') and websocket_manager.redis_client:
                    await websocket_manager.redis_client.ping()
                    redis_available = True
            except Exception:
                pass
            
            details = {
                "manager_initialized": manager_initialized,
                "redis_pubsub_available": redis_available,
                "connection_limit": websocket_manager.max_connections if manager_initialized else 0,
                "active_connections": len(websocket_manager.active_connections) if manager_initialized else 0,
            }
            
            if not manager_initialized:
                return {
                    "status": "fail",
                    "message": "WebSocket manager not initialized",
                    "details": details
                }
            elif not redis_available:
                return {
                    "status": "warning",
                    "message": "WebSocket Redis pub/sub unavailable (polling fallback active)",
                    "details": details
                }
            else:
                return {
                    "status": "pass",
                    "message": "WebSocket system operational",
                    "details": details
                }
                
        except Exception as e:
            return {
                "status": "error",
                "message": f"WebSocket validation failed: {e}",
                "details": {}
            }
    
    async def validate_models(self) -> Dict[str, Any]:
        """Validate model management system"""
        try:
            model_manager = ModelManager()
            
            # Check model configuration
            model_config = model_manager.get_model_config()
            config_valid = bool(model_config)
            
            # Check if model directory exists
            model_dir = Path(model_config.get("cache_dir", "./models"))
            model_dir_exists = model_dir.exists()
            
            # Check available disk space
            if model_dir_exists:
                disk_usage = psutil.disk_usage(str(model_dir))
                available_gb = disk_usage.free / (1024**3)
            else:
                available_gb = 0
            
            details = {
                "config_valid": config_valid,
                "model_directory_exists": model_dir_exists,
                "available_disk_space_gb": round(available_gb, 2),
                "model_config": model_config,
                "minimum_space_required": 10  # GB
            }
            
            if not config_valid:
                return {
                    "status": "fail",
                    "message": "Model configuration invalid",
                    "details": details
                }
            elif available_gb < 10:
                return {
                    "status": "warning",
                    "message": f"Low disk space for models: {available_gb:.1f}GB available",
                    "details": details
                }
            else:
                return {
                    "status": "pass",
                    "message": "Model management system ready",
                    "details": details
                }
                
        except Exception as e:
            return {
                "status": "error",
                "message": f"Model validation failed: {e}",
                "details": {}
            }
    
    async def validate_security(self) -> Dict[str, Any]:
        """Validate security configuration"""
        try:
            # settings already imported at module level
            config = get_environment_config()
            
            security_checks = {
                "secret_key_set": bool(settings.secret_key),
                "secret_key_strong": len(settings.secret_key) >= 32 if settings.secret_key else False,
                "jwt_algorithm_secure": settings.jwt_algorithm in ["HS256", "RS256"],
                "cors_configured": len(config.cors_origins) > 0,
                "allowed_hosts_configured": len(config.allowed_hosts) > 0,
                "debug_disabled": not config.debug,
                "rate_limiting_enabled": bool(config.api_rate_limit),
                "password_policy_enforced": config.password_min_length >= 8,
                "login_attempt_limiting": config.max_login_attempts <= 5,
            }
            
            passed_checks = sum(security_checks.values())
            total_checks = len(security_checks)
            
            details = {
                "security_checks": security_checks,
                "passed_checks": passed_checks,
                "total_checks": total_checks,
                "security_score": round((passed_checks / total_checks) * 100, 1),
                "jwt_expire_minutes": config.jwt_access_token_expire_minutes,
                "cors_origins": config.cors_origins,
                "allowed_hosts": config.allowed_hosts,
            }
            
            if passed_checks == total_checks:
                return {
                    "status": "pass",
                    "message": "Security configuration optimal",
                    "details": details
                }
            elif passed_checks >= total_checks * 0.8:
                return {
                    "status": "warning",
                    "message": f"Security score: {details['security_score']}%",
                    "details": details
                }
            else:
                return {
                    "status": "fail",
                    "message": f"Security configuration insufficient: {details['security_score']}%",
                    "details": details
                }
                
        except Exception as e:
            return {
                "status": "error",
                "message": f"Security validation failed: {e}",
                "details": {}
            }
    
    async def validate_performance(self) -> Dict[str, Any]:
        """Validate performance settings"""
        try:
            config = get_environment_config()
            
            performance_checks = {
                "database_pool_adequate": config.database_pool_size >= 5,
                "redis_connections_adequate": config.redis_max_connections >= 20,
                "celery_concurrency_set": config.celery_worker_concurrency > 0,
                "websocket_limit_reasonable": config.websocket_max_connections >= 100,
                "timeouts_configured": config.external_api_timeout > 0,
            }
            
            # Check system resources
            cpu_count = psutil.cpu_count()
            memory = psutil.virtual_memory()
            disk = psutil.disk_usage('/')
            
            system_adequate = {
                "cpu_cores": cpu_count >= 2,
                "memory_gb": memory.total / (1024**3) >= 2,
                "disk_space_gb": disk.free / (1024**3) >= 10,
            }
            
            all_checks = {**performance_checks, **system_adequate}
            passed_checks = sum(all_checks.values())
            total_checks = len(all_checks)
            
            details = {
                "performance_checks": performance_checks,
                "system_checks": system_adequate,
                "system_resources": {
                    "cpu_cores": cpu_count,
                    "memory_gb": round(memory.total / (1024**3), 1),
                    "available_memory_gb": round(memory.available / (1024**3), 1),
                    "disk_free_gb": round(disk.free / (1024**3), 1),
                },
                "passed_checks": passed_checks,
                "total_checks": total_checks,
                "performance_score": round((passed_checks / total_checks) * 100, 1),
            }
            
            if passed_checks == total_checks:
                return {
                    "status": "pass",
                    "message": "Performance configuration optimal",
                    "details": details
                }
            elif passed_checks >= total_checks * 0.7:
                return {
                    "status": "warning",
                    "message": f"Performance score: {details['performance_score']}%",
                    "details": details
                }
            else:
                return {
                    "status": "fail",
                    "message": f"Performance configuration insufficient: {details['performance_score']}%",
                    "details": details
                }
                
        except Exception as e:
            return {
                "status": "error",
                "message": f"Performance validation failed: {e}",
                "details": {}
            }
    
    async def validate_monitoring(self) -> Dict[str, Any]:
        """Validate monitoring and logging configuration"""
        try:
            config = get_environment_config()
            
            monitoring_checks = {
                "metrics_enabled": config.enable_metrics,
                "tracing_enabled": config.enable_tracing,
                "health_checks_enabled": config.enable_health_checks,
                "logging_configured": bool(config.log_level),
                "sentry_configured": bool(os.getenv("SENTRY_DSN")),
            }
            
            # Check if log directory is writable
            log_writable = True
            try:
                log_dir = Path("./logs")
                log_dir.mkdir(exist_ok=True)
                test_file = log_dir / "test.log"
                test_file.write_text("test")
                test_file.unlink()
            except Exception:
                log_writable = False
            
            monitoring_checks["log_directory_writable"] = log_writable
            
            passed_checks = sum(monitoring_checks.values())
            total_checks = len(monitoring_checks)
            
            details = {
                "monitoring_checks": monitoring_checks,
                "log_level": config.log_level,
                "passed_checks": passed_checks,
                "total_checks": total_checks,
                "monitoring_score": round((passed_checks / total_checks) * 100, 1),
            }
            
            if passed_checks >= total_checks * 0.8:
                return {
                    "status": "pass",
                    "message": "Monitoring configuration adequate",
                    "details": details
                }
            elif passed_checks >= total_checks * 0.6:
                return {
                    "status": "warning",
                    "message": f"Monitoring score: {details['monitoring_score']}%",
                    "details": details
                }
            else:
                return {
                    "status": "fail",
                    "message": f"Monitoring configuration insufficient: {details['monitoring_score']}%",
                    "details": details
                }
                
        except Exception as e:
            return {
                "status": "error",
                "message": f"Monitoring validation failed: {e}",
                "details": {}
            }
    
    async def validate_external_services(self) -> Dict[str, Any]:
        """Validate external service integrations"""
        try:
            service_checks = {
                "openai_configured": bool(os.getenv("OPENAI_API_KEY")),
                "google_credentials_configured": bool(os.getenv("GOOGLE_APPLICATION_CREDENTIALS")),
                "anthropic_configured": bool(os.getenv("ANTHROPIC_API_KEY")),
                "push_notifications_configured": bool(os.getenv("FCM_SERVER_KEY")) or bool(os.getenv("APNS_KEY_ID")),
                "email_service_configured": bool(os.getenv("SENDGRID_API_KEY")),
            }
            
            # Try to validate some services with basic connectivity
            connectivity_results = {}
            
            # This would include actual service connectivity tests
            # For now, we'll just check if the credentials are present
            
            available_services = sum(service_checks.values())
            total_services = len(service_checks)
            
            details = {
                "service_checks": service_checks,
                "connectivity_results": connectivity_results,
                "available_services": available_services,
                "total_services": total_services,
                "availability_percentage": round((available_services / total_services) * 100, 1),
            }
            
            if available_services >= total_services * 0.8:
                return {
                    "status": "pass",
                    "message": f"External services configured: {available_services}/{total_services}",
                    "details": details
                }
            elif available_services >= total_services * 0.5:
                return {
                    "status": "warning",
                    "message": f"Some external services missing: {available_services}/{total_services}",
                    "details": details
                }
            else:
                return {
                    "status": "fail",
                    "message": f"Insufficient external services: {available_services}/{total_services}",
                    "details": details
                }
                
        except Exception as e:
            return {
                "status": "error",
                "message": f"External services validation failed: {e}",
                "details": {}
            }
    
    async def validate_system_resources(self) -> Dict[str, Any]:
        """Validate system resources and capacity"""
        try:
            # CPU information
            cpu_info = {
                "count": psutil.cpu_count(),
                "usage_percent": psutil.cpu_percent(interval=1),
            }
            
            # Memory information
            memory = psutil.virtual_memory()
            memory_info = {
                "total_gb": round(memory.total / (1024**3), 2),
                "available_gb": round(memory.available / (1024**3), 2),
                "usage_percent": memory.percent,
            }
            
            # Disk information
            disk = psutil.disk_usage('/')
            disk_info = {
                "total_gb": round(disk.total / (1024**3), 2),
                "free_gb": round(disk.free / (1024**3), 2),
                "usage_percent": round((disk.used / disk.total) * 100, 2),
            }
            
            # Network information
            try:
                network = psutil.net_io_counters()
                network_info = {
                    "bytes_sent": network.bytes_sent,
                    "bytes_recv": network.bytes_recv,
                }
            except Exception:
                network_info = {"error": "Network stats unavailable"}
            
            # Resource adequacy checks
            resource_checks = {
                "cpu_adequate": cpu_info["count"] >= 2,
                "memory_adequate": memory_info["total_gb"] >= 2,
                "memory_available": memory_info["available_gb"] >= 1,
                "disk_space_adequate": disk_info["free_gb"] >= 10,
                "cpu_usage_ok": cpu_info["usage_percent"] < 80,
                "memory_usage_ok": memory_info["usage_percent"] < 80,
                "disk_usage_ok": disk_info["usage_percent"] < 90,
            }
            
            passed_checks = sum(resource_checks.values())
            total_checks = len(resource_checks)
            
            details = {
                "cpu_info": cpu_info,
                "memory_info": memory_info,
                "disk_info": disk_info,
                "network_info": network_info,
                "resource_checks": resource_checks,
                "passed_checks": passed_checks,
                "total_checks": total_checks,
                "resource_score": round((passed_checks / total_checks) * 100, 1),
            }
            
            if passed_checks == total_checks:
                return {
                    "status": "pass",
                    "message": "System resources optimal",
                    "details": details
                }
            elif passed_checks >= total_checks * 0.8:
                return {
                    "status": "warning",
                    "message": f"Resource score: {details['resource_score']}%",
                    "details": details
                }
            else:
                return {
                    "status": "fail",
                    "message": f"Insufficient system resources: {details['resource_score']}%",
                    "details": details
                }
                
        except Exception as e:
            return {
                "status": "error",
                "message": f"System resource validation failed: {e}",
                "details": {}
            }
    
    async def generate_report(self) -> Dict[str, Any]:
        """Generate comprehensive validation report"""
        timestamp = datetime.utcnow().isoformat()
        
        # Calculate statistics
        total_validations = len(self.validation_results)
        passed_validations = len([r for r in self.validation_results.values() if r["status"] == "pass"])
        warning_validations = len([r for r in self.validation_results.values() if r["status"] == "warning"])
        failed_validations = len([r for r in self.validation_results.values() if r["status"] in ["fail", "error"]])
        
        success_rate = (passed_validations / total_validations) * 100 if total_validations > 0 else 0
        
        # Generate recommendations
        recommendations = []
        if self.critical_failures:
            recommendations.append("🔴 Critical: Address all failed validations before production deployment")
        if self.warnings:
            recommendations.append("🟡 Warning: Review and address warning items for optimal performance")
        if success_rate == 100:
            recommendations.append("🟢 Excellent: System is production-ready")
        elif success_rate >= 90:
            recommendations.append("🟢 Good: System is mostly production-ready with minor issues")
        elif success_rate >= 70:
            recommendations.append("🟡 Fair: System needs improvements before production deployment")
        else:
            recommendations.append("🔴 Poor: System requires significant improvements before production deployment")
        
        report = {
            "validation_summary": {
                "timestamp": timestamp,
                "overall_status": self.overall_status,
                "total_validations": total_validations,
                "passed": passed_validations,
                "warnings": warning_validations,
                "failed": failed_validations,
                "success_rate": round(success_rate, 1),
            },
            "critical_failures": self.critical_failures,
            "warnings": self.warnings,
            "recommendations": recommendations,
            "detailed_results": self.validation_results,
            "system_info": {
                "environment": env_manager.current_env,
                "python_version": f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}",
                "platform": sys.platform,
            }
        }
        
        return report

async def main():
    """Main validation execution"""
    validator = ProductionValidator()
    
    try:
        report = await validator.run_all_validations()
        
        # Print summary
        print("\n" + "="*60)
        print("🏁 VALIDATION COMPLETE")
        print("="*60)
        
        summary = report["validation_summary"]
        print(f"📊 Overall Status: {summary['overall_status'].upper()}")
        print(f"📈 Success Rate: {summary['success_rate']}%")
        print(f"✅ Passed: {summary['passed']}")
        print(f"⚠️  Warnings: {summary['warnings']}")
        print(f"❌ Failed: {summary['failed']}")
        
        if report["critical_failures"]:
            print(f"\n🚨 CRITICAL FAILURES ({len(report['critical_failures'])}):")
            for failure in report["critical_failures"]:
                print(f"  • {failure}")
        
        if report["warnings"]:
            print(f"\n⚠️  WARNINGS ({len(report['warnings'])}):")
            for warning in report["warnings"]:
                print(f"  • {warning}")
        
        print(f"\n📋 RECOMMENDATIONS:")
        for rec in report["recommendations"]:
            print(f"  • {rec}")
        
        # Save detailed report
        report_file = f"production_validation_report_{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}.json"
        with open(report_file, 'w') as f:
            json.dump(report, f, indent=2, default=str)
        
        print(f"\n📄 Detailed report saved to: {report_file}")
        
        # Exit with appropriate code
        if summary["overall_status"] == "passed":
            print("\n🎉 PRODUCTION READY! 🚀")
            sys.exit(0)
        elif summary["overall_status"] == "warning":
            print("\n⚠️  PRODUCTION READY WITH WARNINGS")
            sys.exit(0)
        else:
            print("\n❌ NOT PRODUCTION READY")
            sys.exit(1)
            
    except Exception as e:
        print(f"\n💥 VALIDATION FAILED: {e}")
        logger.exception("Validation execution failed")
        sys.exit(1)

if __name__ == "__main__":
    asyncio.run(main())
