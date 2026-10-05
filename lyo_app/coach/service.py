"""Deterministic Lyo Coach orchestration.

This is the control plane, not another tutor.  It reads the canonical evidence
ledger and concept graph, converts product-specific objects into LearningGoals,
and chooses the next useful pedagogical action.  No language model is required
for scheduling, readiness or routing.

A mission is deliberately receding-horizon: it is rebuilt from the latest
LearningEvent watermark whenever evidence or the goal changes.  The persisted
CoachSnapshot is only a cache for fast Chat/Home reads.
"""

from __future__ import annotations

import math
from datetime import date, datetime, time, timedelta, timezone
from typing import Any, Dict, Iterable, List, Optional, Sequence

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from lyo_app.ai.lesson_composer import slugify_skill
from lyo_app.ai_classroom.models import Concept
from lyo_app.ai_classroom.skill_identity import topic_scope
from lyo_app.events.concept_record import ConceptRecord, learner_record, next_rung_after
from lyo_app.events.evidence import evidence_rank, normalize_evidence_kind
from lyo_app.events.models import LearningEvent
from lyo_app.study_plans.models import TestProfile
from lyo_app.study_plans.topic_standing import topic_name, topic_weight

from .models import CoachSnapshot, GoalSkill, LearningGoal
from .schemas import (
    GoalCoachView,
    GoalSkillInput,
    GoalSkillRead,
    GoalSkillState,
    LearningGoalCreate,
    LearningGoalRead,
    MissionItem,
    ReadinessRead,
    TodayCoachView,
)

MAX_ACTIVE_GOALS = 20
MAX_MISSION_ITEMS = 5
DEFAULT_DAILY_MINUTES = 30
DEFAULT_REQUIRED_RUNG = "transfer"

# "retention" is the highest evidence rung, but a goal normally needs transfer
# to be considered ready.  Retention becomes the follow-up review target.
_TARGET_RUNG_FALLBACK = DEFAULT_REQUIRED_RUNG


class CoachEvidenceUnavailable(RuntimeError):
    """Canonical learner evidence could not be read; do not reinterpret as zero."""


def _now() -> datetime:
    return datetime.utcnow()


def _as_utc_naive(value: Optional[datetime]) -> Optional[datetime]:
    """Normalize an aware client timestamp before storing/comparing it.

    Coach persistence follows the codebase's existing naive-UTC convention.
    Dropping tzinfo without conversion would move the instant by the submitted
    UTC offset and corrupt deadline urgency.
    """
    if value is None or value.tzinfo is None:
        return value
    return value.astimezone(timezone.utc).replace(tzinfo=None)


def _daily_minutes(constraints: Optional[Dict[str, Any]]) -> int:
    """Read the reserved daily-minutes constraint without trusting public JSON."""

    raw = (constraints or {}).get("daily_minutes", DEFAULT_DAILY_MINUTES)
    try:
        value = int(raw)
    except (TypeError, ValueError):
        return DEFAULT_DAILY_MINUTES
    return max(10, min(90, value))


def _safe_rung(value: Optional[str]) -> str:
    normalized = normalize_evidence_kind(value)
    return normalized or _TARGET_RUNG_FALLBACK


def _as_deadline(test_date: date) -> datetime:
    # Existing Test Prep dates are date-only.  Treat the end of that local day
    # as the deadline rather than inventing an exam hour.
    return datetime.combine(test_date, time.max.replace(microsecond=0))


def _goal_deadline_days(goal: LearningGoal, now: datetime) -> Optional[int]:
    if goal.deadline is None:
        return None
    seconds = (goal.deadline - now).total_seconds()
    return math.floor(seconds / 86400)


def _urgency_multiplier(goal: LearningGoal, now: datetime) -> float:
    days = _goal_deadline_days(goal, now)
    if days is None:
        return 1.0
    if days <= 1:
        return 2.5
    if days <= 3:
        return 2.0
    if days <= 7:
        return 1.6
    if days <= 14:
        return 1.3
    return 1.1


def _readiness_level(index: float, critical_gaps: int) -> str:
    # These are presentation bands, not a grade forecast.  The API marks the
    # index uncalibrated until outcome data proves a numeric mapping.
    if index >= 0.82 and critical_gaps == 0:
        return "ready"
    if index >= 0.45:
        return "getting_there"
    return "not_ready"


def _record_strength(record: Optional[ConceptRecord]) -> int:
    if record is None:
        return -1
    return evidence_rank(record.best_rung)


def _parse_last_seen(value: Optional[str]) -> Optional[datetime]:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        # All coach persistence is currently naive UTC.  Compare like with like.
        return parsed.replace(tzinfo=None) if parsed.tzinfo else parsed
    except (TypeError, ValueError):
        return None


def _goal_read(goal: LearningGoal, skills: Sequence[GoalSkill]) -> LearningGoalRead:
    return LearningGoalRead(
        id=goal.id,
        goal_type=goal.goal_type,
        title=goal.title,
        subject=goal.subject,
        status=goal.status,
        deadline=goal.deadline,
        desired_outcome=dict(goal.desired_outcome or {}),
        constraints=dict(goal.constraints or {}),
        source_surface=goal.source_surface,
        source_ref_type=goal.source_ref_type,
        source_ref_id=goal.source_ref_id,
        created_at=goal.created_at,
        updated_at=goal.updated_at,
        skills=[GoalSkillRead.model_validate(skill) for skill in skills],
    )


async def _skills_for_goal(db: AsyncSession, user_id: int, goal_id: str) -> List[GoalSkill]:
    return list(
        (
            await db.execute(
                select(GoalSkill)
                .where(GoalSkill.user_id == user_id, GoalSkill.goal_id == goal_id)
                .order_by(GoalSkill.priority.desc(), GoalSkill.weight.desc(), GoalSkill.display_name)
            )
        ).scalars().all()
    )


async def create_goal(
    db: AsyncSession,
    user_id: int,
    body: LearningGoalCreate,
    *,
    source_surface: Optional[str] = None,
    source_ref_type: Optional[str] = None,
    source_ref_id: Optional[str] = None,
) -> LearningGoal:
    """Create a general LearningGoal without inventing a parallel learner model."""

    goal = LearningGoal(
        user_id=user_id,
        goal_type=body.goal_type,
        title=body.title.strip(),
        subject=(body.subject or "").strip() or None,
        deadline=_as_utc_naive(body.deadline),
        desired_outcome=dict(body.desired_outcome or {}),
        constraints=dict(body.constraints or {}),
        source_surface=source_surface,
        source_ref_type=source_ref_type,
        source_ref_id=source_ref_id,
    )
    db.add(goal)
    await db.flush()

    for item in body.skills:
        concept_id = (item.concept_id or slugify_skill(item.name)).strip()
        db.add(
            GoalSkill(
                goal_id=goal.id,
                user_id=user_id,
                concept_id=concept_id,
                display_name=item.name.strip(),
                weight=float(item.weight),
                required_rung=_safe_rung(item.required_rung),
                priority=item.priority,
            )
        )
    await db.flush()
    return goal


async def ensure_test_goal(
    db: AsyncSession,
    profile: TestProfile,
) -> LearningGoal:
    """Adapt one TestProfile into the general LearningGoal contract.

    The adapter is idempotent and synchronises edits.  Existing evidence is
    never moved or deleted; only the set of concepts this goal currently cares
    about changes.
    """

    goal = (
        await db.execute(
            select(LearningGoal).where(
                LearningGoal.user_id == profile.user_id,
                LearningGoal.source_ref_type == "test_profile",
                LearningGoal.source_ref_id == profile.id,
            )
        )
    ).scalar_one_or_none()

    today = _now().date()
    status = "active" if profile.test_date >= today else "completed"
    workflow = dict(profile.workflow_state or {})
    constraints = {
        "daily_minutes": int(profile.daily_minutes_available or DEFAULT_DAILY_MINUTES),
        "study_days_per_week": int(profile.study_days_per_week or 5),
        "test_format": profile.test_format,
        "stress_level": int(profile.stress_level or 5),
        "timezone": workflow.get("timezone", "UTC"),
    }
    desired = {"test_date": profile.test_date.isoformat(), "test_format": profile.test_format}

    if goal is None:
        goal = LearningGoal(
            user_id=profile.user_id,
            goal_type="test",
            title=f"{profile.subject} test",
            subject=profile.subject,
            status=status,
            deadline=_as_deadline(profile.test_date),
            desired_outcome=desired,
            constraints=constraints,
            source_surface="test_prep",
            source_ref_type="test_profile",
            source_ref_id=profile.id,
            metadata_json={"test_profile_id": profile.id},
        )
        db.add(goal)
        await db.flush()
    else:
        goal.title = f"{profile.subject} test"
        goal.subject = profile.subject
        goal.status = status
        goal.deadline = _as_deadline(profile.test_date)
        goal.desired_outcome = desired
        goal.constraints = constraints
        goal.updated_at = _now()

    existing = {
        row.concept_id: row
        for row in await _skills_for_goal(db, profile.user_id, goal.id)
    }
    keep: set[str] = set()

    for entry in profile.topics or []:
        name = topic_name(entry)
        if not name:
            continue
        concept_id = slugify_skill(name)
        keep.add(concept_id)
        skill = existing.get(concept_id)
        weight = float(topic_weight(entry))
        if skill is None:
            skill = GoalSkill(
                goal_id=goal.id,
                user_id=profile.user_id,
                concept_id=concept_id,
                display_name=name,
                weight=weight,
                required_rung=DEFAULT_REQUIRED_RUNG,
                priority=5,
                metadata_json={"source": "test_profile"},
            )
            db.add(skill)
            # A second profile topic may canonicalize to the same slug. Make
            # the pending row visible to this loop before flush so it updates
            # the same requirement instead of violating uq_goal_skill_concept.
            existing[concept_id] = skill
        else:
            skill.display_name = name
            skill.weight = weight
            skill.required_rung = DEFAULT_REQUIRED_RUNG
            skill.updated_at = _now()

    # A profile edit can remove a topic.  Removing it from the goal does not
    # remove the learner's evidence for that concept.
    for concept_id, skill in existing.items():
        if concept_id not in keep:
            await db.delete(skill)

    await db.flush()
    return goal


async def sync_test_goals(db: AsyncSession, user_id: int) -> None:
    """Lazily backfill/synchronise existing Test Prep profiles for one learner."""

    profiles = list(
        (
            await db.execute(
                select(TestProfile)
                .where(TestProfile.user_id == user_id, TestProfile.intake_complete.is_(True))
                .order_by(TestProfile.test_date.desc())
                .limit(MAX_ACTIVE_GOALS)
            )
        ).scalars().all()
    )
    for profile in profiles:
        await ensure_test_goal(db, profile)


async def active_goals(db: AsyncSession, user_id: int) -> List[LearningGoal]:
    await sync_test_goals(db, user_id)
    goals = list(
        (
            await db.execute(
                select(LearningGoal)
                .where(LearningGoal.user_id == user_id, LearningGoal.status == "active")
                # Urgent dated goals must enter the capped set before undated
                # or later goals. Sorting after LIMIT can silently omit the
                # learner's exam tomorrow when many goals exist.
                .order_by(
                    LearningGoal.deadline.is_(None),
                    LearningGoal.deadline.asc(),
                    LearningGoal.created_at.asc(),
                )
                .limit(MAX_ACTIVE_GOALS)
            )
        ).scalars().all()
    )
    return goals


def _weakest_covered_record(
    exact: Optional[ConceptRecord],
    persistent_ids: Sequence[str],
    by_id: Dict[str, ConceptRecord],
) -> Optional[ConceptRecord]:
    """Return the weakest record only when every concrete scoped unit is covered."""

    candidates: List[ConceptRecord] = [exact] if exact is not None else []
    if persistent_ids:
        scoped = [by_id.get(concept_id) for concept_id in persistent_ids]
        if any(item is None for item in scoped):
            return None
        candidates.extend(item for item in scoped if item is not None)
    return min(candidates, key=_record_strength) if candidates else None


async def _record_map_for_goal(
    db: AsyncSession,
    user_id: int,
    skills: Sequence[GoalSkill],
) -> Dict[str, Optional[ConceptRecord]]:
    """Map each goal skill to the most conservative evidence record available.

    A Test Prep topic can be coarser than persistent Classroom skills.  The
    classroom stores those under a deterministic topic scope, so for a goal
    topic we consider the exact slug plus all taught skills in that exact
    scope, then choose the weakest demonstrated unit.  One strong subskill must
    never speak for an entire exam topic.
    """

    record = await learner_record(db, user_id, limit=100)
    if record.unavailable:
        # A failed evidence query is not evidence that the learner knows
        # nothing. Let the API fail explicitly so clients preserve the last
        # valid mission instead of rendering a fabricated "not ready".
        raise CoachEvidenceUnavailable("canonical learner evidence is unavailable")

    by_id = {item.concept_id: item for item in record.concepts}
    scopes = {topic_scope(skill.display_name): skill.concept_id for skill in skills}
    scopes = {scope: concept_id for scope, concept_id in scopes.items() if scope}

    scoped_ids: Dict[str, List[str]] = {}
    if scopes:
        rows = (
            await db.execute(
                select(Concept.subject, Concept.id).where(Concept.subject.in_(list(scopes)))
            )
        ).all()
        for scope, concept_id in rows:
            scoped_ids.setdefault(scope, []).append(concept_id)

    result: Dict[str, Optional[ConceptRecord]] = {}
    for skill in skills:
        exact = by_id.get(skill.concept_id)
        scope = topic_scope(skill.display_name)
        persistent_ids = scoped_ids.get(scope, [])

        # Once the Classroom has defined concrete units under this topic, the
        # goal is only as strong as its weakest unit. An absent record is an
        # unassessed unit, not something to skip; otherwise one transferred
        # subskill could make a multi-unit exam topic look complete.
        result[skill.concept_id] = _weakest_covered_record(
            exact,
            persistent_ids,
            by_id,
        )
    return result


def _action_for_skill(
    skill: GoalSkill,
    record: Optional[ConceptRecord],
    *,
    overdue_review: bool,
) -> tuple[str, Optional[str], str, int, str]:
    """Return action, target evidence, surface, minutes, reason."""

    strongest = record.best_rung if record else None
    rank = evidence_rank(strongest)

    if record and record.misconception:
        return (
            "remediate",
            "application",
            "classroom",
            10,
            "A recent misconception needs a targeted repair before harder practice.",
        )
    if rank < evidence_rank("recognition"):
        return (
            "diagnose",
            "recognition",
            "quiz",
            5,
            "There is not enough evidence yet to choose the right teaching depth.",
        )
    if rank == evidence_rank("recognition"):
        return (
            "guide",
            "application",
            "classroom",
            9,
            "Recognition is present; the next step is using the idea with guidance.",
        )
    if rank == evidence_rank("explanation"):
        return (
            "check_application",
            "application",
            "quiz",
            6,
            "The learner can explain it; now verify they can apply it.",
        )
    if rank == evidence_rank("application"):
        return (
            "check_transfer",
            "transfer",
            "quiz",
            7,
            "Application is demonstrated; a novel problem should test transfer.",
        )
    if rank == evidence_rank("transfer"):
        return (
            "review",
            "retention",
            "review",
            5,
            "Transfer is demonstrated; retrieval after time checks durability.",
        )
    if overdue_review:
        return (
            "review",
            "retention",
            "review",
            5,
            "This strong skill is due for a short retrieval check.",
        )
    return (
        "advance",
        None,
        "review",
        3,
        "The required evidence is already strong; keep it in light review.",
    )


def _state_for_skill(
    goal: LearningGoal,
    skill: GoalSkill,
    record: Optional[ConceptRecord],
    *,
    average_weight: float,
    now: datetime,
) -> GoalSkillState:
    target = _safe_rung(skill.required_rung)
    target_rank = max(1, evidence_rank(target))
    current_rank = evidence_rank(record.best_rung if record else None)

    progress = 0.0 if current_rank < 0 else min(1.0, (min(current_rank, target_rank) + 1) / (target_rank + 1))
    gap = 1.0 - progress

    last_seen = _parse_last_seen(record.last_seen if record else None)
    overdue_review = bool(
        last_seen
        and current_rank >= evidence_rank("transfer")
        and now - last_seen >= timedelta(days=3)
    )

    relative_weight = max(0.2, float(skill.weight or 1.0) / max(average_weight, 0.01))
    priority_factor = 0.75 + (max(1, min(10, int(skill.priority or 5))) / 10.0)
    score = gap * relative_weight * priority_factor * _urgency_multiplier(goal, now)
    if record and record.misconception:
        score += 0.75
    if overdue_review:
        score += 0.35

    return GoalSkillState(
        skill_id=skill.id,
        concept_id=skill.concept_id,
        display_name=skill.display_name,
        weight=float(skill.weight or 1.0),
        required_rung=target,
        evidence_state=record.state if record else "NOT_SEEN",
        strongest_rung=record.best_rung if record else None,
        next_rung=record.next_rung if record else next_rung_after(None),
        misconception=record.misconception if record else None,
        last_seen=record.last_seen if record else None,
        evidence_progress=round(progress, 4),
        priority_score=round(max(0.0, score), 4),
        overdue_review=overdue_review,
    )


def _readiness(states: Sequence[GoalSkillState]) -> ReadinessRead:
    total_weight = sum(max(0.0, state.weight) for state in states)
    if not states or total_weight <= 0:
        return ReadinessRead(
            readiness_index=0.0,
            readiness_level="not_ready",
            calibrated=False,
            assessed_skills=0,
            total_skills=len(states),
            critical_gaps=len(states),
        )

    index = sum(state.weight * state.evidence_progress for state in states) / total_weight
    assessed = sum(1 for state in states if state.strongest_rung is not None)
    critical = sum(
        1
        for state in states
        if evidence_rank(state.strongest_rung) < evidence_rank("application")
    )
    return ReadinessRead(
        readiness_index=round(max(0.0, min(1.0, index)), 4),
        readiness_level=_readiness_level(index, critical),
        calibrated=False,
        assessed_skills=assessed,
        total_skills=len(states),
        critical_gaps=critical,
    )


def _mission_for_states(
    goal: LearningGoal,
    states: Sequence[GoalSkillState],
    skills_by_id: Dict[str, GoalSkill],
    *,
    minute_cap: int,
) -> List[MissionItem]:
    chosen: List[MissionItem] = []
    used = 0

    for state in sorted(states, key=lambda item: item.priority_score, reverse=True):
        skill = skills_by_id[state.skill_id]
        # A fully ready skill is not today's work unless retention is due.
        if state.evidence_progress >= 1.0 and not state.overdue_review:
            continue

        action, evidence, surface, minutes, reason = _action_for_skill(
            skill,
            # only the fields action selection needs
            type("_Record", (), {
                "best_rung": state.strongest_rung,
                "misconception": state.misconception,
            })() if state.strongest_rung or state.misconception else None,
            overdue_review=state.overdue_review,
        )
        if chosen and used + minutes > minute_cap:
            continue

        chosen.append(
            MissionItem(
                goal_id=goal.id,
                goal_title=goal.title,
                skill_id=skill.id,
                concept_id=skill.concept_id,
                title=skill.display_name,
                action=action,
                target_evidence_type=evidence,
                recommended_surface=surface,
                estimated_minutes=minutes,
                priority_score=state.priority_score,
                reason=reason,
            )
        )
        used += minutes
        if len(chosen) >= MAX_MISSION_ITEMS or used >= minute_cap:
            break

    return chosen


def _coach_note(goal: LearningGoal, readiness: ReadinessRead, mission: Sequence[MissionItem]) -> str:
    if not mission:
        if readiness.readiness_level == "ready":
            return f"{goal.title}: required evidence is strong. Keep review light and protect retention."
        return f"{goal.title}: add or assess the missing skills so Lyo can choose the next best move."
    lead = mission[0].title
    if readiness.readiness_level == "ready":
        return f"{goal.title}: readiness is strong. Today's highest-value check is {lead}."
    if readiness.readiness_level == "getting_there":
        return f"{goal.title}: you're progressing. The best next use of time is {lead}."
    return f"{goal.title}: start with {lead}; it is the highest-priority gap for this goal."


async def latest_event_id(db: AsyncSession, user_id: int) -> Optional[int]:
    return (
        await db.execute(
            select(func.max(LearningEvent.id)).where(LearningEvent.user_id == user_id)
        )
    ).scalar_one_or_none()


async def build_goal_view(
    db: AsyncSession,
    user_id: int,
    goal: LearningGoal,
    *,
    use_cache: bool = True,
) -> GoalCoachView:
    skills = await _skills_for_goal(db, user_id, goal.id)
    watermark = await latest_event_id(db, user_id)

    cached = (
        await db.execute(
            select(CoachSnapshot).where(
                CoachSnapshot.user_id == user_id,
                CoachSnapshot.goal_id == goal.id,
            )
        )
    ).scalar_one_or_none()

    if (
        use_cache
        and cached is not None
        and cached.source_event_id == watermark
        and cached.goal_updated_at == goal.updated_at
    ):
        try:
            return GoalCoachView.model_validate(cached.payload)
        except Exception:
            # Cache corruption/stale schema is disposable by design.
            pass

    records = await _record_map_for_goal(db, user_id, skills)
    average_weight = (
        sum(float(skill.weight or 1.0) for skill in skills) / len(skills)
        if skills
        else 1.0
    )
    now = _now()
    states = [
        _state_for_skill(
            goal,
            skill,
            records.get(skill.concept_id),
            average_weight=average_weight,
            now=now,
        )
        for skill in skills
    ]
    readiness = _readiness(states)
    minute_cap = _daily_minutes(goal.constraints)
    mission = _mission_for_states(
        goal,
        states,
        {skill.id: skill for skill in skills},
        minute_cap=minute_cap,
    )

    view = GoalCoachView(
        goal=_goal_read(goal, skills),
        readiness=readiness,
        skills=states,
        mission=mission,
        total_minutes=sum(item.estimated_minutes for item in mission),
        coach_note=_coach_note(goal, readiness, mission),
        source_event_id=watermark,
        generated_at=now,
    )

    payload = view.model_dump(mode="json")
    if cached is None:
        cached = CoachSnapshot(
            user_id=user_id,
            goal_id=goal.id,
            source_event_id=watermark,
            goal_updated_at=goal.updated_at,
            payload=payload,
            generated_at=now,
        )
        db.add(cached)
    else:
        cached.source_event_id = watermark
        cached.goal_updated_at = goal.updated_at
        cached.payload = payload
        cached.generated_at = now
    await db.flush()
    return view


async def build_today_view(db: AsyncSession, user_id: int) -> TodayCoachView:
    goals = await active_goals(db, user_id)
    if not goals:
        return TodayCoachView(
            coach_note="No active learning goal yet. Start with a test, course, assignment, or skill you want to master.",
            generated_at=_now(),
        )

    views = [await build_goal_view(db, user_id, goal) for goal in goals]
    primary = views[0]
    # Cross-goal ordering prevents a long-running course from hiding an exam
    # tomorrow, while preserving each goal's own evidence-based priority.
    candidates = [item for view in views for item in view.mission]
    deadline_by_goal = {goal.id: goal.deadline for goal in goals}

    def cross_goal_score(item: MissionItem) -> float:
        deadline = deadline_by_goal.get(item.goal_id)
        if deadline is None:
            deadline_boost = 1.0
        else:
            days = max(0, math.floor((deadline - _now()).total_seconds() / 86400))
            deadline_boost = 1.8 if days <= 1 else 1.4 if days <= 3 else 1.15 if days <= 7 else 1.0
        return item.priority_score * deadline_boost

    candidates.sort(key=cross_goal_score, reverse=True)
    mission: List[MissionItem] = []
    minutes = 0
    cap = max(15, _daily_minutes(primary.goal.constraints))
    for item in candidates:
        if mission and minutes + item.estimated_minutes > cap:
            continue
        mission.append(item)
        minutes += item.estimated_minutes
        if len(mission) >= MAX_MISSION_ITEMS or minutes >= cap:
            break

    if mission:
        note = (
            f"Today's mission starts with {mission[0].title}. "
            f"It is the highest-value next step across your active goals."
        )
    else:
        note = "Your active goals are currently caught up. Use a light review or set the next goal."

    return TodayCoachView(
        primary_goal_id=primary.goal.id,
        active_goals=[view.goal for view in views],
        readiness={view.goal.id: view.readiness for view in views},
        mission=mission,
        total_minutes=minutes,
        coach_note=note,
        generated_at=_now(),
    )


async def owned_goal(
    db: AsyncSession,
    user_id: int,
    goal_id: str,
) -> Optional[LearningGoal]:
    return (
        await db.execute(
            select(LearningGoal).where(
                LearningGoal.id == goal_id,
                LearningGoal.user_id == user_id,
            )
        )
    ).scalar_one_or_none()
