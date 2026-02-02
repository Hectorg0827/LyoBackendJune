import Foundation

/// Complete A2UI Element Catalog for Lyo Learning Platform
/// 160+ Exhaustive Elements for a Multimodal AI Learning Companion
enum A2UIElementType: String, Codable, CaseIterable {

    // ═══════════════════════════════════════════════════════════════════
    // MARK: - 1. Core Display & Typography (15 Elements)
    // ═══════════════════════════════════════════════════════════════════

    case text
    case heading
    case markdown
    case codeBlock = "code_block"
    case latex                      // Math equations (MathJax/KaTeX)
    case highlight
    case quote
    case callout                    // Colored boxes for warnings, tips, etc.
    case badge                      // Status indicators (e.g., "New", "Hard")
    case tag                        // Clickable keywords
    case label                      // Field labels
    case caption                    // Descriptive text
    case divider
    case spacer
    case skeleton                   // Loading placeholders

    // ═══════════════════════════════════════════════════════════════════
    // MARK: - 2. Multimodal Input (18 Elements)
    // ═══════════════════════════════════════════════════════════════════

    case textInput = "text_input"
    case voiceInput = "voice_input"             // Tap-to-talk waveform
    case microphoneInput = "microphone_input"   // Real-time stream processing
    case audioRecorder = "audio_recorder"       // Record voice notes
    case cameraCapture = "camera_capture"       // Photo/document scan
    case documentUpload = "document_upload"     // PDF, DOCX, etc.
    case fileDropZone = "file_drop_zone"        // Drag-and-drop area
    case screenCapture = "screen_capture"       // Screenshot/recording
    case handwritingInput = "handwriting_input" // Digital ink canvas
    case drawingCanvas = "drawing_canvas"       // Freeform sketching
    case mathInput = "math_input"               // Specialized math keyboard
    case codeEditor = "code_editor"             // Interactive code writing
    case barcodeScanner = "barcode_scanner"     // ISBN/QR scanner
    case ocrCorrection = "ocr_correction"       // Correct scanned text
    case locationInput = "location_input"       // Tag study locations
    case dateTimeInput = "date_time_input"      // Combined date/time picker
    case signaturePad = "signature_pad"         // Digital signatures
    case emojiPicker = "emoji_picker"           // Reaction input

    // ═══════════════════════════════════════════════════════════════════
    // MARK: - 3. Rich Media & Visualization (15 Elements)
    // ═══════════════════════════════════════════════════════════════════

    case image
    case video
    case audio
    case animation
    case lottie
    case gif
    case diagram                    // AI flowcharts (Mermaid/PlantUML)
    case chart                      // Bar, line, or pie charts
    case graph                      // Math function plotting (2D/3D)
    case model3D = "model_3d"       // Interactive 3D models
    case handwritingPreview = "handwriting_preview"  // Rendering ink data
    case qrCode = "qr_code"         // Generated codes for sharing
    case pdfViewer = "pdf_viewer"   // Native PDF rendering
    case imageCarousel = "image_carousel"
    case videoTranscript = "video_transcript" // Interactive synced transcript

    // ═══════════════════════════════════════════════════════════════════
    // MARK: - 4. Quiz & Assessment (22 Elements)
    // ═══════════════════════════════════════════════════════════════════

    case quizMcq = "quiz_mcq"                   // Multiple choice (single)
    case quizMultiSelect = "quiz_multi_select"  // Multiple choice (many)
    case quizTrueFalse = "quiz_true_false"
    case quizFillBlank = "quiz_fill_blank"
    case quizMatching = "quiz_matching"
    case quizDragDrop = "quiz_drag_drop"
    case quizOrdering = "quiz_ordering"         // Arrange in sequence
    case quizShortAnswer = "quiz_short_answer"
    case quizEssay = "quiz_essay"
    case quizMath = "quiz_math"                 // Step-by-step verification
    case quizCode = "quiz_code"                 // Unit-test based challenges
    case quizDrawing = "quiz_drawing"           // Draw the answer
    case quizAudio = "quiz_audio"               // Listen and answer
    case quizSpeaking = "quiz_speaking"         // Pronunciation check
    case quizTiming = "quiz_timing"             // Countdown timer
    case quizAdaptive = "quiz_adaptive"         // Difficulty indicator
    case flashcard
    case flashcardDeck = "flashcard_deck"
    case practiceSet = "practice_set"           // Group of exercises
    case examMode = "exam_mode"                 // Secure testing environment
    case rubric                                 // Grading criteria
    case confidenceMeter = "confidence_meter"   // "How sure are you?"

    // ═══════════════════════════════════════════════════════════════════
    // MARK: - 5. Study Planning & Organization (15 Elements)
    // ═══════════════════════════════════════════════════════════════════

    case studyPlanOverview = "study_plan_overview"      // Macro view
    case studyPlanWeek = "study_plan_week"              // Weekly grid
    case studyPlanDay = "study_plan_day"                // Daily timeline
    case studySession = "study_session"                 // Active focus block
    case examCountdown = "exam_countdown"               // Dynamic countdown
    case goalTracker = "goal_tracker"                   // Progress bar
    case milestoneTimeline = "milestone_timeline"       // Linear path view
    case scheduleImport = "schedule_import"             // External calendar sync
    case calendarEvent = "calendar_event"               // Specific event card
    case reminderSetup = "reminder_setup"               // Notification config
    case timeBlocking = "time_blocking"                 // Drag-and-drop allocator
    case habitTracker = "habit_tracker"                 // Streak/completion grid
    case pomodoroTimer = "pomodoro_timer"               // Focus/Break timer
    case taskList = "task_list"                         // To-do items
    case priorityMatrix = "priority_matrix"             // Eisenhower matrix

    // ═══════════════════════════════════════════════════════════════════
    // MARK: - 6. Mistake Tracking & Remediation (12 Elements)
    // ═══════════════════════════════════════════════════════════════════

    case mistakeCard = "mistake_card"                   // Error details
    case mistakePattern = "mistake_pattern"             // Pattern analysis
    case weakAreaChart = "weak_area_chart"              // Knowledge gap radar
    case remediation = "remediation"                    // AI-suggested fix
    case conceptMastery = "concept_mastery"             // Level progress bar
    case errorHistory = "error_history"                 // Past mistakes log
    case targetedPractice = "targeted_practice"         // Start focused practice
    case masteryPath = "mastery_path"                   // Red -> Green path
    case skillGap = "skill_gap"                         // Comparison vs required
    case improvementPlan = "improvement_plan"           // Step-by-step recovery
    case confidenceHistory = "confidence_history"       // Trend line
    case misconceptionAlert = "misconception_alert"     // "You confuse A with B"

    // ═══════════════════════════════════════════════════════════════════
    // MARK: - 7. Homework & Assignment Management (15 Elements)
    // ═══════════════════════════════════════════════════════════════════

    case homeworkCard = "homework_card"                 // Summary card
    case homeworkHelper = "homework_helper"             // Specific chat UI
    case assignmentList = "assignment_list"             // Filterable list
    case dueDateBadge = "due_date_badge"                // Color-coded label
    case submissionStatus = "submission_status"         // Sent/Graded status
    case problemBreakdown = "problem_breakdown"         // AI decomposition
    case solutionSteps = "solution_steps"               // Step-by-step guide
    case hintReveal = "hint_reveal"                     // Progressive hints
    case workChecker = "work_checker"                   // AI verification
    case citationHelper = "citation_helper"             // Bibliography formatter
    case plagiarismChecker = "plagiarism_checker"       // Score indicator
    case gradePredictor = "grade_predictor"             // AI estimation
    case rubricViewer = "rubric_viewer"                 // Interactive grading
    case peerReview = "peer_review"                     // Review interface
    case submissionPortal = "submission_portal"         // Final file upload

    // ═══════════════════════════════════════════════════════════════════
    // MARK: - 8. Interactive Widgets & Controls (15 Elements)
    // ═══════════════════════════════════════════════════════════════════

    case actionButton = "action_button"
    case suggestions                                    // Quick reply chips
    case selectionChips = "selection_chips"             // Filter tags
    case ratingInput = "rating_input"                   // Star/numeric rating
    case slider
    case toggle
    case picker
    case segmentedControl = "segmented_control"         // Tab-like switch
    case colorPicker = "color_picker"                   // Select colors
    case stepper                                        // +/- input
    case searchBar = "search_bar"                       // Search with clear
    case filterChips = "filter_chips"                   // Active filters
    case sortSelector = "sort_selector"                 // Order control
    case pagination
    case loadMoreButton = "load_more_button"

    // ═══════════════════════════════════════════════════════════════════
    // MARK: - 9. Document AI & Note Processing (10 Elements)
    // ═══════════════════════════════════════════════════════════════════

    case notesSummary = "notes_summary"                 // Bulleted summary
    case keyPointsList = "key_points_list"              // Core concepts
    case conceptMap = "concept_map"                     // Node-link diagram
    case vocabularyList = "vocabulary_list"             // Terms & definitions
    case formulaSheet = "formula_sheet"                 // Compiled formulas
    case documentPreview = "document_preview"           // Full/thumbnail view
    case annotatedDocument = "annotated_document"       // AI overlays
    case compareDocuments = "compare_documents"         // Split view
    case smartHighlights = "smart_highlights"           // Auto-highlighting
    case documentOutline = "document_outline"           // Nav tree

    // ═══════════════════════════════════════════════════════════════════
    // MARK: - 10. Gamification & Feedback (13 Elements)
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
    case encouragement                                  // Motivational text
    case motivationalQuote = "motivational_quote"       // Inspire card
    case rewardUnlock = "reward_unlock"                 // Mystery box
    case socialShare = "social_share"                   // For Instagram/Socials

    // ═══════════════════════════════════════════════════════════════════
    // MARK: - 11. AI Assistant & Proactive Features (10 Elements)
    // ═══════════════════════════════════════════════════════════════════

    case aiThinking = "ai_thinking"                     // Processing indicator
    case aiSuggestion = "ai_suggestion"                 // Recommendation card
    case contextReminder = "context_reminder"           // Proactive nudge
    case checkIn = "check_in"                           // Mood/status check
    case dailyBrief = "daily_brief"                     // Morning summary
    case weeklyReview = "weekly_review"                 // Performance stats
    case smartNudge = "smart_nudge"                     // "Get back on track"
    case focusMode = "focus_mode"                       // Minimalist UI
    case breakReminder = "break_reminder"               // "Take a walk"
    case conversationStarter = "conversation_starter"   // Suggested questions

    // ═══════════════════════════════════════════════════════════════════
    // MARK: - Advanced AI Learning Elements (Added for completeness)
    // ═══════════════════════════════════════════════════════════════════

    case aiPersonalitySelector = "ai_personality_selector"
    case voiceConversation = "voice_conversation"
    case augmentedRealityViewer = "ar_viewer"
    case socialGroupCard = "social_group_card"
    case resourceLibraryFolder = "resource_folder"
    case knowledgeGraph = "knowledge_graph"
    case cognitiveLoadIndicator = "cognitive_load"

    /// Get element category for organization
    var category: A2UIElementCategory {
        switch self {
        case .text, .heading, .markdown, .codeBlock, .latex, .highlight, .quote, .callout, .badge, .tag, .label, .caption, .divider, .spacer, .skeleton:
            return .content
        case .image, .video, .audio, .animation, .lottie, .gif, .diagram, .chart, .graph, .model3D, .handwritingPreview, .qrCode, .pdfViewer, .imageCarousel, .videoTranscript, .augmentedRealityViewer:
            return .media
        case .textInput, .voiceInput, .microphoneInput, .audioRecorder, .cameraCapture, .documentUpload, .fileDropZone, .screenCapture, .handwritingInput, .drawingCanvas, .mathInput, .codeEditor, .barcodeScanner, .ocrCorrection, .locationInput, .dateTimeInput, .signaturePad, .emojiPicker, .voiceConversation:
            return .multimodalInput
        case .quizMcq, .quizMultiSelect, .quizTrueFalse, .quizFillBlank, .quizMatching, .quizDragDrop, .quizOrdering, .quizShortAnswer, .quizEssay, .quizMath, .quizCode, .quizDrawing, .quizAudio, .quizSpeaking, .quizTiming, .quizAdaptive, .flashcard, .flashcardDeck, .practiceSet, .examMode, .rubric, .confidenceMeter:
            return .assessment
        case .studyPlanOverview, .studyPlanWeek, .studyPlanDay, .studySession, .examCountdown, .goalTracker, .milestoneTimeline, .scheduleImport, .calendarEvent, .reminderSetup, .timeBlocking, .habitTracker, .pomodoroTimer, .taskList, .priorityMatrix:
            return .studyPlanning
        case .mistakeCard, .mistakePattern, .weakAreaChart, .remediation, .conceptMastery, .errorHistory, .targetedPractice, .masteryPath, .skillGap, .improvementPlan, .confidenceHistory, .misconceptionAlert:
            return .mistakeTracking
        case .homeworkCard, .homeworkHelper, .assignmentList, .dueDateBadge, .submissionStatus, .problemBreakdown, .solutionSteps, .hintReveal, .workChecker, .citationHelper, .plagiarismChecker, .gradePredictor, .rubricViewer, .peerReview, .submissionPortal:
            return .homework
        case .actionButton, .suggestions, .selectionChips, .ratingInput, .slider, .toggle, .picker, .segmentedControl, .colorPicker, .stepper, .searchBar, .filterChips, .sortSelector, .pagination, .loadMoreButton:
            return .widgets
        case .notesSummary, .keyPointsList, .conceptMap, .vocabularyList, .formulaSheet, .documentPreview, .annotatedDocument, .compareDocuments, .smartHighlights, .documentOutline, .knowledgeGraph:
            return .documentProcessing
        case .progressBar, .progressRing, .xpGain, .streakIndicator, .achievement, .confetti, .levelUp, .leaderboardEntry, .dailyChallenge, .encouragement, .motivationalQuote, .rewardUnlock, .socialShare, .socialGroupCard:
            return .gamification
        case .aiThinking, .aiSuggestion, .contextReminder, .checkIn, .dailyBrief, .weeklyReview, .smartNudge, .focusMode, .breakReminder, .conversationStarter, .aiPersonalitySelector, .cognitiveLoadIndicator:
            return .aiAssistant
        }
    }
}

enum A2UIElementCategory: String, Codable {
    case content
    case media
    case multimodalInput = "multimodal_input"
    case assessment
    case studyPlanning = "study_planning"
    case mistakeTracking = "mistake_tracking"
    case homework
    case widgets
    case documentProcessing = "document_processing"
    case gamification
    case aiAssistant = "ai_assistant"
}

/// Element support matrix for developers
struct A2UIElementSupport {
    static let implemented: Set<A2UIElementType> = [
        .text, .heading, .markdown, .codeBlock, .image, .video, .audio, .divider, .spacer,
        .textInput, .actionButton, .suggestions, .progressBar, .quizMcq
    ]
    
    static let pending: Set<A2UIElementType> = {
        Set(A2UIElementType.allCases).subtracting(implemented)
    }()
}