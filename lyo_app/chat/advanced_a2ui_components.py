"""
Advanced A2UI Components
Implements sophisticated UI components including video players, coding sandbox,
and collaborative features for enhanced learning experiences
"""

from pydantic import BaseModel, Field
from typing import List, Optional, Union, Dict, Any
from enum import Enum
import uuid
from datetime import datetime

# Base imports from existing A2UI system
from .a2ui_recursive import UIComponentBase

class VideoPlayerType(str, Enum):
    """Video player types"""
    STREAMING = "streaming"
    PROGRESSIVE = "progressive"
    ADAPTIVE = "adaptive"
    LIVE = "live"

class CodeLanguage(str, Enum):
    """Supported programming languages"""
    PYTHON = "python"
    JAVASCRIPT = "javascript"
    TYPESCRIPT = "typescript"
    JAVA = "java"
    CPP = "cpp"
    CSHARP = "csharp"
    GO = "go"
    RUST = "rust"
    HTML = "html"
    CSS = "css"
    SQL = "sql"
    SHELL = "shell"
    MARKDOWN = "markdown"

class CollaborationType(str, Enum):
    """Collaboration types"""
    REAL_TIME_EDITING = "real_time_editing"
    WHITEBOARD = "whiteboard"
    VOICE_CHAT = "voice_chat"
    VIDEO_CHAT = "video_chat"
    SCREEN_SHARE = "screen_share"
    ANNOTATION = "annotation"

# ==============================================================================
# VIDEO COMPONENTS
# ==============================================================================

class VideoPlayerComponent(UIComponentBase):
    """Advanced video player with learning features"""
    type: str = "video_player"
    video_url: str
    video_type: VideoPlayerType = VideoPlayerType.STREAMING
    title: Optional[str] = None
    description: Optional[str] = None
    thumbnail_url: Optional[str] = None
    duration_seconds: Optional[int] = None

    # Learning features
    chapters: List[Dict[str, Any]] = Field(default_factory=list)
    interactive_elements: List[Dict[str, Any]] = Field(default_factory=list)
    captions_url: Optional[str] = None
    transcript_url: Optional[str] = None

    # Player controls
    auto_play: bool = False
    show_controls: bool = True
    allow_fullscreen: bool = True
    playback_rates: List[float] = Field(default_factory=lambda: [0.5, 1.0, 1.25, 1.5, 2.0])

    # Analytics
    track_progress: bool = True
    require_completion: bool = False
    quiz_on_completion: Optional[str] = None

    # Accessibility
    keyboard_navigation: bool = True
    screen_reader_compatible: bool = True

class InteractiveVideoComponent(UIComponentBase):
    """Interactive video with embedded questions and activities"""
    type: str = "interactive_video"
    video_url: str
    title: str

    # Interactive elements with timestamps
    interactions: List[Dict[str, Any]] = Field(default_factory=list)
    # Format: {"timestamp": 120, "type": "question", "content": {...}, "required": True}

    # Branching scenarios
    decision_points: List[Dict[str, Any]] = Field(default_factory=list)
    # Format: {"timestamp": 180, "question": "...", "options": [...], "next_video": {...}}

    # Completion requirements
    interaction_completion_rate: float = 0.8  # 80% of interactions must be completed
    allow_skip_interactions: bool = False

class VideoPlaylistComponent(UIComponentBase):
    """Video playlist for course sequences"""
    type: str = "video_playlist"
    title: str
    description: Optional[str] = None

    videos: List[Dict[str, Any]] = Field(default_factory=list)
    # Format: {"id": "...", "title": "...", "url": "...", "duration": 300, "completed": False}

    # Playlist behavior
    auto_advance: bool = True
    shuffle_mode: bool = False
    loop_playlist: bool = False

    # Progress tracking
    overall_progress: float = 0.0
    current_video_index: int = 0

    # Learning path
    prerequisite_completion: bool = True  # Must complete videos in order
    certificate_on_completion: bool = False

# ==============================================================================
# CODING COMPONENTS
# ==============================================================================

class CodeSandboxComponent(UIComponentBase):
    """Interactive coding environment"""
    type: str = "code_sandbox"
    language: CodeLanguage
    title: str
    description: Optional[str] = None

    # Code content
    initial_code: str = ""
    solution_code: Optional[str] = None
    test_cases: List[Dict[str, Any]] = Field(default_factory=list)

    # Sandbox features
    allow_file_upload: bool = False
    allow_package_install: bool = False
    execution_timeout: int = 30  # seconds
    memory_limit_mb: int = 128

    # Learning features
    hints: List[str] = Field(default_factory=list)
    step_by_step_guidance: bool = False
    auto_complete: bool = True
    syntax_highlighting: bool = True

    # Collaboration
    allow_collaboration: bool = False
    max_collaborators: int = 4

    # Assessment
    auto_grade: bool = False
    rubric: Optional[Dict[str, Any]] = None

class CodeEditorComponent(UIComponentBase):
    """Standalone code editor with syntax highlighting"""
    type: str = "code_editor"
    language: CodeLanguage
    content: str = ""

    # Editor features
    theme: str = "dark"  # dark, light, auto
    font_size: int = 14
    tab_size: int = 4
    word_wrap: bool = True
    line_numbers: bool = True

    # Code assistance
    auto_complete: bool = True
    syntax_highlighting: bool = True
    error_highlighting: bool = True
    bracket_matching: bool = True

    # Accessibility
    high_contrast: bool = False
    keyboard_shortcuts: bool = True
    screen_reader_support: bool = True

    # Actions
    run_code_action: Optional[str] = None
    save_action: Optional[str] = None
    share_action: Optional[str] = None

class CodeOutputComponent(UIComponentBase):
    """Display code execution output"""
    type: str = "code_output"
    output_text: str
    error_text: Optional[str] = None
    execution_time: Optional[float] = None
    memory_used: Optional[int] = None

    # Output formatting
    syntax_highlight_output: bool = True
    show_line_numbers: bool = False
    max_output_lines: int = 1000

    # Interactive features
    allow_copy: bool = True
    allow_download: bool = True
    search_in_output: bool = True

class CodeDiffComponent(UIComponentBase):
    """Show differences between code versions"""
    type: str = "code_diff"
    original_code: str
    modified_code: str
    language: CodeLanguage

    # Diff display options
    side_by_side: bool = True
    highlight_changes: bool = True
    show_line_numbers: bool = True

    # Change summary
    additions: int = 0
    deletions: int = 0
    modifications: int = 0

# ==============================================================================
# COLLABORATION COMPONENTS
# ==============================================================================

class CollaborationSpaceComponent(UIComponentBase):
    """Real-time collaboration space"""
    type: str = "collaboration_space"
    session_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    title: str

    # Participants
    max_participants: int = 10
    current_participants: List[Dict[str, Any]] = Field(default_factory=list)
    # Format: {"user_id": "...", "name": "...", "cursor_color": "#...", "active": True}

    # Collaboration features
    collaboration_types: List[CollaborationType] = Field(default_factory=list)

    # Real-time features
    real_time_cursor: bool = True
    real_time_selection: bool = True
    activity_awareness: bool = True

    # Communication
    chat_enabled: bool = True
    voice_enabled: bool = False
    video_enabled: bool = False

    # Permissions
    moderator_controls: bool = True
    participant_permissions: Dict[str, bool] = Field(default_factory=lambda: {
        "edit": True,
        "comment": True,
        "voice_chat": False,
        "screen_share": False
    })

class WhiteboardComponent(UIComponentBase):
    """Interactive whiteboard for visual collaboration"""
    type: str = "whiteboard"
    width: int = 1200
    height: int = 800

    # Drawing tools
    available_tools: List[str] = Field(default_factory=lambda: [
        "pen", "pencil", "highlighter", "eraser", "text", "shapes", "sticky_notes"
    ])

    # Collaboration
    multi_user: bool = True
    real_time_sync: bool = True
    cursor_tracking: bool = True

    # Content
    background_color: str = "#ffffff"
    background_grid: bool = True
    infinite_canvas: bool = True

    # Export options
    export_formats: List[str] = Field(default_factory=lambda: ["png", "pdf", "svg"])

    # Templates
    templates: List[Dict[str, Any]] = Field(default_factory=list)
    # Format: {"id": "...", "name": "...", "preview_url": "...", "content": {...}}

class AnnotationComponent(UIComponentBase):
    """Add annotations to content"""
    type: str = "annotation"
    target_element_id: str  # ID of element to annotate

    # Annotation content
    annotation_text: str
    annotation_type: str = "note"  # note, question, highlight, bookmark

    # Position and styling
    position_x: float = 0.0  # Relative position (0.0-1.0)
    position_y: float = 0.0
    color: str = "#ffeb3b"

    # Metadata
    author_id: str
    created_at: datetime = Field(default_factory=datetime.now)
    replies: List[Dict[str, Any]] = Field(default_factory=list)

    # Visibility
    public: bool = True
    highlighted: bool = False

class PeerReviewComponent(UIComponentBase):
    """Peer review and feedback system"""
    type: str = "peer_review"
    submission_id: str

    # Review configuration
    review_criteria: List[Dict[str, Any]] = Field(default_factory=list)
    # Format: {"criterion": "...", "description": "...", "weight": 0.3, "max_score": 5}

    # Assignment details
    assignment_title: str
    assignment_description: str
    submission_content: Dict[str, Any]  # Code, text, files, etc.

    # Review process
    anonymous_review: bool = True
    peer_count: int = 3  # Number of peer reviewers
    instructor_review: bool = True

    # Review interface
    rubric_based: bool = True
    allow_comments: bool = True
    require_justification: bool = True

    # Status
    review_status: str = "pending"  # pending, in_progress, completed
    reviews_received: int = 0

# ==============================================================================
# ADVANCED INTERACTIVE COMPONENTS
# ==============================================================================

class SimulationComponent(UIComponentBase):
    """Interactive simulations for learning"""
    type: str = "simulation"
    simulation_type: str  # physics, chemistry, economics, etc.
    title: str

    # Simulation parameters
    initial_state: Dict[str, Any]
    configurable_params: List[Dict[str, Any]] = Field(default_factory=list)
    # Format: {"param": "gravity", "min": 0, "max": 20, "default": 9.8, "step": 0.1}

    # Controls
    play_pause_controls: bool = True
    reset_button: bool = True
    step_through_mode: bool = True
    speed_control: bool = True

    # Learning features
    guided_exploration: bool = False
    learning_objectives: List[str] = Field(default_factory=list)
    hypothesis_testing: bool = False

    # Data collection
    export_data: bool = True
    data_visualization: bool = True

class VirtualLabComponent(UIComponentBase):
    """Virtual laboratory environment"""
    type: str = "virtual_lab"
    lab_type: str  # chemistry, physics, biology, etc.
    title: str

    # Lab equipment
    available_equipment: List[Dict[str, Any]] = Field(default_factory=list)
    # Format: {"id": "...", "name": "...", "type": "...", "properties": {...}}

    # Experiment setup
    experiment_instructions: str
    safety_guidelines: List[str] = Field(default_factory=list)

    # Virtual environment
    three_dimensional: bool = True
    physics_simulation: bool = True
    realistic_interactions: bool = True

    # Learning integration
    hypothesis_formation: bool = True
    data_recording: bool = True
    result_analysis: bool = True

    # Assessment
    lab_report_template: Optional[Dict[str, Any]] = None
    auto_assessment: bool = False

class GameBasedLearningComponent(UIComponentBase):
    """Gamified learning experiences"""
    type: str = "game_based_learning"
    game_type: str  # quiz_game, strategy, simulation, puzzle
    title: str

    # Game mechanics
    points_system: bool = True
    levels: int = 1
    achievements: List[Dict[str, Any]] = Field(default_factory=list)
    # Format: {"id": "...", "name": "...", "description": "...", "icon": "...", "criteria": {...}}

    # Learning objectives
    learning_goals: List[str] = Field(default_factory=list)
    skill_progression: Dict[str, Any] = Field(default_factory=dict)

    # Social features
    leaderboards: bool = False
    team_play: bool = False
    peer_challenges: bool = False

    # Adaptive difficulty
    dynamic_difficulty: bool = True
    performance_based_progression: bool = True

    # Analytics
    detailed_analytics: bool = True
    learning_path_optimization: bool = True

# ==============================================================================
# ASSESSMENT COMPONENTS
# ==============================================================================

class AutoGradedAssignmentComponent(UIComponentBase):
    """Automatically graded assignments"""
    type: str = "auto_graded_assignment"
    assignment_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    title: str

    # Assignment details
    instructions: str
    time_limit_minutes: Optional[int] = None
    attempts_allowed: int = 1

    # Questions
    questions: List[Dict[str, Any]] = Field(default_factory=list)
    # Supports multiple question types: multiple_choice, coding, short_answer, essay

    # Grading
    auto_grade_types: List[str] = Field(default_factory=lambda: ["multiple_choice", "coding"])
    manual_grade_types: List[str] = Field(default_factory=lambda: ["essay", "long_answer"])

    # Feedback
    immediate_feedback: bool = True
    show_correct_answers: bool = False
    detailed_explanations: bool = True

    # Anti-cheating
    randomize_questions: bool = True
    proctoring_enabled: bool = False
    plagiarism_detection: bool = False

class PortfolioComponent(UIComponentBase):
    """Student portfolio for work showcase"""
    type: str = "portfolio"
    user_id: str
    title: str

    # Portfolio sections
    sections: List[Dict[str, Any]] = Field(default_factory=list)
    # Format: {"id": "...", "title": "...", "description": "...", "items": [...]}

    # Visibility and sharing
    public: bool = False
    shareable_link: Optional[str] = None
    password_protected: bool = False

    # Customization
    theme: str = "default"
    custom_css: Optional[str] = None
    layout_template: str = "grid"  # grid, list, masonry

    # Assessment integration
    reflection_prompts: List[str] = Field(default_factory=list)
    peer_feedback_enabled: bool = True
    instructor_comments: bool = True

    # Export options
    export_formats: List[str] = Field(default_factory=lambda: ["pdf", "html", "zip"])

# ==============================================================================
# FACTORY FOR ADVANCED COMPONENTS
# ==============================================================================

class AdvancedA2UIFactory:
    """Factory for creating advanced A2UI components"""

    @staticmethod
    def video_player(video_url: str, title: str = None, **kwargs) -> VideoPlayerComponent:
        """Create advanced video player"""
        return VideoPlayerComponent(
            video_url=video_url,
            title=title,
            **kwargs
        )

    @staticmethod
    def interactive_video(video_url: str, title: str, interactions: List[Dict[str, Any]] = None) -> InteractiveVideoComponent:
        """Create interactive video with embedded activities"""
        return InteractiveVideoComponent(
            video_url=video_url,
            title=title,
            interactions=interactions or []
        )

    @staticmethod
    def code_sandbox(language: CodeLanguage, title: str, initial_code: str = "", **kwargs) -> CodeSandboxComponent:
        """Create coding sandbox environment"""
        return CodeSandboxComponent(
            language=language,
            title=title,
            initial_code=initial_code,
            **kwargs
        )

    @staticmethod
    def code_editor(language: CodeLanguage, content: str = "", **kwargs) -> CodeEditorComponent:
        """Create code editor"""
        return CodeEditorComponent(
            language=language,
            content=content,
            **kwargs
        )

    @staticmethod
    def collaboration_space(title: str, collaboration_types: List[CollaborationType] = None, **kwargs) -> CollaborationSpaceComponent:
        """Create collaboration space"""
        return CollaborationSpaceComponent(
            title=title,
            collaboration_types=collaboration_types or [CollaborationType.REAL_TIME_EDITING],
            **kwargs
        )

    @staticmethod
    def whiteboard(width: int = 1200, height: int = 800, **kwargs) -> WhiteboardComponent:
        """Create interactive whiteboard"""
        return WhiteboardComponent(
            width=width,
            height=height,
            **kwargs
        )

    @staticmethod
    def simulation(simulation_type: str, title: str, initial_state: Dict[str, Any], **kwargs) -> SimulationComponent:
        """Create interactive simulation"""
        return SimulationComponent(
            simulation_type=simulation_type,
            title=title,
            initial_state=initial_state,
            **kwargs
        )

    @staticmethod
    def virtual_lab(lab_type: str, title: str, experiment_instructions: str, **kwargs) -> VirtualLabComponent:
        """Create virtual laboratory"""
        return VirtualLabComponent(
            lab_type=lab_type,
            title=title,
            experiment_instructions=experiment_instructions,
            **kwargs
        )

    @staticmethod
    def game_based_learning(game_type: str, title: str, learning_goals: List[str] = None, **kwargs) -> GameBasedLearningComponent:
        """Create gamified learning experience"""
        return GameBasedLearningComponent(
            game_type=game_type,
            title=title,
            learning_goals=learning_goals or [],
            **kwargs
        )

    @staticmethod
    def peer_review(submission_id: str, assignment_title: str, assignment_description: str,
                   submission_content: Dict[str, Any], **kwargs) -> PeerReviewComponent:
        """Create peer review system"""
        return PeerReviewComponent(
            submission_id=submission_id,
            assignment_title=assignment_title,
            assignment_description=assignment_description,
            submission_content=submission_content,
            **kwargs
        )

    @staticmethod
    def auto_graded_assignment(title: str, instructions: str, questions: List[Dict[str, Any]], **kwargs) -> AutoGradedAssignmentComponent:
        """Create auto-graded assignment"""
        return AutoGradedAssignmentComponent(
            title=title,
            instructions=instructions,
            questions=questions,
            **kwargs
        )

    @staticmethod
    def portfolio(user_id: str, title: str, sections: List[Dict[str, Any]] = None, **kwargs) -> PortfolioComponent:
        """Create student portfolio"""
        return PortfolioComponent(
            user_id=user_id,
            title=title,
            sections=sections or [],
            **kwargs
        )

# Export the new components for integration with existing A2UI system
ADVANCED_COMPONENT_TYPES = [
    "video_player",
    "interactive_video",
    "video_playlist",
    "code_sandbox",
    "code_editor",
    "code_output",
    "code_diff",
    "collaboration_space",
    "whiteboard",
    "annotation",
    "peer_review",
    "simulation",
    "virtual_lab",
    "game_based_learning",
    "auto_graded_assignment",
    "portfolio"
]

# Update the UIComponent union type from the main A2UI system
AdvancedUIComponent = Union[
    VideoPlayerComponent,
    InteractiveVideoComponent,
    VideoPlaylistComponent,
    CodeSandboxComponent,
    CodeEditorComponent,
    CodeOutputComponent,
    CodeDiffComponent,
    CollaborationSpaceComponent,
    WhiteboardComponent,
    AnnotationComponent,
    PeerReviewComponent,
    SimulationComponent,
    VirtualLabComponent,
    GameBasedLearningComponent,
    AutoGradedAssignmentComponent,
    PortfolioComponent
]