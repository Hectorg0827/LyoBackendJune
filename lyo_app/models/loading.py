"""Unified AI Model Access Layer

Provides direct integration with the AI Resilience Manager (Gemini) 
for all tutoring and course generation tasks. Local model loading is disabled.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from typing import Any, Dict, Optional

from lyo_app.core.ai_resilience import ai_resilience_manager

logger = logging.getLogger(__name__)


@dataclass
class TutorGenerationResult:
    """Represents a parsed structured tutor output."""
    raw: str
    response: str
    reasoning: Optional[str] = None
    next_hint: Optional[str] = None
    meta: Dict[str, Any] = None


class ModelManager:
    """Encapsulates AI generation logic using Gemini via AIResilienceManager."""

    def __init__(self):
        self.loaded = True # Always "loaded" because we use a remote API
        self.max_new_tokens_default = 512

    def load(self):
        """No-op for compatibility."""
        pass

    def is_loaded(self) -> bool:
        return True

    @staticmethod
    def build_prompt(
        system_goal: str,
        student_input: str,
        level: str = "beginner",
        mode: str = "explanation",
        hint_level: Optional[int] = None,
    ) -> str:
        """Construct a structured tutoring prompt.

        Modes: explanation | hint | reflection
        Output contract: JSON with keys: reason, response, next_hint (optional)
        """
        scaffold_directive = {
            "explanation": "Provide a scaffolded explanation then a reflective question.",
            "hint": "Give ONLY the next minimal Socratic hint. Do NOT give the final answer.",
            "reflection": "Facilitate metacognition: ask learner to evaluate their approach.",
        }.get(mode, "Provide a helpful response.")

        hint_meta = f"HintLevel:{hint_level}" if hint_level else ""
        prompt = (
            f"<|system|>Role: Adaptive expert tutor. Goal:{system_goal}. StudentLevel:{level}. {scaffold_directive} "
            f"Output JSON: {{\"reason\":..., \"response\":..., \"next_hint\": optional}} {hint_meta}</|system|>\n"
            f"<|student|>{student_input}</|student|>\n<|tutor|>"
        )
        return prompt

    async def generate(
        self,
        prompt: str,
        max_new_tokens: Optional[int] = None,
        temperature: float = 0.7,
        top_p: float = 0.9,
    ) -> str:
        """Generate content using Gemini."""
        try:
            messages = [{"role": "user", "content": prompt}]
            max_tokens = max_new_tokens or self.max_new_tokens_default
            
            response = await ai_resilience_manager.chat_completion(
                messages, 
                temperature=temperature, 
                max_tokens=max_tokens
            )
            return response.get("content", "")
        except Exception as e:
            logger.error(f"Gemini generation failed: {e}")
            return "I'm sorry, I'm having trouble connecting to my AI core right now."

    async def structured_generate(
        self,
        system_goal: str,
        student_input: str,
        level: str = "beginner",
        mode: str = "explanation",
        hint_level: Optional[int] = None,
        **gen_kwargs,
    ) -> TutorGenerationResult:
        prompt = self.build_prompt(system_goal, student_input, level, mode, hint_level)
        raw = await self.generate(prompt, **gen_kwargs)
        data = self._extract_json(raw) or {}
        return TutorGenerationResult(
            raw=raw,
            response=data.get("response", raw.strip()),
            reasoning=data.get("reason"),
            next_hint=data.get("next_hint"),
            meta={"parsed": bool(data), "mode": mode, "level": level},
        )

    @staticmethod
    def _extract_json(text: str) -> Optional[Dict[str, Any]]:
        """Attempt to locate and parse first JSON object in text."""
        # Remove markdown code blocks if present
        if "```json" in text:
            text = text.split("```json")[1].split("```")[0]
        elif "```" in text:
            text = text.split("```")[1].split("```")[0]
            
        start = text.find("{")
        end = text.rfind("}")
        if start == -1 or end == -1 or end <= start:
            return None
        snippet = text[start : end + 1]
        try:
            return json.loads(snippet)
        except Exception:
            return None

    async def get_model(self):
        """Compatibility shim for ContentCurator."""
        return self

    async def analyze_content(self, prompt: str) -> Dict[str, Any]:
        """Analyze content quality and characteristics using Gemini."""
        raw = await self.generate(prompt)
        data = self._extract_json(raw) or {}
        return data

    async def generate_learning_path(self, prompt: str) -> Dict[str, Any]:
        """Generate a learning path using Gemini."""
        raw = await self.generate(prompt)
        data = self._extract_json(raw) or {}
        return data

    async def score_content_relevance(self, prompt: str) -> Dict[str, Any]:
        """Score content relevance using Gemini."""
        raw = await self.generate(prompt)
        data = self._extract_json(raw) or {}
        return data

    def info(self) -> Dict[str, Any]:
        return {
            "engine": "Gemini (via AIResilienceManager)",
            "loaded": True,
        }


# Global instance
model_manager = ModelManager()

def ensure_model():
    """Compatibility shim."""
    pass

async def generate_tutor_response(
    system_goal: str,
    student_input: str,
    level: str = "beginner",
    mode: str = "explanation",
    hint_level: Optional[int] = None,
    **gen_kwargs,
) -> TutorGenerationResult:
    return await model_manager.structured_generate(
        system_goal=system_goal,
        student_input=student_input,
        level=level,
        mode=mode,
        hint_level=hint_level,
        **gen_kwargs,
    )

# Backwards compatibility shims
tutor_model = model_manager

async def generate_course_content(prompt: str, **kwargs) -> str:
    """
    Generate course content using Gemini.
    """
    return await model_manager.generate(prompt, **kwargs)
