"""Durable, scoped cache for complete validated classroom units.

Nothing about a learner's answers, diagnostic result or mastery enters the
key or the saved content. The unit's authored material is hashed so editing a
lesson invalidates an old package even when its skill identity stays stable.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from uuid import UUID

from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from lyo_app.ai_classroom.models import ClassroomQuestionExposure, ClassroomUnitPackage
from lyo_app.ai_classroom.teaching_prompt import unit_package_prompt


PACKAGE_VERSION = 1


@dataclass(frozen=True)
class PackageKey:
    cache_key: str
    skill_id: str
    level_band: int
    language_code: str
    content_hash: str


def package_key(context, unit, skill_id: str | None) -> PackageKey | None:
    """Reuse content only when the skill, source, difficulty and locale agree."""
    try:
        UUID(skill_id or "")
    except (ValueError, TypeError):
        return None
    language = context.language_code.strip().lower()
    if not language or len(language) > 35:
        return None
    level = max(0, min(4, int(context.preferred_difficulty * 4)))
    source = {
        "unit": unit.model_dump(mode="json"),
        "goal": context.learning_objective,
        "lesson": (context.lesson_content or "")[:12000],
    }
    content_hash = hashlib.sha256(json.dumps(
        source, sort_keys=True, ensure_ascii=False, separators=(",", ":"),
    ).encode("utf-8")).hexdigest()
    prompt_hash = hashlib.sha256(unit_package_prompt().encode("utf-8")).hexdigest()
    material = f"{PACKAGE_VERSION}\0{prompt_hash}\0{skill_id}\0{level}\0{language}\0{content_hash}"
    digest = hashlib.sha256(material.encode("utf-8")).hexdigest()
    return PackageKey(digest, skill_id, level, language, content_hash)


class DatabaseUnitPackageCache:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def get(self, key: PackageKey) -> dict | None:
        row = await self.db.get(ClassroomUnitPackage, key.cache_key)
        if row is None:
            return None
        if (row.skill_id != key.skill_id or row.level_band != key.level_band or
                row.language_code != key.language_code or row.content_hash != key.content_hash or
                row.version != PACKAGE_VERSION):
            await self.evict(key)
            return None
        return row.content

    async def evict(self, key: PackageKey) -> None:
        row = await self.db.get(ClassroomUnitPackage, key.cache_key)
        if row is not None:
            await self.db.delete(row)
            await self.db.flush()

    async def put(self, key: PackageKey, content: dict) -> None:
        # Two workers may prepare the same skill simultaneously. One wins the
        # unique key; both have validated a complete package before this write.
        try:
            async with self.db.begin_nested():
                self.db.add(ClassroomUnitPackage(
                    cache_key=key.cache_key, skill_id=key.skill_id,
                    level_band=key.level_band, language_code=key.language_code,
                    content_hash=key.content_hash, version=PACKAGE_VERSION,
                    content=content,
                ))
                await self.db.flush()
        except IntegrityError:
            # The transaction that won the race has the same complete key.
            # Never replace an existing package with a partial write.
            pass

    async def claim_question(self, learner_id: str, skill_id: str, task) -> bool:
        """Keep a previously shown question from proving a new skill rung."""
        from lyo_app.ai_classroom.adaptive_teaching import normalize_text

        question = normalize_text(task.scenario + " " + task.question)
        learner_hash = hashlib.sha256(str(learner_id).encode("utf-8")).hexdigest()
        question_hash = hashlib.sha256(question.encode("utf-8")).hexdigest()
        try:
            async with self.db.begin_nested():
                self.db.add(ClassroomQuestionExposure(
                    learner_hash=learner_hash, skill_id=skill_id, question_hash=question_hash,
                ))
                await self.db.flush()
            return True
        except IntegrityError:
            return False
