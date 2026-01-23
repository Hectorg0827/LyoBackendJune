import SwiftUI
import AVKit

struct A2UIRenderer: View {
    let component: A2UIComponent
    // Callback to bubble actions up to parent
    var onAction: ((A2UIAction) -> Void)?

    var body: some View {
        Group {
            switch component.type.lowercased() {

            // MARK: - Layout Containers
            case "vstack", "box":
                VStack(
                    alignment: HorizontalAlignment.from(component.prop("align").asString),
                    spacing: CGFloat(component.prop("spacing").asDouble ?? 8)
                ) {
                    renderChildren()
                }
                .applyCommonModifiers(component: component)

            case "hstack":
                HStack(
                    alignment: VerticalAlignment.from(component.prop("align").asString),
                    spacing: CGFloat(component.prop("spacing").asDouble ?? 8)
                ) {
                    renderChildren()
                }
                .applyCommonModifiers(component: component)

            case "zstack":
                ZStack(
                    alignment: Alignment.from(component.prop("align").asString)
                ) {
                    renderChildren()
                }
                .applyCommonModifiers(component: component)

            case "scroll", "scrollview":
                let axis: Axis.Set = component.prop("direction").asString == "horizontal" ? .horizontal : .vertical
                let showsIndicators = component.prop("showIndicators").asBool ?? true

                ScrollView(axis, showsIndicators: showsIndicators) {
                    if axis == .horizontal {
                        HStack(spacing: CGFloat(component.prop("spacing").asDouble ?? 8)) {
                            renderChildren()
                        }
                    } else {
                        VStack(spacing: CGFloat(component.prop("spacing").asDouble ?? 8)) {
                            renderChildren()
                        }
                    }
                }
                .applyCommonModifiers(component: component)

            case "grid", "lazygrid":
                let columns = component.prop("columns").asInt ?? 2
                let spacing = CGFloat(component.prop("spacing").asDouble ?? 8)

                LazyVGrid(columns: Array(repeating: GridItem(.flexible(), spacing: spacing), count: columns), spacing: spacing) {
                    renderChildren()
                }
                .applyCommonModifiers(component: component)

            // MARK: - Content Components
            case "text":
                let text = component.prop("text").asString ?? component.prop("content").asString ?? ""
                let fontStyle = component.prop("font").asString ?? component.prop("fontStyle").asString
                let color = component.prop("color").asColor
                let alignment = TextAlignment.from(component.prop("textAlign").asString)
                let lineLimit = component.prop("lineLimit").asInt

                Text(text)
                    .font(Font.lyoFont(fontStyle))
                    .foregroundColor(color == .clear ? .primary : color)
                    .multilineTextAlignment(alignment)
                    .lineLimit(lineLimit)
                    .applyCommonModifiers(component: component)

            case "button":
                let label = component.prop("title").asString ?? component.prop("label").asString ?? "Button"
                let actionId = component.prop("action").asString ?? component.prop("actionId").asString ?? "tap"
                let buttonStyle = component.prop("style").asString ?? "primary"

                Button(action: {
                    let action = A2UIAction(
                        actionId: actionId,
                        componentId: component.id,
                        actionType: "tap",
                        params: component.props?.mapValues { value in
                            switch value {
                            case .string(let s): return s
                            case .int(let i): return i
                            case .double(let d): return d
                            case .bool(let b): return b
                            default: return nil
                            }
                        }.compactMapValues { $0 }
                    )
                    onAction?(action)
                }) {
                    Text(label)
                        .font(Font.lyoFont(component.prop("font").asString))
                        .foregroundColor(getButtonTextColor(style: buttonStyle, component: component))
                        .padding(.horizontal, 16)
                        .padding(.vertical, 12)
                        .frame(maxWidth: component.prop("fullWidth").asBool == true ? .infinity : nil)
                        .background(getButtonBackgroundColor(style: buttonStyle, component: component))
                        .cornerRadius(CGFloat(component.prop("cornerRadius").asDouble ?? 8))
                }
                .disabled(component.prop("disabled").asBool ?? false)
                .applyCommonModifiers(component: component)

            case "image":
                let imageUrl = component.prop("url").asString ?? component.prop("src").asString
                let width = component.prop("width").asDouble
                let height = component.prop("height").asDouble
                let aspectRatio = component.prop("aspectRatio").asString ?? "fit"

                if let urlString = imageUrl, let url = URL(string: urlString) {
                    AsyncImage(url: url) { image in
                        image
                            .resizable()
                            .aspectRatio(contentMode: aspectRatio == "fill" ? .fill : .fit)
                    } placeholder: {
                        RoundedRectangle(cornerRadius: 8)
                            .fill(Color(.systemGray5))
                            .overlay(
                                Image(systemName: "photo")
                                    .foregroundColor(.secondary)
                            )
                    }
                    .frame(
                        width: width.map(CGFloat.init),
                        height: height.map(CGFloat.init)
                    )
                    .applyCommonModifiers(component: component)
                } else {
                    // Fallback for system images or local assets
                    let systemName = component.prop("systemName").asString
                    if let systemName = systemName {
                        Image(systemName: systemName)
                            .font(Font.lyoFont(component.prop("font").asString))
                            .foregroundColor(component.prop("color").asColor)
                            .applyCommonModifiers(component: component)
                    } else {
                        Image("placeholder") // Your app's placeholder image
                            .resizable()
                            .aspectRatio(contentMode: .fit)
                            .applyCommonModifiers(component: component)
                    }
                }

            case "textfield", "input":
                let placeholder = component.prop("placeholder").asString ?? ""
                let isSecure = component.prop("secure").asBool ?? false

                if isSecure {
                    SecureField(placeholder, text: .constant(""))
                        .textFieldStyle(RoundedBorderTextFieldStyle())
                        .applyCommonModifiers(component: component)
                } else {
                    TextField(placeholder, text: .constant(""))
                        .textFieldStyle(RoundedBorderTextFieldStyle())
                        .applyCommonModifiers(component: component)
                }

            // MARK: - Interactive Components
            case "slider":
                let minValue = component.prop("min").asDouble ?? 0
                let maxValue = component.prop("max").asDouble ?? 100
                let currentValue = component.prop("value").asDouble ?? 50

                Slider(value: .constant(currentValue), in: minValue...maxValue)
                    .applyCommonModifiers(component: component)

            case "toggle", "switch":
                let isOn = component.prop("value").asBool ?? false
                let label = component.prop("label").asString ?? ""

                Toggle(label, isOn: .constant(isOn))
                    .applyCommonModifiers(component: component)

            case "picker":
                let options = component.prop("options").asArray?.compactMap { $0.asString } ?? []
                let selectedIndex = component.prop("selectedIndex").asInt ?? 0
                let selectedOption = selectedIndex < options.count ? options[selectedIndex] : options.first ?? ""

                Picker("Select", selection: .constant(selectedOption)) {
                    ForEach(options, id: \.self) { option in
                        Text(option).tag(option)
                    }
                }
                .pickerStyle(MenuPickerStyle())
                .applyCommonModifiers(component: component)

            // MARK: - Media Components
            case "video":
                let videoUrl = component.prop("url").asString
                let autoplay = component.prop("autoplay").asBool ?? false
                let controls = component.prop("controls").asBool ?? true

                if let urlString = videoUrl, let url = URL(string: urlString) {
                    VideoPlayer(player: AVPlayer(url: url)) {
                        // Video overlay if needed
                    }
                    .frame(height: CGFloat(component.prop("height").asDouble ?? 200))
                    .applyCommonModifiers(component: component)
                } else {
                    RoundedRectangle(cornerRadius: 8)
                        .fill(Color(.systemGray5))
                        .overlay(
                            Image(systemName: "play.circle")
                                .font(.largeTitle)
                                .foregroundColor(.secondary)
                        )
                        .frame(height: 200)
                        .applyCommonModifiers(component: component)
                }

            // MARK: - Lyo Business Components
            case "coursecard":
                LyoCourseCard(
                    title: component.prop("title").asString ?? "Course",
                    description: component.prop("description").asString ?? "",
                    imageUrl: component.prop("imageUrl").asString,
                    progress: component.prop("progress").asDouble ?? 0,
                    difficulty: component.prop("difficulty").asString ?? "Beginner",
                    duration: component.prop("duration").asString ?? "1 hour",
                    onTap: {
                        let action = A2UIAction(
                            actionId: component.prop("action").asString ?? "course_tap",
                            componentId: component.id,
                            actionType: "tap"
                        )
                        onAction?(action)
                    }
                )

            case "lessoncard":
                LyoLessonCard(
                    title: component.prop("title").asString ?? "Lesson",
                    description: component.prop("description").asString ?? "",
                    isCompleted: component.prop("completed").asBool ?? false,
                    duration: component.prop("duration").asString ?? "10 min",
                    lessonType: component.prop("type").asString ?? "video",
                    onTap: {
                        let action = A2UIAction(
                            actionId: component.prop("action").asString ?? "lesson_tap",
                            componentId: component.id,
                            actionType: "tap"
                        )
                        onAction?(action)
                    }
                )

            case "progressbar":
                let progress = component.prop("progress").asDouble ?? 0
                let color = component.prop("color").asColor

                ProgressView(value: progress / 100)
                    .progressViewStyle(LinearProgressViewStyle(tint: color == .clear ? .lyoPrimary : color))
                    .applyCommonModifiers(component: component)

            case "quiz", "question":
                LyoQuizComponent(
                    question: component.prop("question").asString ?? "",
                    options: component.prop("options").asArray?.compactMap { $0.asString } ?? [],
                    correctAnswer: component.prop("correctAnswer").asInt ?? 0,
                    selectedAnswer: component.prop("selectedAnswer").asInt,
                    onAnswerSelected: { selectedIndex in
                        let action = A2UIAction(
                            actionId: component.prop("action").asString ?? "answer_selected",
                            componentId: component.id,
                            actionType: "selection",
                            params: ["selectedAnswer": selectedIndex]
                        )
                        onAction?(action)
                    }
                )

            case "separator", "divider":
                Divider()
                    .background(component.prop("color").asColor)
                    .applyCommonModifiers(component: component)

            case "spacer":
                let height = component.prop("height").asDouble ?? 20
                Spacer()
                    .frame(height: CGFloat(height))

            // MARK: - List Components
            case "list":
                LazyVStack(alignment: .leading, spacing: CGFloat(component.prop("spacing").asDouble ?? 8)) {
                    renderChildren()
                }
                .applyCommonModifiers(component: component)

            // MARK: - Error/Unknown Component
            default:
                VStack {
                    Image(systemName: "exclamationmark.triangle")
                        .foregroundColor(.orange)
                    Text("Unknown Component: \(component.type)")
                        .font(.caption)
                        .foregroundColor(.secondary)
                }
                .padding()
                .background(Color(.systemGray6))
                .cornerRadius(8)
            }
        }
    }

    // MARK: - Helper Methods
    @ViewBuilder
    private func renderChildren() -> some View {
        if let children = component.children, !children.isEmpty {
            ForEach(children) { child in
                A2UIRenderer(component: child, onAction: onAction)
            }
        }
    }

    private func getButtonBackgroundColor(style: String, component: A2UIComponent) -> Color {
        // Check for custom background color first
        let customBg = component.prop("backgroundColor").asColor
        if customBg != .clear {
            return customBg
        }

        // Apply style-based colors
        switch style.lowercased() {
        case "primary":
            return .lyoPrimary
        case "secondary":
            return .lyoSecondary
        case "success":
            return .lyoSuccess
        case "warning":
            return .lyoWarning
        case "danger", "error":
            return .lyoError
        case "outline":
            return .clear
        default:
            return .lyoPrimary
        }
    }

    private func getButtonTextColor(style: String, component: A2UIComponent) -> Color {
        // Check for custom text color first
        let customColor = component.prop("textColor").asColor
        if customColor != .clear {
            return customColor
        }

        // Apply style-based colors
        switch style.lowercased() {
        case "outline":
            return .lyoPrimary
        default:
            return .white
        }
    }
}

// MARK: - Common View Modifiers
extension View {
    func applyCommonModifiers(component: A2UIComponent) -> some View {
        let padding = CGFloat(component.prop("padding").asDouble ?? 0)
        let margin = CGFloat(component.prop("margin").asDouble ?? 0)
        let backgroundColor = component.prop("backgroundColor").asColor
        let cornerRadius = CGFloat(component.prop("cornerRadius").asDouble ?? 0)
        let borderWidth = CGFloat(component.prop("borderWidth").asDouble ?? 0)
        let borderColor = component.prop("borderColor").asColor
        let width = component.prop("width").asDouble
        let height = component.prop("height").asDouble
        let maxWidth = component.prop("maxWidth").asString
        let opacity = component.prop("opacity").asDouble ?? 1.0
        let hidden = component.prop("hidden").asBool ?? false

        return self
            .padding(padding > 0 ? padding : 0)
            .background(backgroundColor == .clear ? Color.clear : backgroundColor)
            .cornerRadius(cornerRadius)
            .overlay(
                RoundedRectangle(cornerRadius: cornerRadius)
                    .stroke(borderColor, lineWidth: borderWidth)
            )
            .frame(
                width: width.map(CGFloat.init),
                height: height.map(CGFloat.init),
                maxWidth: maxWidth == "infinity" ? .infinity : nil
            )
            .opacity(opacity)
            .hidden(hidden)
            .padding(margin > 0 ? margin : 0)
    }
}

extension View {
    @ViewBuilder
    func hidden(_ shouldHide: Bool) -> some View {
        if shouldHide {
            self.hidden()
        } else {
            self
        }
    }
}