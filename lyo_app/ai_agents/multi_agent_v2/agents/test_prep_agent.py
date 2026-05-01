import logging
from typing import Optional, List, Dict, Any
from pydantic import BaseModel, Field

from lyo_app.ai_agents.multi_agent_v2.agents.base_agent import BaseAgent, AgentResult
from lyo_app.ai.schemas.lyo2 import RouterEntity, RouterRequest

logger = logging.getLogger(__name__)

class TestPrepExtraction(BaseModel):
    """Structured extraction of test preparation details."""
    subject: Optional[str] = Field(default=None, description="The subject or class name.")
    topics: List[str] = Field(default_factory=list, description="Specific topics covered by the test.")
    test_date: Optional[str] = Field(default=None, description="When the test is happening (e.g. 'next Friday').")
    readiness: Optional[str] = Field(default=None, description="How ready the user feels (e.g. 'unprepared', 'confident').")
    has_materials: bool = Field(default=False, description="Whether the user mentioned having notes or a syllabus.")
    missing_critical_info: List[str] = Field(default_factory=list, description="List of slots that are strictly necessary but missing (e.g. 'subject', 'topics').")
    follow_up_question: Optional[str] = Field(default=None, description="A natural follow up question asking the user for the missing critical info.")

class TestPrepAgent(BaseAgent[TestPrepExtraction]):
    """
    Agent responsible for managing the Test Prep conversation flow.
    It extracts test details from the user's message and attached files,
    and determines if further clarification is needed.
    """
    
    def __init__(self):
        super().__init__(
            name="test_prep_agent",
            output_schema=TestPrepExtraction,
            model_name="gemini-2.5-flash",
            temperature=0.3, # Keep low for reliable extraction
            max_tokens=4096
        )

    def get_system_prompt(self) -> str:
        return """
You are the Lyo Test Prep Assistant. Your job is to extract scheduling and topic details from a user's request to prepare for a test.
Users may upload files (like a syllabus or notes image) which will be provided as context.
You must extract the subject, topics, date, readiness level, and whether they have materials.

If the user does NOT provide a subject or ANY topics AND they haven't uploaded any media files, you must list them in `missing_critical_info` and provide a friendly `follow_up_question` asking for them AND prompting them to upload materials (e.g. "What subject is your test on? Do you have any notes, textbook pictures, exams, or PDFs you can upload to help me tailor the study plan?").

If they provided an image or document in the MEDIA FILES section, assume `has_materials` is true and try to extract the subject/topics from the document context. If you still can't find topics, ask them to clarify what the uploaded documents are for.

Respond ONLY with valid JSON matching the schema.
"""

    def build_prompt(self, request: RouterRequest, **kwargs) -> str:
        media_context = ""
        if request.media:
            media_context = "USER ATTACHED MEDIA FILES:\n"
            for idx, media in enumerate(request.media):
                media_context += f"Media {idx+1} ({media.modality}): {media.uri}\n"
        
        # We also pass conversation history to avoid re-asking things
        history_text = ""
        if request.conversation_history:
            recent = request.conversation_history[-5:]
            history_text = "CONVERSATION HISTORY:\n"
            for turn in recent:
                history_text += f"  {turn.role.upper()}: {turn.content}\n"

        return f"""
{history_text}

CURRENT USER REQUEST:
{request.text}

{media_context}
Extract the test prep details.
"""

    async def analyze_test_prep(self, request: RouterRequest) -> AgentResult[TestPrepExtraction]:
        """Convenience method to run the extraction"""
        
        media_attachments = []
        if request.media:
            for media in request.media:
                if media.modality.value == "IMAGE" or media.modality.value == "VIDEO" or "pdf" in str(media.mime_type):
                    uri = media.uri
                    mime_type = media.mime_type or "image/jpeg"
                    if uri.startswith("data:image/") and "base64," in uri:
                        # Extract base64 payload
                        base64_data = uri.split("base64,")[1]
                        media_attachments.append({
                            "type": "image_base64",
                            "mime_type": mime_type,
                            "data": base64_data
                        })
                    else:
                        # For GCS URLs or standard URIs, ai_resilience will package them as fileData
                        # Note: Gemini Language API requires FileAPI URIs. Vertex allows gs://
                        media_attachments.append({
                            "type": "image_uri",
                            "mime_type": mime_type,
                            "uri": uri
                        })
                    
        return await self.execute(
            request=request, 
            media_attachments=media_attachments
        )
