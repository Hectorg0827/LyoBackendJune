from typing import Any, Dict, List, Optional, Union
from enum import Enum
from pydantic import BaseModel, Field
from datetime import datetime
import uuid

# ==============================================================================
# MARK: - Core Enums
# ==============================================================================

class A2UIElementType(str, Enum):
    # 1. Core Display & Typography
    TEXT = "text"
    HEADING = "heading"
    MARKDOWN = "markdown"
    CODE_BLOCK = "code_block"
    LATEX = "latex"
    HIGHLIGHT = "highlight"
    QUOTE = "quote"
    CALLOUT = "callout"
    BADGE = "badge"
    TAG = "tag"
    LABEL = "label"
    CAPTION = "caption"
    DIVIDER = "divider"
    SPACER = "spacer"
    SKELETON = "skeleton"

    # 2. Multimodal Input
    TEXT_INPUT = "text_input"
    VOICE_INPUT = "voice_input"
    MICROPHONE_INPUT = "microphone_input"
    AUDIO_RECORDER = "audio_recorder"
    CAMERA_CAPTURE = "camera_capture"
    DOCUMENT_UPLOAD = "document_upload"
    FILE_DROP_ZONE = "file_drop_zone"
    SCREEN_CAPTURE = "screen_capture"
    HANDWRITING_INPUT = "handwriting_input"
    DRAWING_CANVAS = "drawing_canvas"
    MATH_INPUT = "math_input"
    CODE_EDITOR = "code_editor"
    BARCODE_SCANNER = "barcode_scanner"
    OCR_CORRECTION = "ocr_correction"
    LOCATION_INPUT = "location_input"
    DATE_TIME_INPUT = "date_time_input"
    SIGNATURE_PAD = "signature_pad"
    EMOJI_PICKER = "emoji_picker"

    # 3. Rich Media & Visualization
    IMAGE = "image"
    VIDEO = "video"
    AUDIO = "audio"
    ANIMATION = "animation"
    LOTTIE = "lottie"
    GIF = "gif"
    DIAGRAM = "diagram"
    CHART = "chart"
    GRAPH = "graph"
    MODEL_3D = "model_3d"
    HANDWRITING_PREVIEW = "handwriting_preview"
    QR_CODE = "qr_code"
    PDF_VIEWER = "pdf_viewer"
    IMAGE_CAROUSEL = "image_carousel"
    VIDEO_TRANSCRIPT = "video_transcript"

    # 4. Quiz & Assessment
    QUIZ_MCQ = "quizMcq"
    QUIZ_MULTI_SELECT = "quizMultiSelect"
    QUIZ_TRUE_FALSE = "quizTrueFalse"
    QUIZ_FILL_BLANK = "quizFillBlank"
    QUIZ_MATCHING = "quizMatching"
    QUIZ_DRAG_DROP = "quizDragDrop"
    QUIZ_ORDERING = "quizOrdering"
    QUIZ_SHORT_ANSWER = "quizShortAnswer"
    QUIZ_ESSAY = "quizEssay"
    QUIZ_MATH = "quizMathInput"
    QUIZ_CODE = "quizCodeExercise"
    QUIZ_DRAWING = "quizDrawing"
    QUIZ_AUDIO = "quizVoiceResponse"
    QUIZ_SPEAKING = "quizVoiceResponse"
    QUIZ_TIMING = "quizMcq"
    QUIZ_ADAPTIVE = "quizMcq"
    FLASHCARD = "flashcard"
    FLASHCARD_DECK = "flashcardDeck"
    PRACTICE_SET = "quizMcq"
    EXAM_MODE = "quizMcq"
    RUBRIC = "rubricView"
    CONFIDENCE_METER = "progressBar"

    # 5. Study Planning & Organization
    STUDY_PLAN_OVERVIEW = "study_plan_overview"
    STUDY_PLAN_WEEK = "study_plan_week"
    STUDY_PLAN_DAY = "study_plan_day"
    STUDY_SESSION = "study_session"
    EXAM_COUNTDOWN = "exam_countdown"
    GOAL_TRACKER = "goal_tracker"
    MILESTONE_TIMELINE = "milestone_timeline"
    SCHEDULE_IMPORT = "schedule_import"
    CALENDAR_EVENT = "calendar_event"
    REMINDER_SETUP = "reminder_setup"
    TIME_BLOCKING = "time_blocking"
    HABIT_TRACKER = "habit_tracker"
    POMODORO_TIMER = "pomodoro_timer"
    TASK_LIST = "task_list"
    PRIORITY_MATRIX = "priority_matrix"

    # 6. Mistake Tracking & Remediation
    MISTAKE_CARD = "mistake_card"
    MISTAKE_PATTERN = "mistake_pattern"
    WEAK_AREA_CHART = "weak_area_chart"
    REMEDIATION = "remediation"
    CONCEPT_MASTERY = "concept_mastery"
    ERROR_HISTORY = "error_history"
    TARGETED_PRACTICE = "targeted_practice"
    MASTERY_PATH = "mastery_path"
    SKILL_GAP = "skill_gap"
    IMPROVEMENT_PLAN = "improvement_plan"
    CONFIDENCE_HISTORY = "confidence_history"
    MISCONCEPTION_ALERT = "misconception_alert"

    # 7. Homework & Assignment Management
    HOMEWORK_CARD = "homework_card"
    HOMEWORK_HELPER = "homework_helper"
    ASSIGNMENT_LIST = "assignment_list"
    DUE_DATE_BADGE = "due_date_badge"
    SUBMISSION_STATUS = "submission_status"
    PROBLEM_BREAKDOWN = "problem_breakdown"
    SOLUTION_STEPS = "solution_steps"
    HINT_REVEAL = "hint_reveal"
    WORK_CHECKER = "work_checker"
    CITATION_HELPER = "citation_helper"
    PLAGIARISM_CHECKER = "plagiarism_checker"
    GRADE_PREDICTOR = "grade_predictor"
    RUBRIC_VIEWER = "rubric_viewer"
    PEER_REVIEW = "peer_review"
    SUBMISSION_PORTAL = "submission_portal"

    # 8. Interactive Widgets & Controls
    ACTION_BUTTON = "button"
    SUGGESTIONS = "suggestions"
    SELECTION_CHIPS = "filterChips"
    RATING_INPUT = "rating_input"
    SLIDER = "slider"
    TOGGLE = "toggle"
    PICKER = "picker"
    SEGMENTED_CONTROL = "segmented_control"
    COLOR_PICKER = "color_picker"
    STEPPER = "stepper"
    SEARCH_BAR = "search_bar"
    FILTER_CHIPS = "filter_chips"
    SORT_SELECTOR = "sort_selector"
    PAGINATION = "pagination"
    LOAD_MORE_BUTTON = "load_more_button"

    # 9. Document AI & Note Processing
    NOTES_SUMMARY = "notes_summary"
    KEY_POINTS_LIST = "key_points_list"
    CONCEPT_MAP = "concept_map"
    VOCABULARY_LIST = "vocabulary_list"
    FORMULA_SHEET = "formula_sheet"
    DOCUMENT_PREVIEW = "document_preview"
    ANNOTATED_DOCUMENT = "annotated_document"
    COMPARE_DOCUMENTS = "compare_documents"
    SMART_HIGHLIGHTS = "smart_highlights"
    DOCUMENT_OUTLINE = "document_outline"
    KNOWLEDGE_GRAPH = "knowledge_graph"

    # 10. Gamification & Feedback
    PROGRESS_BAR = "progressBar"
    PROGRESS_RING = "progressBar"
    XP_GAIN = "xpBadge"
    STREAK_INDICATOR = "streak_indicator"
    ACHIEVEMENT = "achievement"
    CONFETTI = "confetti"
    LEVEL_UP = "level_up"
    LEADERBOARD_ENTRY = "leaderboard_entry"
    DAILY_CHALLENGE = "daily_challenge"
    ENCOURAGEMENT = "encouragement"
    MOTIVATIONAL_QUOTE = "motivational_quote"
    REWARD_UNLOCK = "reward_unlock"
    SOCIAL_SHARE = "social_share"
    SOCIAL_GROUP_CARD = "social_group_card"

    # 11. AI Assistant & Proactive Features
    AI_THINKING = "ai_thinking"
    AI_SUGGESTION = "ai_suggestion"
    CONTEXT_REMINDER = "context_reminder"
    CHECK_IN = "check_in"
    DAILY_BRIEF = "daily_brief"
    WEEKLY_REVIEW = "weekly_review"
    SMART_NUDGE = "smart_nudge"
    FOCUS_MODE = "focus_mode"
    BREAK_REMINDER = "break_reminder"
    CONVERSATION_STARTER = "conversation_starter"
    AI_PERSONALITY_SELECTOR = "ai_personality_selector"
    COGNITIVE_LOAD_INDICATOR = "cognitive_load"
    
    # 12. Layout
    VSTACK = "vStack"
    HSTACK = "hStack"
    ZSTACK = "zStack"
    GRID = "grid"
    CARD = "card"
    SCROLL = "scrollView"
    
    # Fallback
    UNKNOWN = "unknown"

# ==============================================================================
# MARK: - Props
# ==============================================================================

class A2UIDimensionUnit(str, Enum):
    POINTS = "pt"
    PERCENT = "%"
    FILL = "fill"
    AUTO = "auto"

class A2UIDimension(BaseModel):
    value: float
    unit: A2UIDimensionUnit = A2UIDimensionUnit.POINTS

class A2UIEdgeInsets(BaseModel):
    top: float = 0
    leading: float = 0
    bottom: float = 0
    trailing: float = 0

class A2UIProps(BaseModel):
    # Content
    text: Optional[str] = None
    title: Optional[str] = None
    label: Optional[str] = None  # For buttons and action components
    subtitle: Optional[str] = None
    body: Optional[str] = None
    placeholder: Optional[str] = None
    
    # Style
    background_color: Optional[str] = Field(None, alias="backgroundColor")
    foreground_color: Optional[str] = Field(None, alias="foregroundColor")
    corner_radius: Optional[float] = Field(None, alias="borderRadius")
    padding: Optional[A2UIEdgeInsets] = None
    margin: Optional[A2UIEdgeInsets] = None
    
    # Layout
    width: Optional[A2UIDimension] = None
    height: Optional[A2UIDimension] = None
    spacing: Optional[float] = None
    alignment: Optional[str] = None
    
    # Actions
    action_id: Optional[str] = Field(None, alias="actionId")
    is_disabled: Optional[bool] = Field(None, alias="isDisabled")
    variant: Optional[str] = None  # For button styles: primary, outline, etc.
    
    # Streaming
    stream_id: Optional[str] = Field(None, alias="streamId")
    
    # Media
    image_url: Optional[str] = Field(None, alias="imageUrl")
    video_url: Optional[str] = Field(None, alias="videoUrl")
    
    # Quiz
    question: Optional[str] = None
    options: Optional[List[str]] = None
    correct_answer_index: Optional[int] = Field(None, alias="correctAnswerIndex")
    explanation: Optional[str] = None
    
    class Config:
        populate_by_name = True
        extra = "allow" # Allow extra fields without validation error

# ==============================================================================
# MARK: - Component
# ==============================================================================

class A2UIComponent(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    type: A2UIElementType
    props: A2UIProps = Field(default_factory=A2UIProps)
    children: Optional[List['A2UIComponent']] = None

    def to_dict(self) -> dict:
        """Convert to dict for iOS consumption.
        
        Uses Python field names (snake_case) NOT aliases (camelCase),
        because iOS CodingKeys expect snake_case:
          foreground_color, background_color, font_size, etc.
        Uses mode="json" to ensure enum values are serialized as strings.
        """
        if hasattr(self, "model_dump"):
            return self.model_dump(by_alias=False, exclude_none=True, mode="json")
        return self.dict(by_alias=False, exclude_none=True)

    def to_json(self) -> str:
        """Convert to JSON string for iOS consumption."""
        if hasattr(self, "model_dump_json"):
            return self.model_dump_json(by_alias=False, exclude_none=True)
        return self.json(by_alias=False, exclude_none=True)

    class Config:
        populate_by_name = True

# Resolve forward reference
A2UIComponent.model_rebuild()
