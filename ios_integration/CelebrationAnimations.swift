// CelebrationAnimations.swift
// Lyo
//
// Celebration animations for milestone achievements
// Copy this file to: Lyo/Views/Components/CelebrationAnimations.swift
//
// Works with backend CelebrationService to show beautiful animations
// at key learning moments

import SwiftUI
import AVFoundation

// MARK: - Celebration Types

enum CelebrationType: String, Codable {
    case confetti
    case fireworks
    case stars
    case levelUp
    case streak
    case trophy
    case sparkle
    case glow
    
    var soundEffect: String {
        switch self {
        case .confetti: return "celebration_pop"
        case .fireworks: return "celebration_firework"
        case .stars: return "celebration_sparkle"
        case .levelUp: return "celebration_levelup"
        case .streak: return "celebration_streak"
        case .trophy: return "celebration_trophy"
        case .sparkle: return "celebration_sparkle"
        case .glow: return "celebration_glow"
        }
    }
    
    var duration: Double {
        switch self {
        case .confetti: return 2.5
        case .fireworks: return 3.0
        case .stars: return 2.0
        case .levelUp: return 3.5
        case .streak: return 2.5
        case .trophy: return 3.0
        case .sparkle: return 1.5
        case .glow: return 2.0
        }
    }
}

// MARK: - Celebration Data (from backend)

struct CelebrationData: Codable {
    let type: String
    let message: String?
    let xpEarned: Int?
    let newBadge: String?
    let streakCount: Int?
    let newLevel: Int?
    
    enum CodingKeys: String, CodingKey {
        case type
        case message
        case xpEarned = "xp_earned"
        case newBadge = "new_badge"
        case streakCount = "streak_count"
        case newLevel = "new_level"
    }
}

// MARK: - Celebration Overlay View

struct CelebrationOverlay: View {
    let celebration: CelebrationData
    @State private var isAnimating = false
    @State private var particles: [Particle] = []
    
    var body: some View {
        ZStack {
            // Particle effects
            ForEach(particles) { particle in
                ParticleView(particle: particle)
            }
            
            // Main celebration content
            VStack(spacing: 20) {
                celebrationIcon
                    .scaleEffect(isAnimating ? 1.2 : 0.5)
                    .opacity(isAnimating ? 1 : 0)
                
                if let message = celebration.message {
                    Text(message)
                        .font(.title2)
                        .fontWeight(.bold)
                        .foregroundColor(.white)
                        .multilineTextAlignment(.center)
                        .opacity(isAnimating ? 1 : 0)
                }
                
                HStack(spacing: 30) {
                    if let xp = celebration.xpEarned, xp > 0 {
                        StatBadge(icon: "star.fill", value: "+\(xp) XP", color: .yellow)
                    }
                    
                    if let streak = celebration.streakCount {
                        StatBadge(icon: "flame.fill", value: "\(streak) Day Streak!", color: .orange)
                    }
                    
                    if let level = celebration.newLevel {
                        StatBadge(icon: "arrow.up.circle.fill", value: "Level \(level)!", color: .green)
                    }
                }
                .opacity(isAnimating ? 1 : 0)
                .offset(y: isAnimating ? 0 : 20)
            }
        }
        .onAppear {
            generateParticles()
            playSound()
            withAnimation(.spring(response: 0.5, dampingFraction: 0.6)) {
                isAnimating = true
            }
        }
    }
    
    @ViewBuilder
    private var celebrationIcon: some View {
        switch CelebrationType(rawValue: celebration.type) ?? .sparkle {
        case .confetti:
            Image(systemName: "party.popper.fill")
                .font(.system(size: 80))
                .foregroundColor(.pink)
        case .fireworks:
            Image(systemName: "sparkles")
                .font(.system(size: 80))
                .foregroundColor(.yellow)
        case .stars:
            Image(systemName: "star.fill")
                .font(.system(size: 80))
                .foregroundColor(.yellow)
        case .levelUp:
            Image(systemName: "arrow.up.circle.fill")
                .font(.system(size: 80))
                .foregroundColor(.green)
        case .streak:
            Image(systemName: "flame.fill")
                .font(.system(size: 80))
                .foregroundColor(.orange)
        case .trophy:
            Image(systemName: "trophy.fill")
                .font(.system(size: 80))
                .foregroundColor(.yellow)
        case .sparkle:
            Image(systemName: "sparkle")
                .font(.system(size: 80))
                .foregroundColor(.blue)
        case .glow:
            Image(systemName: "sun.max.fill")
                .font(.system(size: 80))
                .foregroundColor(.yellow)
        }
    }
    
    private func generateParticles() {
        let particleCount = 50
        let colors: [Color] = [.red, .orange, .yellow, .green, .blue, .purple, .pink]
        
        particles = (0..<particleCount).map { _ in
            Particle(
                x: CGFloat.random(in: 0...UIScreen.main.bounds.width),
                y: CGFloat.random(in: -100...0),
                color: colors.randomElement() ?? .white,
                scale: CGFloat.random(in: 0.5...1.5),
                speed: CGFloat.random(in: 2...6)
            )
        }
    }
    
    private func playSound() {
        let type = CelebrationType(rawValue: celebration.type) ?? .sparkle
        SoundManager.shared.play(type.soundEffect)
    }
}

// MARK: - Particle System

struct Particle: Identifiable {
    let id = UUID()
    var x: CGFloat
    var y: CGFloat
    let color: Color
    let scale: CGFloat
    let speed: CGFloat
}

struct ParticleView: View {
    let particle: Particle
    @State private var offset: CGFloat = 0
    @State private var rotation: Double = 0
    
    var body: some View {
        Rectangle()
            .fill(particle.color)
            .frame(width: 10 * particle.scale, height: 10 * particle.scale)
            .rotationEffect(.degrees(rotation))
            .position(x: particle.x, y: particle.y + offset)
            .onAppear {
                withAnimation(.linear(duration: 3).repeatForever(autoreverses: false)) {
                    offset = UIScreen.main.bounds.height + 200
                }
                withAnimation(.linear(duration: 1).repeatForever(autoreverses: false)) {
                    rotation = 360
                }
            }
    }
}

// MARK: - Stat Badge

struct StatBadge: View {
    let icon: String
    let value: String
    let color: Color
    
    var body: some View {
        HStack(spacing: 6) {
            Image(systemName: icon)
                .foregroundColor(color)
            Text(value)
                .font(.headline)
                .foregroundColor(.white)
        }
        .padding(.horizontal, 12)
        .padding(.vertical, 8)
        .background(Color.black.opacity(0.5))
        .cornerRadius(20)
    }
}

// MARK: - Confetti View (Standalone)

struct ConfettiView: View {
    @Binding var isActive: Bool
    
    var body: some View {
        GeometryReader { geometry in
            ZStack {
                ForEach(0..<100) { index in
                    ConfettiPiece(
                        bounds: geometry.size,
                        delay: Double(index) * 0.02
                    )
                }
            }
        }
        .opacity(isActive ? 1 : 0)
        .animation(.easeInOut(duration: 0.3), value: isActive)
    }
}

struct ConfettiPiece: View {
    let bounds: CGSize
    let delay: Double
    
    @State private var position: CGPoint = .zero
    @State private var rotation: Double = 0
    @State private var scale: CGFloat = 1
    
    private let colors: [Color] = [.red, .orange, .yellow, .green, .blue, .purple, .pink]
    private let shapes = ["circle", "rectangle", "capsule"]
    
    var body: some View {
        confettiShape
            .fill(colors.randomElement() ?? .white)
            .frame(width: CGFloat.random(in: 8...15), height: CGFloat.random(in: 8...15))
            .scaleEffect(scale)
            .rotationEffect(.degrees(rotation))
            .position(position)
            .onAppear {
                position = CGPoint(
                    x: CGFloat.random(in: 0...bounds.width),
                    y: -20
                )
                
                DispatchQueue.main.asyncAfter(deadline: .now() + delay) {
                    withAnimation(.linear(duration: Double.random(in: 2...4))) {
                        position = CGPoint(
                            x: position.x + CGFloat.random(in: -100...100),
                            y: bounds.height + 20
                        )
                    }
                    
                    withAnimation(.linear(duration: 0.3).repeatForever(autoreverses: true)) {
                        scale = CGFloat.random(in: 0.5...1.5)
                    }
                    
                    withAnimation(.linear(duration: 1).repeatForever(autoreverses: false)) {
                        rotation = 360
                    }
                }
            }
    }
    
    @ViewBuilder
    private var confettiShape: some Shape {
        let shape = shapes.randomElement() ?? "circle"
        switch shape {
        case "circle":
            Circle()
        case "rectangle":
            Rectangle()
        default:
            Capsule()
        }
    }
}

// MARK: - Fireworks View

struct FireworksView: View {
    @Binding var isActive: Bool
    @State private var explosions: [FireworkExplosion] = []
    
    var body: some View {
        GeometryReader { geometry in
            ZStack {
                ForEach(explosions) { explosion in
                    FireworkExplosionView(explosion: explosion)
                }
            }
            .onAppear {
                startFireworks(in: geometry.size)
            }
        }
        .opacity(isActive ? 1 : 0)
    }
    
    private func startFireworks(in bounds: CGSize) {
        for i in 0..<5 {
            DispatchQueue.main.asyncAfter(deadline: .now() + Double(i) * 0.5) {
                let explosion = FireworkExplosion(
                    position: CGPoint(
                        x: CGFloat.random(in: bounds.width * 0.2...bounds.width * 0.8),
                        y: CGFloat.random(in: bounds.height * 0.2...bounds.height * 0.5)
                    ),
                    color: [Color.red, .orange, .yellow, .green, .blue, .purple].randomElement() ?? .white
                )
                explosions.append(explosion)
            }
        }
    }
}

struct FireworkExplosion: Identifiable {
    let id = UUID()
    let position: CGPoint
    let color: Color
}

struct FireworkExplosionView: View {
    let explosion: FireworkExplosion
    @State private var isExploding = false
    
    var body: some View {
        ZStack {
            ForEach(0..<12) { index in
                Circle()
                    .fill(explosion.color)
                    .frame(width: 8, height: 8)
                    .offset(x: isExploding ? 100 : 0)
                    .rotationEffect(.degrees(Double(index) * 30))
                    .opacity(isExploding ? 0 : 1)
            }
        }
        .position(explosion.position)
        .onAppear {
            withAnimation(.easeOut(duration: 1)) {
                isExploding = true
            }
        }
    }
}

// MARK: - Glow Effect

struct GlowEffectView: View {
    @Binding var isActive: Bool
    let color: Color
    
    @State private var glowRadius: CGFloat = 0
    
    var body: some View {
        Circle()
            .fill(
                RadialGradient(
                    gradient: Gradient(colors: [color.opacity(0.5), color.opacity(0)]),
                    center: .center,
                    startRadius: 0,
                    endRadius: glowRadius
                )
            )
            .frame(width: 300, height: 300)
            .opacity(isActive ? 1 : 0)
            .onAppear {
                withAnimation(.easeInOut(duration: 1).repeatForever(autoreverses: true)) {
                    glowRadius = 150
                }
            }
    }
}

// MARK: - Sound Manager

class SoundManager {
    static let shared = SoundManager()
    private var audioPlayer: AVAudioPlayer?
    
    func play(_ sound: String) {
        guard let url = Bundle.main.url(forResource: sound, withExtension: "mp3") else {
            print("Sound file not found: \(sound)")
            return
        }
        
        do {
            audioPlayer = try AVAudioPlayer(contentsOf: url)
            audioPlayer?.play()
        } catch {
            print("Error playing sound: \(error)")
        }
    }
}

// MARK: - View Modifiers

struct CelebrationModifier: ViewModifier {
    @Binding var celebration: CelebrationData?
    @State private var showOverlay = false
    
    func body(content: Content) -> some View {
        ZStack {
            content
            
            if showOverlay, let celebration = celebration {
                Color.black.opacity(0.6)
                    .ignoresSafeArea()
                    .transition(.opacity)
                
                CelebrationOverlay(celebration: celebration)
                    .transition(.scale.combined(with: .opacity))
            }
        }
        .onChange(of: celebration != nil) { hasNewCelebration in
            if hasNewCelebration {
                withAnimation(.spring()) {
                    showOverlay = true
                }
                
                // Auto-dismiss after animation duration
                if let type = CelebrationType(rawValue: celebration?.type ?? "") {
                    DispatchQueue.main.asyncAfter(deadline: .now() + type.duration) {
                        withAnimation(.easeOut) {
                            showOverlay = false
                        }
                        DispatchQueue.main.asyncAfter(deadline: .now() + 0.3) {
                            self.celebration = nil
                        }
                    }
                }
            }
        }
    }
}

extension View {
    func celebration(_ celebration: Binding<CelebrationData?>) -> some View {
        modifier(CelebrationModifier(celebration: celebration))
    }
}

// MARK: - Quick Celebration Trigger

extension View {
    func quickCelebration(
        type: CelebrationType,
        isPresented: Binding<Bool>,
        message: String? = nil,
        xpEarned: Int? = nil
    ) -> some View {
        self.overlay {
            if isPresented.wrappedValue {
                CelebrationOverlay(
                    celebration: CelebrationData(
                        type: type.rawValue,
                        message: message,
                        xpEarned: xpEarned,
                        newBadge: nil,
                        streakCount: nil,
                        newLevel: nil
                    )
                )
                .onAppear {
                    DispatchQueue.main.asyncAfter(deadline: .now() + type.duration) {
                        isPresented.wrappedValue = false
                    }
                }
            }
        }
    }
}

// MARK: - Usage Examples

/*
 // Example 1: Show celebration from backend response
 
 @State private var currentCelebration: CelebrationData?
 
 var body: some View {
     InteractiveCinemaView(courseId: courseId)
         .celebration($currentCelebration)
 }
 
 // Example 2: Quick celebration
 
 @State private var showConfetti = false
 
 Button("Complete Lesson") {
     // ... complete lesson logic
     showConfetti = true
 }
 .quickCelebration(type: .confetti, isPresented: $showConfetti, message: "Great job!", xpEarned: 25)
 
 // Example 3: Inline confetti
 
 ZStack {
     ContentView()
     ConfettiView(isActive: $showConfetti)
 }
 */
