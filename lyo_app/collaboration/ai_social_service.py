"""AI-orchestrated social learning (Wedge 2 — "social learning as core").

This layer rides ON TOP of the collaboration engine (CollaborativeLearningEngine)
and the personalization mastery model. Incumbent tutors treat social as a bolt-on;
Lyo makes the AI the orchestrator:

  1. AI peer matching   — pair learners with *complementary* mastery (one strong
                          in skill X, one weak in X) so peers actually teach each
                          other, rather than clustering by shared interest only.
  2. AI study pods      — auto-form a small pod from compatible learners and seed
                          a shared objective (the pod's common weak skill).
  3. AI group challenges— LLM-generated problem targeting the pod's shared weak
                          skill, delivered as a CollaborativeLearningSession.
  4. AI moderation      — summarize a group's PeerInteraction threads and surface
                          unanswered questions / quiet members.

Everything is DB-backed and degrades gracefully: the LLM path (challenges,
summaries) falls back to deterministic templates when no API key/Redis is
available, and mastery lookups that fail never 500 the caller.
"""
from __future__ import annotations

import logging
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from lyo_app.collaboration.models import (
    CollaborativeGroupMembership,
    CollaborativeLearningSession,
    CollaborativeStudyGroup,
    PeerInteraction,
)
from lyo_app.personalization.models import LearnerMastery

logger = logging.getLogger(__name__)


class AISocialOrchestrator:
    """AI orchestration on top of the collaboration engine."""

    # --------------------------------------------------------------- helpers
    async def _masteries_by_user(
        self, db: AsyncSession, user_ids: Optional[List[int]] = None
    ) -> Dict[int, Dict[str, float]]:
        """Return {user_id: {skill_id: mastery_level}} for the given users
        (or all learners with mastery rows when user_ids is None)."""
        stmt = select(LearnerMastery)
        if user_ids:
            stmt = stmt.where(LearnerMastery.user_id.in_(user_ids))
        rows = (await db.execute(stmt)).scalars().all()
        out: Dict[int, Dict[str, float]] = {}
        for r in rows:
            out.setdefault(r.user_id, {})[r.skill_id] = r.mastery_level or 0.0
        return out

    @staticmethod
    def _complementarity(
        me: Dict[str, float], other: Dict[str, float], *,
        strong: float = 0.7, weak: float = 0.4,
    ) -> Dict[str, Any]:
        """Score how well `other` complements `me`.

        High when the partner is strong where I'm weak (they can teach me) and/or
        I'm strong where they're weak (I can teach them). Shared skills give a
        small affinity bonus so pods still cohere around a subject.
        """
        they_teach_me: List[str] = []   # skills they can help me with
        i_teach_them: List[str] = []    # skills I can help them with
        shared = set(me) & set(other)
        for skill in shared:
            if me[skill] < weak and other[skill] >= strong:
                they_teach_me.append(skill)
            elif other[skill] < weak and me[skill] >= strong:
                i_teach_them.append(skill)
        affinity = len(shared) / max(len(set(me) | set(other)), 1)
        # Mutual teaching is the strongest signal; affinity is a tiebreaker.
        score = 0.45 * min(len(they_teach_me), 3) / 3 \
            + 0.45 * min(len(i_teach_them), 3) / 3 \
            + 0.10 * affinity
        return {
            "score": round(min(score, 1.0), 3),
            "they_can_teach_you": they_teach_me,
            "you_can_teach_them": i_teach_them,
            "shared_skills": sorted(shared),
        }

    # ------------------------------------------------------- 1. peer matching
    async def match_peers(
        self, db: AsyncSession, user_id: int, *, limit: int = 5,
    ) -> List[Dict[str, Any]]:
        """Find peers whose mastery complements this learner's.

        Returns ranked matches with the explicit "who teaches whom" reasoning so
        the UI (and the learner) can see *why* a pairing is good.
        """
        all_mastery = await self._masteries_by_user(db)
        me = all_mastery.get(user_id, {})
        if not me:
            return []  # no learner model yet -> nothing to match on
        matches: List[Dict[str, Any]] = []
        for other_id, other in all_mastery.items():
            if other_id == user_id or not other:
                continue
            comp = self._complementarity(me, other)
            if comp["score"] <= 0:
                continue
            matches.append({
                "user_id": other_id,
                "match_score": comp["score"],
                "they_can_teach_you": comp["they_can_teach_you"],
                "you_can_teach_them": comp["you_can_teach_them"],
                "shared_skills": comp["shared_skills"],
                "reason": self._match_reason(comp),
            })
        matches.sort(key=lambda m: m["match_score"], reverse=True)
        return matches[:limit]

    @staticmethod
    def _match_reason(comp: Dict[str, Any]) -> str:
        parts: List[str] = []
        if comp["they_can_teach_you"]:
            parts.append(f"can help you with {', '.join(comp['they_can_teach_you'][:2])}")
        if comp["you_can_teach_them"]:
            parts.append(f"you can mentor them in {', '.join(comp['you_can_teach_them'][:2])}")
        if not parts and comp["shared_skills"]:
            parts.append(f"shared focus on {', '.join(comp['shared_skills'][:2])}")
        return "; ".join(parts) or "compatible learning profile"

    # ---------------------------------------------------------- 2. study pods
    async def form_study_pod(
        self, db: AsyncSession, creator_id: int, *,
        subject: str = "General", max_size: int = 4,
    ) -> Dict[str, Any]:
        """Auto-form a small pod from the creator's best-matched peers and seed a
        shared objective (the skill the most pod members are weak in)."""
        matches = await self.match_peers(db, creator_id, limit=max_size - 1)
        member_ids = [creator_id] + [m["user_id"] for m in matches]

        # Shared objective = the skill the most members are weak in (<0.4).
        all_mastery = await self._masteries_by_user(db, member_ids)
        weak_counts: Dict[str, int] = {}
        for skills in all_mastery.values():
            for skill, lvl in skills.items():
                if lvl < 0.4:
                    weak_counts[skill] = weak_counts.get(skill, 0) + 1
        shared_weak_skill = max(weak_counts, key=weak_counts.get) if weak_counts else None
        objective = (
            f"Master {shared_weak_skill} together"
            if shared_weak_skill else f"Collaborative {subject} practice"
        )

        group = CollaborativeStudyGroup(
            title=f"{subject} Pod",
            description=f"AI-formed study pod • objective: {objective}",
            subject_area=subject,
            max_members=max_size,
            collaboration_type="study_group",
            target_skills=[shared_weak_skill] if shared_weak_skill else [],
            learning_objectives=[objective],
            created_by=creator_id,
        )
        db.add(group)
        await db.flush()
        for uid in member_ids:
            db.add(CollaborativeGroupMembership(
                group_id=group.id, user_id=uid,
                role=("facilitator" if uid == creator_id else "participant"),
            ))
        await db.commit()
        await db.refresh(group)
        return {
            "status": "formed",
            "group_id": group.id,
            "title": group.title,
            "objective": objective,
            "shared_weak_skill": shared_weak_skill,
            "member_ids": member_ids,
            "match_details": matches,
        }

    # ----------------------------------------------------- 3. group challenge
    async def generate_group_challenge(
        self, db: AsyncSession, group_id: int, facilitator_id: int,
    ) -> Dict[str, Any]:
        """Generate a challenge targeting the pod's shared weak skill and persist
        it as a CollaborativeLearningSession. LLM-backed with template fallback."""
        group = (await db.execute(
            select(CollaborativeStudyGroup).where(CollaborativeStudyGroup.id == group_id)
        )).scalar_one_or_none()
        if group is None:
            raise ValueError(f"group {group_id} not found")

        target_skills = group.target_skills or []
        skill = target_skills[0] if target_skills else (group.subject_area or "the topic")

        challenge_text, degraded = await self._llm_challenge(skill, group.subject_area)

        now = datetime.utcnow()
        session = CollaborativeLearningSession(
            group_id=group_id,
            title=f"Group Challenge: {skill}",
            description=challenge_text,
            session_type="challenge",
            target_skills=target_skills or [skill],
            learning_objectives=[f"Collaboratively solve a {skill} challenge"],
            facilitator_id=facilitator_id,
            scheduled_start=now,
            scheduled_end=now + timedelta(hours=1),
            status="scheduled",
        )
        db.add(session)
        await db.commit()
        await db.refresh(session)
        return {
            "status": "created",
            "session_id": session.id,
            "skill": skill,
            "challenge": challenge_text,
            "degraded": degraded,
        }

    async def _llm_challenge(self, skill: str, subject: Optional[str]) -> tuple[str, bool]:
        """Return (challenge_text, degraded). degraded=True when the template
        fallback was used (no LLM available)."""
        prompt = (
            f"Create a single collaborative learning challenge for a small study "
            f"pod working on '{skill}'"
            + (f" within {subject}" if subject else "")
            + ". It must require members to split work and combine answers. "
            "Give a short title, the problem, and how to divide it among 3-4 "
            "members. Keep it under 150 words."
        )
        try:
            from lyo_app.core.ai_resilience import ai_resilience_manager
            resp = await ai_resilience_manager.chat_completion(
                messages=[
                    {"role": "system", "content": "You design engaging group learning challenges."},
                    {"role": "user", "content": prompt},
                ],
                temperature=0.8, max_tokens=400,
            )
            content = (resp or {}).get("content") or (resp or {}).get("text")
            if content:
                return content.strip(), False
        except Exception as e:  # noqa: BLE001
            logger.warning(f"group-challenge LLM unavailable: {e}")
        # Deterministic fallback so the feature still works offline / keyless.
        return (
            f"Group Challenge — {skill}\n\n"
            f"As a pod, solve a multi-part {skill} problem: split into pairs, each "
            f"pair tackles one sub-part, then combine your solutions and explain "
            f"each step to the group. Goal: every member can re-derive the full "
            f"answer unaided by the end.",
            True,
        )

    # ---------------------------------------------------- 4. AI moderation
    async def summarize_group_discussion(
        self, db: AsyncSession, group_id: int, *, limit: int = 50,
    ) -> Dict[str, Any]:
        """Summarize a group's recent peer interactions: surface unanswered
        questions and quiet members. LLM summary with deterministic fallback."""
        rows = (await db.execute(
            select(PeerInteraction)
            .where(PeerInteraction.group_id == group_id)
            .order_by(PeerInteraction.created_at.desc())
            .limit(limit)
        )).scalars().all()

        total = len(rows)
        # Unanswered questions = top-level questions with no child + no resolved_at.
        parent_ids = {r.id for r in rows if r.parent_interaction_id is None}
        answered_parents = {r.parent_interaction_id for r in rows if r.parent_interaction_id}
        unanswered = [
            {"id": r.id, "content": (r.content or "")[:200]}
            for r in rows
            if r.parent_interaction_id is None
            and r.interaction_type in ("question", "help_request")
            and r.id not in answered_parents
            and r.resolved_at is None
        ]
        # Contribution counts per member (to surface quiet members).
        contrib: Dict[int, int] = {}
        for r in rows:
            contrib[r.initiator_id] = contrib.get(r.initiator_id, 0) + 1

        summary_text, degraded = await self._llm_summary(rows)
        return {
            "group_id": group_id,
            "interactions_analyzed": total,
            "summary": summary_text,
            "unanswered_questions": unanswered,
            "contributions_by_user": contrib,
            "degraded": degraded,
        }

    async def _llm_summary(self, rows: List[PeerInteraction]) -> tuple[str, bool]:
        if not rows:
            return "No discussion activity yet.", False
        transcript = "\n".join(
            f"- ({r.interaction_type}) {(r.content or '')[:160]}" for r in reversed(rows)
        )[:4000]
        try:
            from lyo_app.core.ai_resilience import ai_resilience_manager
            resp = await ai_resilience_manager.chat_completion(
                messages=[
                    {"role": "system", "content": "You moderate study-group discussions. Be concise."},
                    {"role": "user", "content": (
                        "Summarize this study-group discussion in 3-4 sentences, then "
                        "list any open questions that still need answering:\n\n" + transcript
                    )},
                ],
                temperature=0.4, max_tokens=300,
            )
            content = (resp or {}).get("content") or (resp or {}).get("text")
            if content:
                return content.strip(), False
        except Exception as e:  # noqa: BLE001
            logger.warning(f"discussion-summary LLM unavailable: {e}")
        return (
            f"{len(rows)} recent interaction(s). Review the open questions below "
            f"and make sure quieter members are drawn into the conversation.",
            True,
        )


ai_social_orchestrator = AISocialOrchestrator()
