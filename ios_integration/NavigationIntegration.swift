// NavigationIntegration.swift
// Lyo
//
// How to integrate AI Classroom into your app's navigation
// Copy the relevant code snippets to your existing navigation files
//
// PRODUCTION URL: https://lyo-backend-production-830162750094.us-central1.run.app

import SwiftUI

// MARK: - Tab Bar Integration (if using TabView)

/*
 Add to your main TabView:
 
 TabView {
     // Your existing tabs...
     
     NavigationStack {
         AIClassroomView()
     }
     .tabItem {
         Image(systemName: "sparkles")
         Text("AI Classroom")
     }
 }
*/

// MARK: - Navigation Link Integration (if using NavigationStack)

/*
 Add to any view's navigation:
 
 NavigationLink {
     AIClassroomView()
 } label: {
     HStack {
         Image(systemName: "sparkles")
             .foregroundColor(.purple)
         VStack(alignment: .leading) {
             Text("AI Classroom")
                 .font(.headline)
             Text("Learn anything with AI")
                 .font(.caption)
                 .foregroundColor(.secondary)
         }
     }
 }
*/

// MARK: - Sheet Presentation

/*
 Present as a sheet:
 
 @State private var showAIClassroom = false
 
 Button("Open AI Classroom") {
     showAIClassroom = true
 }
 .sheet(isPresented: $showAIClassroom) {
     NavigationStack {
         AIClassroomView()
     }
 }
*/

// MARK: - Full Screen Cover

/*
 Present as full screen:
 
 @State private var showAIClassroom = false
 
 Button("Open AI Classroom") {
     showAIClassroom = true
 }
 .fullScreenCover(isPresented: $showAIClassroom) {
     NavigationStack {
         AIClassroomView()
     }
 }
*/

// MARK: - Floating Action Button Integration

struct AIClassroomFloatingButton: View {
    @State private var showAIClassroom = false
    
    var body: some View {
        Button(action: { showAIClassroom = true }) {
            Image(systemName: "sparkles")
                .font(.title2)
                .foregroundColor(.white)
                .frame(width: 56, height: 56)
                .background(
                    LinearGradient(
                        colors: [.purple, .blue],
                        startPoint: .topLeading,
                        endPoint: .bottomTrailing
                    )
                )
                .clipShape(Circle())
                .shadow(color: .purple.opacity(0.3), radius: 8, x: 0, y: 4)
        }
        .fullScreenCover(isPresented: $showAIClassroom) {
            NavigationStack {
                AIClassroomView()
            }
        }
    }
}

// MARK: - Home Screen Card Integration

struct AIClassroomCard: View {
    @State private var showAIClassroom = false
    
    var body: some View {
        Button(action: { showAIClassroom = true }) {
            VStack(alignment: .leading, spacing: 12) {
                HStack {
                    Image(systemName: "sparkles")
                        .font(.title)
                        .foregroundColor(.purple)
                    
                    Spacer()
                    
                    Text("NEW")
                        .font(.caption2)
                        .fontWeight(.bold)
                        .padding(.horizontal, 8)
                        .padding(.vertical, 4)
                        .background(Color.purple.opacity(0.2))
                        .foregroundColor(.purple)
                        .cornerRadius(8)
                }
                
                Text("AI Classroom")
                    .font(.headline)
                    .foregroundColor(.primary)
                
                Text("Ask anything, learn everything. Your personal AI tutor is ready.")
                    .font(.subheadline)
                    .foregroundColor(.secondary)
                    .lineLimit(2)
                
                HStack {
                    Label("TTS", systemImage: "speaker.wave.2.fill")
                    Label("Images", systemImage: "photo.fill")
                    Label("Courses", systemImage: "book.fill")
                }
                .font(.caption)
                .foregroundColor(.blue)
            }
            .padding()
            .background(Color(.systemBackground))
            .cornerRadius(16)
            .shadow(color: .black.opacity(0.1), radius: 8, x: 0, y: 2)
        }
        .buttonStyle(.plain)
        .fullScreenCover(isPresented: $showAIClassroom) {
            NavigationStack {
                AIClassroomView()
            }
        }
    }
}

// MARK: - Quick Access Button (for Toolbar)

struct AIClassroomToolbarButton: View {
    @State private var showAIClassroom = false
    
    var body: some View {
        Button(action: { showAIClassroom = true }) {
            Image(systemName: "sparkles")
        }
        .sheet(isPresented: $showAIClassroom) {
            NavigationStack {
                AIClassroomView()
            }
        }
    }
}

// MARK: - Usage Examples

/*
 
 // Example 1: Add to home screen
 struct HomeView: View {
     var body: some View {
         ScrollView {
             VStack(spacing: 16) {
                 // Your existing content...
                 
                 AIClassroomCard()
                     .padding(.horizontal)
             }
         }
     }
 }
 
 // Example 2: Add floating button overlay
 struct MainView: View {
     var body: some View {
         ZStack(alignment: .bottomTrailing) {
             // Your main content
             ContentView()
             
             // Floating AI button
             AIClassroomFloatingButton()
                 .padding()
         }
     }
 }
 
 // Example 3: Add to toolbar
 struct SomeView: View {
     var body: some View {
         NavigationStack {
             // Content...
         }
         .toolbar {
             ToolbarItem(placement: .topBarTrailing) {
                 AIClassroomToolbarButton()
             }
         }
     }
 }
 
*/

#Preview("Floating Button") {
    ZStack(alignment: .bottomTrailing) {
        Color(.systemBackground)
            .ignoresSafeArea()
        
        AIClassroomFloatingButton()
            .padding()
    }
}

#Preview("Card") {
    AIClassroomCard()
        .padding()
}
