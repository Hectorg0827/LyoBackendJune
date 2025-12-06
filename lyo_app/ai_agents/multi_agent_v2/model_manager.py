"""
Model Manager for Multi-Agent Course Generation.
Intelligently selects between Gemini models based on task complexity.

MIT Architecture Engineering - Cost-Performance Optimization Layer

Model Strategy:
- Gemini 2.5 Pro: Complex tasks (curriculum design, QA review)
- Gemini 1.5 Flash: Simple/repetitive tasks (content generation, assessments)

This provides optimal balance between quality and cost.
"""

import logging
from dataclasses import dataclass
from enum import Enum
from typing import Optional

logger = logging.getLogger(__name__)


class ModelTier(str, Enum):
    """Model tiers for different task complexities"""
    PREMIUM = "premium"      # Gemini 2.5 Pro - complex reasoning
    STANDARD = "standard"    # Gemini 1.5 Flash - balanced
    ECONOMY = "economy"      # Gemini 1.5 Flash (lower temp) - simple tasks


class TaskComplexity(str, Enum):
    """Task complexity levels"""
    HIGH = "high"        # Requires deep reasoning, creativity
    MEDIUM = "medium"    # Standard generation tasks
    LOW = "low"          # Repetitive, template-based tasks


@dataclass
class ModelConfig:
    """Configuration for a specific model"""
    model_name: str
    temperature: float
    max_tokens: int
    description: str
    cost_per_1k_tokens: float  # Approximate cost for tracking


class ModelManager:
    """
    Manages model selection for optimal cost-performance balance.
    
    Strategy:
    - Orchestrator (intent analysis): Premium (Gemini 2.5 Pro)
      Reason: Needs deep understanding of user intent
      
    - Curriculum Architect: Premium (Gemini 2.5 Pro)
      Reason: Requires structured thinking, dependency planning
      
    - Content Creator: Standard (Gemini 1.5 Flash)
      Reason: High volume, benefits from speed, good quality sufficient
      
    - Assessment Designer: Standard (Gemini 1.5 Flash)
      Reason: Template-based, high volume
      
    - QA Agent: Premium (Gemini 2.5 Pro)
      Reason: Critical review requires deep analysis
    """
    
    # Model configurations
    MODELS = {
        ModelTier.PREMIUM: ModelConfig(
            model_name="gemini-2.5-pro-preview-06-05",
            temperature=0.7,
            max_tokens=16384,
            description="Gemini 2.5 Pro - Best for complex reasoning",
            cost_per_1k_tokens=0.00125  # Approximate
        ),
        ModelTier.STANDARD: ModelConfig(
            model_name="gemini-1.5-flash",
            temperature=0.7,
            max_tokens=8192,
            description="Gemini 1.5 Flash - Fast and cost-effective",
            cost_per_1k_tokens=0.000075  # Approximate
        ),
        ModelTier.ECONOMY: ModelConfig(
            model_name="gemini-1.5-flash",
            temperature=0.5,  # Lower temperature for consistency
            max_tokens=4096,
            description="Gemini 1.5 Flash (Economy) - Simple tasks",
            cost_per_1k_tokens=0.000075
        )
    }
    
    # Task to model tier mapping
    TASK_MODEL_MAP = {
        # Agent tasks
        "orchestrator": ModelTier.PREMIUM,
        "curriculum_architect": ModelTier.PREMIUM,
        "content_creator": ModelTier.STANDARD,
        "assessment_designer": ModelTier.STANDARD,
        "qa_agent": ModelTier.PREMIUM,
        
        # Sub-tasks
        "intent_analysis": ModelTier.PREMIUM,
        "module_planning": ModelTier.PREMIUM,
        "lesson_outline": ModelTier.STANDARD,
        "lesson_content": ModelTier.STANDARD,
        "code_examples": ModelTier.STANDARD,
        "quiz_generation": ModelTier.ECONOMY,
        "quality_review": ModelTier.PREMIUM,
        "summary_generation": ModelTier.ECONOMY
    }
    
    @classmethod
    def get_model_for_task(cls, task_name: str) -> ModelConfig:
        """
        Get the appropriate model configuration for a task.
        
        Args:
            task_name: Name of the task/agent
            
        Returns:
            ModelConfig with appropriate settings
        """
        tier = cls.TASK_MODEL_MAP.get(task_name.lower(), ModelTier.STANDARD)
        config = cls.MODELS[tier]
        
        logger.debug(f"Selected {tier.value} model for task '{task_name}': {config.model_name}")
        
        return config
    
    @classmethod
    def get_model_for_complexity(cls, complexity: TaskComplexity) -> ModelConfig:
        """
        Get model based on task complexity level.
        
        Args:
            complexity: TaskComplexity enum
            
        Returns:
            ModelConfig with appropriate settings
        """
        tier_map = {
            TaskComplexity.HIGH: ModelTier.PREMIUM,
            TaskComplexity.MEDIUM: ModelTier.STANDARD,
            TaskComplexity.LOW: ModelTier.ECONOMY
        }
        
        tier = tier_map.get(complexity, ModelTier.STANDARD)
        return cls.MODELS[tier]
    
    @classmethod
    def estimate_cost(cls, task_name: str, estimated_tokens: int) -> float:
        """
        Estimate cost for a task based on expected token usage.
        
        Args:
            task_name: Name of the task
            estimated_tokens: Estimated total tokens (input + output)
            
        Returns:
            Estimated cost in USD
        """
        config = cls.get_model_for_task(task_name)
        cost = (estimated_tokens / 1000) * config.cost_per_1k_tokens
        return cost
    
    @classmethod
    def get_pipeline_cost_estimate(cls, course_request: str) -> dict:
        """
        Estimate total cost for generating a course.
        
        Args:
            course_request: User's course request
            
        Returns:
            Dictionary with cost breakdown
        """
        # Rough token estimates based on typical usage
        estimates = {
            "orchestrator": 3000,
            "curriculum_architect": 8000,
            "content_creator": 50000,  # Multiple lessons
            "assessment_designer": 15000,
            "qa_agent": 10000
        }
        
        breakdown = {}
        total = 0.0
        
        for task, tokens in estimates.items():
            cost = cls.estimate_cost(task, tokens)
            breakdown[task] = {
                "tokens": tokens,
                "model": cls.get_model_for_task(task).model_name,
                "cost_usd": round(cost, 6)
            }
            total += cost
        
        return {
            "breakdown": breakdown,
            "total_estimated_cost_usd": round(total, 4),
            "note": "Estimates based on average course generation"
        }
    
    @classmethod
    def override_model(cls, task_name: str, tier: ModelTier) -> None:
        """
        Override the model tier for a specific task.
        Useful for testing or forcing premium quality.
        
        Args:
            task_name: Name of the task to override
            tier: New model tier to use
        """
        cls.TASK_MODEL_MAP[task_name.lower()] = tier
        logger.info(f"Overriding model for '{task_name}' to {tier.value}")
    
    @classmethod
    def use_premium_for_all(cls) -> None:
        """Force premium model for all tasks (quality over cost)"""
        for task in cls.TASK_MODEL_MAP:
            cls.TASK_MODEL_MAP[task] = ModelTier.PREMIUM
        logger.info("All tasks set to PREMIUM tier")
    
    @classmethod
    def use_economy_for_all(cls) -> None:
        """Force economy model for all tasks (cost over quality)"""
        for task in cls.TASK_MODEL_MAP:
            cls.TASK_MODEL_MAP[task] = ModelTier.ECONOMY
        logger.info("All tasks set to ECONOMY tier")
    
    @classmethod
    def reset_to_defaults(cls) -> None:
        """Reset task-model mapping to defaults"""
        cls.TASK_MODEL_MAP = {
            "orchestrator": ModelTier.PREMIUM,
            "curriculum_architect": ModelTier.PREMIUM,
            "content_creator": ModelTier.STANDARD,
            "assessment_designer": ModelTier.STANDARD,
            "qa_agent": ModelTier.PREMIUM,
            "intent_analysis": ModelTier.PREMIUM,
            "module_planning": ModelTier.PREMIUM,
            "lesson_outline": ModelTier.STANDARD,
            "lesson_content": ModelTier.STANDARD,
            "code_examples": ModelTier.STANDARD,
            "quiz_generation": ModelTier.ECONOMY,
            "quality_review": ModelTier.PREMIUM,
            "summary_generation": ModelTier.ECONOMY
        }
        logger.info("Model mapping reset to defaults")


# Convenience functions
def get_model_name(task_name: str) -> str:
    """Get model name for a task"""
    return ModelManager.get_model_for_task(task_name).model_name


def get_model_temperature(task_name: str) -> float:
    """Get temperature for a task"""
    return ModelManager.get_model_for_task(task_name).temperature


def get_model_max_tokens(task_name: str) -> int:
    """Get max tokens for a task"""
    return ModelManager.get_model_for_task(task_name).max_tokens
