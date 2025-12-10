// AdMobIntegration.swift
// Lyo
//
// AdMob Integration for Interactive Cinema (Hybrid Approach)
// Copy this file to: Lyo/Services/AdMobIntegration.swift
//
// This integrates with the backend's ad coordination system
// Server decides WHEN to show ads, client handles DISPLAY

import Foundation
import GoogleMobileAds
import SwiftUI

// MARK: - AdMob Manager

@MainActor
class LyoAdManager: NSObject, ObservableObject {
    static let shared = LyoAdManager()
    
    // MARK: - Published State
    
    @Published var isAdReady = false
    @Published var isShowingAd = false
    @Published var rewardEarned = false
    
    // MARK: - Ad Units (Replace with your actual ad unit IDs)
    
    private struct AdUnits {
        #if DEBUG
        // Test ad unit IDs
        static let interstitial = "ca-app-pub-3940256099942544/4411468910"
        static let rewarded = "ca-app-pub-3940256099942544/1712485313"
        static let banner = "ca-app-pub-3940256099942544/2934735716"
        #else
        // Production ad unit IDs - Replace with your actual IDs
        static let interstitial = "ca-app-pub-YOUR_ID/interstitial"
        static let rewarded = "ca-app-pub-YOUR_ID/rewarded"
        static let banner = "ca-app-pub-YOUR_ID/banner"
        #endif
    }
    
    // MARK: - Private Properties
    
    private var interstitialAd: GADInterstitialAd?
    private var rewardedAd: GADRewardedAd?
    private var presentingViewController: UIViewController?
    private var onAdComplete: ((Bool) -> Void)?
    
    // MARK: - Initialization
    
    override init() {
        super.init()
        setupNotifications()
        preloadAds()
    }
    
    // MARK: - Setup
    
    private func setupNotifications() {
        // Listen for ad show requests from InteractiveCinemaService
        NotificationCenter.default.addObserver(
            forName: .showAd,
            object: nil,
            queue: .main
        ) { [weak self] notification in
            guard let userInfo = notification.userInfo,
                  let adFormat = userInfo["adFormat"] as? String,
                  let placementType = userInfo["placementType"] as? String else {
                return
            }
            
            Task { @MainActor in
                self?.handleAdRequest(format: adFormat, placement: placementType)
            }
        }
    }
    
    // MARK: - Preload Ads
    
    func preloadAds() {
        preloadInterstitial()
        preloadRewarded()
    }
    
    private func preloadInterstitial() {
        let request = GADRequest()
        
        GADInterstitialAd.load(
            withAdUnitID: AdUnits.interstitial,
            request: request
        ) { [weak self] ad, error in
            if let error = error {
                print("Failed to load interstitial: \(error.localizedDescription)")
                return
            }
            
            self?.interstitialAd = ad
            self?.interstitialAd?.fullScreenContentDelegate = self
            self?.isAdReady = true
        }
    }
    
    private func preloadRewarded() {
        let request = GADRequest()
        
        GADRewardedAd.load(
            withAdUnitID: AdUnits.rewarded,
            request: request
        ) { [weak self] ad, error in
            if let error = error {
                print("Failed to load rewarded: \(error.localizedDescription)")
                return
            }
            
            self?.rewardedAd = ad
            self?.rewardedAd?.fullScreenContentDelegate = self
        }
    }
    
    // MARK: - Handle Ad Request (from backend)
    
    private func handleAdRequest(format: String, placement: String) {
        switch format.lowercased() {
        case "interstitial":
            showInterstitial(placement: placement)
        case "rewarded":
            showRewarded(placement: placement)
        default:
            print("Unknown ad format: \(format)")
        }
    }
    
    // MARK: - Show Interstitial
    
    func showInterstitial(placement: String, completion: ((Bool) -> Void)? = nil) {
        guard let ad = interstitialAd else {
            print("Interstitial not ready, preloading...")
            preloadInterstitial()
            completion?(false)
            return
        }
        
        guard let rootVC = getRootViewController() else {
            completion?(false)
            return
        }
        
        onAdComplete = completion
        isShowingAd = true
        
        ad.present(fromRootViewController: rootVC)
        
        // Report impression to backend
        Task {
            await InteractiveCinemaService.shared.reportAdImpression(
                adUnitId: AdUnits.interstitial,
                placementType: placement
            )
        }
    }
    
    // MARK: - Show Rewarded
    
    func showRewarded(placement: String, completion: ((Bool) -> Void)? = nil) {
        guard let ad = rewardedAd else {
            print("Rewarded not ready, preloading...")
            preloadRewarded()
            completion?(false)
            return
        }
        
        guard let rootVC = getRootViewController() else {
            completion?(false)
            return
        }
        
        onAdComplete = completion
        isShowingAd = true
        rewardEarned = false
        
        ad.present(fromRootViewController: rootVC) { [weak self] in
            // User earned reward
            let reward = ad.adReward
            print("User earned reward: \(reward.amount) \(reward.type)")
            self?.rewardEarned = true
        }
        
        // Report impression to backend
        Task {
            await InteractiveCinemaService.shared.reportAdImpression(
                adUnitId: AdUnits.rewarded,
                placementType: placement
            )
        }
    }
    
    // MARK: - Helpers
    
    private func getRootViewController() -> UIViewController? {
        guard let windowScene = UIApplication.shared.connectedScenes.first as? UIWindowScene,
              let rootVC = windowScene.windows.first?.rootViewController else {
            return nil
        }
        
        // Get the top-most presented view controller
        var topVC = rootVC
        while let presented = topVC.presentedViewController {
            topVC = presented
        }
        
        return topVC
    }
}

// MARK: - Full Screen Content Delegate

extension LyoAdManager: GADFullScreenContentDelegate {
    func adDidDismissFullScreenContent(_ ad: GADFullScreenPresentingAd) {
        isShowingAd = false
        
        // Reload ad for next time
        if ad is GADInterstitialAd {
            preloadInterstitial()
            onAdComplete?(true)
        } else if ad is GADRewardedAd {
            preloadRewarded()
            onAdComplete?(rewardEarned)
        }
        
        onAdComplete = nil
    }
    
    func ad(_ ad: GADFullScreenPresentingAd, didFailToPresentFullScreenContentWithError error: Error) {
        isShowingAd = false
        print("Ad failed to present: \(error.localizedDescription)")
        
        // Reload ad
        if ad is GADInterstitialAd {
            preloadInterstitial()
        } else if ad is GADRewardedAd {
            preloadRewarded()
        }
        
        onAdComplete?(false)
        onAdComplete = nil
    }
}

// MARK: - Banner View (SwiftUI)

struct LyoBannerAdView: UIViewRepresentable {
    let adUnitID: String
    
    init(adUnitID: String = "") {
        #if DEBUG
        self.adUnitID = "ca-app-pub-3940256099942544/2934735716" // Test ID
        #else
        self.adUnitID = adUnitID.isEmpty ? "ca-app-pub-YOUR_ID/banner" : adUnitID
        #endif
    }
    
    func makeUIView(context: Context) -> GADBannerView {
        let bannerView = GADBannerView(adSize: GADAdSizeBanner)
        bannerView.adUnitID = adUnitID
        
        if let windowScene = UIApplication.shared.connectedScenes.first as? UIWindowScene,
           let rootVC = windowScene.windows.first?.rootViewController {
            bannerView.rootViewController = rootVC
        }
        
        bannerView.load(GADRequest())
        return bannerView
    }
    
    func updateUIView(_ uiView: GADBannerView, context: Context) {}
}

// MARK: - Ad-Aware View Modifier

struct AdCoordinatedViewModifier: ViewModifier {
    @StateObject private var adManager = LyoAdManager.shared
    @State private var showBanner = false
    
    func body(content: Content) -> some View {
        ZStack {
            content
                .blur(radius: adManager.isShowingAd ? 3 : 0)
            
            if adManager.isShowingAd {
                Color.black.opacity(0.3)
                    .ignoresSafeArea()
            }
        }
    }
}

extension View {
    func adCoordinated() -> some View {
        modifier(AdCoordinatedViewModifier())
    }
}

// MARK: - Premium Check

extension LyoAdManager {
    /// Check if user has premium (no ads)
    var isPremiumUser: Bool {
        UserDefaults.standard.bool(forKey: "isPremiumUser")
    }
    
    /// Show ad only if not premium
    func showInterstitialIfNeeded(placement: String, completion: ((Bool) -> Void)? = nil) {
        guard !isPremiumUser else {
            completion?(true)
            return
        }
        showInterstitial(placement: placement, completion: completion)
    }
    
    func showRewardedIfNeeded(placement: String, completion: ((Bool) -> Void)? = nil) {
        guard !isPremiumUser else {
            completion?(true)
            return
        }
        showRewarded(placement: placement, completion: completion)
    }
}
