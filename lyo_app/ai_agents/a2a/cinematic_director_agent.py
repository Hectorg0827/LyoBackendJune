"""
Cinematic Director Agent - Master of educational storytelling.

A2A-compliant agent responsible for:
- Transforming pedagogical structure into cinematic experiences
- Designing scene flow and pacing
- Creating emotional arcs that enhance retention
- Applying narrative techniques to education
- Managing attention and engagement

Hollywood meets Harvard - Cinematic learning experiences
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
    CinematicScene,
    ScenePacing,
    EmotionalTone,
)
from lyo_app.ai_agents.multi_agent_v2.model_manager import ModelTier


# ============================================================
# CINEMATIC-SPECIFIC SCHEMAS
# ============================================================

class NarrativeArc(str, Enum):
    """Story arc types for educational content"""
    HERO_JOURNEY = "hero_journey"      # Learner as protagonist
    MYSTERY = "mystery"                 # Uncover knowledge
    TRANSFORMATION = "transformation"   # Before/after growth
    DISCOVERY = "discovery"             # Scientific exploration
    CHALLENGE = "challenge"             # Problem-solving quest


class SceneType(str, Enum):
    """Types of scenes in cinematic learning"""
    HOOK = "hook"                       # Attention grabber
    EXPOSITION = "exposition"           # Background info
    CONCEPT_INTRO = "concept_intro"     # New concept reveal
    DEMONSTRATION = "demonstration"     # Show, don't tell
    PRACTICE = "practice"               # Active learning
    REFLECTION = "reflection"           # Pause to process
    CHALLENGE = "challenge"             # Test understanding
    REVELATION = "revelation"           # Aha moment
    SYNTHESIS = "synthesis"             # Connect concepts
    CLIFFHANGER = "cliffhanger"         # Motivation for next
    CELEBRATION = "celebration"         # Acknowledge progress


class TransitionType(str, Enum):
    """Transition styles between scenes"""
    CUT = "cut"                         # Direct transition
    FADE = "fade"                       # Gradual transition
    CALLBACK = "callback"               # Reference earlier scene
    QUESTION = "question"               # Rhetorical bridge
    METAPHOR = "metaphor"               # Analogical connection
    CONTRAST = "contrast"               # Highlight difference
    ZOOM = "zoom"                       # Detail focus
    PULLBACK = "pullback"               # Big picture view


class AttentionTechnique(str, Enum):
    """Techniques to maintain attention"""
    NOVELTY = "novelty"                 # Unexpected element
    CONTRAST = "contrast"               # Pattern interrupt
    QUESTION = "question"               # Curiosity gap
    STORY = "story"                     # Narrative hook
    HUMOR = "humor"                     # Light moment
    CHALLENGE = "challenge"             # Call to action
    PREVIEW = "preview"                 # What's coming
    RECAP = "recap"                     # What we learned


class SceneBlock(BaseModel):
    """A block of content within a scene"""
    id: str
    type: str  # text, code, image, animation, quiz, etc.
    content: str
    duration_seconds: int
    voiceover_hint: Optional[str] = None
    visual_hint: Optional[str] = None
    interaction_type: Optional[str] = None  # None, tap, swipe, input, etc.


class DirectorScene(BaseModel):
    """Enhanced scene from the Cinematic Director"""
    id: str
    scene_number: int
    title: str
    scene_type: SceneType
    
    # Pacing & timing
    pacing: ScenePacing
    duration_seconds: int
    
    # Emotional design
    emotional_tone: EmotionalTone
    emotional_arc: str  # rising, falling, stable, climax
    
    # Narrative elements
    hook: Optional[str] = None              # Attention grabber
    key_message: str                        # Core takeaway
    narrative_voice: str                    # How to speak to learner
    
    # Content blocks
    blocks: List[SceneBlock]
    
    # Transitions
    transition_in: Optional[TransitionType] = None
    transition_out: Optional[TransitionType] = None
    
    # Engagement
    attention_technique: AttentionTechnique
    interaction_point: Optional[str] = None
    
    # Metadata
    learning_objective_ids: List[str]       # Which objectives this serves
    cognitive_chunk_id: Optional[str] = None
    concepts_covered: List[str]


class EmotionalBeat(BaseModel):
    """An emotional beat in the course narrative"""
    timestamp_percent: float  # 0.0 to 1.0 through the course
    emotion: EmotionalTone
    intensity: float  # 0.0 to 1.0
    purpose: str
    scene_id: str


class NarrativeStructure(BaseModel):
    """Overall narrative structure of the course"""
    arc_type: NarrativeArc
    protagonist: str  # Usually "the learner"
    central_question: str
    stakes: str  # Why this matters
    transformation: str  # What changes by the end
    key_moments: List[str]  # Important story beats


class ModuleCinematic(BaseModel):
    """Cinematic structure for a module"""
    module_id: str
    module_title: str
    narrative_hook: str
    scenes: List[DirectorScene]
    module_climax_scene_id: str
    emotional_beats: List[EmotionalBeat]
    total_duration_seconds: int


class CinematicOutput(BaseModel):
    """Output from the Cinematic Director Agent"""
    # Overall narrative
    course_title: str
    course_tagline: str
    narrative_structure: NarrativeStructure
    
    # Module breakdowns
    modules: List[ModuleCinematic]
    
    # Global pacing
    average_scene_duration_seconds: int
    pacing_variation: str  # Description of pacing strategy
    attention_reset_frequency: int  # Scenes between resets
    
    # Emotional journey
    overall_emotional_arc: str
    emotional_beats: List[EmotionalBeat]
    climax_scene_id: str
    
    # Production notes
    tone_guide: str
    visual_style: str
    audio_style: str
    
    # Engagement metrics targets
    target_engagement_score: float
    interaction_frequency: float  # Per minute
    variety_score: float  # How varied the scenes are
    
    # Scene summary
    total_scenes: int
    scene_type_distribution: Dict[str, int]


# ============================================================
# CINEMATIC DIRECTOR AGENT
# ============================================================

class CinematicDirectorAgent(A2ABaseAgent[CinematicOutput]):
    """
    Master storyteller who transforms pedagogy into cinema.
    
    Takes the pedagogical structure from PedagogyAgent and
    transforms it into an engaging cinematic experience that
    maximizes retention and motivation.
    
    Capabilities:
    - Narrative arc design
    - Scene composition
    - Emotional journey mapping
    - Pacing optimization
    - Attention management
    """
    
    def __init__(self):
        super().__init__(
            name="cinematic_director",
            description="Master of educational storytelling, transforming lessons into cinematic experiences",
            output_schema=CinematicOutput,
            capabilities=[
                AgentCapability.COURSE_DESIGN,
                AgentCapability.CONTENT_GENERATION,
            ],
            skills=[
                AgentSkill(
                    id="narrative_design",
                    name="Narrative Arc Design",
                    description="Creates compelling story arcs for educational content"
                ),
                AgentSkill(
                    id="scene_composition",
                    name="Scene Composition",
                    description="Designs individual scenes with optimal pacing and flow"
                ),
                AgentSkill(
                    id="emotional_mapping",
                    name="Emotional Journey Mapping",
                    description="Plans emotional beats to enhance retention"
                ),
                AgentSkill(
                    id="attention_management",
                    name="Attention Management",
                    description="Applies techniques to maintain learner engagement"
                ),
            ],
            temperature=0.7,  # Higher creativity for storytelling
            max_tokens=32768,  # Large output for full course structure
            timeout_seconds=180.0,
            force_model_tier=ModelTier.PREMIUM
        )
    
    def get_output_artifact_type(self) -> ArtifactType:
        return ArtifactType.CINEMATIC_SCRIPT
    
    def get_system_prompt(self) -> str:
        return """You are a legendary filmmaker and educational psychologist who creates cinematic learning experiences.

## Your Background
- Academy Award-winning documentary filmmaker
- Former creative director at Pixar's educational division
- Collaborated with Stanford's d.school on narrative learning
- Creator of Netflix's most engaging educational content
- Published research on emotional memory and learning

## Your Philosophy

### Learning is an Experience, Not a Transfer
You don't dump information—you craft journeys. Every learner is the protagonist 
of their own hero's journey, and knowledge is the treasure they seek.

### The Pixar Rule
"Story is king." Even the driest technical content can become compelling when 
wrapped in narrative. You find the story in everything.

### Emotional Memory
People remember how content made them FEEL. You design emotional arcs that 
anchor knowledge in memory through curiosity, satisfaction, surprise, and pride.

### Attention is a Limited Resource
You respect the viewer's attention budget. Every scene earns its place. 
You use pattern interrupts, novelty, and strategic pauses to prevent fatigue.

## Cinematic Techniques

### Scene Types (use variety!)
1. **HOOK** - Open with intrigue, a question, a surprising fact
2. **EXPOSITION** - Background, but keep it minimal and relevant
3. **CONCEPT_INTRO** - The "here's something new" moment
4. **DEMONSTRATION** - Show, don't just tell
5. **PRACTICE** - Active learning beats passive watching
6. **REFLECTION** - Pause to let concepts sink in
7. **CHALLENGE** - Test understanding (low stakes, high value)
8. **REVELATION** - The "aha!" moment—orchestrate these carefully
9. **SYNTHESIS** - Connect multiple concepts together
10. **CLIFFHANGER** - End with motivation to continue
11. **CELEBRATION** - Acknowledge progress—dopamine matters!

### Pacing Principles
- **CONTEMPLATIVE**: For complex concepts needing processing time
- **SLOW**: For building understanding step by step
- **MODERATE**: The default for most content
- **FAST**: For energy and excitement
- **RAPID**: For recaps, previews, or high-energy moments

### Emotional Tones
- **curious**: Opening doors, inviting exploration
- **confident**: Building mastery, showing competence
- **playful**: Making learning fun, reducing anxiety
- **dramatic**: Highlighting importance, creating stakes
- **peaceful**: Reflection, consolidation
- **excited**: Breakthroughs, achievements
- **mysterious**: Creating curiosity gaps

### Narrative Arcs
1. **HERO_JOURNEY**: Learner transforms through challenges
2. **MYSTERY**: Knowledge is uncovered piece by piece
3. **TRANSFORMATION**: Clear before/after contrast
4. **DISCOVERY**: Scientific exploration mindset
5. **CHALLENGE**: Problem-solving quest

## Scene Blocks
Each scene contains blocks:
- **text**: Written content, keep chunks short
- **code**: Programming examples with syntax highlighting
- **image**: Static visuals (provide generation hints)
- **animation**: Motion graphics (describe what to animate)
- **quiz**: Interactive questions
- **demo**: Interactive demonstrations
- **reflection**: Prompt for learner thought

## Your Standards

### Every Scene Must Have:
1. A clear purpose (which objective does it serve?)
2. A single key message (no overloading!)
3. An attention hook or technique
4. Visual and audio hints for production
5. Appropriate emotional tone
6. Smooth transitions in and out

### Variety Rules
- Never have 3+ scenes of the same type in a row
- Alternate between passive (watch) and active (do)
- Reset attention every 3-5 scenes
- Include interaction points every 2-3 minutes

### Duration Guidelines
- Hooks: 10-30 seconds
- Concept intros: 60-120 seconds
- Demonstrations: 60-180 seconds
- Practice: 120-300 seconds
- Reflections: 30-60 seconds

CRITICAL: Return valid JSON matching the CinematicOutput schema exactly."""
    
    def build_prompt(
        self, 
        task_input: TaskInput,
        pedagogy_output: Optional[Dict[str, Any]] = None,
        topic: Optional[str] = None,
        **kwargs
    ) -> str:
        course_topic = topic or task_input.user_message
        
        # Build pedagogy section if we have it from previous agent
        pedagogy_section = ""
        if pedagogy_output:
            pedagogy_section = f"""
## Pedagogical Foundation (from PedagogyAgent)

### Learning Objectives
{self._format_list(pedagogy_output.get('learning_objectives', []))}

### Cognitive Chunks
{self._format_list(pedagogy_output.get('cognitive_chunks', []))}

### Scaffolding Plan
{self._format_list(pedagogy_output.get('scaffolding_steps', []))}

### Key Misconceptions to Address
{chr(10).join(f"- {m}" for m in pedagogy_output.get('key_misconceptions', []))}

### Difficulty Spikes
{chr(10).join(f"- {s}" for s in pedagogy_output.get('difficulty_spikes', []))}

### Engagement Risks
{chr(10).join(f"- {r}" for r in pedagogy_output.get('engagement_risks', []))}
"""
        
        return f"""## Cinematic Direction Task

Transform this course into an engaging cinematic experience:

### Course Details
**Topic:** {course_topic}
**Language:** {task_input.language}
{pedagogy_section}

## Your Mission

Create a complete cinematic structure with:

### 1. Narrative Structure
- arc_type: hero_journey, mystery, transformation, discovery, or challenge
- protagonist: "the learner" or a more specific persona
- central_question: The question driving the course
- stakes: Why this matters
- transformation: What changes by the end
- key_moments: 3-5 pivotal story beats

### 2. Course Title & Tagline
- course_title: Catchy, intriguing (not generic!)
- course_tagline: One line that hooks

### 3. Module Cinematics
For each logical module:
- module_id, module_title
- narrative_hook: What makes someone want to watch this module
- scenes: Array of DirectorScene objects (5-15 per module)
- module_climax_scene_id: The payoff scene
- emotional_beats: Planned emotional moments
- total_duration_seconds

### 4. Scene Design
For each scene:
- id: "scene_M1_S1" format (Module 1, Scene 1)
- scene_number: Sequential
- title: Engaging scene title
- scene_type: hook, exposition, concept_intro, demonstration, practice, etc.
- pacing: contemplative, slow, moderate, fast, or rapid
- duration_seconds: Based on scene type
- emotional_tone: curious, confident, playful, dramatic, peaceful, excited, mysterious
- emotional_arc: rising, falling, stable, or climax
- hook: Opening attention grabber (if applicable)
- key_message: Single takeaway
- narrative_voice: How to speak (e.g., "warm, encouraging mentor")
- blocks: Array of content blocks
- transition_in, transition_out: cut, fade, callback, question, metaphor, etc.
- attention_technique: novelty, contrast, question, story, humor, etc.
- interaction_point: Where learner engages (if any)
- learning_objective_ids: Which objectives this serves
- cognitive_chunk_id: Which chunk from pedagogy (if applicable)
- concepts_covered: List of concepts

### 5. Scene Blocks
Each scene has blocks:
- id: "scene_M1_S1_B1" format
- type: text, code, image, animation, quiz, demo, reflection
- content: The actual content or description
- duration_seconds: Block duration
- voiceover_hint: What the narrator should say (optional)
- visual_hint: What to show (optional)
- interaction_type: None, tap, swipe, input (optional)

### 6. Emotional Journey
- overall_emotional_arc: Description of the journey
- emotional_beats: Planned emotions at percentages
- climax_scene_id: The biggest payoff

### 7. Production Guides
- tone_guide: Overall tone description
- visual_style: Art direction hints
- audio_style: Sound design hints

### 8. Engagement Targets
- target_engagement_score: 0.0-1.0 (aim high: 0.85+)
- interaction_frequency: Per minute (aim for 0.3-0.5)
- variety_score: Scene variety 0.0-1.0 (aim for 0.7+)

### 9. Summary Stats
- total_scenes: Count
- scene_type_distribution: {{"hook": N, "concept_intro": N, ...}}

## Quality Checklist
✓ Each module has a hook scene at the start
✓ Variety in scene types (no 3+ same type in a row)
✓ Interaction every 2-3 minutes
✓ Attention reset every 3-5 scenes
✓ Clear emotional arc with climax
✓ Smooth transitions between scenes
✓ Every objective covered by at least one scene

Return valid JSON matching CinematicOutput schema. No markdown, no extra text."""
    
    def _format_list(self, items: List[Any]) -> str:
        """Format a list of items for the prompt"""
        if not items:
            return "(none provided)"
        
        formatted = []
        for i, item in enumerate(items[:10]):  # Limit to 10 items
            if isinstance(item, dict):
                formatted.append(f"{i+1}. {item.get('title', item.get('description', str(item)))}")
            else:
                formatted.append(f"{i+1}. {str(item)}")
        
        return chr(10).join(formatted)
