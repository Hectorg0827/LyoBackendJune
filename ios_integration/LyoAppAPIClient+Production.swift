// LyoAppAPIClient+Production.swift
// Lyo
//
// Production configuration for LyoAppAPIClient
// Copy this file to: Lyo/Services/LyoAppAPIClient+Production.swift
//
// IMPORTANT: This file updates the base URL for production deployment

import Foundation
import Combine

// MARK: - Production Configuration

extension LyoAppAPIClient {
    
    /// Production base URL for LyoBackend
    static let productionBaseURL = "https://lyo-backend-production-830162750094.us-central1.run.app"
    
    /// Development base URL (local)
    static let developmentBaseURL = "http://localhost:8000"
    
    /// Configure the API client for production
    static func configureForProduction() {
        // Update shared instance to use production URL
        // This should be called in AppDelegate or App init
        shared.updateBaseURL(to: productionBaseURL)
    }
    
    /// Configure the API client for development
    static func configureForDevelopment() {
        shared.updateBaseURL(to: developmentBaseURL)
    }
    
    /// Update base URL dynamically
    func updateBaseURL(to newURL: String) {
        // Note: This requires making baseURL a var in LyoAppAPIClient
        // If baseURL is a let constant, modify LyoAppAPIClient.swift directly
        UserDefaults.standard.set(newURL, forKey: "lyo_api_base_url")
    }
    
    /// Get current base URL (with production as default)
    static var currentBaseURL: String {
        #if DEBUG
        return UserDefaults.standard.string(forKey: "lyo_api_base_url") ?? developmentBaseURL
        #else
        return productionBaseURL
        #endif
    }
}

// MARK: - Environment Configuration

enum APIEnvironment {
    case development
    case staging
    case production
    
    var baseURL: String {
        switch self {
        case .development:
            return Endpoints.development.absoluteString
        case .staging:
            return Endpoints.staging.absoluteString
        case .production:
            return Endpoints.production.absoluteString
        }
    }
    
    var apiPath: String {
        return "/\(Endpoints.Version.v1.rawValue)"
    }
    
    static var current: APIEnvironment {
        #if DEBUG
        return .development
        #else
        return .production
        #endif
    }
}


// MARK: - App Initialization Helper

/*
 Add to your App.swift or AppDelegate:
 
 @main
 struct LyoApp: App {
     init() {
         // Configure API for production in release builds
         #if !DEBUG
         LyoAppAPIClient.configureForProduction()
         #endif
     }
     
     var body: some Scene {
         WindowGroup {
             ContentView()
         }
     }
 }
*/
