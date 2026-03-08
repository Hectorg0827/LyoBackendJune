"""
Personality Adapter — Evolves Lyo's communication style for each member.
Part of the Persistent Relationship System (Pillar 4).

The adapter observes interaction signals and slowly adjusts personality
parameters so Lyo's tone & pedagogy match the learner's preferences.
"""

import logging
from typing import Optional, Dict

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from .models import PersonalityProfile

logger = logging.getLogger(__name__)


async def get_personality(db: AsyncSession, user_id: int) -> PersonalityProfile:
    """Return the personality profile for a user, creating a default if missing."""
    result = await db.execute(
        select(PersonalityProfile).where(PersonalityProfile.user_id == user_id)
    )
    profile = result.scalar_one_or_none()
    if not profile:
        profile = PersonalityProfile(user_id=user_id)
        db.add(profile)
        await db.commit()
        await db.refresh(profile)
        logger.info(f"🎭 Created default personality profile for user {user_id}")
    return profile


async def adapt_personality(
    db: AsyncSession,
    user_id: int,
    signal: str,
    value: float,
) -> PersonalityProfile:
    """
    Nudge a personality dimension based on an observed interaction signal.

    Signals:
      - "preferred_concise": user skips long explanations → decrease detail_level
      - "preferred_thorough": user asks follow-ups → increase detail_level
      - "liked_humor": positive reaction to joke → increase humor_level
      - "disliked_humor": negative reaction → decrease humor_level
      - "wanted_challenge": user said "harder" → increase challenge_level
      - "wanted_support": user expressed frustration → decrease challenge_level, increase encouragement
      - "chose_visual": user chose diagram/chart → set prefers_visual
      - "chose_socratic": user engaged with questions → set prefers_socratic
    """
    profile = await get_personality(db, user_id)

    # Clamp helper
    clamp = lambda v: max(0.0, min(1.0, v))
    lr = 0.05  # learning rate — small nudge per signal

    log_entry = {"signal": signal, "value": value}

    if signal == "preferred_concise":
        profile.detail_level = clamp(profile.detail_level - lr)
    elif signal == "preferred_thorough":
        profile.detail_level = clamp(profile.detail_level + lr)
    elif signal == "liked_humor":
        profile.humor_level = clamp(profile.humor_level + lr)
    elif signal == "disliked_humor":
        profile.humor_level = clamp(profile.humor_level - lr)
    elif signal == "wanted_challenge":
        profile.challenge_level = clamp(profile.challenge_level + lr)
    elif signal == "wanted_support":
        profile.challenge_level = clamp(profile.challenge_level - lr)
        profile.encouragement_intensity = clamp(profile.encouragement_intensity + lr)
    elif signal == "chose_visual":
        profile.prefers_visual = True
    elif signal == "chose_socratic":
        profile.prefers_socratic = True
    elif signal == "formality_up":
        profile.formality = clamp(profile.formality + lr)
    elif signal == "formality_down":
        profile.formality = clamp(profile.formality - lr)
    else:
        logger.debug(f"Unknown personality signal: {signal}")

    # Append to adaptation log (keep last 100 entries)
    adaptation_log = list(profile.adaptation_log or [])
    adaptation_log.append(log_entry)
    profile.adaptation_log = adaptation_log[-100:]

    await db.commit()
    await db.refresh(profile)
    logger.info(f"🎭 Adapted personality for user {user_id}: {signal}")
    return profile


def build_system_prompt_modifiers(profile: PersonalityProfile) -> str:
    """
    Generate a system-prompt snippet that shapes the AI's tone
    based on the user's personality profile.
    """
    parts = []
    if profile.formality > 0.7:
        parts.append("Use a professional, respectful tone.")
    elif profile.formality < 0.3:
        parts.append("Be casual and friendly, like talking to a buddy.")

    if profile.humor_level > 0.6:
        parts.append("Include light humor, emojis, or playful metaphors when appropriate.")
    elif profile.humor_level < 0.2:
        parts.append("Stay focused and straightforward. Avoid jokes.")

    if profile.encouragement_intensity > 0.7:
        parts.append("Be very encouraging and celebrate small wins enthusiastically.")
    elif profile.encouragement_intensity < 0.3:
        parts.append("Keep encouragement understated and factual.")

    if profile.detail_level > 0.7:
        parts.append("Provide thorough, detailed explanations with multiple examples.")
    elif profile.detail_level < 0.3:
        parts.append("Keep explanations concise. Get to the point quickly.")

    if profile.challenge_level > 0.7:
        parts.append("Push the learner to think harder. Ask challenging follow-up questions.")
    elif profile.challenge_level < 0.3:
        parts.append("Be patient and supportive. Avoid overwhelming the learner.")

    if profile.prefers_visual:
        parts.append("The learner prefers visual aids — use diagrams, charts, or visual metaphors.")

    if profile.prefers_socratic:
        parts.append("Use the Socratic method — guide through questions rather than direct answers.")

    if profile.prefers_examples_first:
        parts.append("Show a concrete example before explaining the theory.")

    if profile.metaphor_domains:
        domains = ", ".join(profile.metaphor_domains[:3])
        parts.append(f"Use metaphors from: {domains}.")

    return " ".join(parts) if parts else ""
