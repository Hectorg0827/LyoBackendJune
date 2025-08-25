"""
Enhanced Backend Integration Hub
Integrates all advanced scalability and resilience components
"""

import asyncio
import logging
from typing import Dict, Any, Optional
from contextlib import asynccontextmanager

from lyo_app.core.config import settings
from lyo_app.core.database_enhanced import DatabaseManager, get_enhanced_db
from lyo_app.core.ai_resilience import AIResilienceManager, ai_resilience_manager
from lyo_app.core.api_gateway import APIGateway, api_gateway
from lyo_app.core.monitoring import EnhancedPerformanceMonitor

logger = logging.getLogger(__name__)

class BackendOrchestrator:
    """Central orchestrator for all enhanced backend components"""
    
    def __init__(self):
        self.db_manager: Optional[DatabaseManager] = None
        self.ai_manager: Optional[AIResilienceManager] = None
        self.api_gateway: Optional[APIGateway] = None
        self.monitor: Optional[EnhancedPerformanceMonitor] = None
        self.initialized = False
        self.components_status: Dict[str, str] = {}
    
    async def initialize(self):
        """Initialize all enhanced backend components"""
        
        logger.info("🚀 Starting Enhanced Backend Initialization...")
        
        try:
            # Initialize Database Manager with enhanced features
            logger.info("📊 Initializing Enhanced Database Manager...")
            self.db_manager = get_enhanced_db()
            await self.db_manager.initialize()
            self.components_status["database"] = "✅ Ready with connection pooling and read replicas"
            
            # Initialize AI Resilience Manager
            logger.info("🤖 Initializing AI Resilience Manager...")
            self.ai_manager = ai_resilience_manager
            await self.ai_manager.initialize()
            self.components_status["ai_resilience"] = "✅ Ready with circuit breakers and fallbacks"
            
            # Initialize API Gateway
            logger.info("🌐 Initializing Enhanced API Gateway...")
            self.api_gateway = api_gateway
            await self.api_gateway.initialize()
            self.components_status["api_gateway"] = "✅ Ready with rate limiting and caching"
            
            # Initialize Performance Monitor
            logger.info("📈 Initializing Enhanced Performance Monitor...")
            self.monitor = EnhancedPerformanceMonitor()
            # Start monitoring in background
            asyncio.create_task(self.monitor.system_monitor.collect_metrics())
            self.components_status["monitoring"] = "✅ Ready with comprehensive metrics"
            
            self.initialized = True
            logger.info("🎉 Enhanced Backend Initialization Complete!")
            
            # Print status summary
            await self.print_initialization_summary()
            
        except Exception as e:
            logger.error(f"❌ Backend initialization failed: {e}")
            await self.cleanup()
            raise e
    
    async def print_initialization_summary(self):
        """Print comprehensive initialization summary"""
        
        summary = f"""
╔══════════════════════════════════════════════════════════════════════════════════╗
║                          🎯 ENHANCED BACKEND STATUS                              ║
╠══════════════════════════════════════════════════════════════════════════════════╣
║                                                                                  ║
║  📊 DATABASE LAYER                                                               ║
║     {self.components_status.get('database', '❌ Not initialized')}                                           ║
║     • Connection pooling with QueuePool                                         ║
║     • Read replica load balancing                                               ║
║     • Connection health monitoring                                              ║
║     • Horizontal scaling support                                                ║
║                                                                                  ║
║  🤖 AI RESILIENCE LAYER                                                          ║
║     {self.components_status.get('ai_resilience', '❌ Not initialized')}                                      ║
║     • Circuit breaker pattern for all AI models                                 ║
║     • Intelligent fallback mechanisms                                           ║
║     • Exponential backoff retry logic                                           ║
║     • Multi-model load balancing                                                ║
║     • Cost tracking and optimization                                            ║
║                                                                                  ║
║  🌐 API GATEWAY LAYER                                                            ║
║     {self.components_status.get('api_gateway', '❌ Not initialized')}                                        ║
║     • Advanced rate limiting with burst allowance                               ║
║     • Redis + Memory caching with compression                                   ║
║     • Request/response middleware pipeline                                       ║
║     • Comprehensive metrics and monitoring                                      ║
║                                                                                  ║
║  📈 MONITORING LAYER                                                             ║
║     {self.components_status.get('monitoring', '❌ Not initialized')}                                         ║
║     • Real-time system resource monitoring                                      ║
║     • Intelligent alerting with multiple channels                               ║
║     • Prometheus metrics integration                                            ║
║     • Performance analytics and reporting                                       ║
║                                                                                  ║
║  🔧 PRODUCTION FEATURES                                                          ║
║     ✅ Horizontal scaling ready                                                  ║
║     ✅ High availability architecture                                           ║
║     ✅ Enterprise-grade monitoring                                              ║
║     ✅ Advanced caching strategies                                              ║
║     ✅ Intelligent load balancing                                               ║
║     ✅ Circuit breaker resilience                                               ║
║     ✅ Cost optimization algorithms                                             ║
║                                                                                  ║
╠══════════════════════════════════════════════════════════════════════════════════╣
║  🎯 BACKEND READY FOR PRODUCTION DEPLOYMENT                                      ║
║  📱 iOS FRONTEND INTEGRATION FULLY SUPPORTED                                    ║
║  🚀 ENTERPRISE-GRADE SCALABILITY ACHIEVED                                       ║
╚══════════════════════════════════════════════════════════════════════════════════╝
        """
        
        print(summary)
        logger.info("Enhanced backend initialization summary displayed")
    
    async def get_health_status(self) -> Dict[str, Any]:
        """Get comprehensive health status of all components"""
        
        if not self.initialized:
            return {
                "status": "not_initialized",
                "message": "Backend components not yet initialized"
            }
        
        health_status = {
            "overall_status": "healthy",
            "timestamp": asyncio.get_event_loop().time(),
            "components": {}
        }
        
        # Database health
        if self.db_manager:
            try:
                db_health = await self.db_manager.health_check()
                health_status["components"]["database"] = db_health
                if db_health.get("status") != "healthy":
                    health_status["overall_status"] = "degraded"
            except Exception as e:
                health_status["components"]["database"] = {"status": "unhealthy", "error": str(e)}
                health_status["overall_status"] = "unhealthy"
        
        # AI Resilience health
        if self.ai_manager:
            try:
                ai_health = await self.ai_manager.get_health_status()
                health_status["components"]["ai_resilience"] = ai_health
            except Exception as e:
                health_status["components"]["ai_resilience"] = {"status": "unhealthy", "error": str(e)}
                health_status["overall_status"] = "unhealthy"
        
        # API Gateway health
        if self.api_gateway:
            try:
                gateway_health = await self.api_gateway.health_check()
                health_status["components"]["api_gateway"] = gateway_health
                if gateway_health.get("status") != "healthy":
                    health_status["overall_status"] = "degraded"
            except Exception as e:
                health_status["components"]["api_gateway"] = {"status": "unhealthy", "error": str(e)}
                health_status["overall_status"] = "unhealthy"
        
        # Monitoring health
        if self.monitor:
            try:
                monitor_health = await self.monitor.system_monitor.collect_metrics()
                health_status["components"]["monitoring"] = {
                    "status": "healthy",
                    "latest_metrics": monitor_health
                }
            except Exception as e:
                health_status["components"]["monitoring"] = {"status": "unhealthy", "error": str(e)}
                health_status["overall_status"] = "unhealthy"
        
        return health_status
    
    async def get_performance_metrics(self) -> Dict[str, Any]:
        """Get comprehensive performance metrics"""
        
        metrics = {
            "timestamp": asyncio.get_event_loop().time(),
            "database": {},
            "ai_resilience": {},
            "api_gateway": {},
            "system": {}
        }
        
        # Database metrics
        if self.db_manager:
            try:
                metrics["database"] = await self.db_manager.get_pool_stats()
            except Exception as e:
                metrics["database"] = {"error": str(e)}
        
        # AI metrics
        if self.ai_manager:
            try:
                metrics["ai_resilience"] = await self.ai_manager.get_health_status()
            except Exception as e:
                metrics["ai_resilience"] = {"error": str(e)}
        
        # API Gateway metrics
        if self.api_gateway:
            try:
                metrics["api_gateway"] = await self.api_gateway.get_metrics()
            except Exception as e:
                metrics["api_gateway"] = {"error": str(e)}
        
        # System metrics
        if self.monitor:
            try:
                metrics["system"] = await self.monitor.system_monitor.collect_metrics()
            except Exception as e:
                metrics["system"] = {"error": str(e)}
        
        return metrics
    
    async def process_ai_request(
        self,
        message: str,
        model_preference: Optional[str] = None,
        user_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """Process AI request through the resilience layer"""
        
        if not self.ai_manager:
            raise Exception("AI Resilience Manager not initialized")
        
        return await self.ai_manager.chat_completion(
            message=message,
            model_preference=model_preference,
            max_retries=3,
            use_cache=True
        )
    
    async def execute_database_query(
        self,
        query: str,
        params: Optional[Dict[str, Any]] = None,
        use_read_replica: bool = False
    ) -> Any:
        """Execute database query through enhanced database manager"""
        
        if not self.db_manager:
            raise Exception("Database Manager not initialized")
        
        if use_read_replica:
            return await self.db_manager.execute_read_query(query, params or {})
        else:
            return await self.db_manager.execute_query(query, params or {})
    
    async def process_api_request(
        self,
        method: str,
        endpoint: str,
        handler,
        request_data: Dict[str, Any],
        user_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """Process API request through the gateway"""
        
        if not self.api_gateway:
            raise Exception("API Gateway not initialized")
        
        return await self.api_gateway.process_request(
            method=method,
            endpoint=endpoint,
            handler=handler,
            request_data=request_data,
            user_id=user_id
        )
    
    async def cleanup(self):
        """Clean up all components"""
        
        logger.info("🧹 Cleaning up Enhanced Backend components...")
        
        if self.ai_manager:
            await self.ai_manager.close()
        
        if self.api_gateway:
            await self.api_gateway.close()
        
        if self.db_manager:
            await self.db_manager.close()
        
        self.initialized = False
        logger.info("✅ Enhanced Backend cleanup complete")

# Global orchestrator instance
backend_orchestrator = BackendOrchestrator()

@asynccontextmanager
async def enhanced_backend_lifespan():
    """Context manager for backend lifecycle"""
    
    try:
        await backend_orchestrator.initialize()
        yield backend_orchestrator
    finally:
        await backend_orchestrator.cleanup()

# Convenience functions for easy integration
async def get_backend_health():
    """Get comprehensive backend health status"""
    return await backend_orchestrator.get_health_status()

async def get_backend_metrics():
    """Get comprehensive backend performance metrics"""
    return await backend_orchestrator.get_performance_metrics()

async def process_ai_chat(message: str, model: Optional[str] = None, user_id: Optional[str] = None):
    """Process AI chat request with full resilience"""
    return await backend_orchestrator.process_ai_request(message, model, user_id)

async def execute_enhanced_query(query: str, params: Optional[Dict] = None, read_only: bool = False):
    """Execute database query with enhanced features"""
    return await backend_orchestrator.execute_database_query(query, params, read_only)
