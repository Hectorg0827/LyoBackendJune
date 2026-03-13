"""
Researcher Agent - Expert in deep-dive discovery and fact-gathering.

A2A-compliant agent responsible for:
- Gathering key facts about a topic
- Identifying authoritative sources
- Breaking down complex subjects into fundamental concepts
- Finding interesting "hooks" or surprising facts
- Verifying depth requirements for different learning levels

The Scout of the Pipeline - Finding the gold before we build the mine.
"""

from typing import Optional, Dict, Any, List
from pydantic import BaseModel, Field
from enum import Enum

from .base import A2ABaseAgent
from .schemas import (
    AgentCapability,
    AgentSkill,
    TaskInput,
    TaskOutput,
    ArtifactType,
    StreamingEvent,
    EventType,
    AgentAction,
)
from lyo_app.ai_agents.multi_agent_v2.model_manager import ModelTier
from lyo_app.core.config import settings
from lyo_app.storage.enhanced_storage import enhanced_storage
import google.generativeai as genai
import os


# ============================================================
# RESEARCHER-SPECIFIC SCHEMAS
# ============================================================

class SourceType(str, Enum):
    """Types of educational sources"""
    ACADEMIC = "academic"
    PRACTICAL = "practical"
    HISTORICAL = "historical"
    TECHNICAL = "technical"
    POPULAR = "popular"


class ResearchFact(BaseModel):
    """A single verified fact or concept"""
    fact: str
    relevance: str  # Why this is important for the learner
    complexity: str  # beginner, intermediate, advanced
    source_type: SourceType
    is_hook: bool = False  # Potential "surprising fact" for engagement


class ResearcherOutput(BaseModel):
    """Output from the Researcher Agent"""
    topic: str
    summary: str
    key_concepts: List[str]
    core_facts: List[ResearchFact]
    suggested_depth: str
    target_audience_desc: str
    potential_hooks: List[str]
    authoritative_sources: List[str]
    notable_experts: List[str]
    terminology_list: List[Dict[str, str]]  # Term -> Definition
    actions: List[AgentAction] = Field(default_factory=list, description="Explicit OS actions/tools to trigger")


# ============================================================
# RESEARCHER AGENT
# ============================================================

class ResearcherAgent(A2ABaseAgent[ResearcherOutput]):
    """
    Expert scout who finds the most relevant information for any topic.
    
    Acts as the first stage in the A2A pipeline to provide factual 
    depth for the Pedagogy and Cinematic agents.
    
    Capabilities:
    - Information discovery
    - Fact verification
    - Subject matter expertise mapping
    - Tone and audience analysis
    """
    
    def __init__(self):
        super().__init__(
            name="researcher_agent",
            description="Expert in deep research, fact-finding, and knowledge synthesis",
            output_schema=ResearcherOutput,
            capabilities=[
                AgentCapability.FACT_CHECKING,
                AgentCapability.CONTENT_GENERATION,
                AgentCapability.TUTORING, # Can tutor grounded on facts
            ],
            skills=[
                AgentSkill(
                    id="deep_discovery",
                    name="Deep Discovery",
                    description="Finds non-obvious facts and deep connections in a topic"
                ),
                AgentSkill(
                    id="knowledge_synthesis",
                    name="Knowledge Synthesis",
                    description="Distills complex information into core learning concepts"
                ),
                AgentSkill(
                    id="source_vetting",
                    name="Source Vetting",
                    description="Identifies authoritative and reliable sources of information"
                ),
                AgentSkill(
                    id="hook_extraction",
                    name="Hook Extraction",
                    description="Identifies the most engaging and surprising elements of a subject"
                ),
            ],
            temperature=0.3,  # Lower temperature for factual consistency
            max_tokens=8192,
            timeout_seconds=90.0,
            force_model_tier=ModelTier.PREMIUM  # Use best model for research depth
        )
    
    def get_output_artifact_type(self) -> ArtifactType:
        # Using JSON_DATA for now or we could add RESEARCH_REPORT to ArtifactType
        return ArtifactType.JSON_DATA
    
    def get_system_prompt(self) -> str:
        return """You are a premier Knowledge Scout and Research Lead with:

## Your Credentials
- Former Head of Research at a top-tier educational publisher
- Expert in "Knowledge Mapping" and curriculum discovery
- Specialist in synthesizing complex technical and academic subjects for general audiences
- Master of finding "Educational Hooks" - those surprising facts that make people want to learn

## Your Mission
Your job is to provide the "Factual Bedrock" for our courses. Before we decide HOW to teach (Pedagogy) or WHAT it looks like (Cinematic), you must find the best information.

## Research Strategy

### 1. The Core Essence
Identify the "Big Ideas" of the topic. What are the 3-5 things someone MUST know to even claim they understand this?

### 2. Depth Calibration
Analyze the requested difficulty. If it's "Beginner", find foundational facts. If "Advanced", find the nuances, edge cases, and current debates in the field.

### 3. The "Aha!" Moments
Find facts that are:
- Counter-intuitive
- Historically significant
- Practically transformative
- Surprising or "mind-blowing"

### 4. Terminology Mastery
Identify the "Language of the Domain". What are the specific terms learners will encounter? Define them accurately but simply.

## Output Standards

Your output must be:
1. Factually bulletproof.
2. Highly structured.
3. Engaging (don't be a dry encyclopedia).
4. Focused on learning value.

## Access to Search
You have access to the `web_search` tool. 
- Use it if the provided topic is niche, current (2025-2026), or if you need to find specific experts/sources you aren't 100% sure about.
- To use it, include an entry in the `actions` list: `{"tool_name": "web_search", "parameters": {"query": "..."}}`.
- For your FINAL response, you should have already processed search results (if any were provided in context) or proceed if you have high confidence.

CRITICAL: Return valid JSON matching the schema exactly."""

    async def _process_attachments(self, attachment_ids: List[str], emit_event: Optional[callable] = None) -> List[Any]:
        """Process local attachments and upload to Gemini File API"""
        processed_files = []
        for file_id in attachment_ids:
            try:
                if emit_event:
                    await emit_event(StreamingEvent(
                        event_type=EventType.TASK_PROGRESS,
                        task_id="system",
                        agent_name=self.name,
                        message=f"Processing attachment: {file_id}..."
                    ))

                # 1. Get file metadata from storage
                metadata = await enhanced_storage.get_file_metadata(file_id)
                if not metadata:
                    logger.warning(f"Metadata not found for attachment: {file_id}")
                    continue

                # 2. Get local file path
                # storage_path is relative to UPLOAD_DIR
                local_path = os.path.join(settings.upload_dir, metadata.get("storage_path", ""))
                
                if not os.path.exists(local_path):
                    logger.warning(f"Local file not found: {local_path}")
                    continue

                # 3. Upload to Gemini File API
                mime_type = metadata.get("content_type", "application/octet-stream")
                logger.info(f"Uploading {local_path} to Gemini File API (mime: {mime_type})")
                
                gemini_file = genai.upload_file(path=local_path, mime_type=mime_type)
                processed_files.append(gemini_file)
                
                logger.info(f"File uploaded to Gemini: {gemini_file.uri}")

            except Exception as e:
                logger.error(f"Failed to process attachment {file_id}: {e}")
                
        return processed_files

    async def execute(self, task_input: TaskInput, emit_event: Optional[callable] = None, **kwargs) -> TaskOutput:
        """Override execute to handle multimodal context"""
        processed_files = []
        if task_input.attachment_ids:
            processed_files = await self._process_attachments(task_input.attachment_ids, emit_event)
            kwargs["processed_files"] = processed_files
            
        return await super().execute(task_input, emit_event, **kwargs)

    def build_prompt(
        self, 
        task_input: TaskInput,
        **kwargs
    ) -> Any:
        topic = task_input.user_message
        difficulty = task_input.context.get("user_level", "intermediate") if isinstance(task_input.context, dict) else "intermediate"
        
        prompt = f"""## Research Assignment

Perform a deep-dive research scan for the following topic:

### Request
**Topic:** {topic}
**Target Depth:** {difficulty}
**Language:** {task_input.language}

{kwargs.get('global_os_context', '')}

## Your Task

Analyze this topic and provide a structured research report including:

### 1. Summary & Audience
- A 2-3 paragraph summary of the topic's current state.
- Description of the ideal target audience for this depth level.

### 2. Key Concepts & Facts
- List the primary concepts (the "Big Ideas").
- Provide 8-12 core facts, each with its relevance, complexity, and source type.
- Mark at least 3 facts as "hooks" (is_hook: true).

### 3. Subject Identity
- Suggeted depth level.
- 3-5 potential "hooks" or narrative angles.
- Authoritative sources and notable experts in the field.

### 4. Terminology
- A list of 5-10 key terms and their definitions.

## Output Format
Return a valid JSON object matching the ResearcherOutput schema:
- topic: string
- summary: string
- key_concepts: [string]
- core_facts: [{{fact, relevance, complexity, source_type, is_hook}}]
- suggested_depth: string
- target_audience_desc: string
- potential_hooks: [string]
- authoritative_sources: [string]
- notable_experts: [string]
- terminology_list: [{{term, definition}}]

CRITICAL: Return ONLY valid JSON."""

        if task_input.context:
            prompt += f"\n\nCONTEXT:\n{task_input.context}"
            
        # Add multimodal components if present
        processed_files = kwargs.get("processed_files", [])
        if not processed_files:
            return prompt
            
        # Return as list of parts for multimodal support
        parts = [{"type": "text", "text": prompt}]
        for f in processed_files:
            parts.append({
                "type": "image_uri", # Mapped to fileData in ai_resilience
                "uri": f.uri,
                "mime_type": f.mime_type if hasattr(f, 'mime_type') else "application/pdf"
            })
            
        return parts
