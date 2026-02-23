import asyncio
import json
import logging
import os
import uuid
from typing import AsyncGenerator
import anthropic

try:
    from google.cloud import texttospeech
except ImportError:
    texttospeech = None

from .schemas import (
    ConceptCard,
    DiagramCard,
    AnalogyCard,
    QuizCard,
    ReflectCard,
    SummaryCard,
    TransitionCard,
    DiagramNode,
    DiagramConnection,
    LyoLessonMetadata,
    LyoLessonPalette,
    LyoStreamChunk,
    LyoCardType,
)

logger = logging.getLogger(__name__)

class ContentGenerator:
    """
    Simulates the LangGraph multi-agent pipeline (System A) to generate 
    the 7 exact Lyo Cards for a given topic via the Claude API.
    """
    def __init__(self):
        self.client = anthropic.AsyncAnthropic(
            api_key=os.getenv("ANTHROPIC_API_KEY")
        )
        self.tts_client = texttospeech.TextToSpeechAsyncClient() if texttospeech else None
        
        # Ensure audio output directory exists
        self.audio_dir = "/tmp/lyo_classroom_audio"
        os.makedirs(self.audio_dir, exist_ok=True)
        # Server host URL for serving the static files
        self.base_url = os.getenv("API_URL", "http://127.0.0.1:8000")

    async def _synthesize_speech(self, text: str) -> str:
        """Synthesizes text to an MP3 file and returns the local URL."""
        if not self.tts_client:
            logger.warning("Google Cloud TTS not installed. Skipping audio generation.")
            return None
            
        try:
            input_text = texttospeech.SynthesisInput(text=text)
            
            # Neural2 Journey voice for a premium teacher feel
            voice = texttospeech.VoiceSelectionParams(
                language_code="en-US",
                name="en-US-Neural2-F" # Female confident voice
            )
            
            audio_config = texttospeech.AudioConfig(
                audio_encoding=texttospeech.AudioEncoding.MP3
            )
            
            response = await self.tts_client.synthesize_speech(
                request={"input": input_text, "voice": voice, "audio_config": audio_config}
            )
            
            file_id = f"voice_{uuid.uuid4().hex[:8]}.mp3"
            file_path = os.path.join(self.audio_dir, file_id)
            
            with open(file_path, "wb") as out:
                out.write(response.audio_content)
                
            return f"{self.base_url}/static/classroom_audio/{file_id}"
            
        except Exception as e:
            logger.error(f"TTS synthesis error: {e}")
            return None

    async def _generate_card_json(self, system_prompt: str, user_prompt: str) -> dict:
        """Helper to generate a strictly formatted JSON response from Claude."""
        try:
            response = await self.client.messages.create(
                model="claude-3-5-sonnet-20241022",
                max_tokens=1000,
                temperature=0.7,
                system=system_prompt,
                messages=[
                    {"role": "user", "content": user_prompt}
                ]
            )
            raw_text = response.content[0].text
            # Very basic extraction if enclosed in markdown
            if "```json" in raw_text:
                raw_text = raw_text.split("```json")[1].split("```")[0]
            elif "```" in raw_text:
                raw_text = raw_text.split("```")[1].split("```")[0]
            return json.loads(raw_text.strip())
        except Exception as e:
            logger.error(f"Claude Generation error: {e}")
            return {}

    async def stream_lesson(self, topic: str) -> AsyncGenerator[LyoStreamChunk, None]:
        """
        Streams a complete lesson containing exactly 7 cards.
        """
        # Director Agent (Rule-based Palette Assignment)
        # We assign a palette matching the topic vibe.
        palette = LyoLessonPalette(
            color1_hex="#2B1A4A", # Deep indigo
            color2_hex="#1A51AC", # Electric blue
            color3_hex="#111111"  # Near-black
        )
        
        metadata = LyoLessonMetadata(
            topic=topic,
            palette=palette
        )
        yield LyoStreamChunk(metadata=metadata)

        # 1. Transition Card (Intro)
        transition_voice = f"Welcome to today's lesson on {topic}. Let's dive right in."
        transition_audio = await self._synthesize_speech(transition_voice)
        yield LyoStreamChunk(card=TransitionCard(
            title=f"Welcome to {topic}",
            voice_text=transition_voice,
            audio_url=transition_audio
        ))

        # 2. Concept Card
        concept_data = await self._generate_card_json(
            system_prompt="You are a brilliant teacher. Explain a core concept of the user's topic. ONLY output valid JSON strictly matching: {\"key_term\": string, \"body_text\": string, \"voice_text\": string}. No other text.",
            user_prompt=f"Topic: {topic}"
        )
        voice_text = concept_data.get("voice_text", "Let's explore this core concept together.")
        concept_audio = await self._synthesize_speech(voice_text)
        yield LyoStreamChunk(card=ConceptCard(
            key_term=concept_data.get("key_term", topic),
            body_text=concept_data.get("body_text", "A fundamental concept."),
            voice_text=voice_text,
            audio_url=concept_audio
        ))

        # 3. Analogy Card
        analogy_data = await self._generate_card_json(
            system_prompt="You make abstract ideas concrete. Provide an analogy. ONLY output valid JSON strictly matching: {\"concept_side\": string, \"analogy_side\": string, \"voice_text\": string}. No other text.",
            user_prompt=f"Topic: {topic}"
        )
        voice_text = analogy_data.get("voice_text", "To understand this, imagine a familiar scenario.")
        analogy_audio = await self._synthesize_speech(voice_text)
        yield LyoStreamChunk(card=AnalogyCard(
            concept_side=analogy_data.get("concept_side", "The Abstract"),
            analogy_side=analogy_data.get("analogy_side", "The Concrete"),
            voice_text=voice_text,
            audio_url=analogy_audio
        ))

        # 4. Diagram Card
        diagram_data = await self._generate_card_json(
            system_prompt="Visualize a process using SF Symbols. ONLY output valid JSON: {\"nodes\": [{\"id\": string, \"symbol_name\": string, \"label\": string}], \"connections\": [{\"source_id\": string, \"target_id\": string}], \"voice_text\": string}. Ensure symbols exist in iOS SF Symbols.",
            user_prompt=f"Topic: {topic}"
        )
        nodes = [DiagramNode(**n) for n in diagram_data.get("nodes", [{"id":"1", "symbol_name":"star.fill", "label":"Core"}])]
        conns = [DiagramConnection(**c) for c in diagram_data.get("connections", [])]
        voice_text = diagram_data.get("voice_text", "Notice how these components connect.")
        diagram_audio = await self._synthesize_speech(voice_text)
        yield LyoStreamChunk(card=DiagramCard(
            nodes=nodes,
            connections=conns,
            voice_text=voice_text,
            audio_url=diagram_audio
        ))

        # 5. Reflect Card
        reflect_data = await self._generate_card_json(
            system_prompt="Create a contemplative reflection question. ONLY output valid JSON: {\"prompt\": string, \"voice_text\": string}.",
            user_prompt=f"Topic: {topic}"
        )
        voice_text = reflect_data.get("voice_text", "Take a moment to reflect on everything we just discussed.")
        reflect_audio = await self._synthesize_speech(voice_text)
        yield LyoStreamChunk(card=ReflectCard(
            prompt=reflect_data.get("prompt", "What does this mean to you?"),
            voice_text=voice_text,
            audio_url=reflect_audio
        ))

        # 6. Quiz Card
        quiz_data = await self._generate_card_json(
            system_prompt="Create a single multiple choice question to assess understanding. Meaningful wrong answers only. ONLY output valid JSON: {\"question\": string, \"options\": [string, string, string], \"correct_option_index\": int, \"explanation\": string, \"voice_text\": string}.",
            user_prompt=f"Topic: {topic}"
        )
        voice_text = quiz_data.get("voice_text", "Let's test what you've learned.")
        quiz_audio = await self._synthesize_speech(voice_text)
        yield LyoStreamChunk(card=QuizCard(
            question=quiz_data.get("question", "What did we learn?"),
            options=quiz_data.get("options", ["A", "B", "C", "D"])[:4],
            correct_option_index=quiz_data.get("correct_option_index", 0),
            explanation=quiz_data.get("explanation", "Review the concept."),
            voice_text=voice_text,
            audio_url=quiz_audio
        ))

        # 7. Summary Card
        summary_data = await self._generate_card_json(
            system_prompt="Consolidate the lesson into 3-4 key bullet points. ONLY output valid JSON: {\"title\": string, \"key_points\": [string, string, string], \"voice_text\": string}.",
            user_prompt=f"Topic: {topic}"
        )
        voice_text = summary_data.get("voice_text", "To wrap up, here are the key takeaways.")
        summary_audio = await self._synthesize_speech(voice_text)
        yield LyoStreamChunk(card=SummaryCard(
            title=summary_data.get("title", "Lesson Summary"),
            key_points=summary_data.get("key_points", ["Point 1", "Point 2", "Point 3"]),
            voice_text=voice_text,
            audio_url=summary_audio
        ))

        # Stream Complete
        yield LyoStreamChunk(is_complete=True)
