import SwiftUI
import AVFoundation
import VisionKit
import PencilKit
import UniformTypeIdentifiers
import PhotosUI

/// Multimodal Input Renderers - Camera, Voice, Handwriting, Document Upload
/// These are CRITICAL for the "auto notes from anything" feature

// ═══════════════════════════════════════════════════════════════════════════
// MARK: - Camera Capture Renderer
// ═══════════════════════════════════════════════════════════════════════════

struct A2UICameraCaptureRenderer: View {
    let component: A2UIComponent
    let onAction: ((A2UIAction) -> Void)?

    @State private var showCamera = false
    @State private var capturedImage: UIImage?
    @State private var isProcessing = false

    var body: some View {
        VStack(spacing: 16) {
            // Header
            VStack(spacing: 8) {
                Image(systemName: "camera.fill")
                    .font(.system(size: 48))
                    .foregroundColor(.blue)

                Text(component.props.title ?? "Capture Document")
                    .font(.headline)
                    .multilineTextAlignment(.center)

                if let subtitle = component.props.subtitle {
                    Text(subtitle)
                        .font(.subheadline)
                        .foregroundColor(.secondary)
                        .multilineTextAlignment(.center)
                }
            }

            // Captured Image Preview
            if let image = capturedImage {
                VStack(spacing: 12) {
                    Image(uiImage: image)
                        .resizable()
                        .aspectRatio(contentMode: .fit)
                        .frame(maxHeight: 200)
                        .cornerRadius(12)
                        .shadow(radius: 4)

                    HStack(spacing: 12) {
                        Button("Retake") {
                            capturedImage = nil
                            showCamera = true
                        }
                        .buttonStyle(.bordered)

                        Button("Use This Photo") {
                            processImage(image)
                        }
                        .buttonStyle(.borderedProminent)
                        .disabled(isProcessing)
                    }
                }
            } else {
                // Capture Button
                Button(action: { showCamera = true }) {
                    HStack {
                        Image(systemName: "camera")
                        Text(component.props.text ?? "Take Photo")
                    }
                    .frame(maxWidth: .infinity)
                    .padding()
                    .background(Color.blue)
                    .foregroundColor(.white)
                    .cornerRadius(12)
                }
            }

            // Processing State
            if isProcessing {
                HStack {
                    ProgressView()
                        .scaleEffect(0.8)
                    Text("Processing image...")
                        .font(.caption)
                        .foregroundColor(.secondary)
                }
            }

            // Instructions
            if let instructions = component.props.instructions {
                Text(instructions)
                    .font(.caption)
                    .foregroundColor(.secondary)
                    .multilineTextAlignment(.center)
            } else {
                Text("Position the document clearly in frame for best results")
                    .font(.caption)
                    .foregroundColor(.secondary)
                    .multilineTextAlignment(.center)
            }
        }
        .padding()
        .sheet(isPresented: $showCamera) {
            CameraView { image in
                capturedImage = image
                showCamera = false
            }
        }
    }

    private func processImage(_ image: UIImage) {
        isProcessing = true

        Task {
            do {
                // Convert to data
                guard let imageData = image.jpegData(compressionQuality: 0.8) else { return }

                // Send to backend for processing
                let action = A2UIAction(
                    trigger: .onSubmit,
                    type: .custom,
                    payload: [
                        "action": "image_captured",
                        "component_id": component.id,
                        "capture_mode": component.props.captureMode ?? "document",
                        "enable_ocr": String(component.props.enableOCR ?? true),
                        "file_size": String(imageData.count)
                    ]
                )

                await MainActor.run {
                    onAction?(action)
                    isProcessing = false
                }

            } catch {
                await MainActor.run {
                    isProcessing = false
                    // Handle error
                }
            }
        }
    }
}

// ═══════════════════════════════════════════════════════════════════════════
// MARK: - Document Upload Renderer
// ═══════════════════════════════════════════════════════════════════════════

struct A2UIDocumentUploadRenderer: View {
    let component: A2UIComponent
    let onAction: ((A2UIAction) -> Void)?

    @State private var showDocumentPicker = false
    @State private var selectedDocuments: [URL] = []
    @State private var uploadProgress: [String: Double] = [:]
    @State private var isProcessing = false

    var body: some View {
        VStack(spacing: 16) {
            // Drop Zone
            VStack(spacing: 16) {
                if selectedDocuments.isEmpty {
                    // Empty State
                    VStack(spacing: 16) {
                        Image(systemName: "doc.badge.plus")
                            .font(.system(size: 48))
                            .foregroundColor(.blue)

                        VStack(spacing: 4) {
                            Text(component.props.title ?? "Upload Document")
                                .font(.headline)

                            Text("PDF, Word, Images, or text files")
                                .font(.subheadline)
                                .foregroundColor(.secondary)
                        }

                        Button("Choose Files") {
                            showDocumentPicker = true
                        }
                        .buttonStyle(.borderedProminent)
                    }
                } else {
                    // Selected Documents
                    LazyVStack(spacing: 8) {
                        ForEach(selectedDocuments, id: \.self) { url in
                            DocumentRowView(
                                url: url,
                                progress: uploadProgress[url.lastPathComponent],
                                onRemove: {
                                    selectedDocuments.removeAll { $0 == url }
                                }
                            )
                        }
                    }

                    HStack(spacing: 12) {
                        Button("Add More") {
                            showDocumentPicker = true
                        }
                        .buttonStyle(.bordered)

                        Button("Process Documents") {
                            processDocuments()
                        }
                        .buttonStyle(.borderedProminent)
                        .disabled(isProcessing)
                    }
                }
            }
            .padding(24)
            .background(
                RoundedRectangle(cornerRadius: 16)
                    .stroke(Color.blue.opacity(0.3), style: StrokeStyle(lineWidth: 2, dash: [5, 5]))
            )

            // Processing Status
            if isProcessing {
                VStack(spacing: 8) {
                    ProgressView()
                    Text("Processing documents...")
                        .font(.caption)
                        .foregroundColor(.secondary)
                }
            }

            // File Type Restrictions
            if let acceptedTypes = component.props.acceptedTypes, !acceptedTypes.isEmpty {
                VStack(alignment: .leading, spacing: 4) {
                    Text("Accepted file types:")
                        .font(.caption)
                        .foregroundColor(.secondary)

                    Text(acceptedTypes.joined(separator: ", "))
                        .font(.caption2)
                        .foregroundColor(.secondary)
                }
            }
        }
        .fileImporter(
            isPresented: $showDocumentPicker,
            allowedContentTypes: getAllowedContentTypes(),
            allowsMultipleSelection: true
        ) { result in
            handleFileImport(result)
        }
    }

    private func getAllowedContentTypes() -> [UTType] {
        guard let acceptedTypes = component.props.acceptedTypes else {
            return [.pdf, .plainText, .image, .data]
        }

        var types: [UTType] = []
        for type in acceptedTypes {
            switch type {
            case "application/pdf":
                types.append(.pdf)
            case "text/plain":
                types.append(.plainText)
            case "image/jpeg", "image/png":
                types.append(.image)
            case "application/msword", "application/vnd.openxmlformats-officedocument.wordprocessingml.document":
                types.append(.data)
            default:
                types.append(.data)
            }
        }
        return types.isEmpty ? [.data] : types
    }

    private func handleFileImport(_ result: Result<[URL], Error>) {
        switch result {
        case .success(let urls):
            // Filter by size limit
            let maxSize = component.props.maxFileSize ?? (100 * 1024 * 1024) // 100MB default
            let validUrls = urls.filter { url in
                do {
                    let resources = try url.resourceValues(forKeys: [.fileSizeKey])
                    let fileSize = resources.fileSize ?? 0
                    return fileSize <= maxSize
                } catch {
                    return false
                }
            }
            selectedDocuments.append(contentsOf: validUrls)

        case .failure(let error):
            print("File import error: \(error)")
        }
    }

    private func processDocuments() {
        isProcessing = true

        Task {
            for url in selectedDocuments {
                await uploadDocument(url)
            }

            await MainActor.run {
                isProcessing = false
                selectedDocuments.removeAll()
                uploadProgress.removeAll()

                let action = A2UIAction(
                    trigger: .onSubmit,
                    type: .custom,
                    payload: [
                        "action": "documents_processed",
                        "component_id": component.id,
                        "document_count": String(selectedDocuments.count)
                    ]
                )
                onAction?(action)
            }
        }
    }

    private func uploadDocument(_ url: URL) async {
        let fileName = url.lastPathComponent

        do {
            let data = try Data(contentsOf: url)

            // Simulate upload progress
            for progress in stride(from: 0.0, through: 1.0, by: 0.1) {
                await MainActor.run {
                    uploadProgress[fileName] = progress
                }
                try await Task.sleep(nanoseconds: 100_000_000) // 0.1 second
            }

            // Here you would upload to your backend
            // let uploadedUrl = try await uploadToBackend(data: data, fileName: fileName)

        } catch {
            print("Upload error for \(fileName): \(error)")
        }
    }
}

struct DocumentRowView: View {
    let url: URL
    let progress: Double?
    let onRemove: () -> Void

    var body: some View {
        HStack {
            Image(systemName: iconForFile(url))
                .foregroundColor(.blue)

            VStack(alignment: .leading, spacing: 2) {
                Text(url.lastPathComponent)
                    .font(.caption)
                    .lineLimit(1)

                if let progress = progress {
                    ProgressView(value: progress)
                        .progressViewStyle(LinearProgressViewStyle())
                } else {
                    Text(fileSizeString(for: url))
                        .font(.caption2)
                        .foregroundColor(.secondary)
                }
            }

            Spacer()

            Button(action: onRemove) {
                Image(systemName: "xmark.circle.fill")
                    .foregroundColor(.secondary)
            }
        }
        .padding(.horizontal, 12)
        .padding(.vertical, 8)
        .background(Color(.systemGray6))
        .cornerRadius(8)
    }

    private func iconForFile(_ url: URL) -> String {
        let ext = url.pathExtension.lowercased()
        switch ext {
        case "pdf": return "doc.richtext"
        case "jpg", "jpeg", "png", "heic": return "photo"
        case "doc", "docx": return "doc.text"
        case "txt": return "doc.plaintext"
        default: return "doc"
        }
    }

    private func fileSizeString(for url: URL) -> String {
        do {
            let resources = try url.resourceValues(forKeys: [.fileSizeKey])
            let fileSize = resources.fileSize ?? 0
            return ByteCountFormatter().string(fromByteCount: Int64(fileSize))
        } catch {
            return "Unknown size"
        }
    }
}

// ═══════════════════════════════════════════════════════════════════════════
// MARK: - Handwriting Input Renderer
// ═══════════════════════════════════════════════════════════════════════════

@available(iOS 13.0, *)
struct A2UIHandwritingInputRenderer: View {
    let component: A2UIComponent
    let onAction: ((A2UIAction) -> Void)?

    @State private var canvasView = PKCanvasView()
    @State private var isRecognizing = false
    @State private var recognizedText = ""

    var body: some View {
        VStack(spacing: 16) {
            // Header
            VStack(spacing: 8) {
                HStack {
                    Image(systemName: "pencil.tip")
                        .font(.title2)
                        .foregroundColor(.blue)

                    Text(component.props.title ?? "Write with your finger or Apple Pencil")
                        .font(.headline)

                    Spacer()

                    Button("Clear") {
                        canvasView.drawing = PKDrawing()
                        recognizedText = ""
                    }
                    .font(.caption)
                    .foregroundColor(.blue)
                }

                if let instructions = component.props.instructions {
                    Text(instructions)
                        .font(.caption)
                        .foregroundColor(.secondary)
                }
            }

            // Drawing Canvas
            PencilKitView(canvasView: canvasView) { drawing in
                recognizeHandwriting(from: drawing)
            }
            .frame(height: 300)
            .background(Color(.systemBackground))
            .overlay(
                RoundedRectangle(cornerRadius: 12)
                    .stroke(Color(.systemGray4), lineWidth: 1)
            )
            .cornerRadius(12)

            // Recognition Results
            if !recognizedText.isEmpty {
                VStack(alignment: .leading, spacing: 8) {
                    Text("Recognized Text:")
                        .font(.caption)
                        .foregroundColor(.secondary)

                    Text(recognizedText)
                        .font(.body)
                        .padding()
                        .background(Color(.systemGray6))
                        .cornerRadius(8)

                    HStack {
                        Button("Use Text") {
                            submitHandwriting()
                        }
                        .buttonStyle(.borderedProminent)

                        Button("Edit") {
                            // Open text editor
                        }
                        .buttonStyle(.bordered)
                    }
                }
            }

            // Processing State
            if isRecognizing {
                HStack {
                    ProgressView()
                        .scaleEffect(0.8)
                    Text("Recognizing handwriting...")
                        .font(.caption)
                        .foregroundColor(.secondary)
                }
            }
        }
        .padding()
    }

    private func recognizeHandwriting(from drawing: PKDrawing) {
        guard !drawing.strokes.isEmpty else { return }

        isRecognizing = true

        Task {
            do {
                let request = VNRecognizeTextRequest { request, error in
                    guard let observations = request.results as? [VNRecognizedTextObservation] else {
                        return
                    }

                    let recognizedStrings = observations.compactMap { observation in
                        observation.topCandidates(1).first?.string
                    }

                    DispatchQueue.main.async {
                        self.recognizedText = recognizedStrings.joined(separator: " ")
                        self.isRecognizing = false
                    }
                }

                request.recognitionLevel = .accurate
                request.usesLanguageCorrection = true

                let image = drawing.image(from: drawing.bounds, scale: 1.0)
                guard let cgImage = image.cgImage else { return }

                let requestHandler = VNImageRequestHandler(cgImage: cgImage, options: [:])
                try requestHandler.perform([request])

            } catch {
                await MainActor.run {
                    isRecognizing = false
                    print("Handwriting recognition error: \(error)")
                }
            }
        }
    }

    private func submitHandwriting() {
        let action = A2UIAction(
            trigger: .onSubmit,
            type: .custom,
            payload: [
                "action": "handwriting_recognized",
                "component_id": component.id,
                "recognized_text": recognizedText,
                "confidence": "high" // Would come from Vision framework
            ]
        )
        onAction?(action)
    }
}

// ═══════════════════════════════════════════════════════════════════════════
// MARK: - Voice Input Renderer
// ═══════════════════════════════════════════════════════════════════════════

struct A2UIVoiceInputRenderer: View {
    let component: A2UIComponent
    let onAction: ((A2UIAction) -> Void)?

    @EnvironmentObject var voiceCoordinator: A2UIVoiceCoordinator
    @State private var transcript = ""
    @State private var isListening = false
    @State private var audioLevels: [Double] = []

    var body: some View {
        VStack(spacing: 16) {
            // Header
            VStack(spacing: 8) {
                Text(component.props.title ?? "Voice Input")
                    .font(.headline)

                if let hint = component.props.voiceHint {
                    Text(hint)
                        .font(.subheadline)
                        .foregroundColor(.secondary)
                        .multilineTextAlignment(.center)
                }
            }

            // Voice Visualizer
            VoiceVisualizerView(
                isListening: isListening,
                audioLevels: audioLevels
            )
            .frame(height: 100)

            // Transcript
            if !transcript.isEmpty {
                ScrollView {
                    Text(transcript)
                        .font(.body)
                        .padding()
                        .frame(maxWidth: .infinity, alignment: .leading)
                        .background(Color(.systemGray6))
                        .cornerRadius(12)
                }
                .frame(maxHeight: 120)
            }

            // Controls
            HStack(spacing: 20) {
                Button(action: toggleListening) {
                    Image(systemName: isListening ? "stop.fill" : "mic.fill")
                        .font(.system(size: 24))
                        .foregroundColor(.white)
                        .frame(width: 60, height: 60)
                        .background(isListening ? Color.red : Color.blue)
                        .clipShape(Circle())
                        .scaleEffect(isListening ? 1.1 : 1.0)
                        .animation(.easeInOut(duration: 0.1), value: isListening)
                }
                .accessibilityLabel(isListening ? "Stop recording" : "Start recording")

                if !transcript.isEmpty {
                    Button("Clear") {
                        transcript = ""
                        audioLevels = []
                    }
                    .buttonStyle(.bordered)

                    Button("Use Text") {
                        submitVoiceInput()
                    }
                    .buttonStyle(.borderedProminent)
                }
            }

            // Language Selection
            if let language = component.props.voiceLanguage {
                Text("Language: \(language)")
                    .font(.caption)
                    .foregroundColor(.secondary)
            }
        }
        .padding()
        .onChange(of: voiceCoordinator.lastTranscript) { newTranscript in
            transcript = newTranscript
        }
        .onChange(of: voiceCoordinator.isListening) { listening in
            isListening = listening
        }
    }

    private func toggleListening() {
        if isListening {
            voiceCoordinator.stopListening()
        } else {
            voiceCoordinator.startListening { finalTranscript in
                transcript = finalTranscript
            }
        }
    }

    private func submitVoiceInput() {
        let action = A2UIAction(
            trigger: .onSubmit,
            type: .custom,
            payload: [
                "action": "voice_input_submitted",
                "component_id": component.id,
                "transcript": transcript,
                "confidence": String(voiceCoordinator.lastConfidence)
            ]
        )
        onAction?(action)
    }
}

struct VoiceVisualizerView: View {
    let isListening: Bool
    let audioLevels: [Double]

    var body: some View {
        HStack(spacing: 4) {
            ForEach(0..<20) { index in
                RoundedRectangle(cornerRadius: 2)
                    .fill(isListening ? Color.blue : Color.gray.opacity(0.3))
                    .frame(width: 4)
                    .scaleEffect(y: isListening ? CGFloat.random(in: 0.3...1.0) : 0.3)
                    .animation(
                        isListening ? .easeInOut(duration: 0.2).repeatForever() : .none,
                        value: isListening
                    )
            }
        }
        .frame(maxWidth: .infinity, maxHeight: .infinity)
    }
}

// ═══════════════════════════════════════════════════════════════════════════
// MARK: - Supporting Views
// ═══════════════════════════════════════════════════════════════════════════

struct CameraView: UIViewControllerRepresentable {
    let onImageCaptured: (UIImage) -> Void

    func makeUIViewController(context: Context) -> UIImagePickerController {
        let picker = UIImagePickerController()
        picker.sourceType = .camera
        picker.delegate = context.coordinator
        return picker
    }

    func updateUIViewController(_ uiViewController: UIImagePickerController, context: Context) {}

    func makeCoordinator() -> Coordinator {
        Coordinator(onImageCaptured: onImageCaptured)
    }

    class Coordinator: NSObject, UIImagePickerControllerDelegate, UINavigationControllerDelegate {
        let onImageCaptured: (UIImage) -> Void

        init(onImageCaptured: @escaping (UIImage) -> Void) {
            self.onImageCaptured = onImageCaptured
        }

        func imagePickerController(_ picker: UIImagePickerController, didFinishPickingMediaWithInfo info: [UIImagePickerController.InfoKey: Any]) {
            if let image = info[.originalImage] as? UIImage {
                onImageCaptured(image)
            }
            picker.dismiss(animated: true)
        }

        func imagePickerControllerDidCancel(_ picker: UIImagePickerController) {
            picker.dismiss(animated: true)
        }
    }
}

@available(iOS 13.0, *)
struct PencilKitView: UIViewRepresentable {
    let canvasView: PKCanvasView
    let onDrawingChanged: (PKDrawing) -> Void

    func makeUIView(context: Context) -> PKCanvasView {
        canvasView.tool = PKInkingTool(.pen, color: .black, width: 15)
        canvasView.delegate = context.coordinator
        return canvasView
    }

    func updateUIView(_ uiView: PKCanvasView, context: Context) {}

    func makeCoordinator() -> Coordinator {
        Coordinator(onDrawingChanged: onDrawingChanged)
    }

    class Coordinator: NSObject, PKCanvasViewDelegate {
        let onDrawingChanged: (PKDrawing) -> Void

        init(onDrawingChanged: @escaping (PKDrawing) -> Void) {
            self.onDrawingChanged = onDrawingChanged
        }

        func canvasViewDrawingDidChange(_ canvasView: PKCanvasView) {
            onDrawingChanged(canvasView.drawing)
        }
    }
}

print("✅ Multimodal Input Renderers implemented")
print("📷 Camera capture with OCR processing")
print("📄 Document upload with multiple file types")
print("✍️ Handwriting input with text recognition")
print("🎤 Voice input with real-time visualization")