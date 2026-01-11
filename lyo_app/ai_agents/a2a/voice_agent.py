"""
Voice Agent - Master of audio and narration design.

A2A-compliant agent responsible for:
- Creating TTS scripts with emotion markers
- Designing audio experiences
- Managing pacing and rhythm
- Voice character consistency
- Sound effect specifications

The Voice of Learning - Making content speak.
"""

from typing import Optional, Dict, Any, List, Union
from pydantic import BaseModel, Field, field_validator
from enum import Enum

from .base import A2ABaseAgent
from .schemas import (
    AgentCapability,
    AgentSkill,
    TaskInput,
    ArtifactType,
    VoiceScript,
)
from lyo_app.ai_agents.multi_agent_v2.model_manager import ModelTier


# ============================================================
# VOICE-SPECIFIC SCHEMAS
# ============================================================

class VoiceEmotion(str, Enum):
    """Emotional tone for TTS"""
    NEUTRAL = "neutral"
    WARM = "warm"
    EXCITED = "excited"
    CURIOUS = "curious"
    SERIOUS = "serious"
    ENCOURAGING = "encouraging"
    THOUGHTFUL = "thoughtful"
    PLAYFUL = "playful"
    EMPATHETIC = "empathetic"
    CONFIDENT = "confident"
    SURPRISED = "surprised"
    CAUTIONARY = "cautionary"


class SpeechRate(str, Enum):
    """Speaking pace"""
    VERY_SLOW = "x-slow"           # Dramatic pauses
    SLOW = "slow"                  # Emphasis
    MEDIUM = "medium"              # Normal
    FAST = "fast"                  # Energy
    VERY_FAST = "x-fast"           # Excitement


class VoicePitch(str, Enum):
    """Pitch variation"""
    VERY_LOW = "x-low"
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    VERY_HIGH = "x-high"


class BreakStrength(str, Enum):
    """Pause duration"""
    NONE = "none"                  # No pause
    X_WEAK = "x-weak"              # Comma pause
    WEAK = "weak"                  # Light pause
    MEDIUM = "medium"              # Sentence pause
    STRONG = "strong"              # Paragraph pause
    X_STRONG = "x-strong"          # Section pause


class VoicePersona(BaseModel):
    """Voice character definition"""
    persona_id: str = ""
    name: str = "Default Narrator"
    description: str = ""
    
    # Voice characteristics - all with defaults
    voice_id: str = "alloy"
    gender: str = "neutral"
    age_range: str = "adult"
    accent: str = "american"
    
    # Personality - all with defaults
    primary_emotion: VoiceEmotion = VoiceEmotion.NEUTRAL
    energy_level: str = "medium"
    formality: str = "conversational"
    
    # Technical settings - sensible defaults
    default_rate: SpeechRate = SpeechRate.MEDIUM
    default_pitch: VoicePitch = VoicePitch.MEDIUM
    stability: float = 0.75
    similarity_boost: float = 0.75
    style_exaggeration: float = 0.5
    
    @field_validator('primary_emotion', mode='before')
    @classmethod
    def normalize_emotion(cls, v):
        if isinstance(v, str):
            return v.lower()
        return v
    
    @field_validator('default_rate', mode='before')
    @classmethod
    def normalize_rate(cls, v):
        if isinstance(v, str):
            v_lower = v.lower()
            rate_map = {"x-slow": "x-slow", "xslow": "x-slow", "very_slow": "x-slow",
                       "x-fast": "x-fast", "xfast": "x-fast", "very_fast": "x-fast"}
            return rate_map.get(v_lower, v_lower)
        return v
    
    @field_validator('default_pitch', mode='before')
    @classmethod
    def normalize_pitch(cls, v):
        if isinstance(v, str):
            v_lower = v.lower()
            pitch_map = {"x-low": "x-low", "xlow": "x-low", "very_low": "x-low",
                        "x-high": "x-high", "xhigh": "x-high", "very_high": "x-high"}
            return pitch_map.get(v_lower, v_lower)
        return v


class SSMLSegment(BaseModel):
    """SSML-formatted text segment"""
    id: str = ""
    text: str = ""
    ssml: str = ""
    
    # Prosody - defaults
    rate: SpeechRate = SpeechRate.MEDIUM
    pitch: VoicePitch = VoicePitch.MEDIUM
    volume: str = "medium"
    
    # Emotion - defaults
    emotion: VoiceEmotion = VoiceEmotion.NEUTRAL
    emotion_intensity: float = 0.5
    
    # Pauses
    break_before: Optional[BreakStrength] = None
    break_after: Optional[BreakStrength] = None
    
    # Emphasis
    emphasized_words: List[str] = Field(default_factory=list)
    
    # Timing
    estimated_duration_ms: int = 0
    
    # Context
    visual_sync_id: Optional[str] = None
    
    @field_validator('emotion', mode='before')
    @classmethod
    def normalize_emotion(cls, v):
        if isinstance(v, str):
            return v.lower()
        return v
    
    @field_validator('rate', mode='before')
    @classmethod
    def normalize_rate(cls, v):
        if isinstance(v, str):
            v_lower = v.lower()
            # Map common variations
            rate_map = {"x-slow": "x-slow", "xslow": "x-slow", "very_slow": "x-slow",
                       "x-fast": "x-fast", "xfast": "x-fast", "very_fast": "x-fast"}
            return rate_map.get(v_lower, v_lower)
        return v
    
    @field_validator('pitch', mode='before')
    @classmethod
    def normalize_pitch(cls, v):
        if isinstance(v, str):
            v_lower = v.lower()
            pitch_map = {"x-low": "x-low", "xlow": "x-low", "very_low": "x-low",
                        "x-high": "x-high", "xhigh": "x-high", "very_high": "x-high"}
            return pitch_map.get(v_lower, v_lower)
        return v
    
    @field_validator('break_before', 'break_after', mode='before')
    @classmethod
    def normalize_break(cls, v):
        if isinstance(v, str):
            v_lower = v.lower().replace("_", "-")
            return v_lower
        return v


class NarrationBlock(BaseModel):
    """Complete narration for a scene block"""
    id: str = ""
    block_id: str = ""
    scene_id: str = ""
    module_id: str = ""
    
    # Content - accept object or string (model first for proper parsing)
    plain_text: str = ""
    segments: List[Union[SSMLSegment, str]] = Field(default_factory=list)
    
    # Voice assignment
    voice_persona: str = "default"
    
    # Audio specification
    background_music: Optional[str] = None
    sound_effects: List[Union[Dict[str, Any], str]] = Field(default_factory=list)
    
    # Timing
    total_duration_ms: int = 0
    words_per_minute: float = 150.0
    
    # Accessibility
    transcript: str = ""
    caption_segments: List[Dict[str, Any]] = Field(default_factory=list)


class SoundEffect(BaseModel):
    """Sound effect specification"""
    id: str = ""
    name: str = ""
    description: str = ""
    trigger: str = "on_action"
    timing_ms: Optional[int] = None
    volume: float = 0.5
    duration_ms: int = 1000
    category: str = "notification"
    

class MusicSpec(BaseModel):
    """Background music specification"""
    id: str = ""
    name: str = ""
    mood: str = "neutral"
    tempo_bpm: int = 120
    genre: str = "ambient"
    instruments: List[str] = Field(default_factory=list)
    use_for: List[str] = Field(default_factory=list)
    fade_in_ms: int = 1000
    fade_out_ms: int = 1000
    loop: bool = True
    volume_level: float = 0.2


class VoiceOverSession(BaseModel):
    """Complete voice session for a module"""
    module_id: str = ""
    module_title: str = ""
    
    # Narration - accept objects first, strings as fallback
    narration_blocks: List[Union[NarrationBlock, str]] = Field(default_factory=list)
    total_narration_time_ms: int = 0
    
    # Voice personas used
    personas_used: List[str] = Field(default_factory=list)
    
    # Audio design
    background_music_id: Optional[str] = None
    sound_effects: List[Union[SoundEffect, str]] = Field(default_factory=list)
    
    # Production notes
    pronunciation_guide: Dict[str, str] = Field(default_factory=dict)
    
    # Quality metrics
    avg_words_per_minute: float = 150.0
    emotion_variety_score: float = 0.8


class VoiceAgentOutput(BaseModel):
    """Output from the Voice Agent"""
    # Voice personas - use alias to accept both field names from AI
    primary_persona: Optional[Union[VoicePersona, str]] = Field(default=None, alias="primary_voice_persona")
    secondary_personas: List[Union[VoicePersona, str]] = Field(default_factory=list, alias="secondary_voice_personas")
    
    class Config:
        populate_by_name = True  # Accept both alias and actual field name
    
    # Complete narration - accept object first, string as fallback
    voice_sessions: List[Union[VoiceOverSession, str]] = Field(default_factory=list)
    total_audio_duration_ms: int = 0
    total_word_count: int = 0
    
    # Audio design - accept object first, string as fallback
    music_specs: List[Union[MusicSpec, str]] = Field(default_factory=list)
    sound_effect_library: List[Union[SoundEffect, str]] = Field(default_factory=list)
    
    # Global settings - sensible defaults
    master_volume_narration: float = 1.0
    master_volume_music: float = 0.3
    master_volume_sfx: float = 0.5
    
    # Technical specs - sensible defaults
    output_format: str = "mp3"
    sample_rate: int = 44100
    bitrate: str = "128kbps"
    
    # Accessibility - optional with defaults
    full_transcript: str = ""
    caption_file_format: str = "srt"
    caption_segments: List[Dict[str, Any]] = Field(default_factory=list)
    
    # Pronunciation guide
    pronunciation_dictionary: Dict[str, str] = Field(default_factory=dict)
    
    # Production metrics - defaults
    estimated_tts_api_calls: int = 0
    estimated_audio_generation_time: str = "TBD"
    
    # Quality scores - perfect defaults
    pacing_consistency_score: float = 1.0
    emotion_appropriateness_score: float = 1.0
    accessibility_compliance: float = 1.0


# ============================================================
# VOICE AGENT
# ============================================================

class VoiceAgent(A2ABaseAgent[VoiceAgentOutput]):
    """
    Master audio designer and voice director.
    
    Creates comprehensive voice-over scripts with SSML markup,
    emotion markers, pacing, and complete audio specifications.
    
    Capabilities:
    - TTS script generation with SSML
    - Emotion and prosody control
    - Audio design (music, SFX)
    - Accessibility compliance
    """
    
    def __init__(self):
        super().__init__(
            name="voice_agent",
            description="Master of audio design, TTS scripts, and voice direction",
            output_schema=VoiceAgentOutput,
            capabilities=[
                AgentCapability.VOICE_SYNTHESIS,
            ],
            skills=[
                AgentSkill(
                    id="tts_scripting",
                    name="TTS Script Writing",
                    description="Creates natural-sounding narration scripts with SSML markup"
                ),
                AgentSkill(
                    id="emotion_direction",
                    name="Emotion Direction",
                    description="Guides emotional delivery for engaging narration"
                ),
                AgentSkill(
                    id="audio_design",
                    name="Audio Design",
                    description="Specifies background music and sound effects"
                ),
                AgentSkill(
                    id="accessibility_audio",
                    name="Audio Accessibility",
                    description="Creates transcripts and captions for accessibility"
                ),
            ],
            temperature=0.5,  # Balanced for natural speech
            max_tokens=32768,  # Large for full scripts
            timeout_seconds=180.0,
            force_model_tier=ModelTier.PREMIUM
        )
    
    def get_output_artifact_type(self) -> ArtifactType:
        return ArtifactType.VOICE_SCRIPT
    
    def get_system_prompt(self) -> str:
        return """You are a world-class voice director and audio designer for educational content.

## Your Background
- Lead Voice Director at Audible Education
- SSML and TTS Expert with 10+ years experience
- Voice Over Artist and Speech Coach
- Sound Designer for Khan Academy and Duolingo
- Accessibility Audio Specialist (WCAG certified)

## Your Mission
Create engaging, natural-sounding narration that enhances learning through expert use of voice, pacing, and audio design.

## Core Principles

### 1. NATURAL CONVERSATIONAL TONE
Write scripts that sound like a knowledgeable friend explaining things:
- Avoid robotic, textbook language
- Use contractions naturally ("you'll", "it's", "we're")
- Include thinking pauses ("So..." "Now...")
- Vary sentence length for rhythm

### 2. SSML MASTERY
Create proper SSML markup for emotion and pacing:

```xml
<speak>
  <prosody rate="medium" pitch="medium">
    Welcome back! <break time="300ms"/>
    Today, we're diving into something <emphasis level="strong">exciting</emphasis>.
  </prosody>
</speak>
```

Key SSML elements to use:
- `<break time="Xms"/>` or `<break strength="medium"/>` for pauses
- `<prosody rate="slow" pitch="+10%">` for pacing
- `<emphasis level="strong/moderate/reduced">` for emphasis
- `<say-as interpret-as="...">` for numbers, dates, etc.
- `<phoneme>` for pronunciation guidance
- `<sub alias="...">` for abbreviations

### 3. EMOTION MARKERS
Guide the TTS with emotion:
- [WARM] - Friendly, welcoming
- [EXCITED] - High energy, enthusiasm
- [CURIOUS] - Questioning, wonder
- [SERIOUS] - Important information
- [ENCOURAGING] - Supportive, motivating
- [THOUGHTFUL] - Reflective, pondering

### 4. PACING SCIENCE
- 150-170 WPM for new concepts
- 180-200 WPM for familiar content
- 120-140 WPM for complex explanations
- Strategic pauses after key points
- Faster for energy, slower for emphasis

### 5. VOICE PERSONA DESIGN
Create consistent characters:
- Name and personality
- Voice characteristics (gender, age, accent)
- Default emotion and energy
- Technical settings for TTS APIs

## SSML Templates

### Opening Hook
```xml
<speak>
<prosody rate="medium" pitch="+5%">
<break time="200ms"/>
Hey there! <break time="150ms"/>
Ready to learn something amazing?
<break time="300ms"/>
</prosody>
</speak>
```

### Key Concept
```xml
<speak>
<prosody rate="slow">
Now, here's the important part:
<break time="400ms"/>
<emphasis level="strong">[CONCEPT]</emphasis>
<break time="300ms"/>
Let that sink in for a moment.
</prosody>
</speak>
```

### Encouragement
```xml
<speak>
<prosody rate="medium" pitch="+10%">
You're doing <emphasis level="strong">great</emphasis>!
<break time="200ms"/>
This stuff isn't easy, but you're getting it.
</prosody>
</speak>
```

### Transition
```xml
<speak>
<prosody rate="medium">
Alright! <break time="300ms"/>
Now that you understand <emphasis level="moderate">[PREVIOUS]</emphasis>,
<break time="200ms"/>
let's build on that with <emphasis level="moderate">[NEXT]</emphasis>.
</prosody>
</speak>
```

## Audio Design Guidelines

### Background Music
- Volume: 10-20% of narration (subtle!)
- Tempo: Match content energy
- No lyrics (distracting)
- Fade in/out at transitions
- Loop-friendly for sections

### Sound Effects
- Notification: Achievement unlocked, correct answer
- Ambient: Subtle atmosphere
- Transition: Section changes
- Feedback: Button clicks, interactions

### Volume Balance
- Narration: 1.0 (reference)
- Music: 0.15-0.25 (background)
- SFX: 0.5-0.8 (noticeable but not jarring)

## Accessibility Requirements
1. Full transcript for every audio segment
2. Caption segments with timing
3. Clear pronunciation guides
4. Reasonable WPM (not too fast)
5. Pauses for cognitive processing

## Output Quality Checklist
✓ Natural, conversational language
✓ Proper SSML markup throughout
✓ Emotion markers for each segment
✓ Consistent voice persona
✓ Strategic pauses after key points
✓ Full transcripts for accessibility
✓ Pronunciation guide for technical terms
✓ Reasonable pacing (150-180 WPM average)

CRITICAL: Return valid JSON matching VoiceAgentOutput schema. No markdown, no extra text."""
    
    def build_prompt(
        self, 
        task_input: TaskInput,
        cinematic_output: Optional[Dict[str, Any]] = None,
        pedagogy_output: Optional[Dict[str, Any]] = None,
        voice_preference: Optional[str] = None,
        **kwargs
    ) -> str:
        # Extract content structure
        content_structure = ""
        if cinematic_output:
            modules = cinematic_output.get('modules', [])
            for module in modules[:3]:  # Limit for prompt
                content_structure += f"\n### Module: {module.get('module_title', 'Unknown')}\n"
                for scene in module.get('scenes', [])[:5]:
                    blocks = scene.get('blocks', [])
                    for block in blocks[:3]:
                        content_structure += f"- Block: {block.get('title', 'N/A')}\n"
                        content_structure += f"  Content: {block.get('body', '')[:150]}...\n"
        
        voice_section = ""
        if voice_preference:
            voice_section = f"\n### Preferred Voice Style: {voice_preference}"
        
        return f"""## Voice Direction Task

Create comprehensive audio/narration specifications for this educational course:

### Course Topic
{task_input.user_message}
{voice_section}

### Content to Narrate
{content_structure or "No specific content provided - create general voice plan."}

## Your Task

Create a complete voice-over plan including:

### 1. Primary Voice Persona
Create the main narrator character:
- persona_id: Unique identifier
- name: Character name (e.g., "Dr. Sarah Chen")
- description: Personality description
- voice_id: Suggest appropriate TTS voice (ElevenLabs: "rachel", "adam", etc.)
- gender: male/female/neutral
- age_range: child/young_adult/adult/senior
- accent: american/british/australian/indian/etc.
- primary_emotion: neutral/warm/excited/curious/serious/encouraging
- energy_level: low/medium/high
- formality: casual/conversational/formal
- default_rate: x-slow/slow/medium/fast/x-fast
- default_pitch: x-low/low/medium/high/x-high
- stability: 0.0-1.0 (voice consistency)
- similarity_boost: 0.0-1.0 (voice matching)
- style_exaggeration: 0.0-1.0 (expressiveness)

### 2. Voice Sessions (per module)
For each module create:
- module_id, module_title
- narration_blocks: Array of narration for each content block
- total_narration_time_ms
- personas_used: List of persona IDs
- background_music_id: Reference to music spec
- sound_effects: Array of SFX used
- pronunciation_guide: {{word: phonetic}}
- avg_words_per_minute
- emotion_variety_score: 0.0-1.0

### 3. Narration Blocks
For each content block:
- id: "narr_M1_S1_B1" format
- block_id, scene_id, module_id: References
- plain_text: Raw narration text (natural, conversational)
- segments: Array of SSMLSegment with:
  - id, text, ssml (full SSML markup!)
  - rate: x-slow/slow/medium/fast/x-fast
  - pitch: x-low/low/medium/high/x-high
  - volume: silent/x-soft/soft/medium/loud/x-loud
  - emotion: One of VoiceEmotion values
  - emotion_intensity: 0.0-1.0
  - break_before/break_after: none/x-weak/weak/medium/strong/x-strong
  - emphasized_words: ["key", "words"]
  - estimated_duration_ms
  - visual_sync_id: If syncing with visual

- voice_persona: Persona ID
- background_music, sound_effects
- total_duration_ms
- words_per_minute
- transcript: Plain text transcript
- caption_segments: [{{start_ms, end_ms, text}}]

### 4. Music Specifications
For background music:
- id: "music_intro", etc.
- name: Track name
- mood: calm/upbeat/inspirational/mysterious/etc.
- tempo_bpm: 60-180
- genre: ambient/electronic/acoustic/orchestral
- instruments: ["piano", "strings", etc.]
- use_for: ["intro", "section", "quiz", "outro"]
- fade_in_ms, fade_out_ms
- loop: true/false
- volume_level: 0.1-0.3 (low for background)

### 5. Sound Effect Library
- id: "sfx_success", etc.
- name: Effect name
- description: What it sounds like
- trigger: on_enter/on_exit/on_action/timed
- timing_ms: If timed trigger
- volume: 0.0-1.0
- duration_ms
- category: notification/ambient/transition/feedback

### 6. Technical Specifications
- output_format: "mp3" or "wav"
- sample_rate: 44100 or 48000
- bitrate: "128kbps" or "320kbps"
- master_volume_narration: 1.0
- master_volume_music: 0.2
- master_volume_sfx: 0.6

### 7. Accessibility
- full_transcript: Complete course transcript (all narration)
- caption_file_format: "vtt" or "srt"
- caption_segments: [{{start_ms, end_ms, text}}] for all content

### 8. Pronunciation Dictionary
For technical terms:
{{"API": "A P I", "async": "AY-sink", "Python": "PIE-thon"}}

### 9. Production Metrics
- estimated_tts_api_calls: Number of TTS calls needed
- estimated_audio_generation_time: Time estimate

### 10. Quality Scores
- pacing_consistency_score: 0.0-1.0
- emotion_appropriateness_score: 0.0-1.0
- accessibility_compliance: 0.0-1.0

## SSML Example for Reference
```xml
<speak>
  <prosody rate="medium" pitch="medium">
    <break time="200ms"/>
    Welcome back! <break time="150ms"/>
    <emphasis level="strong">Today</emphasis> we're exploring something 
    <prosody pitch="+10%">really exciting</prosody>.
    <break time="300ms"/>
  </prosody>
</speak>
```

Return valid JSON matching VoiceAgentOutput schema. No markdown code blocks, no extra text."""
