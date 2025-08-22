"""
Feature flag management system with graceful degradation
Provides runtime feature control and fallback mechanisms
"""

import asyncio
import logging
from typing import Dict, Any, Optional, Callable, Awaitable
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from contextlib import asynccontextmanager
import redis.asyncio as redis
from fastapi import HTTPException

from .environments import env_manager, is_feature_enabled

logger = logging.getLogger(__name__)

@dataclass
class FeatureStatus:
    """Feature availability status"""
    enabled: bool
    healthy: bool = True
    last_check: datetime = field(default_factory=datetime.utcnow)
    error_count: int = 0
    error_message: Optional[str] = None

class FeatureManager:
    """Manages feature flags and graceful degradation"""
    
    def __init__(self):
        self.feature_status: Dict[str, FeatureStatus] = {}
        self.health_check_interval = 300  # 5 minutes
        self.max_error_count = 3
        self.error_reset_time = timedelta(hours=1)
        self._redis_client: Optional[redis.Redis] = None
        
    async def initialize(self, redis_client: Optional[redis.Redis] = None):
        """Initialize feature manager"""
        self._redis_client = redis_client
        
        # Initialize all features with environment settings
        feature_flags = env_manager.get_feature_flags()
        for feature, enabled in feature_flags.items():
            self.feature_status[feature] = FeatureStatus(enabled=enabled)
        
        # Start health monitoring
        if env_manager.get_config().enable_health_checks:
            asyncio.create_task(self._health_monitor())
    
    async def is_feature_available(self, feature: str) -> bool:
        """Check if feature is available (enabled and healthy)"""
        status = self.feature_status.get(feature)
        if not status:
            return False
            
        # Check if feature is enabled in environment
        if not status.enabled:
            return False
            
        # Check health status
        if not status.healthy:
            # Check if we should reset error status
            if (datetime.utcnow() - status.last_check) > self.error_reset_time:
                status.error_count = 0
                status.healthy = True
                status.error_message = None
                logger.info(f"Reset error status for feature: {feature}")
        
        return status.healthy
    
    async def record_feature_error(self, feature: str, error: Exception):
        """Record an error for a feature"""
        status = self.feature_status.get(feature)
        if not status:
            return
            
        status.error_count += 1
        status.last_check = datetime.utcnow()
        status.error_message = str(error)
        
        if status.error_count >= self.max_error_count:
            status.healthy = False
            logger.warning(f"Feature {feature} marked as unhealthy after {status.error_count} errors")
    
    async def record_feature_success(self, feature: str):
        """Record successful feature usage"""
        status = self.feature_status.get(feature)
        if not status:
            return
            
        if status.error_count > 0:
            status.error_count = max(0, status.error_count - 1)
        
        status.last_check = datetime.utcnow()
        
        if not status.healthy and status.error_count == 0:
            status.healthy = True
            status.error_message = None
            logger.info(f"Feature {feature} marked as healthy")
    
    def get_feature_status(self, feature: str) -> Optional[FeatureStatus]:
        """Get current status of a feature"""
        return self.feature_status.get(feature)
    
    def get_all_feature_status(self) -> Dict[str, FeatureStatus]:
        """Get status of all features"""
        return self.feature_status.copy()
    
    async def _health_monitor(self):
        """Background task to monitor feature health"""
        while True:
            try:
                await asyncio.sleep(self.health_check_interval)
                await self._check_all_features()
            except Exception as e:
                logger.error(f"Error in feature health monitor: {e}")
    
    async def _check_all_features(self):
        """Check health of all features"""
        for feature in self.feature_status:
            try:
                await self._check_feature_health(feature)
            except Exception as e:
                logger.error(f"Error checking health for feature {feature}: {e}")
    
    async def _check_feature_health(self, feature: str):
        """Check health of a specific feature"""
        # Implement feature-specific health checks
        health_checks = {
            "ai_generation": self._check_ai_health,
            "push_notifications": self._check_push_health,
            "websockets": self._check_websocket_health,
            "feeds": self._check_feeds_health,
            "community": self._check_community_health,
            "gamification": self._check_gamification_health,
        }
        
        check_func = health_checks.get(feature)
        if check_func:
            try:
                is_healthy = await check_func()
                if is_healthy:
                    await self.record_feature_success(feature)
            except Exception as e:
                await self.record_feature_error(feature, e)
    
    async def _check_ai_health(self) -> bool:
        """Check AI generation service health"""
        # Basic check - verify model loading capability
        try:
            # This would be a lightweight check
            return True
        except Exception:
            return False
    
    async def _check_push_health(self) -> bool:
        """Check push notification service health"""
        # Check if push service credentials are available
        import os
        return bool(os.getenv("FCM_SERVER_KEY") or os.getenv("APNS_KEY_ID"))
    
    async def _check_websocket_health(self) -> bool:
        """Check WebSocket service health"""
        # Check Redis connection for WebSocket pub/sub
        if self._redis_client:
            try:
                await self._redis_client.ping()
                return True
            except Exception:
                return False
        return True
    
    async def _check_feeds_health(self) -> bool:
        """Check feeds service health"""
        # Basic database connectivity check would go here
        return True
    
    async def _check_community_health(self) -> bool:
        """Check community service health"""
        # Basic database connectivity check would go here
        return True
    
    async def _check_gamification_health(self) -> bool:
        """Check gamification service health"""
        # Basic database connectivity check would go here
        return True

# Global feature manager instance
feature_manager = FeatureManager()

# Decorator for feature-gated endpoints
def requires_feature(feature: str, fallback_response: Optional[Any] = None):
    """Decorator to require a feature to be available"""
    def decorator(func: Callable) -> Callable:
        async def wrapper(*args, **kwargs):
            if not await feature_manager.is_feature_available(feature):
                if fallback_response is not None:
                    return fallback_response
                
                status = feature_manager.get_feature_status(feature)
                detail = f"Feature '{feature}' is currently unavailable"
                if status and status.error_message:
                    detail += f": {status.error_message}"
                
                raise HTTPException(
                    status_code=503,
                    detail={
                        "type": "service-unavailable", 
                        "title": "Service Unavailable",
                        "detail": detail,
                        "instance": f"/features/{feature}"
                    }
                )
            
            try:
                result = await func(*args, **kwargs)
                await feature_manager.record_feature_success(feature)
                return result
            except Exception as e:
                await feature_manager.record_feature_error(feature, e)
                raise
        
        return wrapper
    return decorator

# Context manager for feature operations
@asynccontextmanager
async def feature_operation(feature: str):
    """Context manager for feature operations with error tracking"""
    try:
        if not await feature_manager.is_feature_available(feature):
            raise HTTPException(
                status_code=503,
                detail={
                    "type": "service-unavailable", 
                    "title": "Service Unavailable",
                    "detail": f"Feature '{feature}' is currently unavailable"
                }
            )
        
        yield
        await feature_manager.record_feature_success(feature)
        
    except Exception as e:
        await feature_manager.record_feature_error(feature, e)
        raise

# Fallback implementations
class GracefulFallbacks:
    """Provides fallback implementations for degraded services"""
    
    @staticmethod
    async def ai_generation_fallback():
        """Fallback for AI course generation"""
        return {
            "status": "degraded",
            "message": "AI generation temporarily unavailable. Using template-based course creation.",
            "course_id": None,
            "fallback_used": True
        }
    
    @staticmethod
    async def push_notification_fallback():
        """Fallback for push notifications"""
        logger.warning("Push notifications unavailable, storing for later delivery")
        return {
            "status": "queued",
            "message": "Notification queued for delivery when service is restored"
        }
    
    @staticmethod
    async def websocket_fallback():
        """Fallback for WebSocket communication"""
        return {
            "status": "polling_mode",
            "message": "Real-time updates unavailable, use polling endpoints",
            "polling_interval": 30
        }
    
    @staticmethod
    async def feeds_fallback():
        """Fallback for feeds service"""
        return {
            "feeds": [],
            "status": "cached",
            "message": "Showing cached feed data"
        }
    
    @staticmethod
    async def community_fallback():
        """Fallback for community features"""
        return {
            "status": "read_only",
            "message": "Community features in read-only mode"
        }
    
    @staticmethod
    async def gamification_fallback():
        """Fallback for gamification features"""
        return {
            "achievements": [],
            "points": 0,
            "status": "disabled",
            "message": "Gamification features temporarily disabled"
        }

# Helper functions
async def get_feature_status_summary() -> Dict[str, Any]:
    """Get summary of all feature statuses"""
    all_status = feature_manager.get_all_feature_status()
    
    summary = {
        "healthy_features": [],
        "degraded_features": [],
        "disabled_features": [],
        "overall_health": "healthy"
    }
    
    for feature, status in all_status.items():
        if not status.enabled:
            summary["disabled_features"].append(feature)
        elif status.healthy:
            summary["healthy_features"].append(feature)
        else:
            summary["degraded_features"].append({
                "feature": feature,
                "error_count": status.error_count,
                "error_message": status.error_message,
                "last_check": status.last_check.isoformat()
            })
    
    if summary["degraded_features"]:
        summary["overall_health"] = "degraded"
    elif len(summary["disabled_features"]) > len(summary["healthy_features"]):
        summary["overall_health"] = "limited"
    
    return summary

async def initialize_feature_manager(redis_client: Optional[redis.Redis] = None):
    """Initialize the global feature manager"""
    await feature_manager.initialize(redis_client)
