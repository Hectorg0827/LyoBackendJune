import Foundation
import os.log

// MARK: - A2UI Response Validator
struct A2UIResponseValidator {
    private let logger = Logger(subsystem: "com.lyo.a2ui", category: "validation")

    // MARK: - Component Validation

    func validateComponent(_ component: A2UIComponent) -> ValidationResult {
        var issues: [ValidationIssue] = []

        // Basic component validation
        issues.append(contentsOf: validateBasicComponent(component))

        // Recursive validation of children
        if let children = component.children {
            for (index, child) in children.enumerated() {
                let childResult = validateComponent(child)
                switch childResult {
                case .failure(let childIssues):
                    let prefixedIssues = childIssues.map { issue in
                        ValidationIssue(
                            severity: issue.severity,
                            type: issue.type,
                            message: "Child[\(index)]: \(issue.message)",
                            path: [component.id] + issue.path
                        )
                    }
                    issues.append(contentsOf: prefixedIssues)
                case .success:
                    break
                }
            }
        }

        // Component-specific validation
        issues.append(contentsOf: validateSpecificComponent(component))

        if issues.isEmpty {
            return .success
        } else {
            return .failure(issues)
        }
    }

    private func validateBasicComponent(_ component: A2UIComponent) -> [ValidationIssue] {
        var issues: [ValidationIssue] = []

        // Validate ID
        if component.id.isEmpty {
            issues.append(ValidationIssue(
                severity: .error,
                type: .missingRequiredField,
                message: "Component ID cannot be empty",
                path: [component.id]
            ))
        }

        // Validate type
        if component.type.isEmpty {
            issues.append(ValidationIssue(
                severity: .error,
                type: .missingRequiredField,
                message: "Component type cannot be empty",
                path: [component.id]
            ))
        }

        // Validate known component types
        if !isKnownComponentType(component.type) {
            issues.append(ValidationIssue(
                severity: .warning,
                type: .unknownComponentType,
                message: "Unknown component type: \(component.type)",
                path: [component.id]
            ))
        }

        // Validate props structure
        issues.append(contentsOf: validateProps(component.props, componentId: component.id))

        return issues
    }

    private func validateSpecificComponent(_ component: A2UIComponent) -> [ValidationIssue] {
        switch component.type.lowercased() {
        case "text":
            return validateTextComponent(component)
        case "button":
            return validateButtonComponent(component)
        case "image":
            return validateImageComponent(component)
        case "vstack", "hstack", "zstack":
            return validateStackComponent(component)
        case "coursecard":
            return validateCourseCardComponent(component)
        case "quiz":
            return validateQuizComponent(component)
        default:
            return [] // No specific validation for unknown types
        }
    }

    // MARK: - Specific Component Validators

    private func validateTextComponent(_ component: A2UIComponent) -> [ValidationIssue] {
        var issues: [ValidationIssue] = []

        // Text component must have text content
        let textContent = component.prop("text").asString ?? component.prop("content").asString
        if textContent?.isEmpty != false {
            issues.append(ValidationIssue(
                severity: .warning,
                type: .missingRequiredField,
                message: "Text component should have 'text' or 'content' property",
                path: [component.id]
            ))
        }

        // Validate font if present
        if let font = component.prop("font").asString {
            if !isValidFont(font) {
                issues.append(ValidationIssue(
                    severity: .warning,
                    type: .invalidValue,
                    message: "Unknown font style: \(font)",
                    path: [component.id]
                ))
            }
        }

        // Validate color format if present
        if let color = component.prop("color").asString {
            if !isValidColor(color) {
                issues.append(ValidationIssue(
                    severity: .warning,
                    type: .invalidValue,
                    message: "Invalid color format: \(color)",
                    path: [component.id]
                ))
            }
        }

        return issues
    }

    private func validateButtonComponent(_ component: A2UIComponent) -> [ValidationIssue] {
        var issues: [ValidationIssue] = []

        // Button must have title
        if component.prop("title").asString?.isEmpty != false {
            issues.append(ValidationIssue(
                severity: .error,
                type: .missingRequiredField,
                message: "Button component must have 'title' property",
                path: [component.id]
            ))
        }

        // Button should have action
        if component.prop("action").asString?.isEmpty != false {
            issues.append(ValidationIssue(
                severity: .warning,
                type: .missingRequiredField,
                message: "Button component should have 'action' property",
                path: [component.id]
            ))
        }

        return issues
    }

    private func validateImageComponent(_ component: A2UIComponent) -> [ValidationIssue] {
        var issues: [ValidationIssue] = []

        let hasUrl = component.prop("url").asString?.isEmpty == false
        let hasSystemName = component.prop("systemName").asString?.isEmpty == false

        if !hasUrl && !hasSystemName {
            issues.append(ValidationIssue(
                severity: .error,
                type: .missingRequiredField,
                message: "Image component must have either 'url' or 'systemName' property",
                path: [component.id]
            ))
        }

        // Validate URL format if present
        if let urlString = component.prop("url").asString,
           !urlString.isEmpty,
           URL(string: urlString) == nil {
            issues.append(ValidationIssue(
                severity: .error,
                type: .invalidValue,
                message: "Invalid URL format: \(urlString)",
                path: [component.id]
            ))
        }

        return issues
    }

    private func validateStackComponent(_ component: A2UIComponent) -> [ValidationIssue] {
        var issues: [ValidationIssue] = []

        // Validate spacing if present
        if let spacing = component.prop("spacing").asDouble {
            if spacing < 0 {
                issues.append(ValidationIssue(
                    severity: .warning,
                    type: .invalidValue,
                    message: "Spacing should not be negative: \(spacing)",
                    path: [component.id]
                ))
            }
        }

        // Stack components should have children
        if component.children?.isEmpty != false {
            issues.append(ValidationIssue(
                severity: .warning,
                type: .missingContent,
                message: "Stack component should have children",
                path: [component.id]
            ))
        }

        return issues
    }

    private func validateCourseCardComponent(_ component: A2UIComponent) -> [ValidationIssue] {
        var issues: [ValidationIssue] = []

        // Required fields for course card
        let requiredFields = ["title", "description"]
        for field in requiredFields {
            if component.prop(field).asString?.isEmpty != false {
                issues.append(ValidationIssue(
                    severity: .error,
                    type: .missingRequiredField,
                    message: "CourseCard must have '\(field)' property",
                    path: [component.id]
                ))
            }
        }

        // Validate progress if present
        if let progress = component.prop("progress").asDouble {
            if progress < 0 || progress > 100 {
                issues.append(ValidationIssue(
                    severity: .error,
                    type: .invalidValue,
                    message: "Progress must be between 0 and 100: \(progress)",
                    path: [component.id]
                ))
            }
        }

        return issues
    }

    private func validateQuizComponent(_ component: A2UIComponent) -> [ValidationIssue] {
        var issues: [ValidationIssue] = []

        // Quiz must have question
        if component.prop("question").asString?.isEmpty != false {
            issues.append(ValidationIssue(
                severity: .error,
                type: .missingRequiredField,
                message: "Quiz component must have 'question' property",
                path: [component.id]
            ))
        }

        // Quiz must have options
        guard let options = component.prop("options").asArray else {
            issues.append(ValidationIssue(
                severity: .error,
                type: .missingRequiredField,
                message: "Quiz component must have 'options' array",
                path: [component.id]
            ))
            return issues
        }

        if options.count < 2 {
            issues.append(ValidationIssue(
                severity: .error,
                type: .invalidValue,
                message: "Quiz must have at least 2 options",
                path: [component.id]
            ))
        }

        // Validate correct answer index
        if let correctAnswer = component.prop("correctAnswer").asInt {
            if correctAnswer < 0 || correctAnswer >= options.count {
                issues.append(ValidationIssue(
                    severity: .error,
                    type: .invalidValue,
                    message: "Correct answer index out of bounds: \(correctAnswer)",
                    path: [component.id]
                ))
            }
        }

        return issues
    }

    // MARK: - Props Validation

    private func validateProps(_ props: [String: UIValue]?, componentId: String) -> [ValidationIssue] {
        var issues: [ValidationIssue] = []

        guard let props = props else { return issues }

        for (key, value) in props {
            issues.append(contentsOf: validatePropValue(key: key, value: value, componentId: componentId))
        }

        return issues
    }

    private func validatePropValue(key: String, value: UIValue, componentId: String) -> [ValidationIssue] {
        var issues: [ValidationIssue] = []

        switch key {
        case "width", "height":
            if let numValue = value.asDouble, numValue < 0 {
                issues.append(ValidationIssue(
                    severity: .warning,
                    type: .invalidValue,
                    message: "Dimension '\(key)' should not be negative: \(numValue)",
                    path: [componentId]
                ))
            }

        case "opacity":
            if let opacity = value.asDouble {
                if opacity < 0 || opacity > 1 {
                    issues.append(ValidationIssue(
                        severity: .warning,
                        type: .invalidValue,
                        message: "Opacity should be between 0 and 1: \(opacity)",
                        path: [componentId]
                    ))
                }
            }

        case "cornerRadius", "borderWidth":
            if let numValue = value.asDouble, numValue < 0 {
                issues.append(ValidationIssue(
                    severity: .warning,
                    type: .invalidValue,
                    message: "'\(key)' should not be negative: \(numValue)",
                    path: [componentId]
                ))
            }

        case "backgroundColor", "color", "textColor", "borderColor":
            if let colorString = value.asString, !isValidColor(colorString) {
                issues.append(ValidationIssue(
                    severity: .warning,
                    type: .invalidValue,
                    message: "Invalid color format in '\(key)': \(colorString)",
                    path: [componentId]
                ))
            }

        default:
            break // No specific validation for other props
        }

        return issues
    }

    // MARK: - Validation Helpers

    private func isKnownComponentType(_ type: String) -> Bool {
        let knownTypes = Set([
            // Layout
            "vstack", "hstack", "zstack", "scroll", "scrollview", "grid", "lazygrid", "list",

            // Content
            "text", "button", "image", "video",

            // Interactive
            "textfield", "input", "slider", "toggle", "switch", "picker",

            // Business
            "coursecard", "lessoncard", "quiz", "question", "progressbar",

            // Utility
            "separator", "divider", "spacer",

            // A2UI Extended
            "camera_capture", "document_upload", "voice_input", "handwriting_input",
            "study_plan_overview", "homework_card", "mistake_card", "ocr_result"
        ])

        return knownTypes.contains(type.lowercased())
    }

    private func isValidFont(_ font: String) -> Bool {
        let validFonts = Set([
            "title", "title2", "title3", "headline", "subheadline", "body",
            "callout", "footnote", "caption", "caption2", "code", "large"
        ])

        return validFonts.contains(font.lowercased())
    }

    private func isValidColor(_ color: String) -> Bool {
        // Check hex color format
        let hexPattern = "^#([A-Fa-f0-9]{6}|[A-Fa-f0-9]{3}|[A-Fa-f0-9]{8})$"
        let hexRegex = try? NSRegularExpression(pattern: hexPattern)
        let hexRange = NSRange(color.startIndex..., in: color)

        if hexRegex?.firstMatch(in: color, range: hexRange) != nil {
            return true
        }

        // Check named colors
        let namedColors = Set([
            "red", "green", "blue", "yellow", "orange", "purple", "pink",
            "black", "white", "gray", "clear", "primary", "secondary"
        ])

        return namedColors.contains(color.lowercased())
    }

    // MARK: - Public Validation Methods

    func validateBackendResponse(_ data: Data) -> BackendValidationResult {
        do {
            // First try to decode as screen response
            if let screenResponse = try? JSONDecoder().decode(A2UIScreenResponse.self, from: data) {
                let componentResult = validateComponent(screenResponse.component)
                return .success(componentResult)
            }

            // Then try to decode as action response
            if let actionResponse = try? JSONDecoder().decode(A2UIActionResponse.self, from: data) {
                if let component = actionResponse.component {
                    let componentResult = validateComponent(component)
                    return .success(componentResult)
                } else {
                    return .success(.success) // Action response without component is valid
                }
            }

            // Try to decode as plain component
            if let component = try? JSONDecoder().decode(A2UIComponent.self, from: data) {
                let componentResult = validateComponent(component)
                return .success(componentResult)
            }

            return .failure(.invalidJSON("Unable to decode response as valid A2UI format"))

        } catch {
            return .failure(.decodingError(error))
        }
    }
}

// MARK: - Supporting Types

struct ValidationIssue {
    enum Severity {
        case error    // Will prevent rendering
        case warning  // Will log but allow rendering
    }

    enum IssueType {
        case missingRequiredField
        case invalidValue
        case unknownComponentType
        case missingContent
        case structuralIssue
    }

    let severity: Severity
    let type: IssueType
    let message: String
    let path: [String]

    var fullMessage: String {
        let pathString = path.isEmpty ? "" : " (at \(path.joined(separator: " -> ")))"
        return "\(message)\(pathString)"
    }
}

enum ValidationResult {
    case success
    case failure([ValidationIssue])

    var isValid: Bool {
        switch self {
        case .success:
            return true
        case .failure(let issues):
            return !issues.contains { $0.severity == .error }
        }
    }

    var errors: [ValidationIssue] {
        switch self {
        case .success:
            return []
        case .failure(let issues):
            return issues.filter { $0.severity == .error }
        }
    }

    var warnings: [ValidationIssue] {
        switch self {
        case .success:
            return []
        case .failure(let issues):
            return issues.filter { $0.severity == .warning }
        }
    }
}

enum BackendValidationResult {
    case success(ValidationResult)
    case failure(BackendValidationError)
}

enum BackendValidationError {
    case invalidJSON(String)
    case decodingError(Error)

    var localizedDescription: String {
        switch self {
        case .invalidJSON(let message):
            return "Invalid JSON: \(message)"
        case .decodingError(let error):
            return "Decoding error: \(error.localizedDescription)"
        }
    }
}

// MARK: - Response Models for Validation

struct A2UIScreenResponse: Codable {
    let component: A2UIComponent
    let screenId: String
    let sessionId: String
    let metadata: [String: String]?

    enum CodingKeys: String, CodingKey {
        case component, screenId = "screen_id", sessionId = "session_id", metadata
    }
}

struct A2UIActionResponse: Codable {
    let component: A2UIComponent?
    let navigation: [String: String]?
    let message: String?
    let success: Bool
}