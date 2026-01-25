import Foundation

/// Complete A2UI Element Catalog for Lyo Learning Platform
/// Supports: Multimodal I/O, Study Planning, Mistake Tracking, Homework Management
enum A2UIElementType: String, Codable, CaseIterable {

    // ═══════════════════════════════════════════════════════════════════
    // MARK: - Core Display Elements
    // ═══════════════════════════════════════════════════════════════════

    case text
    case heading
    case markdown
    case codeBlock = "code_block"
    case latex                      // Math equations (MathJax/KaTeX)
    case highlight
    case quote
    case divider
    case spacer

    // ═══════════════════════════════════════════════════════════════════
    // MARK: - Media Elements (Multimodal Output)
    // ═══════════════════════════════════════════════════════════════════

    case image
    case video
    case audio
    case animation
    case lottie
    case diagram                    // AI-generated diagrams (Mermaid/PlantUML)
    case chart                      // Data visualization
    case model3D = "model_3d"       // AR/3D content
    case handwritingPreview = "handwriting_preview"  // Rendered handwriting

    // ═══════════════════════════════════════════════════════════════════
    // MARK: - Multimodal Input Elements (NEW - CRITICAL)
    // ═══════════════════════════════════════════════════════════════════

    case textInput = "text_input"
    case voiceInput = "voice_input"
    case cameraCapture = "camera_capture"       // Photo/document scan
    case documentUpload = "document_upload"     // PDF, DOC, etc.
    case handwritingInput = "handwriting_input" // Draw/write with finger/pencil
    case screenCapture = "screen_capture"       // Screenshot annotation
    case fileDropZone = "file_drop_zone"        // Drag-and-drop area
    case mathInput = "math_input"               // Equation editor
    case codeEditor = "code_editor"             // Syntax-highlighted editor

    // ═══════════════════════════════════════════════════════════════════
    // MARK: - Quiz & Assessment Elements (EXPANDED)
    // ═══════════════════════════════════════════════════════════════════

    case quizMcq = "quiz_mcq"                   // Multiple choice (single)
    case quizMultiSelect = "quiz_multi_select"  // Multiple choice (many)
    case quizTrueFalse = "quiz_true_false"
    case quizFillBlank = "quiz_fill_blank"
    case quizMatching = "quiz_matching"
    case quizDragDrop = "quiz_drag_drop"
    case quizOrdering = "quiz_ordering"         // Put in correct order
    case quizShortAnswer = "quiz_short_answer"
    case quizEssay = "quiz_essay"
    case quizMath = "quiz_math"                 // Math problem with step check
    case quizCode = "quiz_code"                 // Code challenge
    case quizDrawing = "quiz_drawing"           // Draw answer (geometry, etc.)
    case flashcard
    case flashcardDeck = "flashcard_deck"

    // ═══════════════════════════════════════════════════════════════════
    // MARK: - Study Plan Elements (NEW - CRITICAL)
    // ═══════════════════════════════════════════════════════════════════

    case studyPlanOverview = "study_plan_overview"      // Full semester view
    case studyPlanWeek = "study_plan_week"              // Weekly breakdown
    case studyPlanDay = "study_plan_day"                // Daily schedule
    case studySession = "study_session"                 // Single study block
    case examCountdown = "exam_countdown"               // Days until test
    case goalTracker = "goal_tracker"                   // Progress toward goal
    case milestoneTimeline = "milestone_timeline"       // Key dates visualization
    case scheduleImport = "schedule_import"             // Import class schedule
    case calendarEvent = "calendar_event"               // Single event card
    case reminderSetup = "reminder_setup"               // Configure notifications

    // ═══════════════════════════════════════════════════════════════════
    // MARK: - Mistake Tracker Elements (NEW - CRITICAL)
    // ═══════════════════════════════════════════════════════════════════

    case mistakeCard = "mistake_card"                   // Single mistake entry
    case mistakePattern = "mistake_pattern"             // Pattern analysis
    case weakAreaChart = "weak_area_chart"              // Visualization of struggles
    case remediation = "remediation"                    // Suggested fix/practice
    case conceptMastery = "concept_mastery"             // Mastery level indicator
    case errorHistory = "error_history"                 // Past mistakes list
    case targetedPractice = "targeted_practice"         // Practice weak areas

    // ═══════════════════════════════════════════════════════════════════
    // MARK: - Homework & Assignment Elements (NEW - CRITICAL)
    // ═══════════════════════════════════════════════════════════════════

    case homeworkCard = "homework_card"                 // Assignment overview
    case homeworkHelper = "homework_helper"             // Step-by-step guidance
    case assignmentList = "assignment_list"             // All assignments view
    case dueDateBadge = "due_date_badge"                // Urgency indicator
    case submissionStatus = "submission_status"         // Submitted/Pending/Late
    case problemBreakdown = "problem_breakdown"         // Problem decomposition
    case solutionSteps = "solution_steps"               // Guided solution
    case hintReveal = "hint_reveal"                     // Progressive hints
    case workChecker = "work_checker"                   // Validate student work
    case citationHelper = "citation_helper"             // Bibliography/citations

    // ═══════════════════════════════════════════════════════════════════
    // MARK: - Notes & Document Processing Elements (NEW)
    // ═══════════════════════════════════════════════════════════════════

    case notesSummary = "notes_summary"                 // AI-generated summary
    case keyPointsList = "key_points_list"              // Extracted key points
    case conceptMap = "concept_map"                     // Visual concept mapping
    case vocabularyList = "vocabulary_list"             // Terms & definitions
    case formulaSheet = "formula_sheet"                 // Extracted formulas
    case documentPreview = "document_preview"           // Uploaded doc preview
    case ocrResult = "ocr_result"                       // Handwriting recognition
    case annotatedDocument = "annotated_document"       // Doc with AI annotations
    case compareDocuments = "compare_documents"         // Side-by-side comparison
    case smartHighlights = "smart_highlights"           // AI-highlighted passages

    // ═══════════════════════════════════════════════════════════════════
    // MARK: - Course & Learning Path Elements
    // ═══════════════════════════════════════════════════════════════════

    case courseRoadmap = "course_roadmap"
    case lessonCard = "lesson_card"
    case moduleProgress = "module_progress"
    case learningPath = "learning_path"
    case prerequisiteTree = "prerequisite_tree"         // What to learn first
    case skillTree = "skill_tree"                       // Gamified progression
    case certificationBadge = "certification_badge"

    // ═══════════════════════════════════════════════════════════════════
    // MARK: - Interactive Widgets
    // ═══════════════════════════════════════════════════════════════════

    case suggestions
    case actionButton = "action_button"
    case confirmDialog = "confirm_dialog"
    case selectionChips = "selection_chips"
    case ratingInput = "rating_input"
    case slider
    case toggle
    case picker
    case datePicker = "date_picker"
    case timePicker = "time_picker"
    case colorPicker = "color_picker"

    // ═══════════════════════════════════════════════════════════════════
    // MARK: - Layout Containers
    // ═══════════════════════════════════════════════════════════════════

    case stack
    case grid
    case carousel
    case tabs
    case accordion
    case card
    case expandableSection = "expandable_section"
    case splitView = "split_view"
    case scrollableList = "scrollable_list"

    // ═══════════════════════════════════════════════════════════════════
    // MARK: - Feedback & Gamification
    // ═══════════════════════════════════════════════════════════════════

    case progressBar = "progress_bar"
    case progressRing = "progress_ring"
    case xpGain = "xp_gain"
    case streakIndicator = "streak_indicator"
    case achievement
    case confetti
    case levelUp = "level_up"
    case leaderboardEntry = "leaderboard_entry"
    case dailyChallenge = "daily_challenge"
    case encouragement                                  // Motivational message

    // ═══════════════════════════════════════════════════════════════════
    // MARK: - AI Assistant Elements (NEW - PROACTIVE FEATURES)
    // ═══════════════════════════════════════════════════════════════════

    case aiThinking = "ai_thinking"                     // Processing indicator
    case aiSuggestion = "ai_suggestion"                 // Proactive recommendation
    case contextReminder = "context_reminder"           // "Remember, you have..."
    case checkIn = "check_in"                           // "How's studying going?"
    case dailyBrief = "daily_brief"                     // Morning summary
    case weeklyReview = "weekly_review"                 // Weekly progress report
    case smartNudge = "smart_nudge"                     // Gentle reminder
    case focusMode = "focus_mode"                       // Deep work session UI
    case breakReminder = "break_reminder"               // Time to rest

    // ═══════════════════════════════════════════════════════════════════
    // MARK: - System & Navigation
    // ═══════════════════════════════════════════════════════════════════

    case processing
    case error
    case empty
    case skeleton
    case unknown
    case topicSelection = "topic_selection"
    case navigationPrompt = "navigation_prompt"         // "Go to X?"
    case deepLink = "deep_link"                         // Link to app section

    /// Get element category for organization
    var category: A2UIElementCategory {
        switch self {
        case .text, .heading, .markdown, .codeBlock, .latex, .highlight, .quote:
            return .content
        case .image, .video, .audio, .animation, .lottie, .diagram, .chart, .model3D:
            return .media
        case .cameraCapture, .documentUpload, .handwritingInput, .voiceInput, .fileDropZone:
            return .multimodalInput
        case .studyPlanOverview, .studySession, .examCountdown, .goalTracker, .milestoneTimeline:
            return .studyPlanning
        case .mistakeCard, .weakAreaChart, .remediation, .conceptMastery, .targetedPractice:
            return .mistakeTracking
        case .homeworkCard, .homeworkHelper, .problemBreakdown, .solutionSteps, .hintReveal:
            return .homework
        case .notesSummary, .keyPointsList, .vocabularyList, .documentPreview, .ocrResult:
            return .documentProcessing
        case .quizMcq, .quizMultiSelect, .quizTrueFalse, .flashcard, .quizDragDrop:
            return .assessment
        case .stack, .grid, .carousel, .tabs, .accordion, .card:
            return .layout
        case .progressBar, .xpGain, .achievement, .confetti, .streakIndicator:
            return .gamification
        case .aiThinking, .aiSuggestion, .checkIn, .dailyBrief, .smartNudge:
            return .aiAssistant
        default:
            return .system
        }
    }
}

enum A2UIElementCategory: String, Codable {
    case content
    case media
    case multimodalInput = "multimodal_input"
    case studyPlanning = "study_planning"
    case mistakeTracking = "mistake_tracking"
    case homework
    case documentProcessing = "document_processing"
    case assessment
    case layout
    case gamification
    case aiAssistant = "ai_assistant"
    case system
}

/// Element support matrix - which elements are implemented
struct A2UIElementSupport {
    static let implemented: Set<A2UIElementType> = [
        // Current implementation (from your existing renderer)
        .text, .heading, .image, .video, .stack, .grid,
        .textInput, .slider, .toggle, .picker,
        .courseRoadmap, .lessonCard, .progressBar, .suggestions,
        .divider, .spacer, .processing, .unknown
    ]

    static let critical: Set<A2UIElementType> = [
        // Must implement for your vision
        .cameraCapture, .documentUpload, .handwritingInput, .voiceInput,
        .studyPlanOverview, .studySession, .examCountdown, .goalTracker,
        .mistakeCard, .weakAreaChart, .remediation, .targetedPractice,
        .homeworkCard, .homeworkHelper, .problemBreakdown, .solutionSteps,
        .notesSummary, .keyPointsList, .vocabularyList, .ocrResult
    ]

    static let missing: Set<A2UIElementType> = {
        Set(A2UIElementType.allCases).subtracting(implemented)
    }()

    static let completionPercentage: Double = {
        Double(implemented.count) / Double(A2UIElementType.allCases.count) * 100
    }()
}