"""
Visual Director Agent - Master of visual design and image generation.

A2A-compliant agent responsible for:
- Creating image generation prompts (DALL-E, Midjourney compatible)
- Designing diagram specifications
- Planning visual hierarchy and flow
- Ensuring visual accessibility
- Maintaining consistent art direction

The Visual Architect - Making learning beautiful.
"""

from typing import Optional, Dict, Any, List
from pydantic import BaseModel, Field
from enum import Enum

from .base import A2ABaseAgent
from .schemas import (
    AgentCapability,
    AgentSkill,
    TaskInput,
    ArtifactType,
    VisualPrompt,
)
from lyo_app.ai_agents.multi_agent_v2.model_manager import ModelTier


# ============================================================
# VISUAL-SPECIFIC SCHEMAS
# ============================================================

class VisualType(str, Enum):
    """Types of visual content"""
    ILLUSTRATION = "illustration"           # Custom artwork
    DIAGRAM = "diagram"                     # Flowcharts, processes
    INFOGRAPHIC = "infographic"             # Data visualization
    ICON = "icon"                           # Small symbolic graphics
    PHOTOGRAPH = "photograph"               # Realistic photos
    SCREENSHOT = "screenshot"               # UI captures
    ANIMATION = "animation"                 # Motion graphics spec
    CHART = "chart"                         # Graphs and charts
    MEME = "meme"                           # Humorous educational
    MASCOT = "mascot"                       # Character appearance
    CONCEPT_ART = "concept_art"             # Abstract concepts
    COMPARISON = "comparison"               # Side-by-side visuals


class VisualStyle(str, Enum):
    """Art styles for generation"""
    FLAT = "flat"                           # Clean, flat design
    ISOMETRIC = "isometric"                 # 3D isometric
    HAND_DRAWN = "hand_drawn"               # Sketch-like
    PHOTOREALISTIC = "photorealistic"       # Photo-like
    MINIMALIST = "minimalist"               # Ultra simple
    CARTOON = "cartoon"                     # Animated style
    TECHNICAL = "technical"                 # Blueprint/schematic
    WATERCOLOR = "watercolor"               # Artistic, soft
    PIXEL_ART = "pixel_art"                 # Retro gaming
    CORPORATE = "corporate"                 # Professional business
    PLAYFUL = "playful"                     # Fun, colorful
    DARK_MODE = "dark_mode"                 # Dark background


class ColorPalette(BaseModel):
    """Color scheme specification"""
    primary: str                            # Main color (hex)
    secondary: str                          # Supporting color
    accent: str                             # Highlight color
    background: str                         # Background color
    text: str                               # Text color
    semantic: Dict[str, str] = Field(       # Success, error, warning, info
        default_factory=lambda: {
            "success": "#22C55E",
            "error": "#EF4444",
            "warning": "#F59E0B",
            "info": "#3B82F6"
        }
    )


class DiagramSpec(BaseModel):
    """Specification for a diagram"""
    id: str
    diagram_type: str                       # flowchart, sequence, class, etc.
    title: str
    elements: List[Dict[str, Any]]          # Nodes/shapes
    connections: List[Dict[str, Any]]       # Edges/arrows
    layout_direction: str                   # TB, LR, BT, RL
    mermaid_code: Optional[str] = None      # Mermaid.js code
    notes: Optional[str] = None


class ImagePrompt(BaseModel):
    """Prompt for AI image generation"""
    id: str
    scene_id: str
    block_id: str
    
    # Core prompt
    subject: str                            # Main subject
    action: str                             # What's happening
    setting: str                            # Where/background
    mood: str                               # Emotional quality
    
    # Style specifications
    style: VisualStyle
    aspect_ratio: str                       # 1:1, 16:9, 4:3, etc.
    
    # Full generation prompt
    dall_e_prompt: str                      # Optimized for DALL-E
    midjourney_prompt: str                  # Optimized for Midjourney
    stable_diffusion_prompt: str            # Optimized for SD
    
    # Negative prompt (what to avoid)
    negative_prompt: str
    
    # Accessibility
    alt_text: str
    aria_description: str
    
    # Technical
    suggested_dimensions: Dict[str, int]    # width, height
    priority: str                           # critical, high, medium, low


class AnimationSpec(BaseModel):
    """Specification for animation/motion graphics"""
    id: str
    title: str
    duration_seconds: float
    fps: int
    
    # Keyframes
    keyframes: List[Dict[str, Any]]
    
    # Motion type
    motion_type: str                        # fade, slide, scale, morph, etc.
    easing: str                             # linear, ease-in, ease-out, bounce
    
    # Lottie/After Effects hints
    animation_description: str
    reference_style: Optional[str] = None


class IconSet(BaseModel):
    """Set of icons for the course"""
    style: str
    stroke_width: float
    corner_radius: float
    icons: List[Dict[str, str]]             # name -> description


class VisualHierarchy(BaseModel):
    """Visual hierarchy plan for a section"""
    section_id: str
    primary_visual: str                     # Main attention
    secondary_visuals: List[str]            # Supporting visuals
    visual_flow: List[str]                  # Order of visual attention
    white_space_ratio: float                # % of empty space
    density: str                            # sparse, moderate, dense


class VisualDirectorOutput(BaseModel):
    """Output from the Visual Director Agent"""
    # Art direction
    course_visual_style: VisualStyle
    color_palette: ColorPalette
    visual_identity: str                    # Description of overall look
    
    # Image prompts
    image_prompts: List[ImagePrompt]
    total_images_needed: int
    
    # Diagrams
    diagram_specs: List[DiagramSpec]
    total_diagrams: int
    
    # Animations
    animation_specs: List[AnimationSpec]
    total_animations: int
    
    # Icons
    icon_set: IconSet
    
    # Visual hierarchy by module
    module_hierarchies: List[VisualHierarchy]
    
    # Accessibility
    color_contrast_ratio: float             # WCAG compliance
    colorblind_safe: bool
    alt_text_coverage: float                # % with alt text
    
    # Style guide
    typography_guide: Dict[str, str]        # heading, body, code, etc.
    spacing_guide: Dict[str, str]           # margins, padding
    component_styles: Dict[str, Dict]       # buttons, cards, etc.
    
    # Production notes
    image_generation_priority: List[str]    # Order to generate
    estimated_generation_time: str
    budget_estimate_images: int             # API calls needed
    
    # Summary
    visual_complexity_score: float          # 0.0-1.0
    brand_consistency_score: float          # 0.0-1.0


# ============================================================
# VISUAL DIRECTOR AGENT
# ============================================================

class VisualDirectorAgent(A2ABaseAgent[VisualDirectorOutput]):
    """
    Master visual designer who creates the look of courses.
    
    Takes cinematic structure and creates comprehensive visual
    specifications including image prompts, diagrams, and art direction.
    
    Capabilities:
    - Image prompt generation
    - Diagram specification
    - Visual hierarchy design
    - Brand consistency
    - Accessibility compliance
    """
    
    def __init__(self):
        super().__init__(
            name="visual_director",
            description="Master of visual design, image generation prompts, and art direction",
            output_schema=VisualDirectorOutput,
            capabilities=[
                AgentCapability.VISUAL_DESIGN,
            ],
            skills=[
                AgentSkill(
                    id="image_prompting",
                    name="Image Prompt Engineering",
                    description="Creates optimized prompts for DALL-E, Midjourney, and Stable Diffusion"
                ),
                AgentSkill(
                    id="diagram_design",
                    name="Diagram Design",
                    description="Specifies flowcharts, diagrams, and technical illustrations"
                ),
                AgentSkill(
                    id="art_direction",
                    name="Art Direction",
                    description="Maintains consistent visual identity across all assets"
                ),
                AgentSkill(
                    id="accessibility_design",
                    name="Accessible Design",
                    description="Ensures visuals meet WCAG accessibility standards"
                ),
            ],
            temperature=0.6,  # Moderate creativity for visuals
            max_tokens=24576,
            timeout_seconds=120.0,
            force_model_tier=ModelTier.PREMIUM
        )
    
    def get_output_artifact_type(self) -> ArtifactType:
        return ArtifactType.VISUAL_ASSETS
    
    def get_system_prompt(self) -> str:
        return """You are a world-class visual director and prompt engineer specializing in educational content.

## Your Background
- Lead Visual Designer at Apple Education
- Prompt Engineering Expert for DALL-E and Midjourney
- Accessibility certification from WebAIM
- Author of "Visual Learning: The Science of Educational Design"
- Former Art Director at Khan Academy

## Your Mission
Transform educational content into visually stunning, accessible experiences that enhance learning through thoughtful visual design.

## Core Principles

### 1. VISUALS SERVE LEARNING
Every image, diagram, and animation must serve a pedagogical purpose:
- Clarify complex concepts
- Provide memorable anchors
- Reduce cognitive load
- Support different learning styles

### 2. PROMPT ENGINEERING MASTERY
You create prompts optimized for each AI model:

**DALL-E 3 Style:**
- Clear, descriptive prompts
- Include style keywords at the end
- Specify aspect ratio clearly
- Use "digital art", "illustration", "3D render" etc.

**Midjourney Style:**
- Use :: to separate concepts with weights
- Include --ar for aspect ratio
- Use --s for stylization (0-1000)
- Include --v for version

**Stable Diffusion Style:**
- Detailed technical descriptions
- Negative prompts are critical
- Include sampling steps suggestion
- CFG scale recommendations

### 3. DIAGRAM EXCELLENCE
For technical diagrams:
- Use Mermaid.js syntax where possible
- Clear node labeling
- Consistent color coding
- Logical flow direction
- Accessible contrast

### 4. ACCESSIBILITY IS REQUIRED
Every visual must have:
- Meaningful alt text (not "image of...")
- ARIA descriptions for complex visuals
- Color contrast ≥ 4.5:1 for text
- Color-blind safe palettes
- Multiple ways to convey information (not just color)

### 5. VISUAL HIERARCHY
Guide the eye:
- Primary focus (largest, highest contrast)
- Secondary elements (supporting)
- Tertiary details (subtle)
- Use white space effectively

## Style Guidelines

### Color Palettes
Always consider:
- Primary brand color
- Complementary accent
- Semantic colors (success, error, warning, info)
- Light and dark mode variants
- Color-blind friendly alternatives

### Typography in Visuals
- Headlines: Bold, high contrast
- Body: Readable, appropriate size
- Code: Monospace, syntax highlighted
- Captions: Subtle, smaller

### Spacing
- Consistent margins
- Breathing room between elements
- Grid-based alignment
- Visual rhythm

## Image Prompt Templates

### Educational Illustration
"[Subject] demonstrating [concept], educational illustration style, clean background, 
[color palette], professional, clear, pedagogical, digital art, 4K"

### Concept Visualization
"Abstract visualization of [concept], showing [key aspects], metaphorical representation,
[style], [mood], minimalist, educational, thought-provoking"

### Process/Flow
"Step-by-step visual of [process], showing [stages], infographic style,
numbered sequence, clear arrows, [color scheme], professional"

### Technical Diagram
"Technical diagram of [system], showing [components], blueprint style,
labeled parts, clean lines, engineering aesthetic"

## Negative Prompts (Common)
"blurry, low quality, distorted, watermark, text overlay, busy background,
cluttered, confusing, amateur, stock photo watermark, copyrighted characters"

CRITICAL: Return valid JSON matching the VisualDirectorOutput schema exactly."""
    
    def build_prompt(
        self, 
        task_input: TaskInput,
        cinematic_output: Optional[Dict[str, Any]] = None,
        pedagogy_output: Optional[Dict[str, Any]] = None,
        brand_colors: Optional[Dict[str, str]] = None,
        **kwargs
    ) -> str:
        # Extract scene information from cinematic output
        scenes_info = ""
        if cinematic_output:
            modules = cinematic_output.get('modules', [])
            for module in modules[:3]:  # Limit for prompt size
                scenes_info += f"\n**Module: {module.get('module_title', 'Unknown')}**\n"
                for scene in module.get('scenes', [])[:5]:
                    scenes_info += f"- Scene {scene.get('scene_number', 'N')}: {scene.get('title', 'Untitled')} ({scene.get('scene_type', 'unknown')})\n"
        
        # Build color section
        color_section = ""
        if brand_colors:
            color_section = f"""
### Brand Colors
- Primary: {brand_colors.get('primary', '#3B82F6')}
- Secondary: {brand_colors.get('secondary', '#10B981')}
- Accent: {brand_colors.get('accent', '#F59E0B')}
"""
        
        return f"""## Visual Direction Task

Create comprehensive visual specifications for this educational course:

### Course Topic
{task_input.user_message}

### Content Structure
{scenes_info or "No scene information provided - create general visual plan."}
{color_section}

## Your Task

Create a complete visual plan including:

### 1. Art Direction
- course_visual_style: flat, isometric, hand_drawn, photorealistic, minimalist, 
  cartoon, technical, watercolor, pixel_art, corporate, playful, or dark_mode
- visual_identity: Description of the overall look and feel
- color_palette: Complete color scheme with primary, secondary, accent, 
  background, text, and semantic colors (hex values)

### 2. Image Prompts
For each scene that needs a visual, create:
- id: "img_M1_S1" format
- scene_id, block_id: Where this image belongs
- subject: Main subject of the image
- action: What's happening
- setting: Background/environment
- mood: Emotional quality
- style: From VisualStyle enum
- aspect_ratio: "1:1", "16:9", "4:3", etc.
- dall_e_prompt: Full DALL-E 3 optimized prompt
- midjourney_prompt: Full Midjourney prompt with parameters
- stable_diffusion_prompt: SD optimized prompt
- negative_prompt: What to avoid
- alt_text: Accessible description
- aria_description: Detailed description for screen readers
- suggested_dimensions: {{"width": N, "height": N}}
- priority: critical, high, medium, low

### 3. Diagram Specifications
For technical concepts:
- id: "diag_1", etc.
- diagram_type: flowchart, sequence, class, er, state, pie, gantt
- title: Diagram title
- elements: Array of {{"id": "N", "label": "...", "type": "...", "style": {{}}}}
- connections: Array of {{"from": "N", "to": "M", "label": "...", "type": "..."}}
- layout_direction: TB, LR, BT, RL
- mermaid_code: Complete Mermaid.js code (important!)
- notes: Any special rendering notes

### 4. Animation Specifications
For motion graphics:
- id: "anim_1", etc.
- title: Animation name
- duration_seconds: Length
- fps: Frames per second (typically 30 or 60)
- keyframes: Array of {{"time": 0.0, "properties": {{}}}}
- motion_type: fade, slide, scale, morph, etc.
- easing: linear, ease-in, ease-out, bounce, etc.
- animation_description: What happens in the animation
- reference_style: Style reference (e.g., "Apple product animation")

### 5. Icon Set
- style: Line, filled, duotone, etc.
- stroke_width: In pixels
- corner_radius: For rounded icons
- icons: Array of {{"name": "...", "description": "..."}} for all needed icons

### 6. Visual Hierarchy
For each module:
- section_id: Module ID
- primary_visual: Main attention point
- secondary_visuals: Supporting elements
- visual_flow: Order the eye should follow
- white_space_ratio: 0.0-1.0
- density: sparse, moderate, dense

### 7. Style Guide
- typography_guide: {{"heading": "...", "body": "...", "code": "...", "caption": "..."}}
- spacing_guide: {{"margin": "...", "padding": "...", "gap": "..."}}
- component_styles: {{"button": {{}}, "card": {{}}, "alert": {{}}}}

### 8. Accessibility Compliance
- color_contrast_ratio: Minimum contrast ratio
- colorblind_safe: true/false
- alt_text_coverage: 1.0 (100% required!)

### 9. Production Planning
- image_generation_priority: Order to generate images (list of IDs)
- estimated_generation_time: Time estimate
- budget_estimate_images: Number of API calls needed

### 10. Quality Scores
- visual_complexity_score: 0.0-1.0 (balanced complexity)
- brand_consistency_score: 0.0-1.0 (how consistent)

## Image Prompt Quality Checklist
✓ Clear subject description
✓ Appropriate style keywords
✓ Mood/atmosphere specified
✓ Technical specifications included
✓ Negative prompts to avoid issues
✓ Meaningful alt text (not generic)
✓ WCAG-compliant color choices

Return valid JSON matching VisualDirectorOutput schema. No markdown, no extra text."""
