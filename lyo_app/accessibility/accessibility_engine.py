#!/usr/bin/env python3
"""
Accessibility Engine for Lyo Platform
Comprehensive accessibility features including screen reader support,
keyboard navigation, color contrast optimization, and adaptive interfaces
"""

from typing import Dict, List, Optional, Any, Union
from dataclasses import dataclass, field
from enum import Enum
import json
import colorsys
import copy
from datetime import datetime


class AccessibilityLevel(Enum):
    """Accessibility compliance levels"""
    A = "A"          # Basic level
    AA = "AA"        # Standard level (WCAG 2.1 AA)
    AAA = "AAA"      # Enhanced level


class UserNeed(Enum):
    """Types of user accessibility needs"""
    VISUAL_IMPAIRMENT = "visual_impairment"
    HEARING_IMPAIRMENT = "hearing_impairment"
    MOTOR_IMPAIRMENT = "motor_impairment"
    COGNITIVE_IMPAIRMENT = "cognitive_impairment"
    LOW_VISION = "low_vision"
    COLOR_BLINDNESS = "color_blindness"
    DYSLEXIA = "dyslexia"


@dataclass
class AccessibilityProfile:
    """User's accessibility preferences and needs"""
    user_id: str
    needs: List[UserNeed] = field(default_factory=list)
    preferences: Dict[str, Any] = field(default_factory=dict)
    high_contrast: bool = False
    large_text: bool = False
    reduce_motion: bool = False
    screen_reader: bool = False
    keyboard_only: bool = False
    font_size_multiplier: float = 1.0
    color_adjustments: Dict[str, str] = field(default_factory=dict)
    created_at: datetime = field(default_factory=datetime.utcnow)
    updated_at: datetime = field(default_factory=datetime.utcnow)


@dataclass
class AccessibilityAnnotation:
    """Accessibility annotations for UI components"""
    element_id: str
    label: Optional[str] = None
    description: Optional[str] = None
    role: Optional[str] = None
    keyboard_shortcut: Optional[str] = None
    screen_reader_text: Optional[str] = None
    tab_index: Optional[int] = None
    aria_attributes: Dict[str, str] = field(default_factory=dict)
    focus_order: Optional[int] = None


@dataclass
class ColorContrastInfo:
    """Color contrast analysis information"""
    foreground: str
    background: str
    contrast_ratio: float
    aa_compliant: bool
    aaa_compliant: bool
    recommendations: List[str] = field(default_factory=list)


class AccessibilityEngine:
    """Core accessibility engine for the Lyo platform"""

    def __init__(self):
        self.user_profiles: Dict[str, AccessibilityProfile] = {}
        self.component_annotations: Dict[str, AccessibilityAnnotation] = {}
        self.color_themes: Dict[str, Dict[str, str]] = self._initialize_color_themes()

    def _initialize_color_themes(self) -> Dict[str, Dict[str, str]]:
        """Initialize accessible color themes"""
        return {
            "default": {
                "primary": "#007AFF",
                "secondary": "#5856D6",
                "background": "#FFFFFF",
                "surface": "#F2F2F7",
                "text_primary": "#000000",
                "text_secondary": "#6D6D80",
                "accent": "#FF9500",
                "error": "#FF3B30",
                "success": "#34C759",
                "warning": "#FFCC00"
            },
            "high_contrast": {
                "primary": "#0000FF",
                "secondary": "#800080",
                "background": "#FFFFFF",
                "surface": "#F0F0F0",
                "text_primary": "#000000",
                "text_secondary": "#333333",
                "accent": "#FF8C00",
                "error": "#FF0000",
                "success": "#008000",
                "warning": "#FFD700"
            },
            "dark_high_contrast": {
                "primary": "#00BFFF",
                "secondary": "#FF69B4",
                "background": "#000000",
                "surface": "#1C1C1E",
                "text_primary": "#FFFFFF",
                "text_secondary": "#CCCCCC",
                "accent": "#FFA500",
                "error": "#FF4444",
                "success": "#00FF00",
                "warning": "#FFFF00"
            },
            "color_blind_friendly": {
                "primary": "#1f77b4",  # Blue
                "secondary": "#ff7f0e", # Orange
                "background": "#FFFFFF",
                "surface": "#F8F9FA",
                "text_primary": "#212529",
                "text_secondary": "#6C757D",
                "accent": "#17a2b8",   # Cyan
                "error": "#dc3545",    # Red (adjusted for color blindness)
                "success": "#28a745",  # Green (adjusted for color blindness)
                "warning": "#ffc107"   # Yellow (adjusted for color blindness)
            }
        }

    async def create_user_profile(self, user_id: str, needs: List[UserNeed] = None,
                                preferences: Dict[str, Any] = None) -> AccessibilityProfile:
        """Create or update accessibility profile for user"""
        profile = AccessibilityProfile(
            user_id=user_id,
            needs=needs or [],
            preferences=preferences or {}
        )

        # Auto-configure based on needs
        self._apply_need_based_settings(profile)

        self.user_profiles[user_id] = profile
        return profile

    def _apply_need_based_settings(self, profile: AccessibilityProfile):
        """Apply automatic settings based on user needs"""
        for need in profile.needs:
            if need == UserNeed.VISUAL_IMPAIRMENT:
                profile.screen_reader = True
                profile.keyboard_only = True
                profile.high_contrast = True

            elif need == UserNeed.LOW_VISION:
                profile.large_text = True
                profile.font_size_multiplier = 1.5
                profile.high_contrast = True

            elif need == UserNeed.COLOR_BLINDNESS:
                profile.color_adjustments = self._get_color_blind_adjustments()

            elif need == UserNeed.MOTOR_IMPAIRMENT:
                profile.keyboard_only = True
                profile.preferences["larger_touch_targets"] = True
                profile.preferences["click_delay"] = 500  # ms

            elif need == UserNeed.COGNITIVE_IMPAIRMENT:
                profile.reduce_motion = True
                profile.preferences["simplified_interface"] = True
                profile.preferences["reading_assistance"] = True

            elif need == UserNeed.DYSLEXIA:
                profile.preferences["dyslexia_font"] = True
                profile.preferences["increased_line_spacing"] = True
                profile.font_size_multiplier = 1.2

    def _get_color_blind_adjustments(self) -> Dict[str, str]:
        """Get color adjustments for color blindness"""
        return {
            "use_patterns": "true",
            "high_contrast_borders": "true",
            "alternative_indicators": "true"
        }

    def annotate_component(self, component_id: str, annotation: AccessibilityAnnotation):
        """Add accessibility annotations to a component"""
        self.component_annotations[component_id] = annotation

    def get_accessible_theme(self, user_id: str) -> Dict[str, str]:
        """Get appropriate color theme for user"""
        profile = self.user_profiles.get(user_id)
        if not profile:
            return self.color_themes["default"]

        # Determine best theme based on user needs
        if profile.high_contrast:
            return self.color_themes["high_contrast"]

        if UserNeed.COLOR_BLINDNESS in profile.needs:
            return self.color_themes["color_blind_friendly"]

        return self.color_themes["default"]

    def calculate_contrast_ratio(self, color1: str, color2: str) -> float:
        """Calculate WCAG contrast ratio between two colors"""
        def hex_to_rgb(hex_color: str) -> tuple:
            hex_color = hex_color.lstrip('#')
            return tuple(int(hex_color[i:i+2], 16) for i in (0, 2, 4))

        def get_luminance(rgb: tuple) -> float:
            def component_luminance(c):
                c = c / 255.0
                return c / 12.92 if c <= 0.03928 else pow((c + 0.055) / 1.055, 2.4)

            r, g, b = rgb
            return 0.2126 * component_luminance(r) + 0.7152 * component_luminance(g) + 0.0722 * component_luminance(b)

        rgb1 = hex_to_rgb(color1)
        rgb2 = hex_to_rgb(color2)

        lum1 = get_luminance(rgb1)
        lum2 = get_luminance(rgb2)

        brighter = max(lum1, lum2)
        darker = min(lum1, lum2)

        return (brighter + 0.05) / (darker + 0.05)

    def analyze_color_contrast(self, foreground: str, background: str) -> ColorContrastInfo:
        """Analyze color contrast and provide recommendations"""
        contrast_ratio = self.calculate_contrast_ratio(foreground, background)

        # WCAG 2.1 requirements
        aa_compliant = contrast_ratio >= 4.5
        aaa_compliant = contrast_ratio >= 7.0

        recommendations = []
        if not aa_compliant:
            recommendations.append("Increase contrast ratio to meet WCAG AA standard (4.5:1 minimum)")
        if not aaa_compliant:
            recommendations.append("Consider increasing contrast for AAA compliance (7:1 minimum)")

        return ColorContrastInfo(
            foreground=foreground,
            background=background,
            contrast_ratio=contrast_ratio,
            aa_compliant=aa_compliant,
            aaa_compliant=aaa_compliant,
            recommendations=recommendations
        )

    def generate_screen_reader_description(self, component_type: str,
                                         content: Dict[str, Any],
                                         context: str = "") -> str:
        """Generate screen reader friendly descriptions"""
        descriptions = {
            "button": f"Button: {content.get('text', 'unlabeled button')}",
            "text": f"Text: {content.get('content', '')}",
            "image": f"Image: {content.get('alt_text', 'decorative image')}",
            "video": f"Video player: {content.get('title', 'untitled video')}. Duration: {content.get('duration', 'unknown')}",
            "input": f"Input field: {content.get('placeholder', 'text input')}",
            "link": f"Link: {content.get('text', 'untitled link')}",
            "heading": f"Heading level {content.get('level', 1)}: {content.get('text', '')}",
            "list": f"List with {content.get('item_count', 0)} items",
            "table": f"Table with {content.get('rows', 0)} rows and {content.get('columns', 0)} columns"
        }

        base_description = descriptions.get(component_type, f"{component_type} element")

        if context:
            return f"{base_description} in {context}"

        return base_description

    def generate_keyboard_navigation_map(self, components: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Generate keyboard navigation map for components"""
        navigation_map = {
            "tab_order": [],
            "shortcuts": {},
            "focus_groups": [],
            "escape_routes": {}
        }

        # Sort components by focus order
        focusable_components = [c for c in components if c.get("focusable", False)]
        focusable_components.sort(key=lambda x: x.get("tab_index", 0))

        for i, component in enumerate(focusable_components):
            component_id = component["id"]
            navigation_map["tab_order"].append(component_id)

            # Add keyboard shortcuts
            if "shortcut" in component:
                navigation_map["shortcuts"][component["shortcut"]] = component_id

            # Group related components for arrow key navigation
            if component.get("group"):
                group_name = component["group"]
                if group_name not in navigation_map["focus_groups"]:
                    navigation_map["focus_groups"][group_name] = []
                navigation_map["focus_groups"][group_name].append(component_id)

        return navigation_map

    def optimize_for_accessibility(self, ui_tree: Dict[str, Any], user_id: str) -> Dict[str, Any]:
        """Optimize UI tree for accessibility based on user profile"""
        profile = self.user_profiles.get(user_id)
        if not profile:
            return ui_tree

        optimized_tree = copy.deepcopy(ui_tree)

        # Apply font size adjustments
        if profile.font_size_multiplier != 1.0:
            self._apply_font_scaling(optimized_tree, profile.font_size_multiplier)

        # Apply color theme
        if profile.high_contrast or UserNeed.COLOR_BLINDNESS in profile.needs:
            theme = self.get_accessible_theme(user_id)
            self._apply_color_theme(optimized_tree, theme)

        # Reduce motion if requested
        if profile.reduce_motion:
            self._disable_animations(optimized_tree)

        # Add screen reader enhancements
        if profile.screen_reader:
            self._enhance_for_screen_reader(optimized_tree)

        # Optimize for keyboard navigation
        if profile.keyboard_only:
            self._optimize_keyboard_navigation(optimized_tree)

        return optimized_tree

    def _apply_font_scaling(self, ui_tree: Dict[str, Any], multiplier: float):
        """Apply font size scaling to UI tree"""
        if "style" in ui_tree:
            if "font_size" in ui_tree["style"]:
                current_size = ui_tree["style"]["font_size"]
                if isinstance(current_size, (int, float)):
                    ui_tree["style"]["font_size"] = current_size * multiplier

        if "children" in ui_tree:
            for child in ui_tree["children"]:
                self._apply_font_scaling(child, multiplier)

    def _apply_color_theme(self, ui_tree: Dict[str, Any], theme: Dict[str, str]):
        """Apply accessible color theme to UI tree"""
        if "style" in ui_tree:
            style = ui_tree["style"]

            # Map common color properties
            color_mappings = {
                "color": "text_primary",
                "background_color": "background",
                "border_color": "text_secondary"
            }

            for style_prop, theme_key in color_mappings.items():
                if style_prop in style and theme_key in theme:
                    style[style_prop] = theme[theme_key]

        if "children" in ui_tree:
            for child in ui_tree["children"]:
                self._apply_color_theme(child, theme)

    def _disable_animations(self, ui_tree: Dict[str, Any]):
        """Disable animations for reduced motion preference"""
        if "animation" in ui_tree:
            ui_tree["animation"]["disabled"] = True

        if "style" in ui_tree:
            ui_tree["style"]["transition"] = "none"

        if "children" in ui_tree:
            for child in ui_tree["children"]:
                self._disable_animations(child)

    def _enhance_for_screen_reader(self, ui_tree: Dict[str, Any]):
        """Add screen reader enhancements"""
        if "accessibility" not in ui_tree:
            ui_tree["accessibility"] = {}

        # Generate description if not present
        if "description" not in ui_tree["accessibility"]:
            component_type = ui_tree.get("type", "unknown")
            content = ui_tree.get("content", {})
            ui_tree["accessibility"]["description"] = self.generate_screen_reader_description(
                component_type, content
            )

        # Add ARIA attributes
        if "aria" not in ui_tree["accessibility"]:
            ui_tree["accessibility"]["aria"] = {}

        if "children" in ui_tree:
            for child in ui_tree["children"]:
                self._enhance_for_screen_reader(child)

    def _optimize_keyboard_navigation(self, ui_tree: Dict[str, Any]):
        """Optimize for keyboard-only navigation"""
        if ui_tree.get("type") in ["button", "link", "input", "select"]:
            if "focusable" not in ui_tree:
                ui_tree["focusable"] = True

            if "tab_index" not in ui_tree:
                ui_tree["tab_index"] = 0

        if "children" in ui_tree:
            for child in ui_tree["children"]:
                self._optimize_keyboard_navigation(child)

    async def audit_accessibility(self, ui_components: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Perform comprehensive accessibility audit"""
        audit_results = {
            "timestamp": datetime.utcnow().isoformat(),
            "total_components": len(ui_components),
            "issues": [],
            "compliance_level": AccessibilityLevel.AAA,
            "score": 0,
            "recommendations": []
        }

        total_score = 0
        max_score = 0

        for component in ui_components:
            component_audit = self._audit_component(component)
            total_score += component_audit["score"]
            max_score += component_audit["max_score"]

            if component_audit["issues"]:
                audit_results["issues"].extend(component_audit["issues"])

        audit_results["score"] = (total_score / max_score * 100) if max_score > 0 else 0

        # Determine compliance level
        if audit_results["score"] >= 95:
            audit_results["compliance_level"] = AccessibilityLevel.AAA
        elif audit_results["score"] >= 85:
            audit_results["compliance_level"] = AccessibilityLevel.AA
        else:
            audit_results["compliance_level"] = AccessibilityLevel.A

        # Generate recommendations
        audit_results["recommendations"] = self._generate_audit_recommendations(
            audit_results["issues"]
        )

        return audit_results

    def _audit_component(self, component: Dict[str, Any]) -> Dict[str, Any]:
        """Audit individual component for accessibility"""
        issues = []
        score = 0
        max_score = 10

        component_type = component.get("type", "unknown")
        component_id = component.get("id", "unknown")

        # Check for missing alt text on images
        if component_type == "image":
            if not component.get("alt_text"):
                issues.append({
                    "component_id": component_id,
                    "severity": "high",
                    "issue": "Missing alt text for image",
                    "recommendation": "Add descriptive alt text for screen readers"
                })
            else:
                score += 2

        # Check for keyboard accessibility
        if component_type in ["button", "link", "input"]:
            if not component.get("focusable", True):
                issues.append({
                    "component_id": component_id,
                    "severity": "high",
                    "issue": "Interactive element not focusable",
                    "recommendation": "Ensure interactive elements are keyboard accessible"
                })
            else:
                score += 2

        # Check for proper headings hierarchy
        if component_type == "heading":
            level = component.get("level", 1)
            if level > 6 or level < 1:
                issues.append({
                    "component_id": component_id,
                    "severity": "medium",
                    "issue": "Invalid heading level",
                    "recommendation": "Use heading levels 1-6 in proper hierarchy"
                })
            else:
                score += 1

        # Check color contrast
        if "style" in component:
            style = component["style"]
            if "color" in style and "background_color" in style:
                contrast_info = self.analyze_color_contrast(
                    style["color"], style["background_color"]
                )
                if not contrast_info.aa_compliant:
                    issues.append({
                        "component_id": component_id,
                        "severity": "high",
                        "issue": f"Poor color contrast ratio: {contrast_info.contrast_ratio:.2f}",
                        "recommendation": "Increase contrast ratio to meet WCAG AA standards (4.5:1)"
                    })
                else:
                    score += 2

        # Base accessibility score
        score += 3

        return {
            "component_id": component_id,
            "score": score,
            "max_score": max_score,
            "issues": issues
        }

    def _generate_audit_recommendations(self, issues: List[Dict[str, Any]]) -> List[str]:
        """Generate prioritized recommendations based on audit issues"""
        recommendations = []

        # Group issues by severity
        high_severity = [i for i in issues if i["severity"] == "high"]
        medium_severity = [i for i in issues if i["severity"] == "medium"]

        if high_severity:
            recommendations.append(f"🔴 Address {len(high_severity)} high-priority accessibility issues")

        if medium_severity:
            recommendations.append(f"🟡 Address {len(medium_severity)} medium-priority accessibility issues")

        # Common recommendations
        missing_alt_text = len([i for i in issues if "alt text" in i["issue"]])
        if missing_alt_text > 0:
            recommendations.append(f"📷 Add alt text to {missing_alt_text} images")

        contrast_issues = len([i for i in issues if "contrast" in i["issue"]])
        if contrast_issues > 0:
            recommendations.append(f"🎨 Fix color contrast on {contrast_issues} components")

        keyboard_issues = len([i for i in issues if "focusable" in i["issue"]])
        if keyboard_issues > 0:
            recommendations.append(f"⌨️ Fix keyboard navigation for {keyboard_issues} components")

        return recommendations


# Initialize global accessibility engine
accessibility_engine = AccessibilityEngine()


async def get_accessible_ui_for_user(user_id: str, ui_tree: Dict[str, Any]) -> Dict[str, Any]:
    """Convenience function to get accessibility-optimized UI for a user"""
    return accessibility_engine.optimize_for_accessibility(ui_tree, user_id)


async def create_accessibility_profile(user_id: str, needs: List[str],
                                     preferences: Dict[str, Any] = None) -> AccessibilityProfile:
    """Convenience function to create user accessibility profile"""
    user_needs = [UserNeed(need) for need in needs if need in UserNeed.__members__.values()]
    return await accessibility_engine.create_user_profile(user_id, user_needs, preferences)


if __name__ == "__main__":
    # Example usage and testing
    async def demo_accessibility_engine():
        print("🎯 ACCESSIBILITY ENGINE DEMONSTRATION")
        print("=" * 60)

        # Create user profiles
        print("👤 Creating accessibility profiles...")

        # Low vision user
        low_vision_profile = await accessibility_engine.create_user_profile(
            "user_low_vision",
            needs=[UserNeed.LOW_VISION],
            preferences={"large_buttons": True}
        )
        print(f"   ✅ Low vision profile: {low_vision_profile.user_id}")

        # Screen reader user
        screen_reader_profile = await accessibility_engine.create_user_profile(
            "user_screen_reader",
            needs=[UserNeed.VISUAL_IMPAIRMENT, UserNeed.MOTOR_IMPAIRMENT]
        )
        print(f"   ✅ Screen reader profile: {screen_reader_profile.user_id}")

        # Color blind user
        color_blind_profile = await accessibility_engine.create_user_profile(
            "user_color_blind",
            needs=[UserNeed.COLOR_BLINDNESS]
        )
        print(f"   ✅ Color blind profile: {color_blind_profile.user_id}")

        print(f"\n🎨 Testing color contrast analysis...")
        contrast_good = accessibility_engine.analyze_color_contrast("#000000", "#FFFFFF")
        contrast_poor = accessibility_engine.analyze_color_contrast("#777777", "#888888")

        print(f"   ✅ Good contrast (black/white): {contrast_good.contrast_ratio:.2f} - AA: {contrast_good.aa_compliant}")
        print(f"   ⚠️  Poor contrast (gray/gray): {contrast_poor.contrast_ratio:.2f} - AA: {contrast_poor.aa_compliant}")

        print(f"\n🔍 Testing accessibility audit...")
        sample_components = [
            {
                "id": "button_1",
                "type": "button",
                "content": {"text": "Submit"},
                "focusable": True,
                "style": {"color": "#FFFFFF", "background_color": "#007AFF"}
            },
            {
                "id": "image_1",
                "type": "image",
                "content": {"src": "logo.png"},
                # Missing alt_text - should trigger audit issue
            },
            {
                "id": "heading_1",
                "type": "heading",
                "level": 1,
                "content": {"text": "Welcome to Lyo"}
            }
        ]

        audit_results = await accessibility_engine.audit_accessibility(sample_components)
        print(f"   📊 Audit score: {audit_results['score']:.1f}%")
        print(f"   📋 Compliance level: {audit_results['compliance_level'].value}")
        print(f"   🔧 Issues found: {len(audit_results['issues'])}")

        for rec in audit_results['recommendations']:
            print(f"      • {rec}")

        print(f"\n🏗️ Testing UI optimization...")
        sample_ui = {
            "type": "vstack",
            "style": {"font_size": 16, "color": "#333333"},
            "children": [
                {"type": "text", "content": {"text": "Hello World"}},
                {"type": "button", "content": {"text": "Click Me"}}
            ]
        }

        optimized_ui = accessibility_engine.optimize_for_accessibility(
            sample_ui, "user_low_vision"
        )
        original_font = sample_ui["style"]["font_size"]
        optimized_font = optimized_ui["style"]["font_size"]
        print(f"   📝 Font scaling: {original_font}px → {optimized_font}px")

        print(f"\n🎉 ACCESSIBILITY ENGINE READY")
        print("   ✅ User profiles management")
        print("   ✅ Color contrast analysis")
        print("   ✅ Accessibility auditing")
        print("   ✅ UI optimization")
        print("   ✅ Screen reader support")
        print("   ✅ Keyboard navigation")

    # Run demo if called directly
    import asyncio
    asyncio.run(demo_accessibility_engine())