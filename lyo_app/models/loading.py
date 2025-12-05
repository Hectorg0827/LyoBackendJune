"""Unified Tutor Model Loader & Generation Utilities

Provides:
 - Lazy loading of base Gemma (or other) model with optional LoRA adapter
 - 4-bit (QLoRA) quantization support (fallback to full precision if unavailable)
 - Structured tutor prompt construction for: explanations, hints, reflection
 - Safe fallback mock model when heavy deps missing

Environment Variables (override defaults):
 - MODEL_ID (default: google/gemma-2b-it)
 - MODEL_DIR (default: ./models)
 - LORA_ADAPTER_PATH (optional path to PEFT adapter)
 - MAX_NEW_TOKENS (optional int)
"""

from __future__ import annotations

import os
import json
import time
import logging
from dataclasses import dataclass
from typing import Any, Dict, Optional
from pathlib import Path

logger = logging.getLogger(__name__)


def _env(name: str, default: Optional[str] = None) -> Optional[str]:
    return os.getenv(name, default)


@dataclass
class TutorGenerationResult:
    """Represents a parsed structured tutor output."""
    raw: str
    response: str
    reasoning: Optional[str] = None
    next_hint: Optional[str] = None
    meta: Dict[str, Any] = None


class _MockPipe:
    def __call__(self, prompt: str, **kwargs):  # type: ignore
        # Produce minimal structured JSON content for dev.
        content = {
            "reason": "Mock reasoning path demonstrating scaffold.",
            "response": "Let's break this down. First, identify the loop bounds...",
            "next_hint": "What variable changes each iteration?"
        }
        return [{"generated_text": prompt + json.dumps(content)}]


class TutorModel:
    """Encapsulates model + tokenizer + generation pipeline for tutoring tasks."""

    def __init__(self):
        self.base_id: str = _env("MODEL_ID", "google/gemma-2b-it")
        self.cache_dir = Path(_env("MODEL_DIR", "./models"))
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self.adapter_path = _env("LORA_ADAPTER_PATH")
        self.tokenizer = None
        self.model = None
        self.pipe = None
        self.loaded = False
        self.adapter_loaded = False
        self.max_new_tokens_default = int(_env("MAX_NEW_TOKENS", "512"))

    def load(self):
        if self.loaded:
            return
        t0 = time.time()
        try:
            from transformers import (
                AutoTokenizer,
                AutoModelForCausalLM,
                BitsAndBytesConfig,
                pipeline,
            )
            import torch
        except Exception as e:  # dependencies missing
            logger.warning(f"Transformers/torch unavailable, using mock pipeline: {e}")
            self.pipe = _MockPipe()
            self.loaded = True
            return

        quant_cfg = None
        try:
            from transformers import BitsAndBytesConfig  # noqa
            quant_cfg = BitsAndBytesConfig(
                load_in_4bit=True,
                bnb_4bit_use_double_quant=True,
                bnb_4bit_quant_type="nf4",
                bnb_4bit_compute_dtype=torch.bfloat16,
            )
        except Exception as e:  # bitsandbytes not installed or CPU only
            logger.warning(f"4-bit quantization unavailable, falling back to full precision: {e}")

        logger.info(f"Loading base model {self.base_id} (quantized={quant_cfg is not None})")
        self.tokenizer = AutoTokenizer.from_pretrained(
            self.base_id,
            cache_dir=str(self.cache_dir),
            trust_remote_code=True,
        )
        if self.tokenizer.pad_token is None:
            self.tokenizer.pad_token = self.tokenizer.eos_token

        model_kwargs: Dict[str, Any] = {
            "cache_dir": str(self.cache_dir),
            "trust_remote_code": True,
            "device_map": "auto",
        }
        if quant_cfg is not None:
            model_kwargs["quantization_config"] = quant_cfg

        self.model = AutoModelForCausalLM.from_pretrained(self.base_id, **model_kwargs)

        # Attempt LoRA adapter load lazily
        if self.adapter_path and Path(self.adapter_path).exists():
            try:
                from peft import PeftModel
                self.model = PeftModel.from_pretrained(self.model, self.adapter_path)
                self.adapter_loaded = True
                logger.info(f"Loaded LoRA adapter: {self.adapter_path}")
            except Exception as e:
                logger.warning(f"Failed to load LoRA adapter ({self.adapter_path}): {e}")

        try:
            from transformers import pipeline as hf_pipeline
            self.pipe = hf_pipeline(
                "text-generation",
                model=self.model,
                tokenizer=self.tokenizer,
                device_map="auto",
                torch_dtype=getattr(self.model, "dtype", None),
            )
        except Exception as e:
            logger.warning(f"Falling back to mock pipeline: {e}")
            self.pipe = _MockPipe()

        self.loaded = True
        logger.info(
            f"Tutor model ready in {time.time()-t0:.1f}s adapter={self.adapter_loaded} quant={quant_cfg is not None}"
        )

    # -------------------- Prompt & Generation -------------------- #
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

    def generate(
        self,
        prompt: str,
        max_new_tokens: Optional[int] = None,
        temperature: float = 0.7,
        top_p: float = 0.9,
    ) -> str:
        if not self.loaded:
            raise RuntimeError("Model not loaded - call load() first")
        max_new_tokens = max_new_tokens or self.max_new_tokens_default
        out = self.pipe(
            prompt,
            max_new_tokens=max_new_tokens,
            temperature=temperature,
            top_p=top_p,
            do_sample=True,
            pad_token_id=self.tokenizer.eos_token_id if self.tokenizer else None,
            eos_token_id=self.tokenizer.eos_token_id if self.tokenizer else None,
        )[0]["generated_text"]
        return out[len(prompt):].strip()

    # -------------------- Parsing -------------------- #
    @staticmethod
    def _extract_json(text: str) -> Optional[Dict[str, Any]]:
        """Attempt to locate and parse first JSON object in text."""
        start = text.find("{")
        end = text.rfind("}")
        if start == -1 or end == -1 or end <= start:
            return None
        snippet = text[start : end + 1]
        try:
            return json.loads(snippet)
        except Exception:
            return None

    def structured_generate(
        self,
        system_goal: str,
        student_input: str,
        level: str = "beginner",
        mode: str = "explanation",
        hint_level: Optional[int] = None,
        **gen_kwargs,
    ) -> TutorGenerationResult:
        prompt = self.build_prompt(system_goal, student_input, level, mode, hint_level)
        raw = self.generate(prompt, **gen_kwargs)
        data = self._extract_json(raw) or {}
        return TutorGenerationResult(
            raw=raw,
            response=data.get("response", raw.strip()),
            reasoning=data.get("reason"),
            next_hint=data.get("next_hint"),
            meta={"parsed": bool(data), "mode": mode, "level": level},
        )

    # -------------------- Info -------------------- #
    def info(self) -> Dict[str, Any]:
        return {
            "base_model": self.base_id,
            "adapter_loaded": self.adapter_loaded,
            "adapter_path": self.adapter_path if self.adapter_loaded else None,
            "loaded": self.loaded,
        }


# Global instance
tutor_model = TutorModel()


def ensure_model():
    tutor_model.load()


def generate_tutor_response(
    system_goal: str,
    student_input: str,
    level: str = "beginner",
    mode: str = "explanation",
    hint_level: Optional[int] = None,
    **gen_kwargs,
) -> TutorGenerationResult:
    ensure_model()
    return tutor_model.structured_generate(
        system_goal=system_goal,
        student_input=student_input,
        level=level,
        mode=mode,
        hint_level=hint_level,
        **gen_kwargs,
    )


"""Backwards compatibility shim (legacy API names used elsewhere maybe)"""
model_manager = tutor_model  # type: ignore

def generate_course_content(prompt: str, **kwargs) -> str:
    """
    Generate course content using the loaded model.
    Shim for compatibility with ai_model_manager.generate_course_content interface.
    """
    ensure_model()
    return tutor_model.generate(prompt, **kwargs)
