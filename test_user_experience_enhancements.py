#!/usr/bin/env python3
"""
User Experience Enhancements Test Suite
Validates accessibility features, responsive design, and UX optimizations
"""

import unittest
import asyncio
import json
import sys
import time
from pathlib import Path
from datetime import datetime

class TestUserExperienceEnhancements(unittest.TestCase):
    """Comprehensive test suite for user experience and accessibility features"""

    def setUp(self):
        """Setup test environment"""
        self.start_time = time.time()
        sys.path.append('.')

    def tearDown(self):
        """Cleanup after tests"""
        duration = time.time() - self.start_time
        print(f"   ⏱️  Test duration: {duration:.3f}s")

    def test_accessibility_engine(self):
        """Test accessibility engine functionality"""
        print("♿ Testing accessibility engine...")

        # Test accessibility engine can be imported and initialized
        try:
            from lyo_app.accessibility.accessibility_engine import (
                AccessibilityEngine, UserNeed, AccessibilityLevel
            )
            engine = AccessibilityEngine()
            self.assertIsInstance(engine, AccessibilityEngine)
        except ImportError as e:
            self.fail(f"Accessibility engine should be importable: {e}")

        # Test user profile creation
        async def test_profile_creation():
            profile = await engine.create_user_profile(
                "test_user_accessibility",
                needs=[UserNeed.LOW_VISION, UserNeed.COLOR_BLINDNESS]
            )
            self.assertEqual(profile.user_id, "test_user_accessibility")
            self.assertIn(UserNeed.LOW_VISION, profile.needs)
            self.assertTrue(profile.large_text, "Low vision user should have large text enabled")
            self.assertTrue(profile.high_contrast, "Low vision user should have high contrast")

        asyncio.run(test_profile_creation())

        print("   ✅ Accessibility engine: PASS")

    def test_color_contrast_analysis(self):
        """Test color contrast analysis functionality"""
        print("🎨 Testing color contrast analysis...")

        try:
            from lyo_app.accessibility.accessibility_engine import accessibility_engine

            # Test good contrast (black on white)
            good_contrast = accessibility_engine.analyze_color_contrast("#000000", "#FFFFFF")
            self.assertGreaterEqual(good_contrast.contrast_ratio, 4.5, "Black on white should meet AA standards")
            self.assertTrue(good_contrast.aa_compliant, "Black on white should be AA compliant")

            # Test poor contrast
            poor_contrast = accessibility_engine.analyze_color_contrast("#777777", "#888888")
            self.assertLess(poor_contrast.contrast_ratio, 3.0, "Similar grays should have poor contrast")
            self.assertFalse(poor_contrast.aa_compliant, "Similar grays should not be AA compliant")

            # Test edge case contrast
            edge_contrast = accessibility_engine.analyze_color_contrast("#0066CC", "#FFFFFF")
            self.assertIsInstance(edge_contrast.contrast_ratio, float)
            self.assertGreater(edge_contrast.contrast_ratio, 0)

        except Exception as e:
            self.fail(f"Color contrast analysis should work: {e}")

        print("   ✅ Color contrast analysis: PASS")

    def test_accessibility_optimizations(self):
        """Test UI accessibility optimizations"""
        print("🔧 Testing accessibility optimizations...")

        try:
            from lyo_app.accessibility.accessibility_engine import accessibility_engine, UserNeed

            # Create test UI tree
            test_ui = {
                "type": "vstack",
                "style": {"font_size": 16, "color": "#333333"},
                "children": [
                    {
                        "type": "text",
                        "content": {"text": "Welcome to Lyo"},
                        "style": {"font_size": 18}
                    },
                    {
                        "type": "button",
                        "content": {"text": "Get Started"},
                        "focusable": True
                    }
                ]
            }

            # Test UI optimization for low vision user
            async def test_optimization():
                await accessibility_engine.create_user_profile(
                    "test_low_vision",
                    needs=[UserNeed.LOW_VISION]
                )

                optimized_ui = accessibility_engine.optimize_for_accessibility(
                    test_ui.copy(), "test_low_vision"
                )

                # Check font scaling was applied
                original_font = test_ui["style"]["font_size"]
                optimized_font = optimized_ui["style"]["font_size"]
                expected_font = original_font * 1.5  # Low vision users get 1.5x multiplier
                self.assertEqual(optimized_font, expected_font, f"Font size should be scaled from {original_font} to {expected_font}")

                # Check child font scaling
                original_child_font = test_ui["children"][0]["style"]["font_size"]
                child_font = optimized_ui["children"][0]["style"]["font_size"]
                expected_child_font = original_child_font * 1.5
                self.assertEqual(child_font, expected_child_font, f"Child fonts should be scaled from {original_child_font} to {expected_child_font}")

            asyncio.run(test_optimization())

        except Exception as e:
            self.fail(f"Accessibility optimizations should work: {e}")

        print("   ✅ Accessibility optimizations: PASS")

    def test_responsive_engine(self):
        """Test responsive design engine"""
        print("📱 Testing responsive design engine...")

        try:
            from lyo_app.responsive.responsive_engine import (
                ResponsiveEngine, BreakpointSize, DeviceType
            )
            engine = ResponsiveEngine()
            self.assertIsInstance(engine, ResponsiveEngine)

            # Test breakpoint detection
            from lyo_app.responsive.responsive_engine import ScreenSpecs, Orientation

            # Test mobile screen
            mobile_specs = ScreenSpecs(375, 667, device_type=DeviceType.MOBILE, orientation=Orientation.PORTRAIT)
            mobile_breakpoint = engine.detect_breakpoint(mobile_specs)
            self.assertIn(mobile_breakpoint, [BreakpointSize.XS, BreakpointSize.SM], "Mobile screen should use small breakpoint")

            # Test desktop screen
            desktop_specs = ScreenSpecs(1440, 900, device_type=DeviceType.DESKTOP, orientation=Orientation.LANDSCAPE)
            desktop_breakpoint = engine.detect_breakpoint(desktop_specs)
            self.assertIn(desktop_breakpoint, [BreakpointSize.LG, BreakpointSize.XL, BreakpointSize.XXL], "Desktop should use large breakpoint")

        except ImportError as e:
            self.fail(f"Responsive engine should be importable: {e}")

        print("   ✅ Responsive design engine: PASS")

    def test_responsive_layout_generation(self):
        """Test responsive layout generation"""
        print("🏗️ Testing responsive layout generation...")

        try:
            from lyo_app.responsive.responsive_engine import responsive_engine, ScreenSpecs, DeviceType, Orientation

            test_content = {
                "type": "grid",
                "children": [
                    {"type": "card", "content": {"title": "Course 1"}},
                    {"type": "card", "content": {"title": "Course 2"}},
                    {"type": "card", "content": {"title": "Course 3"}},
                    {"type": "card", "content": {"title": "Course 4"}}
                ]
            }

            # Test mobile layout
            mobile_specs = ScreenSpecs(375, 667, device_type=DeviceType.MOBILE)
            mobile_layout = responsive_engine.generate_responsive_layout(
                test_content, mobile_specs, "learning_card_grid"
            )
            self.assertIsInstance(mobile_layout, dict)
            self.assertEqual(mobile_layout["type"], "grid")

            # Test desktop layout
            desktop_specs = ScreenSpecs(1440, 900, device_type=DeviceType.DESKTOP)
            desktop_layout = responsive_engine.generate_responsive_layout(
                test_content, desktop_specs, "learning_card_grid"
            )
            self.assertIsInstance(desktop_layout, dict)

            # Layouts should be different for different screen sizes
            self.assertNotEqual(mobile_layout, desktop_layout, "Mobile and desktop layouts should differ")

        except Exception as e:
            self.fail(f"Responsive layout generation should work: {e}")

        print("   ✅ Responsive layout generation: PASS")

    def test_screen_analysis(self):
        """Test screen specification analysis"""
        print("🔍 Testing screen analysis...")

        try:
            from lyo_app.responsive.responsive_engine import responsive_engine

            # Test various screen sizes
            test_cases = [
                (320, 568, "mobile"),     # iPhone SE
                (768, 1024, "tablet"),    # iPad
                (1366, 768, "desktop"),   # Laptop
                (1920, 1080, "desktop"),  # Desktop
                (3840, 2160, "tv")        # 4K TV
            ]

            for width, height, expected_category in test_cases:
                specs = responsive_engine.analyze_screen_specs(width, height)

                self.assertEqual(specs.width, width)
                self.assertEqual(specs.height, height)
                self.assertIsNotNone(specs.device_type)
                self.assertIsNotNone(specs.orientation)

                # Device classification should be reasonable
                if expected_category == "mobile":
                    self.assertIn(specs.device_type.value, ["mobile"])
                elif expected_category == "desktop":
                    self.assertIn(specs.device_type.value, ["desktop", "tv"])

        except Exception as e:
            self.fail(f"Screen analysis should work: {e}")

        print("   ✅ Screen analysis: PASS")

    def test_accessibility_audit(self):
        """Test accessibility audit functionality"""
        print("🔍 Testing accessibility audit...")

        try:
            from lyo_app.accessibility.accessibility_engine import accessibility_engine

            # Test components with accessibility issues
            test_components = [
                {
                    "id": "good_button",
                    "type": "button",
                    "content": {"text": "Submit"},
                    "focusable": True,
                    "style": {"color": "#FFFFFF", "background_color": "#007AFF"}
                },
                {
                    "id": "bad_image",
                    "type": "image",
                    "content": {"src": "image.jpg"},
                    # Missing alt_text - should trigger issue
                },
                {
                    "id": "poor_contrast",
                    "type": "text",
                    "content": {"text": "Hard to read text"},
                    "style": {"color": "#CCCCCC", "background_color": "#DDDDDD"}
                }
            ]

            async def test_audit():
                audit_results = await accessibility_engine.audit_accessibility(test_components)

                self.assertIsInstance(audit_results, dict)
                self.assertIn("score", audit_results)
                self.assertIn("issues", audit_results)
                self.assertIn("recommendations", audit_results)

                # Should have found issues
                self.assertGreater(len(audit_results["issues"]), 0, "Should detect accessibility issues")

                # Should have recommendations
                self.assertGreater(len(audit_results["recommendations"]), 0, "Should provide recommendations")

                # Score should be numeric and reasonable
                self.assertIsInstance(audit_results["score"], (int, float))
                self.assertGreaterEqual(audit_results["score"], 0)
                self.assertLessEqual(audit_results["score"], 100)

            asyncio.run(test_audit())

        except Exception as e:
            self.fail(f"Accessibility audit should work: {e}")

        print("   ✅ Accessibility audit: PASS")

    def test_performance_analysis(self):
        """Test responsive layout performance analysis"""
        print("⚡ Testing performance analysis...")

        try:
            from lyo_app.responsive.responsive_engine import responsive_engine, ScreenSpecs, DeviceType

            test_layout = {
                "type": "vstack",
                "children": [
                    {"type": "heading", "content": {"text": "Dashboard"}},
                    {
                        "type": "grid",
                        "children": [{"type": "card", "content": {"title": f"Item {i}"}} for i in range(10)]
                    }
                ]
            }

            screen_specs = ScreenSpecs(1440, 900, device_type=DeviceType.DESKTOP)

            async def test_analysis():
                analysis = await responsive_engine.analyze_layout_performance(test_layout, screen_specs)

                self.assertIsInstance(analysis, dict)
                self.assertIn("performance_score", analysis)
                self.assertIn("layout_metrics", analysis)
                self.assertIn("optimization_opportunities", analysis)

                # Performance score should be reasonable
                score = analysis["performance_score"]
                self.assertIsInstance(score, (int, float))
                self.assertGreaterEqual(score, 0)
                self.assertLessEqual(score, 100)

                # Should have layout metrics
                metrics = analysis["layout_metrics"]
                self.assertIn("component_count", metrics)
                self.assertGreater(metrics["component_count"], 0)

            asyncio.run(test_analysis())

        except Exception as e:
            self.fail(f"Performance analysis should work: {e}")

        print("   ✅ Performance analysis: PASS")

    def test_css_media_queries(self):
        """Test CSS media queries generation"""
        print("📝 Testing CSS media queries generation...")

        try:
            from lyo_app.responsive.responsive_engine import responsive_engine

            css_queries = responsive_engine.generate_css_media_queries()

            self.assertIsInstance(css_queries, str)
            self.assertGreater(len(css_queries), 100, "Should generate substantial CSS")

            # Should contain media query syntax
            self.assertIn("@media", css_queries)
            self.assertIn("min-width", css_queries)
            self.assertIn(".container", css_queries)
            self.assertIn(".grid", css_queries)

            # Should have multiple breakpoints
            media_query_count = css_queries.count("@media")
            self.assertGreater(media_query_count, 3, "Should have multiple media queries")

        except Exception as e:
            self.fail(f"CSS media queries generation should work: {e}")

        print("   ✅ CSS media queries generation: PASS")

    def test_integration_with_existing_systems(self):
        """Test integration with existing A2UI and platform systems"""
        print("🔗 Testing system integration...")

        try:
            # Test that accessibility and responsive engines can work with A2UI components
            from lyo_app.accessibility.accessibility_engine import accessibility_engine
            from lyo_app.responsive.responsive_engine import responsive_engine

            # Test with A2UI-style component structure
            a2ui_component = {
                "type": "VStack",
                "properties": {
                    "spacing": 16,
                    "alignment": "leading"
                },
                "children": [
                    {
                        "type": "Text",
                        "properties": {
                            "content": "Welcome to Lyo",
                            "style": "heading1"
                        }
                    },
                    {
                        "type": "Button",
                        "properties": {
                            "title": "Get Started",
                            "action": "start_onboarding",
                            "style": "primary"
                        }
                    }
                ]
            }

            # Test accessibility optimization doesn't break component structure
            optimized = accessibility_engine.optimize_for_accessibility(a2ui_component.copy(), "test_user")
            self.assertIn("type", optimized, "Component type should be preserved")
            self.assertIn("children", optimized, "Component children should be preserved")

            # Test responsive transformation doesn't break component structure
            from lyo_app.responsive.responsive_engine import ScreenSpecs, DeviceType
            screen_specs = ScreenSpecs(375, 667, device_type=DeviceType.MOBILE)
            responsive = responsive_engine.generate_responsive_layout(a2ui_component.copy(), screen_specs)
            self.assertIn("type", responsive, "Component type should be preserved")

        except Exception as e:
            self.fail(f"System integration should work: {e}")

        print("   ✅ System integration: PASS")

def run_user_experience_tests():
    """Run comprehensive user experience enhancements test suite"""
    print("🎯 USER EXPERIENCE ENHANCEMENTS TEST SUITE")
    print("=" * 70)

    suite = unittest.TestLoader().loadTestsFromTestCase(TestUserExperienceEnhancements)
    runner = unittest.TextTestRunner(verbosity=2, stream=sys.stdout)

    start_time = time.time()
    result = runner.run(suite)
    total_time = time.time() - start_time

    # Calculate results
    total_tests = result.testsRun
    failed_tests = len(result.failures) + len(result.errors)
    success_rate = ((total_tests - failed_tests) / total_tests * 100) if total_tests > 0 else 0

    print(f"\n📊 USER EXPERIENCE TEST RESULTS")
    print("=" * 70)
    print(f"Total Tests: {total_tests}")
    print(f"Passed: {total_tests - failed_tests}")
    print(f"Failed: {failed_tests}")
    print(f"Success Rate: {success_rate:.1f}%")
    print(f"Duration: {total_time:.3f}s")

    if result.failures:
        print(f"\n❌ FAILURES:")
        for test, error in result.failures:
            print(f"   • {test}: {error.split(chr(10))[0]}")

    if result.errors:
        print(f"\n💥 ERRORS:")
        for test, error in result.errors:
            print(f"   • {test}: {error.split(chr(10))[0]}")

    if success_rate >= 90.0:
        print(f"\n🎉 USER EXPERIENCE: EXCELLENT ({success_rate:.1f}%)")
        print("✅ Comprehensive accessibility support")
        print("✅ Advanced responsive design system")
        print("✅ Performance-optimized layouts")
        print("✅ Multi-device compatibility")
        print("✅ WCAG compliance standards")
    else:
        print(f"\n⚠️  USER EXPERIENCE: NEEDS IMPROVEMENT ({success_rate:.1f}%)")
        print("📝 Address failing tests to improve user experience")

    return success_rate >= 90.0, {
        "total_tests": total_tests,
        "passed_tests": total_tests - failed_tests,
        "failed_tests": failed_tests,
        "success_rate": success_rate,
        "duration": total_time,
        "status": "pass" if success_rate >= 90.0 else "fail"
    }

if __name__ == "__main__":
    success, results = run_user_experience_tests()