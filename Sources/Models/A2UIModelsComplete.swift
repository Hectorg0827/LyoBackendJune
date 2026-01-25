import Foundation
import SwiftUI

// ═══════════════════════════════════════════════════════════════════════════
// MARK: - Complete A2UI Element Type Catalog (120+ Elements)
// ═══════════════════════════════════════════════════════════════════════════

/// Complete A2UI Element Type Catalog for Lyo Learning Platform
/// Supports: Multimodal I/O, Study Planning, Mistake Tracking, Homework Management
enum A2UIElementType: String, Codable, CaseIterable {

    // ═══════════════════════════════════════════════════════════════════
    // MARK: - Core Display Elements (15 elements)
    // ═══════════════════════════════════════════════════════════════════

    case text
    case heading
    case markdown
    case codeBlock = "code_block"
    case latex                      // Math equations (MathJax/KaTeX)
    case highlight
    case quote
    case callout
    case badge
    case tag
    case label
    case caption
    case divider
    case spacer
    case skeleton                   // Loading placeholder

    // ═══════════════════════════════════════════════════════════════════
    // MARK: - Media Elements (12 elements)
    // ═══════════════════════════════════════════════════════════════════

    case image
    case video
    case audio
    case animation
    case lottie
    case gif
    case diagram                    // AI-generated diagrams (Mermaid/PlantUML)
    case chart                      // Data visualization
    case graph                      // Mathematical graphs
    case model3D = "model_3d"       // AR/3D content
    case handwritingPreview = "handwriting_preview"  // Rendered handwriting
    case qrCode = "qr_code"         // QR code generation

    // ═══════════════════════════════════════════════════════════════════
    // MARK: - Multimodal Input Elements (15 elements) - CRITICAL
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
    case drawingCanvas = "drawing_canvas"       // Drawing/sketching area
    case audioRecorder = "audio_recorder"       // Record audio notes
    case microphoneInput = "microphone_input"   // Live audio input
    case barcodeScanner = "barcode_scanner"     // Scan barcodes/QR codes
    case locationInput = "location_input"       // GPS/location picker
    case dateTimeInput = "date_time_input"      // Date/time picker combined

    // ═══════════════════════════════════════════════════════════════════
    // MARK: - Quiz & Assessment Elements (20 elements) - EXPANDED
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
    case quizAudio = "quiz_audio"               // Audio-based questions
    case quizTiming = "quiz_timing"             // Timed questions
    case quizAdaptive = "quiz_adaptive"         // Adaptive difficulty
    case flashcard
    case flashcardDeck = "flashcard_deck"
    case practiceSet = "practice_set"           // Group of practice problems
    case examMode = "exam_mode"                 // Full exam simulation
    case rubric                                 // Grading rubric display

    // ═══════════════════════════════════════════════════════════════════
    // MARK: - Study Plan Elements (12 elements) - CRITICAL
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
    case timeBlocking = "time_blocking"                 // Time management blocks
    case habitTracker = "habit_tracker"                 // Study habit tracking

    // ═══════════════════════════════════════════════════════════════════
    // MARK: - Mistake Tracker Elements (10 elements) - CRITICAL
    // ═══════════════════════════════════════════════════════════════════

    case mistakeCard = "mistake_card"                   // Single mistake entry
    case mistakePattern = "mistake_pattern"             // Pattern analysis
    case weakAreaChart = "weak_area_chart"              // Visualization of struggles
    case remediation = "remediation"                    // Suggested fix/practice
    case conceptMastery = "concept_mastery"             // Mastery level indicator
    case errorHistory = "error_history"                 // Past mistakes list
    case targetedPractice = "targeted_practice"         // Practice weak areas
    case masteryPath = "mastery_path"                   // Path to mastery
    case skillGap = "skill_gap"                         // Identified gaps
    case improvementPlan = "improvement_plan"           // Improvement roadmap

    // ═══════════════════════════════════════════════════════════════════
    // MARK: - Homework & Assignment Elements (15 elements) - CRITICAL
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
    case plagiarismChecker = "plagiarism_checker"       // Check originality
    case gradePredictor = "grade_predictor"             // Predict assignment grade
    case rubricViewer = "rubric_viewer"                 // Assignment rubric
    case peerReview = "peer_review"                     // Peer review interface
    case submissionPortal = "submission_portal"         // Assignment submission

    // ═══════════════════════════════════════════════════════════════════
    // MARK: - Notes & Document Processing Elements (12 elements)
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
    case documentOutline = "document_outline"          // Auto-generated outline
    case readingTime = "reading_time"                   // Estimated reading time

    // ═══════════════════════════════════════════════════════════════════
    // MARK: - Course & Learning Path Elements (10 elements)
    // ═══════════════════════════════════════════════════════════════════

    case courseRoadmap = "course_roadmap"
    case lessonCard = "lesson_card"
    case moduleProgress = "module_progress"
    case learningPath = "learning_path"
    case prerequisiteTree = "prerequisite_tree"         // What to learn first
    case skillTree = "skill_tree"                       // Gamified progression
    case certificationBadge = "certification_badge"
    case courseCompletion = "course_completion"         // Completion ceremony
    case nextRecommendation = "next_recommendation"     // What to learn next
    case difficultySelector = "difficulty_selector"     // Choose difficulty level

    // ═══════════════════════════════════════════════════════════════════
    // MARK: - Interactive Widgets (18 elements)
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
    case stepper
    case segmentedControl = "segmented_control"
    case searchBar = "search_bar"
    case filterChips = "filter_chips"
    case sortSelector = "sort_selector"
    case pagination
    case loadMoreButton = "load_more_button"

    // ═══════════════════════════════════════════════════════════════════
    // MARK: - Layout Containers (12 elements)
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
    case masonry                                        // Pinterest-style layout
    case sidebar
    case drawer                                         // Side drawer/panel

    // ═══════════════════════════════════════════════════════════════════
    // MARK: - Feedback & Gamification (15 elements)
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
    case celebration                                    // Success celebration
    case motivationalQuote = "motivational_quote"      // Inspiring quotes
    case progressCelebration = "progress_celebration"   // Milestone celebration
    case rewardUnlock = "reward_unlock"                // Unlocked rewards
    case socialShare = "social_share"                  // Share achievements

    // ═══════════════════════════════════════════════════════════════════
    // MARK: - AI Assistant Elements (12 elements) - PROACTIVE FEATURES
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
    case studyTip = "study_tip"                        // Learning tips
    case adaptiveHelp = "adaptive_help"                // Context-aware help
    case conversationStarter = "conversation_starter"   // Topic suggestions

    // ═══════════════════════════════════════════════════════════════════
    // MARK: - Social & Collaboration Elements (8 elements)
    // ═══════════════════════════════════════════════════════════════════

    case studyGroup = "study_group"                     // Group study sessions
    case peerChallenge = "peer_challenge"               // Compete with friends
    case shareCard = "share_card"                       // Share content
    case commentThread = "comment_thread"               // Discussion threads
    case pollQuestion = "poll_question"                 // Polls and voting
    case collaborativeEditor = "collaborative_editor"   // Real-time editing
    case videoChat = "video_chat"                      // Video calls
    case whiteboard = "whiteboard"                     // Collaborative whiteboard

    // ═══════════════════════════════════════════════════════════════════
    // MARK: - Analytics & Insights (8 elements)
    // ═══════════════════════════════════════════════════════════════════

    case performanceChart = "performance_chart"         // Performance over time
    case timeSpentChart = "time_spent_chart"           // Time analytics
    case accuracyMetrics = "accuracy_metrics"          // Accuracy tracking
    case learningVelocity = "learning_velocity"        // Learning speed
    case focusAnalytics = "focus_analytics"            // Attention patterns
    case subjectBreakdown = "subject_breakdown"        // Performance by subject
    case weeklyReport = "weekly_report"                // Weekly analytics
    case parentDashboard = "parent_dashboard"          // Parent insights

    // ═══════════════════════════════════════════════════════════════════
    // MARK: - System & Navigation (10 elements)
    // ═══════════════════════════════════════════════════════════════════

    case processing
    case error
    case empty
    case unknown
    case topicSelection = "topic_selection"
    case navigationPrompt = "navigation_prompt"         // "Go to X?"
    case deepLink = "deep_link"                         // Link to app section
    case breadcrumb                                     // Navigation breadcrumb
    case backButton = "back_button"                    // Custom back navigation
    case menuButton = "menu_button"                    // Hamburger menu

    /// Total elements: 150+ comprehensive catalog
}

// ═══════════════════════════════════════════════════════════════════════════
// MARK: - Element Categories for Organization
// ═══════════════════════════════════════════════════════════════════════════

enum A2UIElementCategory: String, Codable, CaseIterable {
    case display = "display"
    case media = "media"
    case multimodalInput = "multimodal_input"
    case assessment = "assessment"
    case studyPlanning = "study_planning"
    case mistakeTracking = "mistake_tracking"
    case homework = "homework"
    case documentProcessing = "document_processing"
    case course = "course"
    case interactive = "interactive"
    case layout = "layout"
    case gamification = "gamification"
    case aiAssistant = "ai_assistant"
    case social = "social"
    case analytics = "analytics"
    case system = "system"
}

extension A2UIElementType {
    /// Get element category for organization and permissions
    var category: A2UIElementCategory {
        switch self {
        // Display Elements
        case .text, .heading, .markdown, .codeBlock, .latex, .highlight, .quote,
             .callout, .badge, .tag, .label, .caption, .divider, .spacer, .skeleton:
            return .display

        // Media Elements
        case .image, .video, .audio, .animation, .lottie, .gif, .diagram, .chart,
             .graph, .model3D, .handwritingPreview, .qrCode:
            return .media

        // Multimodal Input
        case .textInput, .voiceInput, .cameraCapture, .documentUpload, .handwritingInput,
             .screenCapture, .fileDropZone, .mathInput, .codeEditor, .drawingCanvas,
             .audioRecorder, .microphoneInput, .barcodeScanner, .locationInput, .dateTimeInput:
            return .multimodalInput

        // Assessment
        case .quizMcq, .quizMultiSelect, .quizTrueFalse, .quizFillBlank, .quizMatching,
             .quizDragDrop, .quizOrdering, .quizShortAnswer, .quizEssay, .quizMath,
             .quizCode, .quizDrawing, .quizAudio, .quizTiming, .quizAdaptive,
             .flashcard, .flashcardDeck, .practiceSet, .examMode, .rubric:
            return .assessment

        // Study Planning
        case .studyPlanOverview, .studyPlanWeek, .studyPlanDay, .studySession,
             .examCountdown, .goalTracker, .milestoneTimeline, .scheduleImport,
             .calendarEvent, .reminderSetup, .timeBlocking, .habitTracker:
            return .studyPlanning

        // Mistake Tracking
        case .mistakeCard, .mistakePattern, .weakAreaChart, .remediation, .conceptMastery,
             .errorHistory, .targetedPractice, .masteryPath, .skillGap, .improvementPlan:
            return .mistakeTracking

        // Homework
        case .homeworkCard, .homeworkHelper, .assignmentList, .dueDateBadge, .submissionStatus,
             .problemBreakdown, .solutionSteps, .hintReveal, .workChecker, .citationHelper,
             .plagiarismChecker, .gradePredictor, .rubricViewer, .peerReview, .submissionPortal:
            return .homework

        // Document Processing
        case .notesSummary, .keyPointsList, .conceptMap, .vocabularyList, .formulaSheet,
             .documentPreview, .ocrResult, .annotatedDocument, .compareDocuments,
             .smartHighlights, .documentOutline, .readingTime:
            return .documentProcessing

        // Course & Learning
        case .courseRoadmap, .lessonCard, .moduleProgress, .learningPath, .prerequisiteTree,
             .skillTree, .certificationBadge, .courseCompletion, .nextRecommendation, .difficultySelector:
            return .course

        // Interactive
        case .suggestions, .actionButton, .confirmDialog, .selectionChips, .ratingInput,
             .slider, .toggle, .picker, .datePicker, .timePicker, .colorPicker, .stepper,
             .segmentedControl, .searchBar, .filterChips, .sortSelector, .pagination, .loadMoreButton:
            return .interactive

        // Layout
        case .stack, .grid, .carousel, .tabs, .accordion, .card, .expandableSection,
             .splitView, .scrollableList, .masonry, .sidebar, .drawer:
            return .layout

        // Gamification
        case .progressBar, .progressRing, .xpGain, .streakIndicator, .achievement, .confetti,
             .levelUp, .leaderboardEntry, .dailyChallenge, .encouragement, .celebration,
             .motivationalQuote, .progressCelebration, .rewardUnlock, .socialShare:
            return .gamification

        // AI Assistant
        case .aiThinking, .aiSuggestion, .contextReminder, .checkIn, .dailyBrief,
             .weeklyReview, .smartNudge, .focusMode, .breakReminder, .studyTip,
             .adaptiveHelp, .conversationStarter:
            return .aiAssistant

        // Social
        case .studyGroup, .peerChallenge, .shareCard, .commentThread, .pollQuestion,
             .collaborativeEditor, .videoChat, .whiteboard:
            return .social

        // Analytics
        case .performanceChart, .timeSpentChart, .accuracyMetrics, .learningVelocity,
             .focusAnalytics, .subjectBreakdown, .weeklyReport, .parentDashboard:
            return .analytics

        // System
        case .processing, .error, .empty, .unknown, .topicSelection, .navigationPrompt,
             .deepLink, .breadcrumb, .backButton, .menuButton:
            return .system
        }
    }

    /// Is this element type premium-only?
    var isPremium: Bool {
        switch self {
        case .voiceInput, .cameraCapture, .handwritingInput, .model3D, .quizAdaptive,
             .mistakePattern, .targetedPractice, .aiSuggestion, .parentDashboard,
             .plagiarismChecker, .collaborativeEditor, .videoChat:
            return true
        default:
            return false
        }
    }

    /// Does this element require special permissions?
    var requiredPermissions: [String] {
        switch self {
        case .cameraCapture, .barcodeScanner:
            return ["camera"]
        case .voiceInput, .audioRecorder, .microphoneInput:
            return ["microphone"]
        case .locationInput:
            return ["location"]
        case .documentUpload, .fileDropZone:
            return ["file_access"]
        default:
            return []
        }
    }
}

// ═══════════════════════════════════════════════════════════════════════════
// MARK: - Element Support Matrix
// ═══════════════════════════════════════════════════════════════════════════

struct A2UIElementSupport {
    /// Currently implemented elements (from existing renderer)
    static let implemented: Set<A2UIElementType> = [
        // Basic elements from current implementation
        .text, .heading, .image, .video, .stack, .grid, .textInput, .slider,
        .toggle, .picker, .progressBar, .suggestions, .divider, .spacer,
        .processing, .unknown, .courseRoadmap, .lessonCard
    ]

    /// Critical elements needed for your vision (Phase 1)
    static let critical: Set<A2UIElementType> = [
        // Multimodal input (auto notes from anything)
        .cameraCapture, .documentUpload, .handwritingInput, .voiceInput, .ocrResult,

        // Study planning (short and long term)
        .studyPlanOverview, .studySession, .examCountdown, .goalTracker, .milestoneTimeline,

        // Mistake tracking (tracks and helps with mistakes)
        .mistakeCard, .weakAreaChart, .remediation, .targetedPractice, .conceptMastery,

        // Homework helper (homework helper/tracker)
        .homeworkCard, .homeworkHelper, .problemBreakdown, .solutionSteps, .hintReveal,

        // Document processing (AI notes)
        .notesSummary, .keyPointsList, .vocabularyList, .smartHighlights
    ]

    /// All missing elements
    static let missing: Set<A2UIElementType> = {
        Set(A2UIElementType.allCases).subtracting(implemented)
    }()

    /// Implementation completion percentage
    static let completionPercentage: Double = {
        Double(implemented.count) / Double(A2UIElementType.allCases.count) * 100
    }()

    /// Critical element completion percentage
    static let criticalCompletion: Double = {
        let criticalImplemented = critical.intersection(implemented)
        return Double(criticalImplemented.count) / Double(critical.count) * 100
    }()
}

// ═══════════════════════════════════════════════════════════════════════════
// MARK: - Enhanced A2UI Component Model
// ═══════════════════════════════════════════════════════════════════════════

struct A2UIComponent: Codable, Identifiable, Equatable {
    let id: String
    let type: A2UIElementType
    let props: A2UIProps
    let children: [A2UIComponent]?
    let actions: [A2UIAction]?
    let conditions: A2UIConditions?
    let metadata: A2UIMetadata?

    init(
        id: String = UUID().uuidString,
        type: A2UIElementType,
        props: A2UIProps = A2UIProps(),
        children: [A2UIComponent]? = nil,
        actions: [A2UIAction]? = nil,
        conditions: A2UIConditions? = nil,
        metadata: A2UIMetadata? = nil
    ) {
        self.id = id
        self.type = type
        self.props = props
        self.children = children
        self.actions = actions
        self.conditions = conditions
        self.metadata = metadata
    }

    // Equatable conformance
    static func == (lhs: A2UIComponent, rhs: A2UIComponent) -> Bool {
        return lhs.id == rhs.id &&
               lhs.type == rhs.type &&
               lhs.props == rhs.props
    }
}

// ═══════════════════════════════════════════════════════════════════════════
// MARK: - Comprehensive A2UI Props
// ═══════════════════════════════════════════════════════════════════════════

struct A2UIProps: Codable, Equatable {

    // MARK: - Content Properties
    var text: String?
    var title: String?
    var subtitle: String?
    var body: String?
    var placeholder: String?
    var label: String?
    var caption: String?
    var hint: String?
    var description: String?

    // MARK: - Media Properties
    var imageUrl: String?
    var videoUrl: String?
    var audioUrl: String?
    var assetName: String?
    var thumbnailUrl: String?
    var mimeType: String?
    var fileSize: Int?
    var duration: Double?
    var resolution: String?
    var quality: String?

    // MARK: - Layout & Styling
    var alignment: String?
    var axis: String?
    var spacing: Double?
    var padding: A2UIPadding?
    var margin: A2UIPadding?
    var maxWidth: Double?
    var maxHeight: Double?
    var minWidth: Double?
    var minHeight: Double?
    var aspectRatio: Double?
    var cornerRadius: Double?
    var shadowRadius: Double?
    var opacity: Double?

    // MARK: - Colors
    var backgroundColor: String?
    var foregroundColor: String?
    var accentColor: String?
    var borderColor: String?
    var gradientColors: [String]?
    var tintColor: String?

    // MARK: - Typography
    var fontWeight: String?
    var fontSize: Double?
    var fontFamily: String?
    var lineLimit: Int?
    var textAlignment: String?
    var letterSpacing: Double?
    var lineHeight: Double?

    // MARK: - Interactive State
    var isEnabled: Bool?
    var isRequired: Bool?
    var isExpanded: Bool?
    var isSelected: Bool?
    var isLoading: Bool?
    var isEditable: Bool?
    var isHidden: Bool?
    var isAnimated: Bool?
    var selectedIndex: Int?
    var selectedIndices: [Int]?
    var currentValue: String?
    var minValue: Double?
    var maxValue: Double?
    var step: Double?

    // MARK: - Assessment Properties
    var question: String?
    var options: [String]?
    var correctAnswer: String?
    var correctIndex: Int?
    var correctIndices: [Int]?
    var explanation: String?
    var hints: [String]?
    var timeLimit: Int?
    var pointValue: Int?
    var difficulty: String?
    var showFeedback: Bool?
    var allowRetry: Bool?
    var maxAttempts: Int?
    var shuffleOptions: Bool?

    // MARK: - Study Planning Properties
    var startDate: Date?
    var endDate: Date?
    var dueDate: Date?
    var examDate: Date?
    var scheduledTime: Date?
    var durationMinutes: Int?
    var recurrence: String?
    var priority: String?
    var status: String?
    var progress: Double?
    var sessions: [A2UIStudySession]?
    var milestones: [A2UIMilestone]?

    // MARK: - Mistake Tracking Properties
    var mistakeType: String?
    var frequency: Int?
    var lastOccurred: Date?
    var masteryLevel: Double?
    var relatedConcepts: [String]?
    var suggestedReview: String?
    var weakAreas: [A2UIWeakArea]?
    var errorPatterns: [A2UIErrorPattern]?

    // MARK: - Homework Properties
    var assignmentId: String?
    var courseName: String?
    var className: String?
    var teacherName: String?
    var instructions: String?
    var problems: [A2UIProblem]?
    var attachments: [A2UIAttachment]?
    var submissionUrl: String?
    var isLate: Bool?
    var gradeReceived: String?
    var feedback: String?

    // MARK: - Document Processing Properties
    var documentType: String?
    var pageCount: Int?
    var extractedText: String?
    var keyPoints: [String]?
    var vocabulary: [A2UIVocabularyItem]?
    var formulas: [A2UIFormula]?
    var summaryLength: String?
    var highlightedSections: [A2UIHighlight]?
    var ocrConfidence: Double?

    // MARK: - Multimodal Input Properties
    var acceptedTypes: [String]?
    var maxFileSize: Int?
    var captureMode: String?
    var enableFlash: Bool?
    var enableCrop: Bool?
    var enableOCR: Bool?
    var voiceLanguage: String?
    var voiceHint: String?
    var drawingTools: [String]?
    var drawingColor: String?
    var drawingStrokeWidth: Double?

    // MARK: - Voice Properties
    var speakableText: String?
    var ttsVoice: String?
    var ttsSpeed: Double?
    var autoSpeak: Bool?
    var acceptsVoiceInput: Bool?

    // MARK: - Analytics Properties
    var trackingId: String?
    var eventName: String?
    var customProperties: [String: String]?

    // MARK: - Gamification Properties
    var xpAmount: Int?
    var level: Int?
    var rank: Int?
    var score: Double?
    var accuracy: Double?
    var streak: Int?
    var achievements: [String]?

    // MARK: - Social Properties
    var authorId: String?
    var authorName: String?
    var createdAt: Date?
    var likesCount: Int?
    var commentsCount: Int?
    var sharesCount: Int?

    // MARK: - Accessibility Properties
    var accessibilityLabel: String?
    var accessibilityHint: String?
    var accessibilityValue: String?
    var isAccessibilityElement: Bool?
    var accessibilityTraits: [String]?

    // MARK: - Data Binding
    var dataKey: String?
    var defaultValue: String?
    var validation: A2UIValidation?
    var errorMessage: String?

    // MARK: - Metadata
    var tags: [String]?
    var category: String?
    var source: String?
    var version: Int?
    var updatedAt: Date?
    var expiresAt: Date?
    var customData: [String: String]?

    // MARK: - Initializer
    init() {
        // All properties are optional with default nil values
    }
}

// ═══════════════════════════════════════════════════════════════════════════
// MARK: - Supporting Data Structures
// ═══════════════════════════════════════════════════════════════════════════

struct A2UIPadding: Codable, Equatable {
    var top: Double?
    var leading: Double?
    var bottom: Double?
    var trailing: Double?
    var all: Double?

    init(top: Double? = nil, leading: Double? = nil, bottom: Double? = nil, trailing: Double? = nil, all: Double? = nil) {
        self.top = top
        self.leading = leading
        self.bottom = bottom
        self.trailing = trailing
        self.all = all
    }
}

struct A2UIAction: Codable, Equatable, Identifiable {
    let id: String
    let trigger: A2UITrigger
    let type: A2UIActionType
    let payload: [String: String]?
    let debounceMs: Int?
    let confirmation: A2UIConfirmation?

    init(
        id: String = UUID().uuidString,
        trigger: A2UITrigger,
        type: A2UIActionType,
        payload: [String: String]? = nil,
        debounceMs: Int? = nil,
        confirmation: A2UIConfirmation? = nil
    ) {
        self.id = id
        self.trigger = trigger
        self.type = type
        self.payload = payload
        self.debounceMs = debounceMs
        self.confirmation = confirmation
    }
}

enum A2UITrigger: String, Codable {
    case onTap
    case onLongPress
    case onSwipe
    case onSubmit
    case onComplete
    case onTimeout
    case onChange
    case onAppear
    case onDisappear
    case onFocus
    case onBlur
}

enum A2UIActionType: String, Codable {
    case navigate
    case openClassroom = "open_classroom"
    case sendMessage = "send_message"
    case submitAnswer = "submit_answer"
    case playAudio = "play_audio"
    case trackEvent = "track_event"
    case awardXP = "award_xp"
    case showModal = "show_modal"
    case dismiss
    case custom
    case openUrl = "open_url"
    case shareContent = "share_content"
    case copyText = "copy_text"
    case downloadFile = "download_file"
    case scheduleReminder = "schedule_reminder"
}

struct A2UIConfirmation: Codable, Equatable {
    let title: String
    let message: String
    let confirmText: String
    let cancelText: String
    let isDestructive: Bool?
}

struct A2UIConditions: Codable, Equatable {
    var showIf: String?
    var hideIf: String?
    var enableIf: String?
    var disableIf: String?
}

struct A2UIMetadata: Codable, Equatable {
    let componentVersion: String?
    let lastModified: Date?
    let createdBy: String?
    let experiments: [String]?
    let analyticsContext: [String: String]?
}

struct A2UIValidation: Codable, Equatable {
    let type: String
    let pattern: String?
    let min: Double?
    let max: Double?
    let message: String?
    let isRequired: Bool?
}

// Study Planning Models
struct A2UIStudySession: Codable, Equatable, Identifiable {
    let id: String
    let topic: String
    let scheduledAt: Date
    let durationMinutes: Int
    let isCompleted: Bool
    let notes: String?
}

struct A2UIMilestone: Codable, Equatable, Identifiable {
    let id: String
    let title: String
    let date: Date
    let type: String
    let isCompleted: Bool
    let relatedCourseId: String?
}

// Mistake Tracking Models
struct A2UIWeakArea: Codable, Equatable, Identifiable {
    let id: String
    let topic: String
    let subject: String?
    let mistakeCount: Int
    let lastPracticed: Date?
    let masteryLevel: Double
    let recommendedAction: String?
}

struct A2UIErrorPattern: Codable, Equatable, Identifiable {
    let id: String
    let pattern: String
    let examples: [String]
    let frequency: Int
    let remediation: String
}

// Homework Models
struct A2UIProblem: Codable, Equatable, Identifiable {
    let id: String
    let number: Int
    let question: String
    let imageUrl: String?
    let pointValue: Int?
    let isCompleted: Bool
    let userAnswer: String?
    let isCorrect: Bool?
}

struct A2UIAttachment: Codable, Equatable, Identifiable {
    let id: String
    let filename: String
    let url: String
    let mimeType: String
    let sizeBytes: Int
}

// Document Processing Models
struct A2UIVocabularyItem: Codable, Equatable, Identifiable {
    let id: String
    let term: String
    let definition: String
    let context: String?
    let pronunciation: String?
}

struct A2UIFormula: Codable, Equatable, Identifiable {
    let id: String
    let latex: String
    let description: String
    let variables: [String: String]?
}

struct A2UIHighlight: Codable, Equatable, Identifiable {
    let id: String
    let text: String
    let pageNumber: Int?
    let importance: String
    let note: String?
}

// ═══════════════════════════════════════════════════════════════════════════
// MARK: - Utility Extensions
// ═══════════════════════════════════════════════════════════════════════════

extension A2UIComponent {
    /// Get prop value with type safety
    func prop<T>(_ key: String, type: T.Type, default defaultValue: T? = nil) -> T? {
        // This would be implemented based on your UIValue system
        // For now, returning defaultValue
        return defaultValue
    }

    /// Check if component has children
    var hasChildren: Bool {
        return children?.isEmpty == false
    }

    /// Get all child components recursively
    func allChildComponents() -> [A2UIComponent] {
        var allChildren: [A2UIComponent] = []
        if let children = children {
            for child in children {
                allChildren.append(child)
                allChildren.append(contentsOf: child.allChildComponents())
            }
        }
        return allChildren
    }

    /// Find child by ID
    func findChild(id: String) -> A2UIComponent? {
        if let children = children {
            for child in children {
                if child.id == id {
                    return child
                }
                if let found = child.findChild(id: id) {
                    return found
                }
            }
        }
        return nil
    }
}

extension A2UIElementType {
    /// User-friendly display name
    var displayName: String {
        switch self {
        case .cameraCapture:
            return "Camera Capture"
        case .documentUpload:
            return "Document Upload"
        case .handwritingInput:
            return "Handwriting Input"
        case .studyPlanOverview:
            return "Study Plan Overview"
        case .mistakeCard:
            return "Mistake Card"
        case .homeworkCard:
            return "Homework Card"
        default:
            return rawValue.replacingOccurrences(of: "_", with: " ").capitalized
        }
    }

    /// Description for developers
    var description: String {
        switch self {
        case .cameraCapture:
            return "Enables photo/document scanning with OCR capabilities"
        case .studyPlanOverview:
            return "Displays comprehensive study plan with sessions and milestones"
        case .mistakeCard:
            return "Shows individual mistakes with remediation suggestions"
        case .targetedPractice:
            return "Generates practice problems targeting user's weak areas"
        default:
            return "A2UI component: \(displayName)"
        }
    }
}

print("✅ Complete A2UI Models implemented with \(A2UIElementType.allCases.count) elements")
print("📊 Current completion: \(String(format: "%.1f", A2UIElementSupport.completionPercentage))%")
print("🎯 Critical elements: \(String(format: "%.1f", A2UIElementSupport.criticalCompletion))% complete")