import SwiftUI
import VisionKit
import PDFKit
import UniformTypeIdentifiers

struct A2UIDocumentUploadRenderer: View {
    let component: A2UIComponent

    @State private var showingDocumentPicker = false
    @State private var showingCamera = false
    @State private var processingDocument = false

    private var acceptedTypes: [String] {
        component.props["accepted_types"]?.arrayValue?.compactMap { $0.stringValue } ?? ["pdf", "image", "text"]
    }

    private var maxFileSize: Int {
        component.props["max_file_size"]?.intValue ?? 10 // MB
    }

    private var allowMultiple: Bool {
        component.props["allow_multiple"]?.boolValue ?? false
    }

    private var placeholder: String {
        component.props["placeholder"]?.stringValue ?? "Upload documents, photos, or handwritten notes"
    }

    var body: some View {
        VStack(spacing: 16) {
            VStack(spacing: 12) {
                Image(systemName: "doc.badge.plus")
                    .font(.largeTitle)
                    .foregroundColor(.blue)

                Text(placeholder)
                    .font(.headline)
                    .multilineTextAlignment(.center)
                    .foregroundColor(.primary)

                Text("Supported: \(acceptedTypes.joined(separator: ", ").uppercased())")
                    .font(.caption)
                    .foregroundColor(.secondary)

                Text("Max size: \(maxFileSize)MB")
                    .font(.caption2)
                    .foregroundColor(.secondary)
            }
            .padding(.vertical, 24)
            .frame(maxWidth: .infinity)
            .background(
                RoundedRectangle(cornerRadius: 12)
                    .stroke(Color.blue.opacity(0.3), style: StrokeStyle(lineWidth: 2, dash: [8, 4]))
            )

            HStack(spacing: 16) {
                Button(action: { showingDocumentPicker = true }) {
                    HStack {
                        Image(systemName: "folder")
                        Text("Browse Files")
                    }
                    .frame(maxWidth: .infinity)
                    .padding()
                    .background(Color.blue.opacity(0.1))
                    .foregroundColor(.blue)
                    .cornerRadius(8)
                }

                Button(action: { showingCamera = true }) {
                    HStack {
                        Image(systemName: "camera")
                        Text("Take Photo")
                    }
                    .frame(maxWidth: .infinity)
                    .padding()
                    .background(Color.green.opacity(0.1))
                    .foregroundColor(.green)
                    .cornerRadius(8)
                }
            }

            if processingDocument {
                HStack {
                    ProgressView()
                        .scaleEffect(0.8)

                    Text("Processing document...")
                        .font(.caption)
                        .foregroundColor(.secondary)
                }
                .padding()
                .background(Color.gray.opacity(0.1))
                .cornerRadius(8)
            }
        }
        .padding()
        .sheet(isPresented: $showingDocumentPicker) {
            DocumentPickerView(
                acceptedTypes: acceptedTypes,
                allowMultiple: allowMultiple,
                onDocumentSelected: handleDocumentSelection
            )
        }
        .sheet(isPresented: $showingCamera) {
            CameraView(onImageCaptured: handleImageCapture)
        }
    }

    private func handleDocumentSelection(_ urls: [URL]) {
        processingDocument = true

        A2UIActionHandler.shared.handleAction(
            type: .custom,
            payload: [
                "action": "process_documents",
                "document_urls": urls.map { $0.absoluteString },
                "component_id": component.id
            ]
        )

        DispatchQueue.main.asyncAfter(deadline: .now() + 2) {
            processingDocument = false
        }
    }

    private func handleImageCapture(_ image: UIImage) {
        processingDocument = true

        A2UIActionHandler.shared.handleAction(
            type: .custom,
            payload: [
                "action": "process_image",
                "image_data": image.pngData()?.base64EncodedString() ?? "",
                "component_id": component.id
            ]
        )

        DispatchQueue.main.asyncAfter(deadline: .now() + 2) {
            processingDocument = false
        }
    }
}

struct A2UIOCRResultRenderer: View {
    let component: A2UIComponent

    private var extractedText: String {
        component.props["extracted_text"]?.stringValue ?? ""
    }

    private var confidence: Double {
        component.props["confidence"]?.doubleValue ?? 0.0
    }

    private var sourceType: String {
        component.props["source_type"]?.stringValue ?? "document"
    }

    private var processedSections: [OCRSection] {
        guard let sectionsArray = component.props["sections"]?.arrayValue else { return [] }
        return sectionsArray.compactMap { value in
            guard let dict = value.dictionaryValue else { return nil }
            return OCRSection(
                type: dict["type"]?.stringValue ?? "text",
                content: dict["content"]?.stringValue ?? "",
                confidence: dict["confidence"]?.doubleValue ?? 0.0,
                boundingBox: dict["bounding_box"]?.stringValue ?? ""
            )
        }
    }

    @State private var selectedSection: OCRSection?
    @State private var showingFullText = false

    var body: some View {
        VStack(alignment: .leading, spacing: 16) {
            HStack {
                VStack(alignment: .leading, spacing: 4) {
                    Text("Extracted Content")
                        .font(.headline)
                        .fontWeight(.semibold)

                    Text("From \(sourceType)")
                        .font(.caption)
                        .foregroundColor(.secondary)
                }

                Spacer()

                VStack(alignment: .trailing, spacing: 4) {
                    HStack {
                        Circle()
                            .fill(confidenceColor)
                            .frame(width: 8, height: 8)

                        Text("\(Int(confidence * 100))% confident")
                            .font(.caption)
                            .foregroundColor(confidenceColor)
                    }

                    Button("View All") {
                        showingFullText = true
                    }
                    .font(.caption2)
                    .foregroundColor(.blue)
                }
            }

            if !processedSections.isEmpty {
                LazyVStack(alignment: .leading, spacing: 8) {
                    ForEach(Array(processedSections.enumerated()), id: \.offset) { index, section in
                        Button(action: { selectedSection = section }) {
                            HStack {
                                VStack(alignment: .leading, spacing: 4) {
                                    HStack {
                                        Image(systemName: sectionIcon(for: section.type))
                                            .font(.caption)
                                            .foregroundColor(.blue)

                                        Text(section.type.capitalized)
                                            .font(.caption)
                                            .fontWeight(.medium)
                                            .foregroundColor(.primary)

                                        Spacer()

                                        Text("\(Int(section.confidence * 100))%")
                                            .font(.caption2)
                                            .foregroundColor(.secondary)
                                    }

                                    Text(section.content)
                                        .font(.caption)
                                        .foregroundColor(.secondary)
                                        .lineLimit(2)
                                        .multilineTextAlignment(.leading)
                                }

                                Spacer()

                                Image(systemName: "chevron.right")
                                    .font(.caption2)
                                    .foregroundColor(.secondary)
                            }
                        }
                        .buttonStyle(PlainButtonStyle())
                        .padding()
                        .background(Color.gray.opacity(0.05))
                        .cornerRadius(8)
                    }
                }
            } else if !extractedText.isEmpty {
                ScrollView {
                    Text(extractedText)
                        .font(.body)
                        .foregroundColor(.primary)
                        .fixedSize(horizontal: false, vertical: true)
                }
                .frame(maxHeight: 200)
                .padding()
                .background(Color.gray.opacity(0.05))
                .cornerRadius(8)
            }

            HStack {
                Button("Generate Notes") {
                    A2UIActionHandler.shared.handleAction(
                        type: .custom,
                        payload: [
                            "action": "generate_notes",
                            "extracted_text": extractedText,
                            "component_id": component.id
                        ]
                    )
                }
                .padding(.horizontal, 12)
                .padding(.vertical, 6)
                .background(Color.blue.opacity(0.1))
                .foregroundColor(.blue)
                .cornerRadius(6)

                Button("Create Flashcards") {
                    A2UIActionHandler.shared.handleAction(
                        type: .custom,
                        payload: [
                            "action": "create_flashcards",
                            "extracted_text": extractedText,
                            "component_id": component.id
                        ]
                    )
                }
                .padding(.horizontal, 12)
                .padding(.vertical, 6)
                .background(Color.green.opacity(0.1))
                .foregroundColor(.green)
                .cornerRadius(6)

                Spacer()

                Button("Save Text") {
                    A2UIActionHandler.shared.handleAction(
                        type: .custom,
                        payload: [
                            "action": "save_extracted_text",
                            "text": extractedText,
                            "component_id": component.id
                        ]
                    )
                }
                .padding(.horizontal, 12)
                .padding(.vertical, 6)
                .background(Color.orange.opacity(0.1))
                .foregroundColor(.orange)
                .cornerRadius(6)
            }
        }
        .padding()
        .sheet(item: $selectedSection) { section in
            OCRSectionDetailView(section: section)
        }
        .sheet(isPresented: $showingFullText) {
            FullTextView(text: extractedText)
        }
    }

    private var confidenceColor: Color {
        if confidence > 0.8 {
            return .green
        } else if confidence > 0.6 {
            return .orange
        } else {
            return .red
        }
    }

    private func sectionIcon(for type: String) -> String {
        switch type.lowercased() {
        case "heading": return "text.format"
        case "paragraph": return "text.alignleft"
        case "table": return "tablecells"
        case "image": return "photo"
        case "formula": return "function"
        case "handwriting": return "pencil"
        default: return "text.quote"
        }
    }
}

struct A2UIDocumentLibraryRenderer: View {
    let component: A2UIComponent

    private var documents: [ProcessedDocument] {
        guard let docsArray = component.props["documents"]?.arrayValue else { return [] }
        return docsArray.compactMap { value in
            guard let dict = value.dictionaryValue else { return nil }
            return ProcessedDocument(
                id: dict["id"]?.stringValue ?? "",
                name: dict["name"]?.stringValue ?? "",
                type: dict["type"]?.stringValue ?? "document",
                uploadDate: dict["upload_date"]?.stringValue ?? "",
                processingStatus: dict["processing_status"]?.stringValue ?? "completed",
                tags: dict["tags"]?.arrayValue?.compactMap { $0.stringValue } ?? [],
                hasNotes: dict["has_notes"]?.boolValue ?? false,
                hasFlashcards: dict["has_flashcards"]?.boolValue ?? false
            )
        }
    }

    @State private var selectedDocument: ProcessedDocument?
    @State private var searchText = ""

    var body: some View {
        VStack(alignment: .leading, spacing: 16) {
            HStack {
                Text("Document Library")
                    .font(.title2)
                    .fontWeight(.semibold)

                Spacer()

                Button(action: {
                    A2UIActionHandler.shared.handleAction(
                        type: .custom,
                        payload: ["action": "upload_new_document"]
                    )
                }) {
                    Image(systemName: "plus.circle")
                        .font(.title3)
                        .foregroundColor(.blue)
                }
            }

            SearchBar(text: $searchText, placeholder: "Search documents...")

            if !filteredDocuments.isEmpty {
                LazyVStack(spacing: 12) {
                    ForEach(filteredDocuments, id: \.id) { document in
                        DocumentRow(
                            document: document,
                            onTap: { selectedDocument = document }
                        )
                    }
                }
            } else {
                VStack(spacing: 12) {
                    Image(systemName: "doc.text")
                        .font(.largeTitle)
                        .foregroundColor(.secondary)

                    Text(searchText.isEmpty ? "No documents uploaded yet" : "No documents found")
                        .font(.subheadline)
                        .foregroundColor(.secondary)

                    if searchText.isEmpty {
                        Button("Upload Your First Document") {
                            A2UIActionHandler.shared.handleAction(
                                type: .custom,
                                payload: ["action": "upload_new_document"]
                            )
                        }
                        .padding(.horizontal, 16)
                        .padding(.vertical, 8)
                        .background(Color.blue)
                        .foregroundColor(.white)
                        .cornerRadius(8)
                    }
                }
                .frame(maxWidth: .infinity)
                .padding(.vertical, 32)
            }
        }
        .padding()
        .sheet(item: $selectedDocument) { document in
            DocumentDetailView(document: document)
        }
    }

    private var filteredDocuments: [ProcessedDocument] {
        if searchText.isEmpty {
            return documents
        } else {
            return documents.filter { document in
                document.name.localizedCaseInsensitiveContains(searchText) ||
                document.tags.contains { $0.localizedCaseInsensitiveContains(searchText) }
            }
        }
    }
}

private struct DocumentRow: View {
    let document: ProcessedDocument
    let onTap: () -> Void

    private var statusColor: Color {
        switch document.processingStatus {
        case "completed": return .green
        case "processing": return .blue
        case "failed": return .red
        default: return .gray
        }
    }

    private var typeIcon: String {
        switch document.type.lowercased() {
        case "pdf": return "doc.richtext"
        case "image": return "photo"
        case "text": return "doc.text"
        default: return "doc"
        }
    }

    var body: some View {
        Button(action: onTap) {
            HStack {
                Image(systemName: typeIcon)
                    .font(.title3)
                    .foregroundColor(.blue)
                    .frame(width: 32)

                VStack(alignment: .leading, spacing: 4) {
                    Text(document.name)
                        .font(.subheadline)
                        .fontWeight(.medium)
                        .foregroundColor(.primary)
                        .lineLimit(1)

                    HStack {
                        Text(document.uploadDate)
                            .font(.caption)
                            .foregroundColor(.secondary)

                        if !document.tags.isEmpty {
                            Text("•")
                                .foregroundColor(.secondary)

                            Text(document.tags.prefix(2).joined(separator: ", "))
                                .font(.caption)
                                .foregroundColor(.secondary)
                                .lineLimit(1)
                        }
                    }

                    HStack(spacing: 8) {
                        if document.hasNotes {
                            Label("Notes", systemImage: "note.text")
                                .font(.caption2)
                                .foregroundColor(.blue)
                        }

                        if document.hasFlashcards {
                            Label("Cards", systemImage: "rectangle.stack")
                                .font(.caption2)
                                .foregroundColor(.green)
                        }
                    }
                }

                Spacer()

                VStack(alignment: .trailing, spacing: 4) {
                    Circle()
                        .fill(statusColor)
                        .frame(width: 8, height: 8)

                    if document.processingStatus == "processing" {
                        ProgressView()
                            .scaleEffect(0.6)
                    }
                }
            }
        }
        .buttonStyle(PlainButtonStyle())
        .padding()
        .background(Color.gray.opacity(0.05))
        .cornerRadius(8)
    }
}

private struct SearchBar: View {
    @Binding var text: String
    let placeholder: String

    var body: some View {
        HStack {
            Image(systemName: "magnifyingglass")
                .foregroundColor(.secondary)

            TextField(placeholder, text: $text)
                .textFieldStyle(PlainTextFieldStyle())

            if !text.isEmpty {
                Button(action: { text = "" }) {
                    Image(systemName: "xmark.circle.fill")
                        .foregroundColor(.secondary)
                }
            }
        }
        .padding(.horizontal, 12)
        .padding(.vertical, 8)
        .background(Color.gray.opacity(0.1))
        .cornerRadius(8)
    }
}

private struct DocumentDetailView: View {
    let document: ProcessedDocument

    var body: some View {
        NavigationView {
            VStack(alignment: .leading, spacing: 16) {
                HStack {
                    Image(systemName: "doc.richtext")
                        .font(.largeTitle)
                        .foregroundColor(.blue)

                    VStack(alignment: .leading, spacing: 4) {
                        Text(document.name)
                            .font(.headline)
                            .fontWeight(.semibold)

                        Text("Uploaded \(document.uploadDate)")
                            .font(.caption)
                            .foregroundColor(.secondary)
                    }

                    Spacer()
                }

                if !document.tags.isEmpty {
                    ScrollView(.horizontal, showsIndicators: false) {
                        HStack {
                            ForEach(document.tags, id: \.self) { tag in
                                Text(tag)
                                    .font(.caption)
                                    .padding(.horizontal, 8)
                                    .padding(.vertical, 4)
                                    .background(Color.blue.opacity(0.1))
                                    .foregroundColor(.blue)
                                    .cornerRadius(4)
                            }
                        }
                        .padding(.horizontal)
                    }
                }

                Spacer()

                VStack(spacing: 12) {
                    if document.hasNotes {
                        Button("View Generated Notes") {
                            // Handle action
                        }
                        .frame(maxWidth: .infinity)
                        .padding()
                        .background(Color.blue.opacity(0.1))
                        .foregroundColor(.blue)
                        .cornerRadius(8)
                    }

                    if document.hasFlashcards {
                        Button("Study Flashcards") {
                            // Handle action
                        }
                        .frame(maxWidth: .infinity)
                        .padding()
                        .background(Color.green.opacity(0.1))
                        .foregroundColor(.green)
                        .cornerRadius(8)
                    }

                    Button("View Original Document") {
                        // Handle action
                    }
                    .frame(maxWidth: .infinity)
                    .padding()
                    .background(Color.gray.opacity(0.1))
                    .foregroundColor(.primary)
                    .cornerRadius(8)
                }
            }
            .padding()
            .navigationTitle("Document Details")
            .navigationBarTitleDisplayMode(.inline)
        }
    }
}

private struct OCRSectionDetailView: View {
    let section: OCRSection

    var body: some View {
        NavigationView {
            ScrollView {
                VStack(alignment: .leading, spacing: 16) {
                    HStack {
                        Text("Confidence: \(Int(section.confidence * 100))%")
                            .font(.caption)
                            .foregroundColor(.secondary)

                        Spacer()
                    }

                    Text(section.content)
                        .font(.body)
                        .foregroundColor(.primary)
                        .fixedSize(horizontal: false, vertical: true)

                    Spacer()
                }
                .padding()
            }
            .navigationTitle(section.type.capitalized)
            .navigationBarTitleDisplayMode(.inline)
        }
    }
}

private struct FullTextView: View {
    let text: String

    var body: some View {
        NavigationView {
            ScrollView {
                Text(text)
                    .font(.body)
                    .foregroundColor(.primary)
                    .fixedSize(horizontal: false, vertical: true)
                    .padding()
            }
            .navigationTitle("Extracted Text")
            .navigationBarTitleDisplayMode(.inline)
        }
    }
}

// Supporting Views
private struct DocumentPickerView: UIViewControllerRepresentable {
    let acceptedTypes: [String]
    let allowMultiple: Bool
    let onDocumentSelected: ([URL]) -> Void

    func makeUIViewController(context: Context) -> UIDocumentPickerViewController {
        let types = acceptedTypes.compactMap { type in
            switch type.lowercased() {
            case "pdf": return UTType.pdf
            case "image": return UTType.image
            case "text": return UTType.text
            default: return nil
            }
        }

        let picker = UIDocumentPickerViewController(forOpeningContentTypes: types.isEmpty ? [.item] : types)
        picker.allowsMultipleSelection = allowMultiple
        picker.delegate = context.coordinator
        return picker
    }

    func updateUIViewController(_ uiViewController: UIDocumentPickerViewController, context: Context) {}

    func makeCoordinator() -> Coordinator {
        Coordinator(self)
    }

    class Coordinator: NSObject, UIDocumentPickerDelegate {
        let parent: DocumentPickerView

        init(_ parent: DocumentPickerView) {
            self.parent = parent
        }

        func documentPicker(_ controller: UIDocumentPickerViewController, didPickDocumentsAt urls: [URL]) {
            parent.onDocumentSelected(urls)
        }
    }
}

private struct CameraView: UIViewControllerRepresentable {
    let onImageCaptured: (UIImage) -> Void

    func makeUIViewController(context: Context) -> UIImagePickerController {
        let picker = UIImagePickerController()
        picker.sourceType = .camera
        picker.delegate = context.coordinator
        return picker
    }

    func updateUIViewController(_ uiViewController: UIImagePickerController, context: Context) {}

    func makeCoordinator() -> Coordinator {
        Coordinator(self)
    }

    class Coordinator: NSObject, UIImagePickerControllerDelegate, UINavigationControllerDelegate {
        let parent: CameraView

        init(_ parent: CameraView) {
            self.parent = parent
        }

        func imagePickerController(_ picker: UIImagePickerController, didFinishPickingMediaWithInfo info: [UIImagePickerController.InfoKey : Any]) {
            if let image = info[.originalImage] as? UIImage {
                parent.onImageCaptured(image)
            }
            picker.dismiss(animated: true)
        }
    }
}

private struct OCRSection: Identifiable {
    let id = UUID()
    let type: String
    let content: String
    let confidence: Double
    let boundingBox: String
}

private struct ProcessedDocument: Identifiable {
    let id: String
    let name: String
    let type: String
    let uploadDate: String
    let processingStatus: String
    let tags: [String]
    let hasNotes: Bool
    let hasFlashcards: Bool
}