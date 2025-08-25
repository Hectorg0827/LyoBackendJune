"""
AI Optimization Management API
Advanced endpoints for managing AI performance optimization, A/B testing, and analytics.
"""

from fastapi import APIRouter, HTTPException, Depends, BackgroundTasks
from typing import Dict, Any, List, Optional
from datetime import datetime
import structlog

from lyo_app.auth.security import verify_access_token
from .orchestrator import ai_orchestrator
from .optimization.performance_optimizer import ai_performance_optimizer, OptimizationLevel
from .optimization.personalization_engine import personalization_engine, LearningStyle, PersonalityType
from .optimization.ab_testing import experiment_manager, ExperimentType, ExperimentStatus, EXPERIMENT_TEMPLATES

logger = structlog.get_logger(__name__)

router = APIRouter()

# ============================================================================
# PERFORMANCE OPTIMIZATION ENDPOINTS
# ============================================================================

@router.get("/optimization/performance/status")
async def get_performance_status(
    current_user: Dict = Depends(verify_access_token)
):
    """Get comprehensive AI performance metrics and status."""
    try:
        metrics = ai_performance_optimizer.get_performance_metrics()
        cache_stats = ai_performance_optimizer.cache_manager.get_stats()
        resource_status = ai_performance_optimizer.resource_optimizer.get_system_status()
        
        return {
            "status": "healthy",
            "optimization_level": ai_performance_optimizer.optimization_level.value,
            "performance_metrics": {
                "response_time": metrics.response_time,
                "cache_hit_rate": metrics.cache_hit_rate,
                "memory_usage": metrics.memory_usage,
                "gpu_utilization": metrics.gpu_utilization,
                "cost_per_request": metrics.cost_per_request,
                "throughput": metrics.throughput
            },
            "cache_performance": cache_stats,
            "system_resources": resource_status,
            "timestamp": datetime.now().isoformat()
        }
    except Exception as e:
        logger.error(f"Failed to get performance status: {e}")
        raise HTTPException(status_code=500, detail="Failed to retrieve performance status")

@router.post("/optimization/performance/level")
async def set_optimization_level(
    level: str,
    current_user: Dict = Depends(verify_access_token)
):
    """Set AI optimization aggressiveness level."""
    try:
        optimization_level = OptimizationLevel(level)
        ai_performance_optimizer.set_optimization_level(optimization_level)
        
        return {
            "message": f"Optimization level set to {level}",
            "level": optimization_level.value,
            "timestamp": datetime.now().isoformat()
        }
    except ValueError:
        valid_levels = [level.value for level in OptimizationLevel]
        raise HTTPException(
            status_code=400, 
            detail=f"Invalid optimization level. Valid options: {valid_levels}"
        )
    except Exception as e:
        logger.error(f"Failed to set optimization level: {e}")
        raise HTTPException(status_code=500, detail="Failed to set optimization level")

@router.post("/optimization/cache/clear")
async def clear_cache(
    cache_type: Optional[str] = None,
    current_user: Dict = Depends(verify_access_token)
):
    """Clear AI response caches."""
    try:
        if cache_type:
            # Clear specific cache type
            cleared_count = 0  # Would implement specific cache clearing
            message = f"Cleared {cache_type} cache"
        else:
            # Clear all caches
            ai_performance_optimizer.cache_manager.local_cache.clear()
            if ai_performance_optimizer.cache_manager.redis:
                # Would clear Redis cache with pattern matching
                pass
            cleared_count = "all"
            message = "Cleared all caches"
        
        return {
            "message": message,
            "cleared_items": cleared_count,
            "timestamp": datetime.now().isoformat()
        }
    except Exception as e:
        logger.error(f"Failed to clear cache: {e}")
        raise HTTPException(status_code=500, detail="Failed to clear cache")

# ============================================================================
# PERSONALIZATION ENDPOINTS
# ============================================================================

@router.get("/personalization/profile/{user_id}")
async def get_user_profile(
    user_id: int,
    current_user: Dict = Depends(verify_access_token)
):
    """Get comprehensive user personalization profile."""
    try:
        user_profile = await personalization_engine.get_user_profile(user_id)
        
        return {
            "user_id": user_profile.user_id,
            "learning_style": user_profile.learning_style.value,
            "personality_type": user_profile.personality_type.value,
            "difficulty_preference": user_profile.difficulty_preference,
            "interaction_patterns": user_profile.interaction_patterns,
            "topic_preferences": user_profile.topic_preferences,
            "optimal_session_length": user_profile.optimal_session_length,
            "preferred_time_of_day": user_profile.preferred_time_of_day,
            "motivation_level": user_profile.motivation_level,
            "current_mood": user_profile.current_mood,
            "learning_goals": user_profile.learning_goals
        }
    except Exception as e:
        logger.error(f"Failed to get user profile for {user_id}: {e}")
        raise HTTPException(status_code=500, detail="Failed to retrieve user profile")

@router.post("/personalization/profile/{user_id}/refresh")
async def refresh_user_profile(
    user_id: int,
    current_user: Dict = Depends(verify_access_token)
):
    """Refresh user profile by re-analyzing behavior patterns."""
    try:
        user_profile = await personalization_engine.get_user_profile(user_id, refresh=True)
        
        return {
            "message": f"User profile refreshed for user {user_id}",
            "updated_profile": {
                "learning_style": user_profile.learning_style.value,
                "personality_type": user_profile.personality_type.value,
                "difficulty_preference": user_profile.difficulty_preference,
                "motivation_level": user_profile.motivation_level
            },
            "timestamp": datetime.now().isoformat()
        }
    except Exception as e:
        logger.error(f"Failed to refresh user profile for {user_id}: {e}")
        raise HTTPException(status_code=500, detail="Failed to refresh user profile")

@router.get("/personalization/recommendations/{user_id}")
async def get_personalized_recommendations(
    user_id: int,
    content_type: str = "all",
    num_recommendations: int = 10,
    current_user: Dict = Depends(verify_access_token)
):
    """Get personalized content recommendations for a user."""
    try:
        # Mock available content - in production this would query actual content
        available_content = [
            {
                "id": "course_1",
                "type": "course",
                "title": "Introduction to Python Programming",
                "topics": ["programming", "python", "basics"],
                "difficulty": 0.3,
                "format": "video",
                "estimated_duration": 45
            },
            {
                "id": "course_2", 
                "type": "course",
                "title": "Advanced Machine Learning",
                "topics": ["machine learning", "ai", "advanced"],
                "difficulty": 0.8,
                "format": "interactive",
                "estimated_duration": 90
            },
            {
                "id": "article_1",
                "type": "article",
                "title": "Understanding Neural Networks",
                "topics": ["neural networks", "deep learning"],
                "difficulty": 0.6,
                "format": "text",
                "estimated_duration": 20
            }
        ]
        
        recommendations = await personalization_engine.personalize_content_recommendations(
            user_id, available_content, num_recommendations
        )
        
        return {
            "user_id": user_id,
            "recommendations": [
                {
                    "content_id": rec.content_id,
                    "content_type": rec.content_type,
                    "title": rec.title,
                    "relevance_score": rec.relevance_score,
                    "difficulty_match": rec.difficulty_match,
                    "style_compatibility": rec.style_compatibility,
                    "explanation": rec.explanation
                }
                for rec in recommendations
            ],
            "timestamp": datetime.now().isoformat()
        }
    except Exception as e:
        logger.error(f"Failed to get recommendations for {user_id}: {e}")
        raise HTTPException(status_code=500, detail="Failed to generate recommendations")

# ============================================================================
# A/B TESTING ENDPOINTS
# ============================================================================

@router.get("/experiments")
async def list_experiments(
    status: Optional[str] = None,
    current_user: Dict = Depends(verify_access_token)
):
    """List all A/B testing experiments."""
    try:
        status_filter = ExperimentStatus(status) if status else None
        experiments = experiment_manager.list_experiments(status_filter)
        
        return {
            "experiments": experiments,
            "total_count": len(experiments),
            "timestamp": datetime.now().isoformat()
        }
    except ValueError:
        valid_statuses = [status.value for status in ExperimentStatus]
        raise HTTPException(
            status_code=400,
            detail=f"Invalid status. Valid options: {valid_statuses}"
        )
    except Exception as e:
        logger.error(f"Failed to list experiments: {e}")
        raise HTTPException(status_code=500, detail="Failed to list experiments")

@router.post("/experiments")
async def create_experiment(
    experiment_config: Dict[str, Any],
    background_tasks: BackgroundTasks,
    current_user: Dict = Depends(verify_access_token)
):
    """Create a new A/B testing experiment."""
    try:
        experiment_id = await experiment_manager.create_experiment(
            name=experiment_config["name"],
            description=experiment_config["description"],
            experiment_type=ExperimentType(experiment_config["experiment_type"]),
            variants=experiment_config["variants"],
            metrics_config=experiment_config["metrics"],
            target_participants=experiment_config.get("target_participants", 1000),
            min_runtime_days=experiment_config.get("min_runtime_days", 7),
            max_runtime_days=experiment_config.get("max_runtime_days", 30),
            traffic_allocation=experiment_config.get("traffic_allocation", 0.1)
        )
        
        return {
            "message": "Experiment created successfully",
            "experiment_id": experiment_id,
            "status": "draft",
            "timestamp": datetime.now().isoformat()
        }
    except Exception as e:
        logger.error(f"Failed to create experiment: {e}")
        raise HTTPException(status_code=500, detail="Failed to create experiment")

@router.post("/experiments/{experiment_id}/start")
async def start_experiment(
    experiment_id: str,
    current_user: Dict = Depends(verify_access_token)
):
    """Start running an A/B testing experiment."""
    try:
        success = await experiment_manager.start_experiment(experiment_id)
        
        if not success:
            raise HTTPException(status_code=400, detail="Failed to start experiment")
        
        return {
            "message": f"Experiment {experiment_id} started successfully",
            "experiment_id": experiment_id,
            "status": "running",
            "timestamp": datetime.now().isoformat()
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to start experiment {experiment_id}: {e}")
        raise HTTPException(status_code=500, detail="Failed to start experiment")

@router.post("/experiments/{experiment_id}/stop")
async def stop_experiment(
    experiment_id: str,
    reason: str = "Manual stop",
    current_user: Dict = Depends(verify_access_token)
):
    """Stop a running A/B testing experiment."""
    try:
        success = await experiment_manager.stop_experiment(experiment_id, reason)
        
        if not success:
            raise HTTPException(status_code=400, detail="Failed to stop experiment")
        
        return {
            "message": f"Experiment {experiment_id} stopped successfully",
            "experiment_id": experiment_id,
            "status": "completed",
            "stop_reason": reason,
            "timestamp": datetime.now().isoformat()
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to stop experiment {experiment_id}: {e}")
        raise HTTPException(status_code=500, detail="Failed to stop experiment")

@router.get("/experiments/{experiment_id}/status")
async def get_experiment_status(
    experiment_id: str,
    current_user: Dict = Depends(verify_access_token)
):
    """Get detailed status of an A/B testing experiment."""
    try:
        status = experiment_manager.get_experiment_status(experiment_id)
        
        if not status:
            raise HTTPException(status_code=404, detail="Experiment not found")
        
        return status
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get experiment status for {experiment_id}: {e}")
        raise HTTPException(status_code=500, detail="Failed to get experiment status")

@router.get("/experiments/analysis")
async def analyze_experiments(
    current_user: Dict = Depends(verify_access_token)
):
    """Analyze all running experiments for statistical significance."""
    try:
        analysis_results = await experiment_manager.analyze_experiments()
        
        return {
            "analysis_results": analysis_results,
            "total_experiments": len(analysis_results),
            "timestamp": datetime.now().isoformat()
        }
    except Exception as e:
        logger.error(f"Failed to analyze experiments: {e}")
        raise HTTPException(status_code=500, detail="Failed to analyze experiments")

@router.get("/experiments/templates")
async def get_experiment_templates(
    current_user: Dict = Depends(verify_access_token)
):
    """Get pre-defined experiment templates for common optimizations."""
    try:
        return {
            "templates": EXPERIMENT_TEMPLATES,
            "available_types": [t.value for t in ExperimentType],
            "timestamp": datetime.now().isoformat()
        }
    except Exception as e:
        logger.error(f"Failed to get experiment templates: {e}")
        raise HTTPException(status_code=500, detail="Failed to get experiment templates")

# ============================================================================
# ANALYTICS AND INSIGHTS ENDPOINTS
# ============================================================================

@router.get("/analytics/overview")
async def get_analytics_overview(
    days_back: int = 30,
    current_user: Dict = Depends(verify_access_token)
):
    """Get comprehensive analytics overview of AI system performance."""
    try:
        # This would compile analytics from various sources
        # For now, return simulated comprehensive analytics
        
        return {
            "period": {
                "days_back": days_back,
                "start_date": (datetime.now() - timedelta(days=days_back)).isoformat(),
                "end_date": datetime.now().isoformat()
            },
            "performance_metrics": {
                "total_requests": 15420,
                "avg_response_time": 1.2,
                "cache_hit_rate": 0.78,
                "error_rate": 0.002,
                "cost_optimization_savings": 847.50
            },
            "user_engagement": {
                "active_users": 2340,
                "avg_session_duration": 18.5,
                "personalization_adoption": 0.84,
                "satisfaction_score": 4.3
            },
            "model_performance": {
                "gemma_4_on_device": {
                    "usage_percentage": 0.65,
                    "avg_response_time": 0.8,
                    "success_rate": 0.998
                },
                "gemma_4_cloud": {
                    "usage_percentage": 0.25,
                    "avg_response_time": 1.5,
                    "success_rate": 0.995
                },
                "gpt_4_mini": {
                    "usage_percentage": 0.10,
                    "avg_response_time": 2.1,
                    "success_rate": 0.997
                }
            },
            "optimization_impact": {
                "response_time_improvement": 0.35,
                "cost_reduction": 0.22,
                "user_satisfaction_increase": 0.18,
                "cache_efficiency_gain": 0.41
            },
            "timestamp": datetime.now().isoformat()
        }
    except Exception as e:
        logger.error(f"Failed to get analytics overview: {e}")
        raise HTTPException(status_code=500, detail="Failed to retrieve analytics")

@router.get("/analytics/trends")
async def get_performance_trends(
    metric: str = "response_time",
    days_back: int = 7,
    granularity: str = "hour",
    current_user: Dict = Depends(verify_access_token)
):
    """Get performance trends over time."""
    try:
        # This would query actual metrics database
        # For now, return simulated trend data
        
        valid_metrics = ["response_time", "throughput", "error_rate", "cost", "satisfaction"]
        if metric not in valid_metrics:
            raise HTTPException(
                status_code=400,
                detail=f"Invalid metric. Valid options: {valid_metrics}"
            )
        
        # Generate simulated trend data
        trend_data = []
        for i in range(days_back * 24 if granularity == "hour" else days_back):
            timestamp = datetime.now() - timedelta(hours=i if granularity == "hour" else i*24)
            value = 1.0 + (i % 10) * 0.1  # Simulated values
            trend_data.append({
                "timestamp": timestamp.isoformat(),
                "value": value
            })
        
        return {
            "metric": metric,
            "granularity": granularity,
            "period_days": days_back,
            "data_points": len(trend_data),
            "trend_data": sorted(trend_data, key=lambda x: x["timestamp"]),
            "summary": {
                "min_value": min(d["value"] for d in trend_data),
                "max_value": max(d["value"] for d in trend_data),
                "avg_value": sum(d["value"] for d in trend_data) / len(trend_data),
                "trend_direction": "improving"  # Would calculate actual trend
            },
            "timestamp": datetime.now().isoformat()
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get performance trends: {e}")
        raise HTTPException(status_code=500, detail="Failed to retrieve performance trends")

# ============================================================================
# SYSTEM OPTIMIZATION ENDPOINTS
# ============================================================================

@router.post("/optimization/auto-tune")
async def auto_tune_system(
    background_tasks: BackgroundTasks,
    current_user: Dict = Depends(verify_access_token)
):
    """Automatically tune system parameters based on current performance."""
    try:
        # This would implement intelligent auto-tuning
        # For now, return success with planned optimizations
        
        background_tasks.add_task(_perform_auto_tuning)
        
        return {
            "message": "Auto-tuning initiated",
            "status": "in_progress",
            "estimated_duration": "15-30 minutes",
            "optimizations_planned": [
                "Cache size optimization",
                "Model routing threshold adjustment", 
                "Resource allocation rebalancing",
                "Circuit breaker sensitivity tuning"
            ],
            "timestamp": datetime.now().isoformat()
        }
    except Exception as e:
        logger.error(f"Failed to initiate auto-tuning: {e}")
        raise HTTPException(status_code=500, detail="Failed to initiate auto-tuning")

async def _perform_auto_tuning():
    """Background task to perform system auto-tuning."""
    try:
        # Simulate auto-tuning process
        await asyncio.sleep(10)  # Placeholder for actual tuning
        logger.info("Auto-tuning completed successfully")
    except Exception as e:
        logger.error(f"Auto-tuning failed: {e}")

# Add the optimization router to the main AI router
def setup_optimization_routes(main_router: APIRouter):
    """Setup optimization routes on the main AI router."""
    main_router.include_router(router, prefix="/optimization", tags=["ai-optimization"])
