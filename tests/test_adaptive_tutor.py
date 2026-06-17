"""
Adaptive-tutor wiring tests (7-pillar parity + leapfrog wedges).

These assert the *wiring/structure* of the adaptive tutor — that the learner
model reaches the tutoring path, difficulty adapts to mastery, etc. They do not
assert LLM output quality (that needs live API keys; validated on staging).

Each test boots the real app on the shared temp-file DB from conftest.py.
"""

import os

os.environ.setdefault("ENVIRONMENT", "development")
os.environ.setdefault("SECRET_KEY", "test-secret-key-at-least-32-characters-long-xx")

import asyncio
import pytest
from starlette.testclient import TestClient


@pytest.fixture(scope="module")
def client():
    import lyo_app.enhanced_main as m
    from lyo_app.core.database import init_db
    asyncio.get_event_loop().run_until_complete(init_db())
    return TestClient(m.app, raise_server_exceptions=False)


def _auth(client, email, username, ip):
    client.post("/auth/register", json={
        "email": email, "username": username, "password": "SweepPass123!",
        "confirm_password": "SweepPass123!", "first_name": username})
    body = client.post("/auth/login", json={
        "email": email, "password": "SweepPass123!"}).json()
    return {"Authorization": f"Bearer {body['access_token']}", "X-Forwarded-For": ip}, body["user"]["id"]


async def _make_superuser(uid):
    """Promote a user to superuser (satisfies the instructor gate)."""
    from sqlalchemy import update
    from lyo_app.core.database import AsyncSessionLocal
    from lyo_app.auth.models import User
    async with AsyncSessionLocal() as db:
        await db.execute(update(User).where(User.id == uid).values(is_superuser=True))
        await db.commit()


async def _make_graph_course(course_id, *, published=False):
    """Create a GraphCourse row to act as an AI-drafted course under review."""
    from lyo_app.core.database import AsyncSessionLocal
    from lyo_app.ai_classroom.models import GraphCourse
    async with AsyncSessionLocal() as db:
        db.add(GraphCourse(id=course_id, title="Intro to Fractions",
                           subject="math", is_published=published))
        await db.commit()


async def _course_published(course_id):
    from lyo_app.core.database import AsyncSessionLocal
    from lyo_app.ai_classroom.models import GraphCourse
    from sqlalchemy import select
    async with AsyncSessionLocal() as db:
        c = (await db.execute(
            select(GraphCourse).where(GraphCourse.id == course_id))).scalar_one()
        return c.is_published


async def _seed_learner(uid, *, affect="frustrated", masteries=None):
    """Seed a LearnerState + LearnerMastery rows for a user."""
    from lyo_app.core.database import AsyncSessionLocal
    from lyo_app.personalization.models import LearnerState, LearnerMastery, AffectState
    async with AsyncSessionLocal() as db:
        db.add(LearnerState(
            user_id=uid, current_affect=AffectState(affect),
            fatigue_level=0.4, focus_level=0.6, reading_level=9,
            preferred_pace="moderate",
        ))
        for skill_id, level in (masteries or {}).items():
            db.add(LearnerMastery(user_id=uid, skill_id=skill_id, mastery_level=level))
        await db.commit()


# ---------------------------------------------------------------- Pillar A
def test_build_prompt_context_returns_learner_profile_without_greenlet(client):
    """The keystone: the learner model assembles into a prompt block safely."""
    _, uid = _auth(client, "at_a@x.com", "at_alice", "10.70.0.1")
    asyncio.get_event_loop().run_until_complete(_seed_learner(
        uid, affect="frustrated",
        masteries={"linear_equations": 0.85, "quadratics": 0.2, "fractions": 0.5},
    ))

    async def _build():
        from lyo_app.core.database import AsyncSessionLocal
        from lyo_app.personalization.service import personalization_engine
        async with AsyncSessionLocal() as db:
            return await personalization_engine.build_prompt_context(
                db, str(uid), current_skill="quadratics")

    ctx = asyncio.get_event_loop().run_until_complete(_build())
    assert ctx, "expected a non-empty learner context"
    assert "quadratics" in ctx                 # struggling skill surfaced
    assert "linear_equations" in ctx           # mastered skill surfaced
    assert "frustrated" in ctx                 # affect surfaced
    assert "mastery" in ctx.lower()            # readiness line present


def test_greeting_injects_learner_context(client):
    """GET /chat/greeting reports context_used=True once the learner has state."""
    headers, uid = _auth(client, "at_g@x.com", "at_greet", "10.70.0.2")
    asyncio.get_event_loop().run_until_complete(_seed_learner(
        uid, masteries={"quadratics": 0.2}))
    r = client.get("/api/v1/chat/greeting", headers=headers)
    assert r.status_code == 200, r.text
    assert r.json().get("context_used") is True


# ---------------------------------------------------------------- Pillar C / Wedge 3 (emotional)
def test_coaching_directive_varies_by_affect():
    """The emotional layer maps affect -> an explicit tutoring instruction."""
    from lyo_app.personalization.service import personalization_engine as pe
    frustrated = pe.coaching_directive("frustrated", fatigue=0.2)
    bored = pe.coaching_directive("bored", fatigue=0.2)
    flow = pe.coaching_directive("flow", fatigue=0.2)
    assert "encourag" in frustrated.lower() and "worked example" in frustrated.lower()
    assert "concise" in bored.lower()
    assert "momentum" in flow.lower()
    assert frustrated != bored != flow
    # fatigue rider appends a break suggestion
    tired = pe.coaching_directive("engaged", fatigue=0.85)
    assert "break" in tired.lower()


def test_coaching_directive_injected_into_prompt_context(client):
    """A frustrated learner's context must carry the coaching directive."""
    _, uid = _auth(client, "at_e@x.com", "at_emo", "10.70.0.4")
    asyncio.get_event_loop().run_until_complete(_seed_learner(
        uid, affect="frustrated", masteries={"quadratics": 0.2}))

    async def _build():
        from lyo_app.core.database import AsyncSessionLocal
        from lyo_app.personalization.service import personalization_engine
        async with AsyncSessionLocal() as db:
            return await personalization_engine.build_prompt_context(db, str(uid))

    ctx = asyncio.get_event_loop().run_until_complete(_build())
    assert "Coaching directive:" in ctx


# ---------------------------------------------------------------- Wedge 1 (identity)
def test_learning_identity_endpoint(client):
    """GET /api/v1/me/identity composes mastery + memory + goals + arc, no 500."""
    headers, uid = _auth(client, "at_i@x.com", "at_ident", "10.70.0.5")
    asyncio.get_event_loop().run_until_complete(_seed_learner(
        uid, affect="engaged",
        masteries={"linear_equations": 0.9, "quadratics": 0.2, "fractions": 0.55}))
    r = client.get("/api/v1/me/identity", headers=headers)
    assert r.status_code == 200, r.text
    body = r.json()
    # The durable identity surface: heatmap + strengths/gaps + arc always present,
    # even if memory/goals subsystems are empty for a fresh user.
    assert "mastery_heatmap" in body
    assert "strengths" in body and "weaknesses" in body
    assert "active_goals" in body and isinstance(body["active_goals"], list)
    assert "learning_arc" in body
    assert "summary" in body["learning_arc"]
    assert body["learning_arc"]["skills_mastered"] >= 1  # linear_equations mastered


def test_chat_endpoint_personalization_path_no_500(client):
    """POST /chat runs the re-enabled personalization path without 500.

    (No API key in tests -> the AI layer returns a graceful fallback, but the
    personalization wiring must not raise.)
    """
    headers, uid = _auth(client, "at_c@x.com", "at_chat", "10.70.0.3")
    asyncio.get_event_loop().run_until_complete(_seed_learner(
        uid, masteries={"quadratics": 0.2}))
    r = client.post("/api/v1/chat", headers=headers,
                    json={"message": "Help me understand quadratics"})
    assert r.status_code == 200, r.text


# ---------------------------------------------------------------- Pillar B (difficulty drives content)
def test_difficulty_band_mapping():
    """Pure mapping check (no DB): the band thresholds target ~70-80% success."""
    from lyo_app.personalization.service import personalization_engine as pe
    assert pe._mastery_to_band(0.1) == "easy"
    assert pe._mastery_to_band(0.5) == "medium"
    assert pe._mastery_to_band(0.9) == "hard"


def test_suggest_content_difficulty_from_seeded_mastery(client):
    """End-to-end: a learner with low avg mastery gets 'easy', high gets 'hard'."""
    _, weak_uid = _auth(client, "at_bw@x.com", "at_b_weak", "10.70.0.10")
    _, strong_uid = _auth(client, "at_bs@x.com", "at_b_strong", "10.70.0.11")
    asyncio.get_event_loop().run_until_complete(_seed_learner(
        weak_uid, masteries={"algebra": 0.1, "geometry": 0.15}))
    asyncio.get_event_loop().run_until_complete(_seed_learner(
        strong_uid, masteries={"algebra": 0.9, "geometry": 0.85}))

    async def _band(uid):
        from lyo_app.core.database import AsyncSessionLocal
        from lyo_app.personalization.service import personalization_engine as pe
        async with AsyncSessionLocal() as db:
            return await pe.suggest_content_difficulty(db, str(uid))

    loop = asyncio.get_event_loop()
    assert loop.run_until_complete(_band(weak_uid)) == "easy"
    assert loop.run_until_complete(_band(strong_uid)) == "hard"


# ---------------------------------------------------------------- Pillar F (plateau detection)
async def _seed_attempts(uid, correctness):
    """Seed InteractionAttempt rows (oldest first) with distinct timestamps.

    Creates a real GraphCourse + LearningNode first (FK constraints are enforced
    on the test SQLite DB) and points every attempt at that node.
    """
    from datetime import datetime, timedelta
    from uuid import uuid4
    from lyo_app.core.database import AsyncSessionLocal
    from lyo_app.ai_classroom.models import (
        InteractionAttempt, GraphCourse, LearningNode, NodeType)
    base = datetime.utcnow() - timedelta(hours=len(correctness))
    async with AsyncSessionLocal() as db:
        course = GraphCourse(id=f"course-{uid}", title="T", subject="math")
        node = LearningNode(
            id=f"node-{uid}", course_id=course.id,
            node_type=NodeType.INTERACTION.value, content={}, sequence_order=0)
        db.add(course)
        db.add(node)
        await db.flush()
        for i, ok in enumerate(correctness):
            db.add(InteractionAttempt(
                id=str(uuid4()), user_id=str(uid), node_id=node.id,
                user_answer="x", is_correct=bool(ok),
                created_at=base + timedelta(minutes=i)))
        await db.commit()


def _detect(uid):
    from lyo_app.core.database import AsyncSessionLocal
    from lyo_app.personalization.service import personalization_engine as pe

    async def _run():
        async with AsyncSessionLocal() as db:
            return await pe.detect_plateau(db, uid)
    return asyncio.get_event_loop().run_until_complete(_run())


def test_plateau_detection_consistent_success_advances(client):
    _, uid = _auth(client, "at_fa@x.com", "at_f_adv", "10.70.0.12")
    # prior mixed, recent all correct -> consistent success -> advance.
    asyncio.get_event_loop().run_until_complete(_seed_attempts(
        uid, [False, True, False, True, True, True, True, True, True, True, True, True]))
    result = _detect(uid)
    assert result is not None
    assert result["trigger"] == "consistent_success"
    assert result["action"] == "advance"


def test_plateau_detection_performance_drop_inserts_review(client):
    _, uid = _auth(client, "at_fd@x.com", "at_f_drop", "10.70.0.13")
    # prior strong, recent weak -> performance drop -> insert review.
    asyncio.get_event_loop().run_until_complete(_seed_attempts(
        uid, [True, True, True, True, True, True, False, False, False, True, False, False]))
    result = _detect(uid)
    assert result is not None
    assert result["action"] == "insert_review"
    assert result["trigger"] in ("performance_drop", "learning_plateau")


def test_plateau_detection_insufficient_history_returns_none(client):
    _, uid = _auth(client, "at_fn@x.com", "at_f_none", "10.70.0.14")
    asyncio.get_event_loop().run_until_complete(_seed_attempts(uid, [True, False]))
    assert _detect(uid) is None


# ---------------------------------------------------------------- Resilience-fallback handling
def test_social_challenge_ignores_resilience_fallback():
    """When the AI manager returns its is_fallback response, the challenge uses
    our on-topic template (degraded=True), not the generic 'retry shortly' text."""
    from lyo_app.collaboration.ai_social_service import ai_social_orchestrator
    import lyo_app.core.ai_resilience as res

    class _FallbackAI:
        async def chat_completion(self, *a, **k):
            return {"content": "Experiencing technical issues; retry shortly.",
                    "is_fallback": True}

    orig = res.ai_resilience_manager
    res.ai_resilience_manager = _FallbackAI()
    try:
        text, degraded = asyncio.get_event_loop().run_until_complete(
            ai_social_orchestrator._llm_challenge("fractions", "Math"))
    finally:
        res.ai_resilience_manager = orig
    assert degraded is True
    assert "retry shortly" not in text.lower()
    assert "fractions" in text.lower()


def test_progressive_hint_ignores_resilience_fallback():
    """A leveled hint never surfaces the resilience manager's fallback string."""
    from lyo_app.ai_classroom.progressive_hints import generate_hint, HintLevel

    class _FallbackAI:
        async def chat_completion(self, *a, **k):
            return {"content": "AI services unavailable right now.", "is_fallback": True}

    hint = asyncio.get_event_loop().run_until_complete(
        generate_hint(HintLevel.CONCEPT, concept="ratios", ai_manager=_FallbackAI()))
    assert "unavailable" not in hint.lower()
    assert "ratios" in hint.lower()


# ---------------------------------------------------------------- Pillar D (progressive hints)
def test_hint_level_escalates_with_attempts():
    """More stuck attempts -> higher hint level, clamped to 1..4."""
    from lyo_app.ai_classroom.progressive_hints import hint_level_for_attempt, HintLevel
    assert hint_level_for_attempt(1) == HintLevel.NUDGE
    assert hint_level_for_attempt(2) == HintLevel.CONCEPT
    assert hint_level_for_attempt(3) == HintLevel.WORKED_EXAMPLE
    assert hint_level_for_attempt(4) == HintLevel.NEAR_SOLUTION
    assert hint_level_for_attempt(99) == HintLevel.NEAR_SOLUTION  # clamped
    assert hint_level_for_attempt(0) == HintLevel.NUDGE           # clamped


def test_generate_hint_template_fallback_differs_by_level():
    """Offline (no ai_manager): each level yields a distinct, escalating template."""
    from lyo_app.ai_classroom.progressive_hints import generate_hint, HintLevel

    async def _h(level):
        return await generate_hint(level, concept="quadratic equations",
                                   question="Solve x^2 - 5x + 6 = 0")

    loop = asyncio.get_event_loop()
    nudge = loop.run_until_complete(_h(HintLevel.NUDGE))
    concept = loop.run_until_complete(_h(HintLevel.CONCEPT))
    example = loop.run_until_complete(_h(HintLevel.WORKED_EXAMPLE))
    near = loop.run_until_complete(_h(HintLevel.NEAR_SOLUTION))
    assert len({nudge, concept, example, near}) == 4  # all distinct
    assert "quadratic equations" in nudge
    assert "example" in example.lower()
    # The near-solution hint scaffolds the final step without handing it over.
    assert "step" in near.lower()


# ---------------------------------------------------------------- Pillar E (mastery-gated edges)
class _FakeDB:
    """Collects objects passed to .add() (no real session needed)."""
    def __init__(self):
        self.added = []

    def add(self, obj):
        self.added.append(obj)


def _node(node_type, seq, *, module_index=0, concept_id=None):
    from lyo_app.ai_classroom.models import LearningNode
    from uuid import uuid4
    return LearningNode(
        id=str(uuid4()), course_id="course-1", node_type=node_type,
        content={"title": f"node {seq}", "module_index": module_index},
        sequence_order=seq, concept_id=concept_id,
    )


def test_mastery_gated_edges_emitted():
    """An interaction node yields MASTERY_LOW (review) + MASTERY_HIGH (skip) edges."""
    from lyo_app.ai_classroom.graph_generator import GraphCourseGenerator
    from lyo_app.ai_classroom.models import NodeType, EdgeCondition

    gen = GraphCourseGenerator()
    inter = _node(NodeType.INTERACTION.value, 0)
    review = _node(NodeType.SUMMARY.value, 1)
    skip_to = _node(NodeType.CONTENT.value, 2) if hasattr(NodeType, "CONTENT") \
        else _node(NodeType.SUMMARY.value, 2)
    remediation = _node(NodeType.REMEDIATION.value, 99)
    ordered = [inter, review, skip_to]

    db = _FakeDB()
    gen._emit_mastery_gated_edges_for_interaction(db, inter, remediation, ordered, 0)

    conds = {e.condition for e in db.added}
    assert EdgeCondition.MASTERY_LOW.value in conds
    assert EdgeCondition.MASTERY_HIGH.value in conds
    # Thresholds are set on every mastery edge.
    for e in db.added:
        assert e.mastery_threshold is not None
    # Targets carry a concept id so the router can evaluate mastery.
    assert remediation.concept_id is not None
    assert skip_to.concept_id is not None


def test_skip_ahead_never_targets_remediation():
    """High-mastery skip-ahead must not route into a remediation node."""
    from lyo_app.ai_classroom.graph_generator import GraphCourseGenerator
    from lyo_app.ai_classroom.models import NodeType

    gen = GraphCourseGenerator()
    inter = _node(NodeType.INTERACTION.value, 0)
    review = _node(NodeType.SUMMARY.value, 1)
    rem = _node(NodeType.REMEDIATION.value, 2)
    assert gen._skip_ahead_target([inter, review, rem], 0) is None


# ---------------------------------------------------------------- Pillar G (real quick-check)
def test_quick_check_is_not_self_assessment_fallback():
    """The fallback quick-check is a real concept T/F, not 'do you feel confident?'."""
    from lyo_app.ai_classroom.graph_generator import GraphCourseGenerator
    from lyo_app.ai_classroom.models import NodeType

    class _BoomAI:
        async def chat_completion(self, *a, **k):
            raise RuntimeError("no key")

    gen = GraphCourseGenerator(ai_manager=_BoomAI())
    node = _node(NodeType.SUMMARY.value, 0)
    q = asyncio.get_event_loop().run_until_complete(
        gen._generate_quick_check(node, None))
    assert q["is_self_assessment"] is False
    assert "feel confident" not in q["question"].lower()
    assert q["type"] == "true_false"


def test_quick_check_reuses_authored_assessment_question():
    """When a module assessment exists, the quick-check reuses a real question."""
    from lyo_app.ai_classroom.graph_generator import GraphCourseGenerator
    from lyo_app.ai_classroom.models import NodeType
    from lyo_app.ai_agents.multi_agent_v2.schemas.course_schemas import (
        CourseAssessments, ModuleAssessment, TrueFalseQuestion,
    )

    assessments = CourseAssessments(module_assessments=[
        ModuleAssessment(module_id="m0", questions=[
            TrueFalseQuestion(
                question_id="q1",
                statement="Photosynthesis converts light energy into chemical energy.",
                correct_answer=True,
                explanation="Plants store light energy as glucose."),
            TrueFalseQuestion(
                question_id="q2", statement="The mitochondria is the powerhouse of the cell.",
                correct_answer=True, explanation="It produces ATP."),
            TrueFalseQuestion(
                question_id="q3", statement="Water boils at 100C at sea level.",
                correct_answer=True, explanation="True at one atmosphere of pressure."),
        ]),
    ])
    gen = GraphCourseGenerator()
    node = _node(NodeType.SUMMARY.value, 0, module_index=0)
    q = asyncio.get_event_loop().run_until_complete(
        gen._generate_quick_check(node, assessments))
    assert q["is_self_assessment"] is False
    assert "Photosynthesis" in q["question"]
    assert q["correct_answer"] == "true"


# ---------------------------------------------------------------- Wedge 2 (social)
def test_ai_peer_matching_pairs_complementary_mastery(client):
    """AI matching pairs a learner strong in X with one weak in X (and vice versa)."""
    h_a, uid_a = _auth(client, "at_pa@x.com", "at_peer_a", "10.70.0.6")
    _, uid_b = _auth(client, "at_pb@x.com", "at_peer_b", "10.70.0.7")
    # A is strong in algebra, weak in geometry; B is the mirror image.
    asyncio.get_event_loop().run_until_complete(_seed_learner(
        uid_a, affect="engaged",
        masteries={"algebra": 0.9, "geometry": 0.15}))
    asyncio.get_event_loop().run_until_complete(_seed_learner(
        uid_b, affect="engaged",
        masteries={"algebra": 0.15, "geometry": 0.9}))

    r = client.get("/api/v1/collaboration/ai/peer-matches", headers=h_a)
    assert r.status_code == 200, r.text
    matches = r.json()["matches"]
    assert matches, "expected at least one complementary peer"
    top = next((m for m in matches if m["user_id"] == uid_b), None)
    assert top is not None, "B should be matched to A"
    # B can teach A geometry; A can teach B algebra.
    assert "geometry" in top["they_can_teach_you"]
    assert "algebra" in top["you_can_teach_them"]


def test_ai_study_pod_and_challenge_and_moderation(client):
    """Forming a pod seeds a shared objective; challenge + moderation don't 500."""
    h_a, uid_a = _auth(client, "at_pda@x.com", "at_pod_a", "10.70.0.8")
    _, uid_b = _auth(client, "at_pdb@x.com", "at_pod_b", "10.70.0.9")
    asyncio.get_event_loop().run_until_complete(_seed_learner(
        uid_a, masteries={"calculus": 0.9, "trig": 0.1}))
    asyncio.get_event_loop().run_until_complete(_seed_learner(
        uid_b, masteries={"calculus": 0.1, "trig": 0.9}))

    pod = client.post("/api/v1/collaboration/ai/study-pods?subject=Math&max_size=4",
                      headers=h_a)
    assert pod.status_code == 200, pod.text
    pod_body = pod.json()
    assert pod_body["status"] == "formed"
    gid = pod_body["group_id"]
    assert uid_a in pod_body["member_ids"]
    assert pod_body["objective"]  # a shared objective was derived

    # Challenge generation (LLM falls back to template offline; must still succeed).
    ch = client.post(f"/api/v1/collaboration/ai/groups/{gid}/challenge", headers=h_a)
    assert ch.status_code == 200, ch.text
    assert ch.json()["challenge"]

    # Moderation summary on a fresh group: no interactions yet, must not 500.
    mod = client.get(f"/api/v1/collaboration/ai/groups/{gid}/moderation", headers=h_a)
    assert mod.status_code == 200, mod.text
    assert "summary" in mod.json()
    assert mod.json()["unanswered_questions"] == []


# ---------------------------------------------------------------- Teacher-in-the-loop (#7)
def test_teacher_routes_require_instructor(client):
    """A normal (non-instructor, non-superuser) user is forbidden."""
    headers, _ = _auth(client, "at_stu@x.com", "at_student", "10.70.0.20")
    r = client.get("/api/v1/teacher/reviews", headers=headers)
    assert r.status_code == 403, r.text


def test_content_review_approve_publishes_course(client):
    """Submitting a draft holds it unpublished; approving publishes it."""
    headers, uid = _auth(client, "at_t1@x.com", "at_teacher1", "10.70.0.21")
    asyncio.get_event_loop().run_until_complete(_make_superuser(uid))
    cid = "gc-review-approve"
    asyncio.get_event_loop().run_until_complete(_make_graph_course(cid, published=True))

    sub = client.post("/api/v1/teacher/reviews", headers=headers,
                      json={"course_id": cid, "qa_score": 82,
                            "qa_recommendation": "publish_with_minor_fixes"})
    assert sub.status_code == 200, sub.text
    rid = sub.json()["id"]
    assert sub.json()["status"] == "pending"
    # Submission forces the draft unpublished until a human approves.
    assert asyncio.get_event_loop().run_until_complete(_course_published(cid)) is False

    # It shows up in the pending queue.
    q = client.get("/api/v1/teacher/reviews?status=pending", headers=headers)
    assert q.status_code == 200
    assert any(rv["id"] == rid for rv in q.json()["reviews"])

    appr = client.post(f"/api/v1/teacher/reviews/{rid}/approve", headers=headers,
                       json={"notes": "Looks accurate."})
    assert appr.status_code == 200, appr.text
    assert appr.json()["status"] == "approved"
    assert asyncio.get_event_loop().run_until_complete(_course_published(cid)) is True


def test_content_review_flag_keeps_unpublished(client):
    """Flagging a draft keeps it from students."""
    headers, uid = _auth(client, "at_t2@x.com", "at_teacher2", "10.70.0.22")
    asyncio.get_event_loop().run_until_complete(_make_superuser(uid))
    cid = "gc-review-flag"
    asyncio.get_event_loop().run_until_complete(_make_graph_course(cid, published=False))

    rid = client.post("/api/v1/teacher/reviews", headers=headers,
                      json={"course_id": cid}).json()["id"]
    flg = client.post(f"/api/v1/teacher/reviews/{rid}/flag", headers=headers,
                      json={"notes": "Module 2 has a factual error."})
    assert flg.status_code == 200, flg.text
    assert flg.json()["status"] == "flagged"
    assert asyncio.get_event_loop().run_until_complete(_course_published(cid)) is False


def test_scan_at_risk_surfaces_struggling_student(client):
    """AI flags a plateaued learner; the alert can be listed and resolved."""
    headers, uid = _auth(client, "at_t3@x.com", "at_teacher3", "10.70.0.23")
    asyncio.get_event_loop().run_until_complete(_make_superuser(uid))
    # Seed a clear performance drop for this (instructor's own) user id.
    asyncio.get_event_loop().run_until_complete(_seed_attempts(
        uid, [True, True, True, True, True, True, False, False, False, True, False, False]))

    scan = client.post("/api/v1/teacher/students/scan-at-risk", headers=headers)
    assert scan.status_code == 200, scan.text
    at_risk = scan.json()["at_risk"]
    mine = next((a for a in at_risk if a["student_id"] == uid), None)
    assert mine is not None, f"expected {uid} flagged; got {at_risk}"
    assert mine["trigger"] in ("performance_drop", "learning_plateau")
    assert "alert_id" in mine

    alerts = client.get("/api/v1/teacher/students/alerts?status=open", headers=headers)
    assert alerts.status_code == 200
    assert any(a["id"] == mine["alert_id"] for a in alerts.json()["alerts"])

    res = client.post(f"/api/v1/teacher/students/alerts/{mine['alert_id']}/resolve",
                      headers=headers,
                      json={"status": "resolved", "notes": "Scheduled a 1:1."})
    assert res.status_code == 200, res.text
    assert res.json()["status"] == "resolved"


# ---------------------------------------------------------------- Teaching-through-creation (#4)
def test_creation_project_lifecycle(client):
    """Start a build, submit work step-by-step, and reach completion."""
    headers, uid = _auth(client, "at_cr@x.com", "at_creator", "10.70.0.30")
    # Strong learner -> expect LOW scaffold (autonomy) via mastery band.
    asyncio.get_event_loop().run_until_complete(_seed_learner(
        uid, affect="engaged", masteries={"python": 0.9}))

    start = client.post("/api/v1/create/projects", headers=headers,
                        json={"goal": "Build a command-line to-do app in Python",
                              "skill_id": "python"})
    assert start.status_code == 200, start.text
    proj = start.json()
    pid = proj["id"]
    assert proj["status"] == "active"
    assert len(proj["steps"]) >= 3
    assert proj["steps"][0]["status"] == "active"
    assert proj["scaffold_level"] == "low"          # high mastery -> low scaffold

    n_steps = len(proj["steps"])
    # Walk every step with substantive submissions; offline review accepts them.
    completed = False
    for i in range(n_steps):
        r = client.post(f"/api/v1/create/projects/{pid}/submit", headers=headers,
                        json={"content": f"Here is my detailed work for step {i}: "
                                         "I built the module and tested it thoroughly."})
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["accepted"] is True
        completed = body["completed"]
    assert completed is True

    got = client.get(f"/api/v1/create/projects/{pid}", headers=headers)
    assert got.status_code == 200
    assert got.json()["status"] == "completed"
    assert all(s["status"] == "done" for s in got.json()["steps"])


def test_creation_thin_submission_is_rejected(client):
    """A near-empty artifact is sent back for revision (no free advance)."""
    headers, uid = _auth(client, "at_cr2@x.com", "at_creator2", "10.70.0.31")
    pid = client.post("/api/v1/create/projects", headers=headers,
                      json={"goal": "Write a short story about a robot"}).json()["id"]
    r = client.post(f"/api/v1/create/projects/{pid}/submit", headers=headers,
                    json={"content": "ok"})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["accepted"] is False
    assert body["advanced"] is False
    assert body["current_step"] == 0          # stayed on the same step


def test_creation_scaffold_tracks_mastery(client):
    """A weak learner gets HIGH scaffold (more hand-holding)."""
    headers, uid = _auth(client, "at_cr3@x.com", "at_creator3", "10.70.0.32")
    asyncio.get_event_loop().run_until_complete(_seed_learner(
        uid, masteries={"music": 0.1}))
    proj = client.post("/api/v1/create/projects", headers=headers,
                       json={"goal": "Compose a simple melody", "skill_id": "music"}).json()
    assert proj["scaffold_level"] == "high"
