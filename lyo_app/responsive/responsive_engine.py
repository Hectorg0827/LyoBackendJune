#!/usr/bin/env python3
"""
Responsive Design Engine for Lyo Platform
Adaptive layouts and responsive UI components that work across
all devices and screen sizes with optimal user experience
"""

from typing import Dict, List, Optional, Any, Tuple, Union
from dataclasses import dataclass, field
from enum import Enum
import json
import math
from datetime import datetime


class DeviceType(Enum):
    """Device type classifications"""
    MOBILE = "mobile"
    TABLET = "tablet"
    DESKTOP = "desktop"
    TV = "tv"
    WATCH = "watch"


class Orientation(Enum):
    """Screen orientation"""
    PORTRAIT = "portrait"
    LANDSCAPE = "landscape"


class BreakpointSize(Enum):
    """Responsive breakpoint sizes"""
    XS = "xs"    # Extra small (mobile)
    SM = "sm"    # Small (large mobile)
    MD = "md"    # Medium (tablet)
    LG = "lg"    # Large (desktop)
    XL = "xl"    # Extra large (large desktop)
    XXL = "xxl"  # Extra extra large (ultra-wide)


@dataclass
class ScreenSpecs:
    """Screen specifications and capabilities"""
    width: int
    height: int
    pixel_ratio: float = 1.0
    orientation: Orientation = Orientation.PORTRAIT
    device_type: DeviceType = DeviceType.MOBILE
    safe_area_insets: Dict[str, int] = field(default_factory=dict)
    supports_hover: bool = False
    supports_touch: bool = True
    color_depth: int = 24
    refresh_rate: int = 60


@dataclass
class LayoutConstraints:
    """Layout constraints for responsive design"""
    min_width: Optional[int] = None
    max_width: Optional[int] = None
    min_height: Optional[int] = None
    max_height: Optional[int] = None
    aspect_ratio: Optional[float] = None
    margins: Dict[str, int] = field(default_factory=dict)
    padding: Dict[str, int] = field(default_factory=dict)


@dataclass
class ResponsiveBreakpoint:
    """Responsive breakpoint configuration"""
    name: BreakpointSize
    min_width: int
    max_width: Optional[int]
    columns: int
    gutter: int
    margin: int
    container_max_width: Optional[int] = None


@dataclass
class AdaptiveLayout:
    """Adaptive layout configuration for different screen sizes"""
    layout_id: str
    breakpoints: Dict[BreakpointSize, Dict[str, Any]]
    component_adaptations: Dict[str, Dict[str, Any]] = field(default_factory=dict)
    priority_order: List[str] = field(default_factory=list)
    progressive_enhancement: bool = True


class ResponsiveEngine:
    """Core responsive design engine for adaptive UI layouts"""

    def __init__(self):
        self.breakpoints = self._initialize_breakpoints()
        self.layout_patterns = self._initialize_layout_patterns()
        self.component_adaptations = self._initialize_component_adaptations()
        self.cached_layouts: Dict[str, Any] = {}

    def _initialize_breakpoints(self) -> Dict[BreakpointSize, ResponsiveBreakpoint]:
        """Initialize responsive breakpoint system"""
        return {
            BreakpointSize.XS: ResponsiveBreakpoint(
                name=BreakpointSize.XS,
                min_width=0,
                max_width=575,
                columns=1,
                gutter=16,
                margin=16,
                container_max_width=None
            ),
            BreakpointSize.SM: ResponsiveBreakpoint(
                name=BreakpointSize.SM,
                min_width=576,
                max_width=767,
                columns=2,
                gutter=20,
                margin=20,
                container_max_width=540
            ),
            BreakpointSize.MD: ResponsiveBreakpoint(
                name=BreakpointSize.MD,
                min_width=768,
                max_width=991,
                columns=3,
                gutter=24,
                margin=24,
                container_max_width=720
            ),
            BreakpointSize.LG: ResponsiveBreakpoint(
                name=BreakpointSize.LG,
                min_width=992,
                max_width=1199,
                columns=4,
                gutter=32,
                margin=32,
                container_max_width=960
            ),
            BreakpointSize.XL: ResponsiveBreakpoint(
                name=BreakpointSize.XL,
                min_width=1200,
                max_width=1399,
                columns=6,
                gutter=40,
                margin=40,
                container_max_width=1140
            ),
            BreakpointSize.XXL: ResponsiveBreakpoint(
                name=BreakpointSize.XXL,
                min_width=1400,
                max_width=None,
                columns=8,
                gutter=48,
                margin=48,
                container_max_width=1320
            )
        }

    def _initialize_layout_patterns(self) -> Dict[str, Dict[str, Any]]:
        """Initialize common responsive layout patterns"""
        return {
            "learning_card_grid": {
                BreakpointSize.XS: {"columns": 1, "card_width": "100%", "spacing": 16},
                BreakpointSize.SM: {"columns": 1, "card_width": "100%", "spacing": 20},
                BreakpointSize.MD: {"columns": 2, "card_width": "48%", "spacing": 24},
                BreakpointSize.LG: {"columns": 3, "card_width": "32%", "spacing": 32},
                BreakpointSize.XL: {"columns": 4, "card_width": "24%", "spacing": 40},
                BreakpointSize.XXL: {"columns": 5, "card_width": "19%", "spacing": 48}
            },
            "content_sidebar": {
                BreakpointSize.XS: {"layout": "stacked", "content_width": "100%", "sidebar_width": "100%"},
                BreakpointSize.SM: {"layout": "stacked", "content_width": "100%", "sidebar_width": "100%"},
                BreakpointSize.MD: {"layout": "side_by_side", "content_width": "65%", "sidebar_width": "30%"},
                BreakpointSize.LG: {"layout": "side_by_side", "content_width": "70%", "sidebar_width": "25%"},
                BreakpointSize.XL: {"layout": "side_by_side", "content_width": "75%", "sidebar_width": "20%"},
                BreakpointSize.XXL: {"layout": "side_by_side", "content_width": "80%", "sidebar_width": "15%"}
            },
            "dashboard_layout": {
                BreakpointSize.XS: {"columns": 1, "widget_size": "full", "navigation": "bottom_tabs"},
                BreakpointSize.SM: {"columns": 1, "widget_size": "full", "navigation": "bottom_tabs"},
                BreakpointSize.MD: {"columns": 2, "widget_size": "half", "navigation": "side_drawer"},
                BreakpointSize.LG: {"columns": 3, "widget_size": "third", "navigation": "sidebar"},
                BreakpointSize.XL: {"columns": 4, "widget_size": "quarter", "navigation": "sidebar"},
                BreakpointSize.XXL: {"columns": 6, "widget_size": "sixth", "navigation": "sidebar"}
            }
        }

    def _initialize_component_adaptations(self) -> Dict[str, Dict[str, Any]]:
        """Initialize component-specific responsive adaptations"""
        return {
            "navigation": {
                BreakpointSize.XS: {"type": "bottom_tabs", "items_visible": 4, "collapse_threshold": 5},
                BreakpointSize.SM: {"type": "bottom_tabs", "items_visible": 5, "collapse_threshold": 6},
                BreakpointSize.MD: {"type": "side_drawer", "items_visible": 8, "collapse_threshold": 10},
                BreakpointSize.LG: {"type": "sidebar", "items_visible": 12, "collapse_threshold": 15},
                BreakpointSize.XL: {"type": "sidebar", "items_visible": 15, "collapse_threshold": 20},
                BreakpointSize.XXL: {"type": "mega_menu", "items_visible": 20, "collapse_threshold": 25}
            },
            "video_player": {
                BreakpointSize.XS: {"aspect_ratio": "16:9", "controls": "overlay", "quality": "auto"},
                BreakpointSize.SM: {"aspect_ratio": "16:9", "controls": "overlay", "quality": "720p"},
                BreakpointSize.MD: {"aspect_ratio": "16:9", "controls": "standard", "quality": "720p"},
                BreakpointSize.LG: {"aspect_ratio": "16:9", "controls": "extended", "quality": "1080p"},
                BreakpointSize.XL: {"aspect_ratio": "16:9", "controls": "extended", "quality": "1080p"},
                BreakpointSize.XXL: {"aspect_ratio": "21:9", "controls": "extended", "quality": "4k"}
            },
            "text_content": {
                BreakpointSize.XS: {"font_size": 16, "line_height": 1.4, "max_width": "100%", "columns": 1},
                BreakpointSize.SM: {"font_size": 16, "line_height": 1.5, "max_width": "100%", "columns": 1},
                BreakpointSize.MD: {"font_size": 18, "line_height": 1.6, "max_width": "65ch", "columns": 1},
                BreakpointSize.LG: {"font_size": 18, "line_height": 1.6, "max_width": "70ch", "columns": 1},
                BreakpointSize.XL: {"font_size": 20, "line_height": 1.7, "max_width": "75ch", "columns": 2},
                BreakpointSize.XXL: {"font_size": 20, "line_height": 1.8, "max_width": "80ch", "columns": 2}
            }
        }

    def detect_breakpoint(self, screen_specs: ScreenSpecs) -> BreakpointSize:
        """Detect appropriate breakpoint based on screen specifications"""
        width = screen_specs.width

        for breakpoint_size in reversed(list(BreakpointSize)):
            breakpoint = self.breakpoints[breakpoint_size]
            if width >= breakpoint.min_width:
                if breakpoint.max_width is None or width <= breakpoint.max_width:
                    return breakpoint_size

        return BreakpointSize.XS

    def analyze_screen_specs(self, width: int, height: int, user_agent: str = "",
                           pixel_ratio: float = 1.0) -> ScreenSpecs:
        """Analyze screen specifications from device information"""
        # Determine device type
        device_type = self._classify_device(width, height, user_agent)

        # Determine orientation
        orientation = Orientation.LANDSCAPE if width > height else Orientation.PORTRAIT

        # Determine capabilities
        supports_hover = device_type in [DeviceType.DESKTOP]
        supports_touch = device_type in [DeviceType.MOBILE, DeviceType.TABLET]

        # Calculate safe area insets (for mobile devices with notches/home indicators)
        safe_area_insets = self._calculate_safe_area_insets(device_type, orientation, width, height)

        return ScreenSpecs(
            width=width,
            height=height,
            pixel_ratio=pixel_ratio,
            orientation=orientation,
            device_type=device_type,
            safe_area_insets=safe_area_insets,
            supports_hover=supports_hover,
            supports_touch=supports_touch
        )

    def _classify_device(self, width: int, height: int, user_agent: str) -> DeviceType:
        """Classify device type based on screen size and user agent"""
        # Basic classification based on screen size
        max_dimension = max(width, height)

        if max_dimension < 600:
            return DeviceType.MOBILE
        elif max_dimension < 1024:
            return DeviceType.TABLET
        elif max_dimension < 1920:
            return DeviceType.DESKTOP
        else:
            return DeviceType.TV

        # Could be enhanced with user agent parsing for more accuracy

    def _calculate_safe_area_insets(self, device_type: DeviceType, orientation: Orientation,
                                  width: int, height: int) -> Dict[str, int]:
        """Calculate safe area insets for devices with notches/home indicators"""
        if device_type != DeviceType.MOBILE:
            return {"top": 0, "bottom": 0, "left": 0, "right": 0}

        # Basic safe area calculations (would be more sophisticated in real implementation)
        if orientation == Orientation.PORTRAIT:
            return {"top": 44, "bottom": 34, "left": 0, "right": 0}
        else:
            return {"top": 0, "bottom": 21, "left": 44, "right": 44}

    def generate_responsive_layout(self, content_tree: Dict[str, Any],
                                 screen_specs: ScreenSpecs,
                                 layout_pattern: str = "auto") -> Dict[str, Any]:
        """Generate responsive layout for given content and screen specifications"""
        breakpoint = self.detect_breakpoint(screen_specs)

        # Create cache key
        cache_key = f"{layout_pattern}_{breakpoint.value}_{screen_specs.width}x{screen_specs.height}"

        if cache_key in self.cached_layouts:
            return self.cached_layouts[cache_key]

        # Apply responsive transformations
        responsive_tree = self._apply_responsive_transformations(
            content_tree, breakpoint, screen_specs, layout_pattern
        )

        # Apply device-specific optimizations
        responsive_tree = self._apply_device_optimizations(responsive_tree, screen_specs)

        # Cache the result
        self.cached_layouts[cache_key] = responsive_tree

        return responsive_tree

    def _apply_responsive_transformations(self, content_tree: Dict[str, Any],
                                        breakpoint: BreakpointSize,
                                        screen_specs: ScreenSpecs,
                                        layout_pattern: str) -> Dict[str, Any]:
        """Apply responsive transformations to content tree"""
        transformed_tree = content_tree.copy()

        # Apply layout pattern if specified
        if layout_pattern != "auto" and layout_pattern in self.layout_patterns:
            pattern_config = self.layout_patterns[layout_pattern][breakpoint]
            transformed_tree = self._apply_layout_pattern(transformed_tree, pattern_config)

        # Apply component-specific adaptations
        transformed_tree = self._apply_component_adaptations(transformed_tree, breakpoint)

        # Apply grid system
        transformed_tree = self._apply_grid_system(transformed_tree, breakpoint)

        # Apply typography scaling
        transformed_tree = self._apply_typography_scaling(transformed_tree, breakpoint, screen_specs)

        return transformed_tree

    def _apply_layout_pattern(self, content_tree: Dict[str, Any],
                            pattern_config: Dict[str, Any]) -> Dict[str, Any]:
        """Apply specific layout pattern configuration"""
        if "columns" in pattern_config:
            self._apply_column_layout(content_tree, pattern_config["columns"])

        if "card_width" in pattern_config:
            self._apply_card_sizing(content_tree, pattern_config["card_width"])

        if "spacing" in pattern_config:
            self._apply_spacing(content_tree, pattern_config["spacing"])

        return content_tree

    def _apply_component_adaptations(self, content_tree: Dict[str, Any],
                                   breakpoint: BreakpointSize) -> Dict[str, Any]:
        """Apply component-specific responsive adaptations"""
        component_type = content_tree.get("type", "unknown")

        if component_type in self.component_adaptations:
            adaptations = self.component_adaptations[component_type].get(breakpoint, {})

            # Apply adaptations to component
            if "style" not in content_tree:
                content_tree["style"] = {}

            for key, value in adaptations.items():
                if key not in ["type"]:  # Don't override component type
                    content_tree["style"][key] = value

        # Recursively apply to children
        if "children" in content_tree:
            for child in content_tree["children"]:
                self._apply_component_adaptations(child, breakpoint)

        return content_tree

    def _apply_grid_system(self, content_tree: Dict[str, Any],
                         breakpoint: BreakpointSize) -> Dict[str, Any]:
        """Apply responsive grid system"""
        grid_config = self.breakpoints[breakpoint]

        if content_tree.get("type") == "grid" or content_tree.get("layout") == "grid":
            if "style" not in content_tree:
                content_tree["style"] = {}

            content_tree["style"].update({
                "columns": grid_config.columns,
                "gap": grid_config.gutter,
                "margin": grid_config.margin
            })

        if "children" in content_tree:
            for child in content_tree["children"]:
                self._apply_grid_system(child, breakpoint)

        return content_tree

    def _apply_typography_scaling(self, content_tree: Dict[str, Any],
                                breakpoint: BreakpointSize,
                                screen_specs: ScreenSpecs) -> Dict[str, Any]:
        """Apply responsive typography scaling"""
        if content_tree.get("type") in ["text", "heading", "paragraph"]:
            if "style" not in content_tree:
                content_tree["style"] = {}

            # Apply text adaptations if available
            if "text_content" in self.component_adaptations:
                text_config = self.component_adaptations["text_content"].get(breakpoint, {})
                content_tree["style"].update(text_config)

            # Apply pixel ratio scaling
            if "font_size" in content_tree["style"] and screen_specs.pixel_ratio > 1:
                original_size = content_tree["style"]["font_size"]
                # Slightly reduce font size on high-DPI screens for better readability
                content_tree["style"]["font_size"] = max(12, int(original_size / (screen_specs.pixel_ratio * 0.8)))

        if "children" in content_tree:
            for child in content_tree["children"]:
                self._apply_typography_scaling(child, breakpoint, screen_specs)

        return content_tree

    def _apply_column_layout(self, content_tree: Dict[str, Any], columns: int):
        """Apply column-based layout"""
        if "style" not in content_tree:
            content_tree["style"] = {}

        content_tree["style"]["display"] = "grid"
        content_tree["style"]["grid_template_columns"] = f"repeat({columns}, 1fr)"

    def _apply_card_sizing(self, content_tree: Dict[str, Any], card_width: str):
        """Apply card sizing for grid layouts"""
        if content_tree.get("type") == "card":
            if "style" not in content_tree:
                content_tree["style"] = {}
            content_tree["style"]["width"] = card_width

        if "children" in content_tree:
            for child in content_tree["children"]:
                if child.get("type") == "card":
                    self._apply_card_sizing(child, card_width)

    def _apply_spacing(self, content_tree: Dict[str, Any], spacing: int):
        """Apply responsive spacing"""
        if "style" not in content_tree:
            content_tree["style"] = {}

        content_tree["style"]["gap"] = spacing
        content_tree["style"]["padding"] = spacing // 2

    def _apply_device_optimizations(self, content_tree: Dict[str, Any],
                                  screen_specs: ScreenSpecs) -> Dict[str, Any]:
        """Apply device-specific optimizations"""
        # Touch device optimizations
        if screen_specs.supports_touch:
            self._optimize_for_touch(content_tree)

        # Hover device optimizations
        if screen_specs.supports_hover:
            self._optimize_for_hover(content_tree)

        # High DPI optimizations
        if screen_specs.pixel_ratio > 1.5:
            self._optimize_for_high_dpi(content_tree)

        # Safe area optimizations for mobile devices
        if screen_specs.device_type == DeviceType.MOBILE:
            self._apply_safe_area_constraints(content_tree, screen_specs.safe_area_insets)

        return content_tree

    def _optimize_for_touch(self, content_tree: Dict[str, Any]):
        """Optimize UI for touch interaction"""
        if content_tree.get("type") in ["button", "link", "input"]:
            if "style" not in content_tree:
                content_tree["style"] = {}

            # Ensure minimum touch target size (44pt minimum)
            current_height = content_tree["style"].get("height", 32)
            content_tree["style"]["min_height"] = max(44, current_height)

            # Add touch feedback
            content_tree["style"]["touch_feedback"] = True

        if "children" in content_tree:
            for child in content_tree["children"]:
                self._optimize_for_touch(child)

    def _optimize_for_hover(self, content_tree: Dict[str, Any]):
        """Optimize UI for hover interaction"""
        if content_tree.get("type") in ["button", "link", "card"]:
            if "style" not in content_tree:
                content_tree["style"] = {}

            # Enable hover effects
            content_tree["style"]["hover_effects"] = True

        if "children" in content_tree:
            for child in content_tree["children"]:
                self._optimize_for_hover(child)

    def _optimize_for_high_dpi(self, content_tree: Dict[str, Any]):
        """Optimize for high DPI screens"""
        if content_tree.get("type") == "image":
            if "style" not in content_tree:
                content_tree["style"] = {}

            # Request high-resolution images
            content_tree["style"]["high_resolution"] = True

        if "children" in content_tree:
            for child in content_tree["children"]:
                self._optimize_for_high_dpi(child)

    def _apply_safe_area_constraints(self, content_tree: Dict[str, Any],
                                   safe_area_insets: Dict[str, int]):
        """Apply safe area constraints for mobile devices"""
        if content_tree.get("type") in ["navigation", "header", "footer"]:
            if "style" not in content_tree:
                content_tree["style"] = {}

            # Apply safe area padding
            for side, inset in safe_area_insets.items():
                if inset > 0:
                    padding_key = f"padding_{side}"
                    current_padding = content_tree["style"].get(padding_key, 0)
                    content_tree["style"][padding_key] = max(current_padding, inset)

    def generate_css_media_queries(self) -> str:
        """Generate CSS media queries for responsive breakpoints"""
        css_queries = []

        for breakpoint_size, breakpoint in self.breakpoints.items():
            if breakpoint.max_width:
                query = f"@media (min-width: {breakpoint.min_width}px) and (max-width: {breakpoint.max_width}px)"
            else:
                query = f"@media (min-width: {breakpoint.min_width}px)"

            css_queries.append(f"""
{query} {{
  .container {{
    max-width: {breakpoint.container_max_width or '100%'};
    margin: 0 {breakpoint.margin}px;
    padding: 0 {breakpoint.gutter}px;
  }}

  .grid {{
    grid-template-columns: repeat({breakpoint.columns}, 1fr);
    gap: {breakpoint.gutter}px;
  }}
}}""")

        return "\n".join(css_queries)

    async def analyze_layout_performance(self, content_tree: Dict[str, Any],
                                       screen_specs: ScreenSpecs) -> Dict[str, Any]:
        """Analyze responsive layout performance and optimization opportunities"""
        breakpoint = self.detect_breakpoint(screen_specs)

        analysis = {
            "timestamp": datetime.utcnow().isoformat(),
            "breakpoint": breakpoint.value,
            "screen_specs": {
                "width": screen_specs.width,
                "height": screen_specs.height,
                "device_type": screen_specs.device_type.value,
                "pixel_ratio": screen_specs.pixel_ratio
            },
            "layout_metrics": {},
            "optimization_opportunities": [],
            "performance_score": 0
        }

        # Analyze component count and complexity
        component_count = self._count_components(content_tree)
        max_nesting_depth = self._calculate_nesting_depth(content_tree)

        analysis["layout_metrics"]["component_count"] = component_count
        analysis["layout_metrics"]["max_nesting_depth"] = max_nesting_depth

        # Performance scoring
        score = 100

        if component_count > 50:
            score -= 10
            analysis["optimization_opportunities"].append(
                "Consider component virtualization for large component trees"
            )

        if max_nesting_depth > 8:
            score -= 15
            analysis["optimization_opportunities"].append(
                "Reduce component nesting depth for better performance"
            )

        # Check for responsive optimizations
        if not self._has_responsive_images(content_tree):
            score -= 10
            analysis["optimization_opportunities"].append(
                "Implement responsive images for better loading performance"
            )

        if not self._has_efficient_layout(content_tree, breakpoint):
            score -= 15
            analysis["optimization_opportunities"].append(
                f"Optimize layout for {breakpoint.value} breakpoint"
            )

        analysis["performance_score"] = max(0, score)

        return analysis

    def _count_components(self, content_tree: Dict[str, Any]) -> int:
        """Count total components in content tree"""
        count = 1  # Count this component

        if "children" in content_tree:
            for child in content_tree["children"]:
                count += self._count_components(child)

        return count

    def _calculate_nesting_depth(self, content_tree: Dict[str, Any], current_depth: int = 0) -> int:
        """Calculate maximum nesting depth"""
        if "children" not in content_tree or not content_tree["children"]:
            return current_depth

        max_child_depth = current_depth
        for child in content_tree["children"]:
            child_depth = self._calculate_nesting_depth(child, current_depth + 1)
            max_child_depth = max(max_child_depth, child_depth)

        return max_child_depth

    def _has_responsive_images(self, content_tree: Dict[str, Any]) -> bool:
        """Check if content tree uses responsive images"""
        if content_tree.get("type") == "image":
            style = content_tree.get("style", {})
            return "responsive" in style or "srcset" in content_tree.get("content", {})

        if "children" in content_tree:
            for child in content_tree["children"]:
                if self._has_responsive_images(child):
                    return True

        return False

    def _has_efficient_layout(self, content_tree: Dict[str, Any],
                            breakpoint: BreakpointSize) -> bool:
        """Check if layout is optimized for the given breakpoint"""
        # Simple heuristic: check if grid/flex layouts are used appropriately
        layout_type = content_tree.get("type", "")

        if breakpoint in [BreakpointSize.XS, BreakpointSize.SM]:
            # Small screens should use simple layouts
            return layout_type in ["vstack", "list", "scroll"]

        if breakpoint in [BreakpointSize.MD, BreakpointSize.LG]:
            # Medium screens should use more sophisticated layouts
            return layout_type in ["grid", "hstack", "sidebar"]

        # Large screens can use complex layouts
        return True


# Initialize global responsive engine
responsive_engine = ResponsiveEngine()


async def generate_responsive_ui(content_tree: Dict[str, Any], width: int, height: int,
                               user_agent: str = "", layout_pattern: str = "auto") -> Dict[str, Any]:
    """Convenience function to generate responsive UI for given screen dimensions"""
    screen_specs = responsive_engine.analyze_screen_specs(width, height, user_agent)
    return responsive_engine.generate_responsive_layout(content_tree, screen_specs, layout_pattern)


if __name__ == "__main__":
    # Example usage and testing
    async def demo_responsive_engine():
        print("🎯 RESPONSIVE ENGINE DEMONSTRATION")
        print("=" * 60)

        # Test different screen sizes
        test_screens = [
            (375, 667, "iPhone"),     # iPhone
            (768, 1024, "iPad"),      # iPad
            (1440, 900, "Desktop"),   # Desktop
            (1920, 1080, "Desktop"),  # Large Desktop
        ]

        sample_content = {
            "type": "vstack",
            "children": [
                {
                    "type": "heading",
                    "content": {"text": "Learning Dashboard"},
                    "style": {"font_size": 24}
                },
                {
                    "type": "grid",
                    "children": [
                        {"type": "card", "content": {"title": "Course 1"}},
                        {"type": "card", "content": {"title": "Course 2"}},
                        {"type": "card", "content": {"title": "Course 3"}},
                        {"type": "card", "content": {"title": "Course 4"}}
                    ]
                },
                {
                    "type": "navigation",
                    "children": [
                        {"type": "nav_item", "content": {"text": "Home"}},
                        {"type": "nav_item", "content": {"text": "Courses"}},
                        {"type": "nav_item", "content": {"text": "Progress"}},
                        {"type": "nav_item", "content": {"text": "Settings"}}
                    ]
                }
            ]
        }

        print("📱 Testing responsive layouts...")

        for width, height, device_name in test_screens:
            print(f"\\n   🖥️  {device_name} ({width}x{height})")

            screen_specs = responsive_engine.analyze_screen_specs(width, height)
            breakpoint = responsive_engine.detect_breakpoint(screen_specs)

            print(f"      📏 Breakpoint: {breakpoint.value}")
            print(f"      📱 Device Type: {screen_specs.device_type.value}")
            print(f"      🔄 Orientation: {screen_specs.orientation.value}")

            responsive_layout = responsive_engine.generate_responsive_layout(
                sample_content, screen_specs, "dashboard_layout"
            )

            # Check grid configuration
            if "children" in responsive_layout:
                for child in responsive_layout["children"]:
                    if child.get("type") == "grid" and "style" in child:
                        grid_style = child["style"]
                        print(f"      🔲 Grid Columns: {grid_style.get('columns', 'auto')}")

            # Performance analysis
            performance_analysis = await responsive_engine.analyze_layout_performance(
                responsive_layout, screen_specs
            )
            print(f"      ⚡ Performance Score: {performance_analysis['performance_score']}/100")

        print(f"\\n🎨 Testing CSS media queries generation...")
        css_queries = responsive_engine.generate_css_media_queries()
        lines_count = len(css_queries.split('\\n'))
        print(f"   ✅ Generated {lines_count} lines of CSS media queries")

        print(f"\\n🎉 RESPONSIVE ENGINE READY")
        print("   ✅ Multi-breakpoint support")
        print("   ✅ Device-specific optimizations")
        print("   ✅ Touch/hover adaptations")
        print("   ✅ Safe area handling")
        print("   ✅ Performance analysis")
        print("   ✅ CSS media query generation")

    # Run demo if called directly
    import asyncio
    asyncio.run(demo_responsive_engine())