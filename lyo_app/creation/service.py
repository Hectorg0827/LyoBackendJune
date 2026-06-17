"""Teaching-through-creation service (#4 — "build-with-me").

Flow:
  1. start_project — the learner names what they want to build; the tutor
     decomposes it into 3-6 steps, scaffolded at the learner's mastery level
     (more guidance when weak, more autonomy when strong).
  2. get_project — the current step + what to do.
  3. submit_artifact — the learner submits their work for the current step; the
     tutor reviews it (accept & advance, or give revision feedback). Completing
     the last step completes the project.

LLM calls (planning + review) ride ai_resilience_manager and degrade to
deterministic templates so the mode works keyless/offline.
"""
import json
import logging
from datetime import datetime
from typing import Any, Dict, List, Optional

from sqlalchemy import select, desc
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm.attributes import flag_modified

from lyo_app.creation.models import (
    CreationProject, CreationArtifact, ProjectStatus, ScaffoldLevel,
)

logger = logging.getLogger(__name__)

# mastery band (from personalization.suggest_content_difficulty) -> scaffold
_BAND_TO_SCAFFOLD = {
    "easy": ScaffoldLevel.HIGH,    # weak learner -> hold their hand
    "medium": ScaffoldLevel.MEDIUM,
    "hard": ScaffoldLevel.LOW,     # strong learner -> push for autonomy
}

_SCAFFOLD_GUIDANCE = {
    ScaffoldLevel.HIGH: ("Give detailed, concrete guidance and break each step "
                         "into small sub-steps with an example."),
    ScaffoldLevel.MEDIUM: ("Give hints and checkpoints, but let the learner do "
                           "the thinking."),
    ScaffoldLevel.LOW: ("Keep guidance minimal; pose stretch questions and let "
                        "the learner drive."),
}


class CreationService:
    # ------------------------------------------------------------ start
    async def start_project(
        self, db: AsyncSession, *, user_id: int, goal: str,
        title: Optional[str] = None, skill_id: Optional[str] = None,
    ) -> CreationProject:
        scaffold = await self._scaffold_for(db, user_id, skill_id)
        steps, degraded = await self._plan_steps(goal, scaffold)
        # First step becomes active.
        if steps:
            steps[0]["status"] = "active"

        project = CreationProject(
            user_id=user_id,
            title=(title or goal)[:300],
            goal=goal,
            skill_id=skill_id,
            scaffold_level=scaffold,
            steps=steps,
            current_step=0,
            status=ProjectStatus.ACTIVE,
            degraded=degraded,
        )
        db.add(project)
        await db.commit()
        await db.refresh(project)
        return project

    async def get_project(self, db: AsyncSession, project_id: int, user_id: int
                          ) -> Optional[CreationProject]:
        project = (await db.execute(
            select(CreationProject).where(CreationProject.id == project_id)
        )).scalar_one_or_none()
        if project is None or project.user_id != user_id:
            return None
        return project

    async def list_projects(self, db: AsyncSession, user_id: int
                            ) -> List[CreationProject]:
        rows = (await db.execute(
            select(CreationProject)
            .where(CreationProject.user_id == user_id)
            .order_by(desc(CreationProject.created_at))
        )).scalars().all()
        return list(rows)

    # ------------------------------------------------------ submit & review
    async def submit_artifact(
        self, db: AsyncSession, *, project_id: int, user_id: int, content: str,
    ) -> Dict[str, Any]:
        project = await self.get_project(db, project_id, user_id)
        if project is None:
            raise ValueError("project not found")
        if project.status != ProjectStatus.ACTIVE:
            raise ValueError("project is not active")

        steps = list(project.steps or [])
        idx = project.current_step
        step = steps[idx] if 0 <= idx < len(steps) else {"title": "your work",
                                                          "description": ""}

        feedback, accepted, degraded = await self._review_artifact(
            project.goal, step, content, project.scaffold_level)

        artifact = CreationArtifact(
            project_id=project.id, step_index=idx, content=content,
            feedback=feedback, accepted=accepted, degraded=degraded)
        db.add(artifact)

        advanced = False
        completed = False
        if accepted:
            if 0 <= idx < len(steps):
                steps[idx]["status"] = "done"
            next_idx = idx + 1
            if next_idx < len(steps):
                steps[next_idx]["status"] = "active"
                project.current_step = next_idx
                advanced = True
            else:
                project.status = ProjectStatus.COMPLETED
                project.completed_at = datetime.utcnow()
                completed = True
            # Reassign AND flag: plain JSON columns don't track in-place mutation,
            # and even reassignment can be missed, so be explicit.
            project.steps = steps
            flag_modified(project, "steps")

        await db.commit()
        await db.refresh(project)
        return {
            "accepted": accepted,
            "advanced": advanced,
            "completed": completed,
            "feedback": feedback,
            "degraded": degraded,
            "current_step": project.current_step,
            "status": project.status.value,
        }

    # ------------------------------------------------------ pod tie-in
    async def to_pod_challenge(
        self, db: AsyncSession, *, project_id: int, user_id: int,
    ) -> Dict[str, Any]:
        """Turn a creation project into a collaborative pod challenge so a group
        can build it together (composes #4 with the social engine)."""
        project = await self.get_project(db, project_id, user_id)
        if project is None:
            raise ValueError("project not found")
        from lyo_app.collaboration.ai_social_service import ai_social_orchestrator
        pod = await ai_social_orchestrator.form_study_pod(
            db, user_id, subject=(project.skill_id or "Creation"), max_size=4)
        gid = pod.get("group_id")
        challenge = None
        if gid:
            challenge = await ai_social_orchestrator.generate_group_challenge(
                db, gid, user_id)
        return {"project_id": project.id, "pod": pod, "challenge": challenge}

    # ----------------------------------------------------------- helpers
    async def _scaffold_for(
        self, db: AsyncSession, user_id: int, skill_id: Optional[str],
    ) -> ScaffoldLevel:
        try:
            from lyo_app.personalization.service import personalization_engine
            band = await personalization_engine.suggest_content_difficulty(
                db, str(user_id), skill_id=skill_id)
            return _BAND_TO_SCAFFOLD.get(band, ScaffoldLevel.MEDIUM)
        except Exception as e:  # noqa: BLE001
            logger.warning(f"scaffold lookup failed for {user_id}: {e}")
            return ScaffoldLevel.MEDIUM

    async def _plan_steps(
        self, goal: str, scaffold: ScaffoldLevel,
    ) -> tuple[List[Dict[str, Any]], bool]:
        """Decompose the build into ordered steps. Returns (steps, degraded)."""
        prompt = (
            f"A learner wants to BUILD/CREATE this: '{goal}'.\n"
            f"{_SCAFFOLD_GUIDANCE[scaffold]}\n"
            "Break it into 3-6 ordered steps where the learner makes something at "
            "each step (not just reads). Respond as strict JSON: "
            '{"steps": [{"title": "...", "description": "..."}, ...]}. '
            "Each description says what the learner should produce and submit."
        )
        try:
            from lyo_app.core.ai_resilience import ai_resilience_manager
            resp = await ai_resilience_manager.chat_completion(
                messages=[
                    {"role": "system", "content": "You design hands-on, build-first learning projects."},
                    {"role": "user", "content": prompt},
                ],
                temperature=0.6, max_tokens=700,
                response_format={"type": "json_object"},
            )
            if resp and not resp.get("is_fallback"):
                text = resp.get("content") or resp.get("text") or ""
                start, end = text.find("{"), text.rfind("}") + 1
                data = json.loads(text[start:end])
                raw = data.get("steps") or []
                steps = [
                    {"index": i, "title": str(s.get("title", f"Step {i+1}"))[:200],
                     "description": str(s.get("description", ""))[:1000],
                     "status": "pending"}
                    for i, s in enumerate(raw) if isinstance(s, dict)
                ][:6]
                if steps:
                    return steps, False
        except Exception as e:  # noqa: BLE001
            logger.warning(f"creation step planning LLM unavailable: {e}")

        # Deterministic constructionist fallback (plan -> build -> test -> explain).
        templates = [
            ("Plan it", f"Sketch what you'll build for '{goal}' and list its parts. Submit your plan."),
            ("Build the core", "Create the main piece. Submit what you made."),
            ("Make it work end-to-end", "Connect the parts into a working whole. Submit the result."),
            ("Teach it back", "Explain how your creation works as if teaching a peer. Submit your explanation."),
        ]
        steps = [{"index": i, "title": t, "description": d, "status": "pending"}
                 for i, (t, d) in enumerate(templates)]
        return steps, True

    async def _review_artifact(
        self, goal: str, step: Dict[str, Any], content: str,
        scaffold: ScaffoldLevel,
    ) -> tuple[str, bool, bool]:
        """Review a submitted artifact. Returns (feedback, accepted, degraded)."""
        prompt = (
            f"Project goal: '{goal}'.\n"
            f"Current step: {step.get('title')} — {step.get('description')}\n"
            f"The learner submitted:\n\"\"\"\n{content[:2000]}\n\"\"\"\n\n"
            f"{_SCAFFOLD_GUIDANCE[scaffold]}\n"
            "Review their work for this step. Be encouraging and specific. Decide "
            "if it's good enough to move on. Respond as strict JSON: "
            '{"accepted": true|false, "feedback": "..."}.'
        )
        try:
            from lyo_app.core.ai_resilience import ai_resilience_manager
            resp = await ai_resilience_manager.chat_completion(
                messages=[
                    {"role": "system", "content": "You are a warm, rigorous project mentor."},
                    {"role": "user", "content": prompt},
                ],
                temperature=0.4, max_tokens=400,
                response_format={"type": "json_object"},
            )
            if resp and not resp.get("is_fallback"):
                text = resp.get("content") or resp.get("text") or ""
                start, end = text.find("{"), text.rfind("}") + 1
                data = json.loads(text[start:end])
                fb = data.get("feedback")
                if fb:
                    return fb.strip(), bool(data.get("accepted", True)), False
        except Exception as e:  # noqa: BLE001
            logger.warning(f"creation review LLM unavailable: {e}")

        # Fallback: accept substantive submissions, nudge thin ones — keeps the
        # build moving without an LLM while still asking for real effort.
        if len((content or "").strip()) < 15:
            return ("That looks a bit thin — add more detail or show your actual "
                    "work, then resubmit.", False, True)
        return ("Nice work on this step — you produced something concrete. "
                "Moving you on to the next one.", True, True)


creation_service = CreationService()
