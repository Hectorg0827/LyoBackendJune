"""Shared, locale-aware text-to-speech for every Lyo classroom client.

The default provider is a self-hosted Kokoro service.  Kokoro exposes an
OpenAI-compatible ``/v1/audio/speech`` endpoint, so the application server
stays small while Web, iOS, and Android receive the same rendered audio.

Paid providers are deliberately opt-in.  In particular, OpenAI TTS is never
used merely because an OpenAI key happens to exist elsewhere in the backend.
"""

from __future__ import annotations

import asyncio
import base64
import hashlib
import logging
import os
import re
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, AsyncGenerator, Dict, Literal, Optional

import aiohttp

try:
    from lyo_app.integrations.gcp_secrets import get_secret
except Exception:
    def get_secret(name: str, default=None):
        return os.getenv(name, default)


logger = logging.getLogger(__name__)


# These public aliases are retained for existing clients.  Each alias resolves
# to the same canonical teacher identity for the requested language so a lesson
# never changes voice merely because it moved to another device.
VOICE_PROFILES = {
    "alloy": {
        "description": "Clear shared classroom teacher",
        "best_for": ["general_explanations", "definitions", "summaries"],
        "personality": "helpful_tutor",
    },
    "echo": {
        "description": "Warm shared classroom teacher",
        "best_for": ["storytelling", "history", "narratives"],
        "personality": "wise_mentor",
    },
    "fable": {
        "description": "Expressive shared classroom teacher",
        "best_for": ["engaging_content", "literature", "creative"],
        "personality": "enthusiastic_teacher",
    },
    "onyx": {
        "description": "Focused shared classroom teacher",
        "best_for": ["science", "math", "technical"],
        "personality": "expert_professor",
    },
    "nova": {
        "description": "Canonical Lyo classroom teacher",
        "best_for": ["interactive_lessons", "quizzes", "encouragement"],
        "personality": "friendly_coach",
    },
    "shimmer": {
        "description": "Gentle shared classroom teacher",
        "best_for": ["reflection", "study_tips", "calm_explanations"],
        "personality": "calm_guide",
    },
}

Voice = Literal["alloy", "echo", "fable", "onyx", "nova", "shimmer"]
AudioFormat = Literal["mp3", "opus", "aac", "flac", "wav", "pcm"]
Model = Literal["tts-1", "tts-1-hd"]
TTSProvider = Literal["kokoro", "google", "openai"]


KOKORO_VOICES = {
    "en": "af_heart",
    "es": "ef_dora",
    "fr": "ff_siwis",
    "it": "if_sara",
    "pt": "pf_dora",
}

GOOGLE_CHIRP_VOICES = {
    "en": ("en-US", "en-US-Chirp3-HD-Aoede"),
    "es": ("es-US", "es-US-Chirp3-HD-Aoede"),
    "fr": ("fr-FR", "fr-FR-Chirp3-HD-Aoede"),
    "it": ("it-IT", "it-IT-Chirp3-HD-Aoede"),
    "pt": ("pt-BR", "pt-BR-Chirp3-HD-Aoede"),
}

OPENAI_VOICES = {
    "alloy": "alloy",
    "echo": "echo",
    "fable": "fable",
    "onyx": "onyx",
    "nova": "nova",
    "shimmer": "shimmer",
}


class TTSUnavailableError(RuntimeError):
    """Raised when the explicitly configured provider is unavailable."""


@dataclass
class TTSConfig:
    """Runtime configuration with cost-safe defaults."""

    provider: TTSProvider = "kokoro"
    kokoro_base_url: str = "http://kokoro-tts:8880"
    kokoro_api_key: str = ""
    google_api_key: str = ""
    openai_api_key: str = ""
    allow_openai_tts: bool = False
    default_voice: Voice = "nova"
    default_model: Model = "tts-1-hd"
    default_format: AudioFormat = "mp3"
    default_speed: float = 0.98
    default_language: str = "en-US"
    cache_enabled: bool = True
    cache_dir: str = "/tmp/lyo_tts_cache"
    cache_ttl_hours: int = 168
    max_text_length: int = 1200
    request_timeout_seconds: int = 90

    @classmethod
    def from_environment(cls) -> "TTSConfig":
        raw_provider = (os.getenv("TTS_PROVIDER", "kokoro") or "kokoro").strip().lower()
        if raw_provider not in {"kokoro", "google", "openai"}:
            logger.warning("Unknown TTS_PROVIDER=%r; using kokoro", raw_provider)
            raw_provider = "kokoro"

        return cls(
            provider=raw_provider,  # type: ignore[arg-type]
            kokoro_base_url=(
                os.getenv("KOKORO_TTS_BASE_URL", "http://kokoro-tts:8880")
                or "http://kokoro-tts:8880"
            ).rstrip("/"),
            kokoro_api_key=(
                get_secret("KOKORO_TTS_API_KEY", os.getenv("KOKORO_TTS_API_KEY", ""))
                or ""
            ).strip(),
            google_api_key=(
                get_secret("GOOGLE_TTS_API_KEY", os.getenv("GOOGLE_TTS_API_KEY", ""))
                or ""
            ).strip(),
            openai_api_key=(
                get_secret("OPENAI_API_KEY", os.getenv("OPENAI_API_KEY", ""))
                or ""
            ).strip(),
            allow_openai_tts=(
                os.getenv("ALLOW_OPENAI_TTS", "false").strip().lower() == "true"
            ),
            default_language=os.getenv("TTS_DEFAULT_LANGUAGE", "en-US") or "en-US",
            cache_ttl_hours=max(1, int(os.getenv("TTS_CACHE_TTL_HOURS", "168"))),
        )


@dataclass(frozen=True)
class ResolvedVoice:
    provider: TTSProvider
    language_code: str
    language_family: str
    requested_voice: Voice
    provider_voice: str
    provider_model: str


class TTSService:
    """Render one consistent teacher voice for Web, iOS, and Android."""

    def __init__(self, config: Optional[TTSConfig] = None):
        self.config = config or TTSConfig.from_environment()
        self._session: Optional[aiohttp.ClientSession] = None
        self._initialized = False
        self._key_locks: Dict[str, asyncio.Lock] = {}

    async def initialize(self) -> None:
        if self._initialized:
            return

        Path(self.config.cache_dir).mkdir(parents=True, exist_ok=True)
        headers = {"Content-Type": "application/json"}
        if self.config.provider == "kokoro" and self.config.kokoro_api_key:
            headers["Authorization"] = f"Bearer {self.config.kokoro_api_key}"

        self._session = aiohttp.ClientSession(
            headers=headers,
            timeout=aiohttp.ClientTimeout(total=self.config.request_timeout_seconds),
        )
        self._initialized = True
        logger.info(
            "TTS initialized: provider=%s default_language=%s cache_ttl=%sh",
            self.config.provider,
            self.config.default_language,
            self.config.cache_ttl_hours,
        )

    async def close(self) -> None:
        if self._session:
            await self._session.close()
        self._session = None
        self._initialized = False

    @property
    def provider_available(self) -> bool:
        if self.config.provider == "kokoro":
            return bool(self.config.kokoro_base_url)
        if self.config.provider == "google":
            return bool(self.config.google_api_key)
        return bool(self.config.allow_openai_tts and self.config.openai_api_key)

    def select_voice_for_content(
        self, content_type: str, topic: Optional[str] = None
    ) -> Voice:
        # The alias still describes mood to older clients, but provider voice
        # resolution intentionally keeps one teacher identity per language.
        content_voice_map: Dict[str, Voice] = {
            "explanation": "alloy",
            "definition": "alloy",
            "summary": "alloy",
            "story": "echo",
            "history": "echo",
            "biography": "echo",
            "introduction": "fable",
            "welcome": "fable",
            "creative": "fable",
            "science": "onyx",
            "math": "onyx",
            "technical": "onyx",
            "code": "onyx",
            "quiz": "nova",
            "exercise": "nova",
            "encouragement": "nova",
            "congratulations": "nova",
            "reflection": "shimmer",
            "study_tips": "shimmer",
        }
        return content_voice_map.get(content_type, self.config.default_voice)

    @staticmethod
    def normalize_language(language: Optional[str], text: str, default: str) -> str:
        raw = (language or "").strip().replace("_", "-")
        if raw and raw.lower() not in {"auto", "und"}:
            language_names = {
                "english": "en-US",
                "spanish": "es-US",
                "español": "es-US",
                "french": "fr-FR",
                "français": "fr-FR",
                "italian": "it-IT",
                "italiano": "it-IT",
                "portuguese": "pt-BR",
                "português": "pt-BR",
            }
            if raw.lower() in language_names:
                return language_names[raw.lower()]
            family = raw.split("-", 1)[0].lower()
            locale_defaults = {
                "en": "en-US",
                "es": "es-US",
                "fr": "fr-FR",
                "it": "it-IT",
                "pt": "pt-BR",
            }
            parts = raw.split("-")
            if family in locale_defaults and len(parts) > 1 and len(parts[1]) == 2:
                return f"{family}-{parts[1].upper()}"
            return locale_defaults.get(family, raw)

        lowered = f" {text.lower()} "
        if re.search(r"[\u3040-\u30ff]", text):
            return "ja-JP"
        if re.search(r"[\u4e00-\u9fff]", text):
            return "zh-CN"
        if re.search(r"[\uac00-\ud7af]", text):
            return "ko-KR"

        token_sets = {
            "es-US": {
                " el ", " la ", " los ", " las ", " que ", " para ", " por ",
                " una ", " como ", " con ", " esta ", " este ", " porque ",
            },
            "fr-FR": {
                " le ", " la ", " les ", " des ", " une ", " pour ", " avec ",
                " est ", " que ", " dans ",
            },
            "it-IT": {
                " il ", " lo ", " gli ", " una ", " che ", " per ", " con ",
                " questo ", " questa ",
            },
            "pt-BR": {
                " os ", " as ", " uma ", " que ", " para ", " com ", " isso ",
                " este ", " esta ",
            },
        }
        accent_hints = {
            "es-US": "¿¡ñáéíóúü",
            "fr-FR": "àâçéèêëîïôùûüÿœ",
            "it-IT": "àèéìíîòóù",
            "pt-BR": "ãõáâàçéêíóôú",
        }
        scores = {
            locale: sum(token in lowered for token in tokens)
            + sum(char in text.lower() for char in accent_hints[locale])
            for locale, tokens in token_sets.items()
        }
        best_locale, best_score = max(scores.items(), key=lambda item: item[1])
        return best_locale if best_score >= 2 else default

    def resolve_voice(
        self,
        text: str,
        voice: Optional[Voice] = None,
        language: Optional[str] = None,
        content_type: Optional[str] = None,
    ) -> ResolvedVoice:
        requested_voice = (
            voice
            or (
                self.select_voice_for_content(content_type)
                if content_type
                else self.config.default_voice
            )
        )
        language_code = self.normalize_language(
            language, text, self.config.default_language
        )
        family = language_code.split("-", 1)[0].lower()

        if self.config.provider == "kokoro":
            provider_voice = KOKORO_VOICES.get(family)
            if not provider_voice:
                raise TTSUnavailableError(
                    f"Kokoro does not have a configured teacher voice for {language_code}"
                )
            provider_model = "kokoro"
        elif self.config.provider == "google":
            google_voice = GOOGLE_CHIRP_VOICES.get(family)
            if not google_voice:
                raise TTSUnavailableError(
                    f"Google Chirp does not have a configured teacher voice for {language_code}"
                )
            language_code, provider_voice = google_voice
            provider_model = "chirp-3-hd"
        else:
            if not self.config.allow_openai_tts:
                raise TTSUnavailableError(
                    "OpenAI TTS is disabled; set ALLOW_OPENAI_TTS=true explicitly"
                )
            provider_voice = OPENAI_VOICES[requested_voice]
            provider_model = self.config.default_model

        return ResolvedVoice(
            provider=self.config.provider,
            language_code=language_code,
            language_family=family,
            requested_voice=requested_voice,
            provider_voice=provider_voice,
            provider_model=provider_model,
        )

    def _get_cache_key(
        self,
        text: str,
        resolved: ResolvedVoice,
        audio_format: AudioFormat,
        speed: float,
    ) -> str:
        content = "|".join(
            [
                resolved.provider,
                resolved.provider_model,
                resolved.provider_voice,
                resolved.language_code,
                audio_format,
                f"{speed:.2f}",
                text,
            ]
        )
        return hashlib.sha256(content.encode("utf-8")).hexdigest()

    def _cache_path(self, cache_key: str, audio_format: AudioFormat) -> Path:
        return Path(self.config.cache_dir) / f"{cache_key}.{audio_format}"

    def _get_cached_audio(
        self, cache_key: str, audio_format: AudioFormat
    ) -> Optional[bytes]:
        if not self.config.cache_enabled:
            return None
        path = self._cache_path(cache_key, audio_format)
        try:
            modified = datetime.fromtimestamp(path.stat().st_mtime, tz=timezone.utc)
            if datetime.now(timezone.utc) - modified > timedelta(
                hours=self.config.cache_ttl_hours
            ):
                path.unlink(missing_ok=True)
                return None
            return path.read_bytes()
        except FileNotFoundError:
            return None
        except OSError as exc:
            logger.warning("TTS cache read failed: %s", exc)
            return None

    def _cache_audio(
        self, cache_key: str, audio_format: AudioFormat, audio_data: bytes
    ) -> None:
        if not self.config.cache_enabled:
            return
        path = self._cache_path(cache_key, audio_format)
        temp_path = path.with_suffix(path.suffix + ".tmp")
        try:
            temp_path.write_bytes(audio_data)
            temp_path.replace(path)
        except OSError as exc:
            logger.warning("TTS cache write failed: %s", exc)
            temp_path.unlink(missing_ok=True)

    async def synthesize(
        self,
        text: str,
        voice: Optional[Voice] = None,
        model: Optional[Model] = None,
        format: Optional[AudioFormat] = None,
        speed: float = 1.0,
        content_type: Optional[str] = None,
        language: Optional[str] = None,
    ) -> bytes:
        if not self._initialized:
            await self.initialize()
        if not self.provider_available:
            raise TTSUnavailableError(
                f"The configured TTS provider ({self.config.provider}) is unavailable"
            )

        normalized_text = " ".join(text.split())
        if not normalized_text:
            raise ValueError("Text cannot be empty")
        if len(normalized_text) > self.config.max_text_length:
            raise ValueError(
                f"Text exceeds the {self.config.max_text_length}-character speech limit"
            )
        if not 0.75 <= speed <= 1.25:
            raise ValueError("Classroom speech speed must be between 0.75 and 1.25")

        audio_format = format or self.config.default_format
        resolved = self.resolve_voice(
            normalized_text,
            voice=voice,
            language=language,
            content_type=content_type,
        )
        cache_key = self._get_cache_key(
            normalized_text, resolved, audio_format, speed
        )
        cached = self._get_cached_audio(cache_key, audio_format)
        if cached is not None:
            return cached

        lock = self._key_locks.setdefault(cache_key, asyncio.Lock())
        try:
            async with lock:
                cached = self._get_cached_audio(cache_key, audio_format)
                if cached is not None:
                    return cached
                audio_data = await self._synthesize_uncached(
                    normalized_text,
                    resolved,
                    audio_format,
                    speed,
                    model=model,
                )
                if not audio_data:
                    raise RuntimeError("TTS provider returned empty audio")
                self._cache_audio(cache_key, audio_format, audio_data)
                logger.info(
                    "TTS rendered %s bytes provider=%s locale=%s voice=%s",
                    len(audio_data),
                    resolved.provider,
                    resolved.language_code,
                    resolved.provider_voice,
                )
                return audio_data
        finally:
            self._key_locks.pop(cache_key, None)

    async def _synthesize_uncached(
        self,
        text: str,
        resolved: ResolvedVoice,
        audio_format: AudioFormat,
        speed: float,
        model: Optional[Model],
    ) -> bytes:
        if not self._session:
            raise TTSUnavailableError("TTS HTTP session is not initialized")

        if resolved.provider == "kokoro":
            payload = {
                "model": resolved.provider_model,
                "input": text,
                "voice": resolved.provider_voice,
                "response_format": audio_format,
                "speed": speed,
            }
            return await self._post_binary(
                f"{self.config.kokoro_base_url}/v1/audio/speech", payload
            )

        if resolved.provider == "google":
            payload = {
                "input": {"text": text},
                "voice": {
                    "languageCode": resolved.language_code,
                    "name": resolved.provider_voice,
                },
                "audioConfig": {
                    "audioEncoding": audio_format.upper(),
                    "speakingRate": speed,
                },
            }
            url = (
                "https://texttospeech.googleapis.com/v1/text:synthesize"
                f"?key={self.config.google_api_key}"
            )
            async with self._session.post(url, json=payload) as response:
                if response.status != 200:
                    detail = (await response.text())[:500]
                    raise RuntimeError(
                        f"Google TTS request failed with status {response.status}: {detail}"
                    )
                data = await response.json()
            encoded = data.get("audioContent")
            if not encoded:
                raise RuntimeError("Google TTS response did not contain audio")
            return base64.b64decode(encoded)

        payload = {
            "model": model or self.config.default_model,
            "input": text,
            "voice": resolved.provider_voice,
            "response_format": audio_format,
            "speed": speed,
        }
        headers = {
            "Authorization": f"Bearer {self.config.openai_api_key}",
            "Content-Type": "application/json",
        }
        return await self._post_binary(
            "https://api.openai.com/v1/audio/speech", payload, headers=headers
        )

    async def _post_binary(
        self,
        url: str,
        payload: Dict[str, Any],
        headers: Optional[Dict[str, str]] = None,
    ) -> bytes:
        if not self._session:
            raise TTSUnavailableError("TTS HTTP session is not initialized")
        async with self._session.post(url, json=payload, headers=headers) as response:
            if response.status != 200:
                detail = (await response.text())[:500]
                raise RuntimeError(
                    f"TTS provider request failed with status {response.status}: {detail}"
                )
            return await response.read()

    async def synthesize_streaming(
        self,
        text: str,
        voice: Optional[Voice] = None,
        model: Optional[Model] = None,
        format: AudioFormat = "mp3",
        speed: float = 1.0,
        language: Optional[str] = None,
        chunk_size: int = 8192,
    ) -> AsyncGenerator[bytes, None]:
        # Render once so streaming and base64 clients share the same cache and
        # never trigger duplicate metered synthesis for the same sentence.
        audio_data = await self.synthesize(
            text=text,
            voice=voice,
            model=model,
            format=format,
            speed=speed,
            language=language,
        )
        for offset in range(0, len(audio_data), chunk_size):
            yield audio_data[offset:offset + chunk_size]

    async def synthesize_lesson_audio(
        self,
        lesson_content: Dict[str, Any],
        voice: Optional[Voice] = None,
        language: Optional[str] = None,
    ) -> Dict[str, bytes]:
        segments: Dict[str, bytes] = {}
        candidates = []
        if lesson_content.get("introduction"):
            candidates.append(
                ("introduction", lesson_content["introduction"], "introduction")
            )
        for index, block in enumerate(lesson_content.get("content_blocks", [])):
            if block.get("block_type") == "code":
                content = block.get("explanation", "")
                content_type = "code"
            else:
                content = block.get("content", "")
                content_type = "explanation"
            if content:
                candidates.append((f"block_{index}", content, content_type))
        if lesson_content.get("summary"):
            candidates.append(("summary", lesson_content["summary"], "summary"))

        # Sequential generation protects a metered fallback from bursts and
        # maximizes deterministic cache reuse.
        for segment_id, content, content_type in candidates:
            segments[segment_id] = await self.synthesize(
                content,
                voice=voice,
                content_type=content_type,
                language=language,
            )
        return segments

    def get_voice_info(self, voice: Voice) -> Dict[str, Any]:
        profile = VOICE_PROFILES.get(voice, {})
        return {
            "voice": voice,
            "description": profile.get("description", ""),
            "best_for": profile.get("best_for", []),
            "personality": profile.get("personality", ""),
        }

    def list_voices(self) -> Dict[str, Dict[str, Any]]:
        return {
            voice: self.get_voice_info(voice)
            for voice in VOICE_PROFILES
        }


_tts_service: Optional[TTSService] = None


async def get_tts_service() -> TTSService:
    global _tts_service
    if _tts_service is None:
        _tts_service = TTSService()
        await _tts_service.initialize()
    return _tts_service
