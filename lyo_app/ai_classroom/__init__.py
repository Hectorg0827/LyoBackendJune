"""
LYO AI Classroom Module
The core intelligence for the award-winning AI learning experience

This module implements the "Interactive Cinema + Adaptive Tutor" architecture:
- Graph-based learning with conditional node routing
- Bayesian mastery tracking with confidence decay
- SM-2 spaced repetition for long-term retention
- Netflix-like playback with pre-fetched assets
- LLM-powered remediation for struggling learners
"""

# Intent Detection
from .intent_detector import (
    IntentDetector,
    ChatIntent,
    IntentType,
    get_intent_detector
)

# Conversation Flow
from .conversation_flow import (
    ConversationManager,
    ConversationState,
    get_conversation_manager
)

# Graph Learning Models
from .models import (
    GraphCourse,
    LearningNode,
    LearningEdge,
    Concept,
    Misconception,
    MasteryState,
    ReviewSchedule,
    InteractionAttempt,
    CourseProgress,
    CelebrationConfig,
    AdPlacementConfig,
    NodeType,
    EdgeCondition
)

# Schemas
from .schemas import (
    LearningNodeRead,
    LearningNodeCreate,
    LearningEdgeRead,
    PlaybackState,
    InteractionSubmitRequest,
    InteractionSubmitResponse,
    CourseGenerationRequest,
    ReviewQueueResponse,
    ReviewSubmitResponse,
    MasteryStateRead
)

# Core Services
from .graph_service import GraphService
from .interaction_service import InteractionService
from .remediation_service import RemediationService
from .spaced_repetition_service import SpacedRepetitionService
from .asset_service import AssetPipelineService, get_asset_service
from .ad_service import AdIntegrationService, CelebrationService, get_ad_service, get_celebration_service
from .graph_generator import GraphCourseGenerator, create_graph_generator

# Routes
from .playback_routes import router as playback_router

__all__ = [
    # Intent Detection
    "IntentDetector",
    "ChatIntent",
    "IntentType",
    "get_intent_detector",
    
    # Conversation Flow
    "ConversationManager", 
    "ConversationState",
    "get_conversation_manager",
    
    # Models
    "GraphCourse",
    "LearningNode",
    "LearningEdge",
    "Concept",
    "Misconception",
    "MasteryState",
    "ReviewSchedule",
    "InteractionAttempt",
    "CourseProgress",
    "CelebrationConfig",
    "AdPlacementConfig",
    "NodeType",
    "EdgeCondition",
    
    # Schemas
    "LearningNodeRead",
    "LearningNodeCreate",
    "LearningEdgeRead",
    "PlaybackState",
    "InteractionSubmitRequest",
    "InteractionSubmitResponse",
    "CourseGenerationRequest",
    "ReviewQueueResponse",
    "ReviewSubmitResponse",
    "MasteryStateRead",
    
    # Services
    "GraphService",
    "InteractionService",
    "RemediationService",
    "SpacedRepetitionService",
    "AssetPipelineService",
    "get_asset_service",
    "AdIntegrationService",
    "CelebrationService",
    "get_ad_service",
    "get_celebration_service",
    "GraphCourseGenerator",
    "create_graph_generator",
    
    # Routes
    "playback_router"
]
