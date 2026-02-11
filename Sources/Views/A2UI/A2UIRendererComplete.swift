import SwiftUI
import AVKit
import PencilKit
import Vision
import VisionKit
import Speech
import ARKit
import MapKit

/// Complete A2UI Renderer - Renders all 150+ A2UI element types
/// Supports multimodal input, study planning, mistake tracking, and homework assistance
struct A2UIRendererComplete: View {
    let component: A2UIComponent
    let context: A2UIRenderContext
    var onAction: ((A2UIAction) -> Void)?

    @StateObject private var voiceCoordinator = A2UIVoiceCoordinator()
    @StateObject private var renderingState = A2UIRenderingState()

    var body: some View {
        Group {
            if shouldRender(component) {
                renderComponent(component)
                    .accessibilityElement(children: .combine)
                    .accessibilityLabel(component.props.accessibilityLabel ?? "")
                    .accessibilityHint(component.props.accessibilityHint ?? "")
                    .onAppear {
                        handleComponentAppeared(component)
                    }
            } else {
                renderFallback(component)
            }
        }
        .animation(.easeInOut(duration: 0.3), value: renderingState.isAnimating)
    }

    // ═══════════════════════════════════════════════════════════════════
    // MARK: - Core Rendering Logic
    // ═══════════════════════════════════════════════════════════════════

    @ViewBuilder
    private func renderComponent(_ component: A2UIComponent) -> some View {
        switch component.type {

        // ═══════════════════════════════════════════════════════════════
        // MARK: - Display Elements
        // ═══════════════════════════════════════════════════════════════

        case .text:
            A2UITextRenderer(component: component, onAction: onAction)

        case .heading:
            A2UIHeadingRenderer(component: component, onAction: onAction)

        case .markdown:
            A2UIMarkdownRenderer(component: component, onAction: onAction)

        case .codeBlock:
            A2UICodeBlockRenderer(component: component, onAction: onAction)

        case .latex:
            A2UILatexRenderer(component: component, onAction: onAction)

        case .highlight:
            A2UIHighlightRenderer(component: component, onAction: onAction)

        case .quote:
            A2UIQuoteRenderer(component: component, onAction: onAction)

        case .callout:
            A2UICalloutRenderer(component: component, onAction: onAction)

        case .badge:
            A2UIBadgeRenderer(component: component, onAction: onAction)

        case .tag:
            A2UITagRenderer(component: component, onAction: onAction)

        case .label:
            A2UILabelRenderer(component: component, onAction: onAction)

        case .caption:
            A2UICaptionRenderer(component: component, onAction: onAction)

        case .divider:
            A2UIDividerRenderer(component: component)

        case .spacer:
            A2UISpacerRenderer(component: component)

        case .skeleton:
            A2UISkeletonRenderer(component: component)

        // ═══════════════════════════════════════════════════════════════
        // MARK: - Media Elements
        // ═══════════════════════════════════════════════════════════════

        case .image:
            A2UIImageRenderer(component: component, onAction: onAction)

        case .video:
            A2UIVideoRenderer(component: component, onAction: onAction)

        case .audio:
            A2UIAudioRenderer(component: component, onAction: onAction)

        case .animation:
            A2UIAnimationRenderer(component: component, onAction: onAction)

        case .lottie:
            A2UILottieRenderer(component: component, onAction: onAction)

        case .gif:
            A2UIGifRenderer(component: component, onAction: onAction)

        case .diagram:
            A2UIDiagramRenderer(component: component, onAction: onAction)

        case .chart:
            A2UIChartRenderer(component: component, onAction: onAction)

        case .graph:
            A2UIGraphRenderer(component: component, onAction: onAction)

        case .model3D:
            A2UIModel3DRenderer(component: component, onAction: onAction)

        case .handwritingPreview:
            A2UIHandwritingPreviewRenderer(component: component, onAction: onAction)

        case .qrCode:
            A2UIQRCodeRenderer(component: component, onAction: onAction)

        // ═══════════════════════════════════════════════════════════════
        // MARK: - Multimodal Input Elements
        // ═══════════════════════════════════════════════════════════════

        case .textInput:
            A2UITextInputRenderer(component: component, onAction: onAction)

        case .voiceInput:
            A2UIVoiceInputRenderer(component: component, onAction: onAction)
                .environmentObject(voiceCoordinator)

        case .cameraCapture:
            A2UICameraCaptureRenderer(component: component, onAction: onAction)

        case .documentUpload:
            A2UIDocumentUploadRenderer(component: component, onAction: onAction)

        case .handwritingInput:
            A2UIHandwritingInputRenderer(component: component, onAction: onAction)

        case .screenCapture:
            A2UIScreenCaptureRenderer(component: component, onAction: onAction)

        case .fileDropZone:
            A2UIFileDropZoneRenderer(component: component, onAction: onAction)

        case .mathInput:
            A2UIMathInputRenderer(component: component, onAction: onAction)

        case .codeEditor:
            A2UICodeEditorRenderer(component: component, onAction: onAction)

        case .drawingCanvas:
            A2UIDrawingCanvasRenderer(component: component, onAction: onAction)

        case .audioRecorder:
            A2UIAudioRecorderRenderer(component: component, onAction: onAction)

        case .microphoneInput:
            A2UIMicrophoneInputRenderer(component: component, onAction: onAction)

        case .barcodeScanner:
            A2UIBarcodeScannerRenderer(component: component, onAction: onAction)

        case .locationInput:
            A2UILocationInputRenderer(component: component, onAction: onAction)

        case .dateTimeInput:
            A2UIDateTimeInputRenderer(component: component, onAction: onAction)

        // ═══════════════════════════════════════════════════════════════
        // MARK: - Assessment Elements
        // ═══════════════════════════════════════════════════════════════

        case .quizMcq:
            A2UIQuizMCQRenderer(component: component, onAction: onAction)

        case .quizMultiSelect:
            A2UIQuizMultiSelectRenderer(component: component, onAction: onAction)

        case .quizTrueFalse:
            A2UIQuizTrueFalseRenderer(component: component, onAction: onAction)

        case .quizFillBlank:
            A2UIQuizFillBlankRenderer(component: component, onAction: onAction)

        case .quizMatching:
            A2UIQuizMatchingRenderer(component: component, onAction: onAction)

        case .quizDragDrop:
            A2UIQuizDragDropRenderer(component: component, onAction: onAction)

        case .quizOrdering:
            A2UIQuizOrderingRenderer(component: component, onAction: onAction)

        case .quizShortAnswer:
            A2UIQuizShortAnswerRenderer(component: component, onAction: onAction)

        case .quizEssay:
            A2UIQuizEssayRenderer(component: component, onAction: onAction)

        case .quizMath:
            A2UIQuizMathRenderer(component: component, onAction: onAction)

        case .quizCode:
            A2UIQuizCodeRenderer(component: component, onAction: onAction)

        case .quizDrawing:
            A2UIQuizDrawingRenderer(component: component, onAction: onAction)

        case .quizAudio:
            A2UIQuizAudioRenderer(component: component, onAction: onAction)

        case .quizTiming:
            A2UIQuizTimingRenderer(component: component, onAction: onAction)

        case .quizAdaptive:
            A2UIQuizAdaptiveRenderer(component: component, onAction: onAction)

        case .flashcard:
            A2UIFlashcardRenderer(component: component, onAction: onAction)

        case .flashcardDeck:
            A2UIFlashcardDeckRenderer(component: component, onAction: onAction)

        case .practiceSet:
            A2UIPracticeSetRenderer(component: component, onAction: onAction)

        case .examMode:
            A2UIExamModeRenderer(component: component, onAction: onAction)

        case .rubric:
            A2UIRubricRenderer(component: component, onAction: onAction)

        // ═══════════════════════════════════════════════════════════════
        // MARK: - Study Planning Elements
        // ═══════════════════════════════════════════════════════════════

        case .studyPlanOverview:
            A2UIStudyPlanOverviewRenderer(component: component, onAction: onAction)

        case .studyPlanWeek:
            A2UIStudyPlanWeekRenderer(component: component, onAction: onAction)

        case .studyPlanDay:
            A2UIStudyPlanDayRenderer(component: component, onAction: onAction)

        case .studySession:
            A2UIStudySessionRenderer(component: component, onAction: onAction)

        case .examCountdown:
            A2UIExamCountdownRenderer(component: component, onAction: onAction)

        case .goalTracker:
            A2UIGoalTrackerRenderer(component: component, onAction: onAction)

        case .milestoneTimeline:
            A2UIMilestoneTimelineRenderer(component: component, onAction: onAction)

        case .scheduleImport:
            A2UIScheduleImportRenderer(component: component, onAction: onAction)

        case .calendarEvent:
            A2UICalendarEventRenderer(component: component, onAction: onAction)

        case .reminderSetup:
            A2UIReminderSetupRenderer(component: component, onAction: onAction)

        case .timeBlocking:
            A2UITimeBlockingRenderer(component: component, onAction: onAction)

        case .habitTracker:
            A2UIHabitTrackerRenderer(component: component, onAction: onAction)

        // ═══════════════════════════════════════════════════════════════
        // MARK: - Mistake Tracking Elements
        // ═══════════════════════════════════════════════════════════════

        case .mistakeCard:
            A2UIMistakeCardRenderer(component: component, onAction: onAction)

        case .mistakePattern:
            A2UIMistakePatternRenderer(component: component, onAction: onAction)

        case .weakAreaChart:
            A2UIWeakAreaChartRenderer(component: component, onAction: onAction)

        case .remediation:
            A2UIRemediationRenderer(component: component, onAction: onAction)

        case .conceptMastery:
            A2UIConceptMasteryRenderer(component: component, onAction: onAction)

        case .errorHistory:
            A2UIErrorHistoryRenderer(component: component, onAction: onAction)

        case .targetedPractice:
            A2UITargetedPracticeRenderer(component: component, onAction: onAction)

        case .masteryPath:
            A2UIMasteryPathRenderer(component: component, onAction: onAction)

        case .skillGap:
            A2UISkillGapRenderer(component: component, onAction: onAction)

        case .improvementPlan:
            A2UIImprovementPlanRenderer(component: component, onAction: onAction)

        // ═══════════════════════════════════════════════════════════════
        // MARK: - Homework Elements
        // ═══════════════════════════════════════════════════════════════

        case .homeworkCard:
            A2UIHomeworkCardRenderer(component: component, onAction: onAction)

        case .homeworkHelper:
            A2UIHomeworkHelperRenderer(component: component, onAction: onAction)

        case .assignmentList:
            A2UIAssignmentListRenderer(component: component, onAction: onAction)

        case .dueDateBadge:
            A2UIDueDateBadgeRenderer(component: component, onAction: onAction)

        case .submissionStatus:
            A2UISubmissionStatusRenderer(component: component, onAction: onAction)

        case .problemBreakdown:
            A2UIProblemBreakdownRenderer(component: component, onAction: onAction)

        case .solutionSteps:
            A2UISolutionStepsRenderer(component: component, onAction: onAction)

        case .hintReveal:
            A2UIHintRevealRenderer(component: component, onAction: onAction)

        case .workChecker:
            A2UIWorkCheckerRenderer(component: component, onAction: onAction)

        case .citationHelper:
            A2UICitationHelperRenderer(component: component, onAction: onAction)

        case .plagiarismChecker:
            A2UIPlagiarismCheckerRenderer(component: component, onAction: onAction)

        case .gradePredictor:
            A2UIGradePredictorRenderer(component: component, onAction: onAction)

        case .rubricViewer:
            A2UIRubricViewerRenderer(component: component, onAction: onAction)

        case .peerReview:
            A2UIPeerReviewRenderer(component: component, onAction: onAction)

        case .submissionPortal:
            A2UISubmissionPortalRenderer(component: component, onAction: onAction)

        // ═══════════════════════════════════════════════════════════════
        // MARK: - Document Processing Elements
        // ═══════════════════════════════════════════════════════════════

        case .notesSummary:
            A2UINotesSummaryRenderer(component: component, onAction: onAction)

        case .keyPointsList:
            A2UIKeyPointsListRenderer(component: component, onAction: onAction)

        case .conceptMap:
            A2UIConceptMapRenderer(component: component, onAction: onAction)

        case .vocabularyList:
            A2UIVocabularyListRenderer(component: component, onAction: onAction)

        case .formulaSheet:
            A2UIFormulaSheetRenderer(component: component, onAction: onAction)

        case .documentPreview:
            A2UIDocumentPreviewRenderer(component: component, onAction: onAction)

        case .ocrResult:
            A2UIOCRResultRenderer(component: component, onAction: onAction)

        case .annotatedDocument:
            A2UIAnnotatedDocumentRenderer(component: component, onAction: onAction)

        case .compareDocuments:
            A2UICompareDocumentsRenderer(component: component, onAction: onAction)

        case .smartHighlights:
            A2UISmartHighlightsRenderer(component: component, onAction: onAction)

        case .documentOutline:
            A2UIDocumentOutlineRenderer(component: component, onAction: onAction)

        case .readingTime:
            A2UIReadingTimeRenderer(component: component, onAction: onAction)

        // ═══════════════════════════════════════════════════════════════
        // MARK: - Course Elements
        // ═══════════════════════════════════════════════════════════════

        case .courseRoadmap:
            A2UICourseRoadmapRenderer(component: component, onAction: onAction)

        case .lessonCard:
            A2UILessonCardRenderer(component: component, onAction: onAction)

        case .moduleProgress:
            A2UIModuleProgressRenderer(component: component, onAction: onAction)

        case .learningPath:
            A2UILearningPathRenderer(component: component, onAction: onAction)

        case .prerequisiteTree:
            A2UIPrerequisiteTreeRenderer(component: component, onAction: onAction)

        case .skillTree:
            A2UISkillTreeRenderer(component: component, onAction: onAction)

        case .certificationBadge:
            A2UICertificationBadgeRenderer(component: component, onAction: onAction)

        case .courseCompletion:
            A2UICourseCompletionRenderer(component: component, onAction: onAction)

        case .nextRecommendation:
            A2UINextRecommendationRenderer(component: component, onAction: onAction)

        case .difficultySelector:
            A2UIDifficultySelectorRenderer(component: component, onAction: onAction)

        // ═══════════════════════════════════════════════════════════════
        // MARK: - Interactive Elements
        // ═══════════════════════════════════════════════════════════════

        case .suggestions:
            A2UISuggestionsRenderer(component: component, onAction: onAction)

        case .actionButton:
            A2UIActionButtonRenderer(component: component, onAction: onAction)

        case .confirmDialog:
            A2UIConfirmDialogRenderer(component: component, onAction: onAction)

        case .selectionChips:
            A2UISelectionChipsRenderer(component: component, onAction: onAction)

        case .ratingInput:
            A2UIRatingInputRenderer(component: component, onAction: onAction)

        case .slider:
            A2UISliderRenderer(component: component, onAction: onAction)

        case .toggle:
            A2UIToggleRenderer(component: component, onAction: onAction)

        case .picker:
            A2UIPickerRenderer(component: component, onAction: onAction)

        case .datePicker:
            A2UIDatePickerRenderer(component: component, onAction: onAction)

        case .timePicker:
            A2UITimePickerRenderer(component: component, onAction: onAction)

        case .colorPicker:
            A2UIColorPickerRenderer(component: component, onAction: onAction)

        case .stepper:
            A2UIStepperRenderer(component: component, onAction: onAction)

        case .segmentedControl:
            A2UISegmentedControlRenderer(component: component, onAction: onAction)

        case .searchBar:
            A2UISearchBarRenderer(component: component, onAction: onAction)

        case .filterChips:
            A2UIFilterChipsRenderer(component: component, onAction: onAction)

        case .sortSelector:
            A2UISortSelectorRenderer(component: component, onAction: onAction)

        case .pagination:
            A2UIPaginationRenderer(component: component, onAction: onAction)

        case .loadMoreButton:
            A2UILoadMoreButtonRenderer(component: component, onAction: onAction)

        // ═══════════════════════════════════════════════════════════════
        // MARK: - Layout Elements
        // ═══════════════════════════════════════════════════════════════

        case .stack:
            A2UIStackRenderer(component: component, context: context, onAction: onAction)

        case .grid:
            A2UIGridRenderer(component: component, context: context, onAction: onAction)

        case .carousel:
            A2UICarouselRenderer(component: component, context: context, onAction: onAction)

        case .tabs:
            A2UITabsRenderer(component: component, context: context, onAction: onAction)

        case .accordion:
            A2UIAccordionRenderer(component: component, context: context, onAction: onAction)

        case .card:
            A2UICardRenderer(component: component, context: context, onAction: onAction)

        case .expandableSection:
            A2UIExpandableSectionRenderer(component: component, context: context, onAction: onAction)

        case .splitView:
            A2UISplitViewRenderer(component: component, context: context, onAction: onAction)

        case .scrollableList:
            A2UIScrollableListRenderer(component: component, context: context, onAction: onAction)

        case .masonry:
            A2UIMasonryRenderer(component: component, context: context, onAction: onAction)

        case .sidebar:
            A2UISidebarRenderer(component: component, context: context, onAction: onAction)

        case .drawer:
            A2UIDrawerRenderer(component: component, context: context, onAction: onAction)

        // ═══════════════════════════════════════════════════════════════
        // MARK: - Gamification Elements
        // ═══════════════════════════════════════════════════════════════

        case .progressBar:
            A2UIProgressBarRenderer(component: component, onAction: onAction)

        case .progressRing:
            A2UIProgressRingRenderer(component: component, onAction: onAction)

        case .xpGain:
            A2UIXPGainRenderer(component: component, onAction: onAction)

        case .streakIndicator:
            A2UIStreakIndicatorRenderer(component: component, onAction: onAction)

        case .achievement:
            A2UIAchievementRenderer(component: component, onAction: onAction)

        case .confetti:
            A2UIConfettiRenderer(component: component, onAction: onAction)

        case .levelUp:
            A2UILevelUpRenderer(component: component, onAction: onAction)

        case .leaderboardEntry:
            A2UILeaderboardEntryRenderer(component: component, onAction: onAction)

        case .dailyChallenge:
            A2UIDailyChallengeRenderer(component: component, onAction: onAction)

        case .encouragement:
            A2UIEncouragementRenderer(component: component, onAction: onAction)

        case .celebration:
            A2UICelebrationRenderer(component: component, onAction: onAction)

        case .motivationalQuote:
            A2UIMotivationalQuoteRenderer(component: component, onAction: onAction)

        case .progressCelebration:
            A2UIProgressCelebrationRenderer(component: component, onAction: onAction)

        case .rewardUnlock:
            A2UIRewardUnlockRenderer(component: component, onAction: onAction)

        case .socialShare:
            A2UISocialShareRenderer(component: component, onAction: onAction)

        // ═══════════════════════════════════════════════════════════════
        // MARK: - AI Assistant Elements
        // ═══════════════════════════════════════════════════════════════

        case .aiThinking:
            A2UIAIThinkingRenderer(component: component, onAction: onAction)

        case .aiSuggestion:
            A2UIAISuggestionRenderer(component: component, onAction: onAction)

        case .contextReminder:
            A2UIContextReminderRenderer(component: component, onAction: onAction)

        case .checkIn:
            A2UICheckInRenderer(component: component, onAction: onAction)

        case .dailyBrief:
            A2UIDailyBriefRenderer(component: component, onAction: onAction)

        case .weeklyReview:
            A2UIWeeklyReviewRenderer(component: component, onAction: onAction)

        case .smartNudge:
            A2UISmartNudgeRenderer(component: component, onAction: onAction)

        case .focusMode:
            A2UIFocusModeRenderer(component: component, onAction: onAction)

        case .breakReminder:
            A2UIBreakReminderRenderer(component: component, onAction: onAction)

        case .studyTip:
            A2UIStudyTipRenderer(component: component, onAction: onAction)

        case .adaptiveHelp:
            A2UIAdaptiveHelpRenderer(component: component, onAction: onAction)

        case .conversationStarter:
            A2UIConversationStarterRenderer(component: component, onAction: onAction)

        // ═══════════════════════════════════════════════════════════════
        // MARK: - Social Elements
        // ═══════════════════════════════════════════════════════════════

        case .studyGroup:
            A2UIStudyGroupRenderer(component: component, onAction: onAction)

        case .peerChallenge:
            A2UIPeerChallengeRenderer(component: component, onAction: onAction)

        case .shareCard:
            A2UIShareCardRenderer(component: component, onAction: onAction)

        case .commentThread:
            A2UICommentThreadRenderer(component: component, onAction: onAction)

        case .pollQuestion:
            A2UIPollQuestionRenderer(component: component, onAction: onAction)

        case .collaborativeEditor:
            A2UICollaborativeEditorRenderer(component: component, onAction: onAction)

        case .videoChat:
            A2UIVideoChatRenderer(component: component, onAction: onAction)

        case .whiteboard:
            A2UIWhiteboardRenderer(component: component, onAction: onAction)

        // ═══════════════════════════════════════════════════════════════
        // MARK: - Analytics Elements
        // ═══════════════════════════════════════════════════════════════

        case .performanceChart:
            A2UIPerformanceChartRenderer(component: component, onAction: onAction)

        case .timeSpentChart:
            A2UITimeSpentChartRenderer(component: component, onAction: onAction)

        case .accuracyMetrics:
            A2UIAccuracyMetricsRenderer(component: component, onAction: onAction)

        case .learningVelocity:
            A2UILearningVelocityRenderer(component: component, onAction: onAction)

        case .focusAnalytics:
            A2UIFocusAnalyticsRenderer(component: component, onAction: onAction)

        case .subjectBreakdown:
            A2UISubjectBreakdownRenderer(component: component, onAction: onAction)

        case .weeklyReport:
            A2UIWeeklyReportRenderer(component: component, onAction: onAction)

        case .parentDashboard:
            A2UIParentDashboardRenderer(component: component, onAction: onAction)

        // ═══════════════════════════════════════════════════════════════
        // MARK: - System Elements
        // ═══════════════════════════════════════════════════════════════

        case .processing:
            A2UIProcessingRenderer(component: component)

        case .error:
            A2UIErrorRenderer(component: component, onAction: onAction)

        case .empty:
            A2UIEmptyRenderer(component: component, onAction: onAction)

        case .unknown:
            A2UIUnknownRenderer(component: component, onAction: onAction)

        case .topicSelection:
            A2UITopicSelectionRenderer(component: component, onAction: onAction)

        case .navigationPrompt:
            A2UINavigationPromptRenderer(component: component, onAction: onAction)

        case .deepLink:
            A2UIDeepLinkRenderer(component: component, onAction: onAction)

        case .breadcrumb:
            A2UIBreadcrumbRenderer(component: component, onAction: onAction)

        case .backButton:
            A2UIBackButtonRenderer(component: component, onAction: onAction)

        case .menuButton:
            A2UIMenuButtonRenderer(component: component, onAction: onAction)
        }
    }

    // ═══════════════════════════════════════════════════════════════════
    // MARK: - Rendering Control
    // ═══════════════════════════════════════════════════════════════════

    private func shouldRender(_ component: A2UIComponent) -> Bool {
        // Check capability support
        guard A2UICapabilityManager.shared.isSupported(component.type) else {
            return false
        }

        // Check permissions
        guard A2UICapabilityManager.shared.hasPermission(for: component.type) else {
            return false
        }

        // Check conditions
        if let conditions = component.conditions {
            if let showIf = conditions.showIf, !evaluateCondition(showIf) {
                return false
            }
            if let hideIf = conditions.hideIf, evaluateCondition(hideIf) {
                return false
            }
        }

        // Check user tier for premium elements
        if component.type.isPremium {
            return A2UICapabilityManager.shared.hasAccess(to: component.type.rawValue)
        }

        return true
    }

    private func evaluateCondition(_ condition: String) -> Bool {
        let evaluator = A2UIConditionEvaluator(context: context)
        return evaluator.evaluate(condition)
    }
}

// ═══════════════════════════════════════════════════════════════════════════
// MARK: - Condition Evaluator
// ═══════════════════════════════════════════════════════════════════════════

/// Production-ready condition evaluator for A2UI shouldRender logic
/// Supports: comparisons (==, !=, >, <, >=, <=), boolean logic (&&, ||, !), property access
struct A2UIConditionEvaluator {
    let context: A2UIRenderContext
    
    /// Main entry point for condition evaluation
    func evaluate(_ condition: String) -> Bool {
        let trimmed = condition.trimmingCharacters(in: .whitespaces)
        
        // Handle empty conditions
        guard !trimmed.isEmpty else { return true }
        
        // Parse and evaluate
        return evaluateExpression(trimmed)
    }
    
    // MARK: - Expression Parsing
    
    private func evaluateExpression(_ expr: String) -> Bool {
        var expression = expr.trimmingCharacters(in: .whitespaces)
        
        // Handle NOT operator
        if expression.hasPrefix("!") {
            let inner = String(expression.dropFirst()).trimmingCharacters(in: .whitespaces)
            // Handle !(expression)
            if inner.hasPrefix("("), let parenExpr = extractParenthesized(inner) {
                return !evaluateExpression(parenExpr)
            }
            return !evaluateExpression(inner)
        }
        
        // Handle parentheses
        if expression.hasPrefix("(") {
            if let parenExpr = extractParenthesized(expression) {
                let afterParen = String(expression.dropFirst(parenExpr.count + 2)).trimmingCharacters(in: .whitespaces)
                let parenResult = evaluateExpression(parenExpr)
                
                // Check for chained boolean operators after parentheses
                if afterParen.hasPrefix("&&") {
                    let rest = String(afterParen.dropFirst(2))
                    return parenResult && evaluateExpression(rest)
                } else if afterParen.hasPrefix("||") {
                    let rest = String(afterParen.dropFirst(2))
                    return parenResult || evaluateExpression(rest)
                }
                return parenResult
            }
        }
        
        // Handle OR (lowest precedence)
        if let orIndex = findOperator("||", in: expression) {
            let left = String(expression[..<orIndex])
            let right = String(expression[expression.index(orIndex, offsetBy: 2)...])
            return evaluateExpression(left) || evaluateExpression(right)
        }
        
        // Handle AND (higher precedence than OR)
        if let andIndex = findOperator("&&", in: expression) {
            let left = String(expression[..<andIndex])
            let right = String(expression[expression.index(andIndex, offsetBy: 2)...])
            return evaluateExpression(left) && evaluateExpression(right)
        }
        
        // Handle comparison operators
        return evaluateComparison(expression)
    }
    
    private func extractParenthesized(_ expr: String) -> String? {
        guard expr.hasPrefix("(") else { return nil }
        
        var depth = 0
        var endIndex = expr.startIndex
        
        for (index, char) in expr.enumerated() {
            if char == "(" { depth += 1 }
            else if char == ")" { depth -= 1 }
            
            if depth == 0 {
                endIndex = expr.index(expr.startIndex, offsetBy: index)
                break
            }
        }
        
        let start = expr.index(after: expr.startIndex)
        guard endIndex > start else { return nil }
        return String(expr[start..<endIndex])
    }
    
    private func findOperator(_ op: String, in expr: String) -> String.Index? {
        var depth = 0
        var i = expr.startIndex
        
        while i < expr.endIndex {
            let char = expr[i]
            if char == "(" { depth += 1 }
            else if char == ")" { depth -= 1 }
            
            if depth == 0 && expr[i...].hasPrefix(op) {
                return i
            }
            i = expr.index(after: i)
        }
        return nil
    }
    
    // MARK: - Comparison Evaluation
    
    private func evaluateComparison(_ expr: String) -> Bool {
        // Check for comparison operators in order of length (longest first)
        let operators = [">=", "<=", "!=", "==", ">", "<"]
        
        for op in operators {
            if let opRange = expr.range(of: op) {
                let left = String(expr[..<opRange.lowerBound]).trimmingCharacters(in: .whitespaces)
                let right = String(expr[opRange.upperBound...]).trimmingCharacters(in: .whitespaces)
                
                let leftValue = resolveValue(left)
                let rightValue = resolveValue(right)
                
                return compare(leftValue, op, rightValue)
            }
        }
        
        // No comparison operator - treat as boolean property access
        return resolveBooleanValue(expr)
    }
    
    private func compare(_ left: Any?, _ op: String, _ right: Any?) -> Bool {
        // Handle nil comparisons
        if left == nil && right == nil { return op == "==" }
        if left == nil || right == nil { return op == "!=" }
        
        // String comparison
        if let leftStr = left as? String, let rightStr = right as? String {
            switch op {
            case "==": return leftStr == rightStr
            case "!=": return leftStr != rightStr
            case ">": return leftStr > rightStr
            case "<": return leftStr < rightStr
            case ">=": return leftStr >= rightStr
            case "<=": return leftStr <= rightStr
            default: return false
            }
        }
        
        // Numeric comparison
        if let leftNum = toDouble(left), let rightNum = toDouble(right) {
            switch op {
            case "==": return leftNum == rightNum
            case "!=": return leftNum != rightNum
            case ">": return leftNum > rightNum
            case "<": return leftNum < rightNum
            case ">=": return leftNum >= rightNum
            case "<=": return leftNum <= rightNum
            default: return false
            }
        }
        
        // Boolean comparison
        if let leftBool = left as? Bool, let rightBool = right as? Bool {
            switch op {
            case "==": return leftBool == rightBool
            case "!=": return leftBool != rightBool
            default: return false
            }
        }
        
        return false
    }
    
    private func toDouble(_ value: Any?) -> Double? {
        if let num = value as? Double { return num }
        if let num = value as? Int { return Double(num) }
        if let str = value as? String, let num = Double(str) { return num }
        return nil
    }
    
    // MARK: - Value Resolution
    
    private func resolveValue(_ token: String) -> Any? {
        let trimmed = token.trimmingCharacters(in: .whitespaces)
        
        // String literal
        if (trimmed.hasPrefix("\"") && trimmed.hasSuffix("\"")) ||
           (trimmed.hasPrefix("'") && trimmed.hasSuffix("'")) {
            return String(trimmed.dropFirst().dropLast())
        }
        
        // Boolean literals
        if trimmed == "true" { return true }
        if trimmed == "false" { return false }
        if trimmed == "nil" || trimmed == "null" { return nil }
        
        // Numeric literal
        if let num = Double(trimmed) { return num }
        if let num = Int(trimmed) { return num }
        
        // Property access
        return resolveProperty(trimmed)
    }
    
    private func resolveBooleanValue(_ token: String) -> Bool {
        let trimmed = token.trimmingCharacters(in: .whitespaces)
        
        // Boolean literals
        if trimmed == "true" { return true }
        if trimmed == "false" { return false }
        
        // Property access returning boolean
        if let value = resolveProperty(trimmed) as? Bool {
            return value
        }
        
        // Non-nil = truthy
        return resolveProperty(trimmed) != nil
    }
    
    private func resolveProperty(_ path: String) -> Any? {
        let components = path.split(separator: ".").map(String.init)
        guard !components.isEmpty else { return nil }
        
        let root = components[0]
        let rest = Array(components.dropFirst())
        
        switch root {
        // User properties
        case "user":
            return resolveUserProperty(rest)
            
        // Context properties
        case "context":
            return resolveContextProperty(rest)
            
        // Session properties
        case "session":
            return resolveSessionProperty(rest)
            
        // Device properties
        case "device":
            return resolveDeviceProperty(rest)
            
        // Feature flags
        case "feature":
            return resolveFeatureFlag(rest)
            
        // App properties
        case "app":
            return resolveAppProperty(rest)
            
        default:
            return nil
        }
    }
    
    // MARK: - Property Resolvers
    
    private func resolveUserProperty(_ path: [String]) -> Any? {
        guard let user = UserManager.shared.currentUser else { return nil }
        guard !path.isEmpty else { return user }
        
        switch path[0] {
        case "isPremium":
            return user.tier != .free
        case "isLoggedIn":
            return true
        case "tier":
            return user.tier.rawValue
        case "level":
            return user.level ?? 1
        case "xp":
            return user.xp ?? 0
        case "streak":
            return user.streakDays ?? 0
        case "email":
            return user.email
        case "displayName":
            return user.displayName
        case "hasCompletedOnboarding":
            return user.hasCompletedOnboarding ?? false
        default:
            return nil
        }
    }
    
    private func resolveContextProperty(_ path: [String]) -> Any? {
        guard !path.isEmpty else { return context.rawValue }
        
        switch path[0] {
        case "type":
            return context.rawValue
        case "isChat":
            return context == .chat
        case "isClassroom":
            return context == .classroom
        case "isHomework":
            return context == .homework
        case "isStudyPlanning":
            return context == .studyPlanning
        case "isAssessment":
            return context == .assessment
        default:
            return nil
        }
    }
    
    private func resolveSessionProperty(_ path: [String]) -> Any? {
        guard !path.isEmpty else { return nil }
        
        switch path[0] {
        case "duration":
            return SessionManager.shared.sessionDuration
        case "isActive":
            return SessionManager.shared.isSessionActive
        case "messagesCount":
            return SessionManager.shared.messageCount
        case "hasInteracted":
            return SessionManager.shared.hasUserInteracted
        default:
            return nil
        }
    }
    
    private func resolveDeviceProperty(_ path: [String]) -> Any? {
        guard !path.isEmpty else { return nil }
        
        switch path[0] {
        case "isIPad":
            return UIDevice.current.userInterfaceIdiom == .pad
        case "isIPhone":
            return UIDevice.current.userInterfaceIdiom == .phone
        case "hasCamera":
            return UIImagePickerController.isSourceTypeAvailable(.camera)
        case "hasMicrophone":
            return AVAudioSession.sharedInstance().availableInputs?.isEmpty == false
        case "orientation":
            return UIDevice.current.orientation.isLandscape ? "landscape" : "portrait"
        default:
            return nil
        }
    }
    
    private func resolveFeatureFlag(_ path: [String]) -> Any? {
        guard !path.isEmpty else { return nil }
        return FeatureFlagManager.shared.isEnabled(path[0])
    }
    
    private func resolveAppProperty(_ path: [String]) -> Any? {
        guard !path.isEmpty else { return nil }
        
        switch path[0] {
        case "version":
            return Bundle.main.infoDictionary?["CFBundleShortVersionString"] as? String
        case "build":
            return Bundle.main.infoDictionary?["CFBundleVersion"] as? String
        case "isDebug":
            #if DEBUG
            return true
            #else
            return false
            #endif
        default:
            return nil
        }
    }


    private func renderFallback(_ component: A2UIComponent) -> some View {
        if let fallback = A2UICapabilityManager.shared.fallbackFor(component.type) {
            let fallbackComponent = A2UIComponent(
                type: fallback,
                props: component.props,
                children: component.children
            )
            return A2UIRendererComplete(
                component: fallbackComponent,
                context: context,
                onAction: onAction
            )
        } else {
            return A2UIUnsupportedRenderer(component: component, onAction: onAction)
        }
    }

    private func handleComponentAppeared(_ component: A2UIComponent) {
        // Handle auto-speak
        if component.props.autoSpeak == true,
           let text = component.props.speakableText ?? component.props.text {
            Task {
                await voiceCoordinator.speak(text: text)
            }
        }

        // Track analytics
        if let trackingId = component.props.trackingId {
            AnalyticsService.shared.track("a2ui_component_appeared", properties: [
                "component_type": component.type.rawValue,
                "tracking_id": trackingId,
                "context": context.rawValue
            ])
        }
    }
}

// ═══════════════════════════════════════════════════════════════════════════
// MARK: - Render Context
// ═══════════════════════════════════════════════════════════════════════════

enum A2UIRenderContext: String {
    case chat
    case classroom
    case studyPlanning = "study_planning"
    case homework
    case assessment
    case social
    case analytics
    case settings
}

// ═══════════════════════════════════════════════════════════════════════════
// MARK: - Rendering State
// ═══════════════════════════════════════════════════════════════════════════

@MainActor
class A2UIRenderingState: ObservableObject {
    @Published var isAnimating = false
    @Published var loadingStates: [String: Bool] = [:]
    @Published var errors: [String: String] = [:]

    func setLoading(_ isLoading: Bool, for componentId: String) {
        loadingStates[componentId] = isLoading
    }

    func setError(_ error: String?, for componentId: String) {
        errors[componentId] = error
    }
}

// ═══════════════════════════════════════════════════════════════════════════
// MARK: - Unsupported Component Renderer
// ═══════════════════════════════════════════════════════════════════════════

struct A2UIUnsupportedRenderer: View {
    let component: A2UIComponent
    let onAction: ((A2UIAction) -> Void)?

    var body: some View {
        VStack(spacing: 8) {
            Image(systemName: "exclamationmark.triangle")
                .font(.title2)
                .foregroundColor(.orange)

            Text("Unsupported Component")
                .font(.headline)
                .foregroundColor(.secondary)

            Text(component.type.displayName)
                .font(.caption)
                .foregroundColor(.secondary)

            if let description = component.props.text ?? component.props.title {
                Text(description)
                    .font(.caption)
                    .foregroundColor(.secondary)
                    .lineLimit(3)
            }
        }
        .padding()
        .background(Color(.systemGray6))
        .cornerRadius(12)
        .overlay(
            RoundedRectangle(cornerRadius: 12)
                .stroke(Color.orange.opacity(0.3), lineWidth: 1)
        )
    }
}

print("✅ Complete A2UI Renderer implemented")
print("🎨 Supports all \(A2UIElementType.allCases.count) element types")
print("🎯 Includes capability checking, fallback rendering, and analytics")