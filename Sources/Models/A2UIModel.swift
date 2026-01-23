import Foundation
import SwiftUI

// MARK: - Safe Dynamic Value Wrapper
enum UIValue: Decodable {
    case string(String)
    case int(Int)
    case double(Double)
    case bool(Bool)
    case array([UIValue])
    case object([String: UIValue])
    case null

    init(from decoder: Decoder) throws {
        let container = try decoder.singleValueContainer()
        if let x = try? container.decode(String.self) { self = .string(x); return }
        if let x = try? container.decode(Int.self) { self = .int(x); return }
        if let x = try? container.decode(Double.self) { self = .double(x); return }
        if let x = try? container.decode(Bool.self) { self = .bool(x); return }
        if let x = try? container.decode([UIValue].self) { self = .array(x); return }
        if let x = try? container.decode([String: UIValue].self) { self = .object(x); return }
        self = .null
    }

    var asString: String? {
        if case .string(let s) = self { return s }
        if case .int(let i) = self { return String(i) }
        if case .double(let d) = self { return String(d) }
        if case .bool(let b) = self { return String(b) }
        return nil
    }

    var asInt: Int? {
        if case .int(let i) = self { return i }
        if case .double(let d) = self { return Int(d) }
        if case .string(let s) = self { return Int(s) }
        return nil
    }

    var asDouble: Double? {
        if case .double(let d) = self { return d }
        if case .int(let i) = self { return Double(i) }
        if case .string(let s) = self { return Double(s) }
        return nil
    }

    var asBool: Bool? {
        if case .bool(let b) = self { return b }
        if case .string(let s) = self { return Bool(s) }
        return nil
    }

    // Hex Color Helper
    var asColor: Color {
        guard let hex = asString else { return .clear }
        return Color(hex: hex)
    }

    var asArray: [UIValue]? {
        if case .array(let arr) = self { return arr }
        return nil
    }

    var asObject: [String: UIValue]? {
        if case .object(let obj) = self { return obj }
        return nil
    }
}

// MARK: - Component Node
struct A2UIComponent: Decodable, Identifiable {
    let id: String
    let type: String
    let props: [String: UIValue]?
    let children: [A2UIComponent]?

    // Custom initializer for manual creation
    init(id: String = UUID().uuidString, type: String, props: [String: UIValue]? = nil, children: [A2UIComponent]? = nil) {
        self.id = id
        self.type = type
        self.props = props
        self.children = children
    }

    // Helper for safe prop access
    func prop(_ key: String) -> UIValue {
        return props?[key] ?? .null
    }

    // Helper for safe prop access with default
    func prop(_ key: String, default defaultValue: UIValue) -> UIValue {
        return props?[key] ?? defaultValue
    }
}

// MARK: - Action Event
struct A2UIAction {
    let actionId: String
    let componentId: String
    let actionType: String
    let params: [String: Any]?
    let timestamp: Date

    init(actionId: String, componentId: String, actionType: String = "tap", params: [String: Any]? = nil) {
        self.actionId = actionId
        self.componentId = componentId
        self.actionType = actionType
        self.params = params
        self.timestamp = Date()
    }
}

// MARK: - Color Extension
extension Color {
    init(hex: String) {
        let hex = hex.trimmingCharacters(in: CharacterSet.alphanumerics.inverted)
        var int: UInt64 = 0
        Scanner(string: hex).scanHexInt64(&int)
        let a, r, g, b: UInt64
        switch hex.count {
        case 3: // RGB (12-bit)
            (a, r, g, b) = (255, (int >> 8) * 17, (int >> 4 & 0xF) * 17, (int & 0xF) * 17)
        case 6: // RGB (24-bit)
            (a, r, g, b) = (255, int >> 16, int >> 8 & 0xFF, int & 0xFF)
        case 8: // ARGB (32-bit)
            (a, r, g, b) = (int >> 24, int >> 16 & 0xFF, int >> 8 & 0xFF, int & 0xFF)
        default:
            (a, r, g, b) = (255, 128, 128, 128) // Default to gray
        }
        self.init(
            .sRGB,
            red: Double(r) / 255,
            green: Double(g) / 255,
            blue: Double(b) / 255,
            opacity: Double(a) / 255
        )
    }

    // Predefined colors for common use
    static let lyoPrimary = Color(hex: "007AFF")
    static let lyoSecondary = Color(hex: "5856D6")
    static let lyoSuccess = Color(hex: "34C759")
    static let lyoWarning = Color(hex: "FFCC00")
    static let lyoError = Color(hex: "FF3B30")
}

// MARK: - Font Mapping
extension Font {
    static func lyoFont(_ style: String?) -> Font {
        switch style?.lowercased() {
        case "title":
            return .title
        case "title2":
            return .title2
        case "title3":
            return .title3
        case "headline":
            return .headline
        case "subheadline":
            return .subheadline
        case "body":
            return .body
        case "callout":
            return .callout
        case "footnote":
            return .footnote
        case "caption":
            return .caption
        case "caption2":
            return .caption2
        case "code":
            return .system(.body, design: .monospaced)
        case "large":
            return .largeTitle
        default:
            return .body
        }
    }
}

// MARK: - Alignment Helpers
extension HorizontalAlignment {
    static func from(_ string: String?) -> HorizontalAlignment {
        switch string?.lowercased() {
        case "leading", "left":
            return .leading
        case "trailing", "right":
            return .trailing
        case "center":
            return .center
        default:
            return .center
        }
    }
}

extension VerticalAlignment {
    static func from(_ string: String?) -> VerticalAlignment {
        switch string?.lowercased() {
        case "top":
            return .top
        case "bottom":
            return .bottom
        case "center":
            return .center
        default:
            return .center
        }
    }
}

extension TextAlignment {
    static func from(_ string: String?) -> TextAlignment {
        switch string?.lowercased() {
        case "leading", "left":
            return .leading
        case "trailing", "right":
            return .trailing
        case "center":
            return .center
        default:
            return .center
        }
    }
}

extension Alignment {
    static func from(_ string: String?) -> Alignment {
        switch string?.lowercased() {
        case "topLeading", "topleft":
            return .topLeading
        case "top":
            return .top
        case "topTrailing", "topright":
            return .topTrailing
        case "leading", "left":
            return .leading
        case "center":
            return .center
        case "trailing", "right":
            return .trailing
        case "bottomLeading", "bottomleft":
            return .bottomLeading
        case "bottom":
            return .bottom
        case "bottomTrailing", "bottomright":
            return .bottomTrailing
        default:
            return .center
        }
    }
}

// MARK: - Edge Insets Helper
extension Edge.Set {
    static func from(_ string: String?) -> Edge.Set {
        switch string?.lowercased() {
        case "top":
            return .top
        case "bottom":
            return .bottom
        case "leading", "left":
            return .leading
        case "trailing", "right":
            return .trailing
        case "horizontal":
            return .horizontal
        case "vertical":
            return .vertical
        case "all":
            return .all
        default:
            return .all
        }
    }
}