"""HTTP routes for the "I Have a Test" prep and study plans system."""
import json
import logging
from datetime import datetime, date, timedelta, timezone
from typing import List, Optional, Dict, Any

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import desc, select, and_
from sqlalchemy.ext.asyncio import AsyncSession

from lyo_app.auth.dependencies import get_current_user, get_db
from lyo_app.auth.models import User
from lyo_app.core.ai_resilience import ai_resilience_manager
from lyo_app.study_plans.models import TestProfile, StudyPlan, StudySession, SessionReminder, PlanEvent
from lyo_app.study_plans.schemas import (
    IntakeMessage,
    IntakeResponse,
    StudyPlanRead,
    StudyPlanUpdate,
    StudySessionRead,
    StudySessionUpdate,
    ProgressDashboardStats,
    PlanEventRead
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/me/study_plans", tags=["study-plans"])

# ═══════════════════════════════════════════════════════════════════════════════════
# 🧩 INTAKE SYSTEM PROMPT & ENDPOINTS
# ═══════════════════════════════════════════════════════════════════════════════════

INTAKE_SYSTEM_PROMPT = """You are Lyo's test-prep intake coach. Your job is to gather just enough information to build a personalized study plan.

You will have a short, warm conversation (5-8 turns max). After each user message, decide:
1. What ONE follow-up question to ask next, OR
2. Whether you have enough info to wrap up

You need to learn:
- Subject and exact test date (in YYYY-MM-DD format)
- Test format (multiple_choice, essay, oral, mixed)
- Topics covered and the user's confidence in each (1-10)
- How many minutes per day they can study
- Their current stress level (1-10)

Rules:
- Ask ONE question per turn. Never stack questions.
- Match the user's energy. If they're brief, be brief.
- Offer interactive suggestions using standard Smart Blocks.
- When you have everything, set "intake_complete": true and produce the final profile fields in "profile_update".

ALWAYS respond in this exact JSON shape:
{
  "message_to_user": "your next message (warm, conversational)",
  "smart_blocks": [],  // optional list of UI block dicts
  "intake_complete": false,
  "profile_update": {
    "subject": "...", // optional updated subject
    "test_date": "YYYY-MM-DD", // optional test date string
    "test_format": "multiple_choice" | "essay" | "oral" | "mixed", // optional
    "baseline_confidence": 5, // optional int 1-10
    "daily_minutes_available": 45, // optional int
    "study_days_per_week": 5, // optional int
    "stress_level": 5, // optional int 1-10
    "topics": [{"name": "...", "weight": 1.0, "confidence": 5}] // optional topics
  }
}
"""

def safe_parse_date(date_str: str) -> Optional[date]:
    if not date_str:
        return None
    try:
        return datetime.fromisoformat(date_str.replace("Z", "+00:00")).date()
    except Exception:
        try:
            return datetime.strptime(date_str, "%Y-%m-%d").date()
        except Exception:
            return None

@router.post(
    "/intake/turn",
    response_model=IntakeResponse,
    summary="Process a single turn of the test-prep intake conversation.",
)
async def intake_turn(
    body: IntakeMessage,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> IntakeResponse:
    # 1. Load or create test_profile
    profile = None
    if body.test_profile_id:
        stmt = select(TestProfile).where(
            and_(TestProfile.id == body.test_profile_id, TestProfile.user_id == current_user.id)
        )
        result = await db.execute(stmt)
        profile = result.scalar_one_or_none()
        if not profile:
            raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Test profile not found")
    
    if not profile:
        profile = TestProfile(
            user_id=current_user.id,
            subject="Pending Test",
            test_date=date.today() + timedelta(days=30),
            intake_transcript=[]
        )
        db.add(profile)
        await db.flush()  # populate ID
    
    # 2. Append user message to transcript
    transcript = list(profile.intake_transcript)
    transcript.append({"role": "user", "content": body.user_message})
    
    # 3. Call resilient LLM
    messages = [{"role": "system", "content": INTAKE_SYSTEM_PROMPT}]
    # Limit transcript context size to last 15 messages for safety
    for turn in transcript[-15:]:
        messages.append({"role": turn["role"], "content": turn["content"]})
    
    try:
        raw_res = await ai_resilience_manager.chat_completion(
            messages=messages,
            temperature=0.7,
            response_format={"type": "json_object"}
        )
        parsed = json.loads(raw_res.get("content", "{}"))
    except Exception as e:
        logger.error(f"Intake LLM call failed: {e}")
        parsed = {
            "message_to_user": "I'm having a little trouble thinking right now. Could you please tell me that again?",
            "smart_blocks": [],
            "intake_complete": False,
            "profile_update": {}
        }
    
    # 4. Update profile updates in DB
    transcript.append({"role": "assistant", "content": parsed.get("message_to_user", "")})
    profile.intake_transcript = transcript
    profile.intake_complete = parsed.get("intake_complete", False)
    
    updates = parsed.get("profile_update", {})
    if updates:
        if "subject" in updates and updates["subject"]:
            profile.subject = str(updates["subject"])
        if "test_date" in updates and updates["test_date"]:
            p_date = safe_parse_date(updates["test_date"])
            if p_date:
                profile.test_date = p_date
        if "test_format" in updates and updates["test_format"]:
            profile.test_format = str(updates["test_format"])
        if "baseline_confidence" in updates:
            profile.baseline_confidence = int(updates["baseline_confidence"])
        if "daily_minutes_available" in updates:
            profile.daily_minutes_available = int(updates["daily_minutes_available"])
        if "study_days_per_week" in updates:
            profile.study_days_per_week = int(updates["study_days_per_week"])
        if "stress_level" in updates:
            profile.stress_level = int(updates["stress_level"])
        if "topics" in updates:
            profile.topics = updates["topics"]
            
    await db.commit()
    await db.refresh(profile)
    
    return IntakeResponse(
        test_profile_id=profile.id,
        message_to_user=parsed.get("message_to_user", "Got it! Let's continue."),
        smart_blocks=parsed.get("smart_blocks", []),
        intake_complete=profile.intake_complete
    )

# ═══════════════════════════════════════════════════════════════════════════════════
# 📅 PLANNER AGENT & GENERATION
# ═══════════════════════════════════════════════════════════════════════════════════

PLANNER_SYSTEM_PROMPT = """You are Lyo's study planner. Given a test profile JSON, produce a complete, realistic study plan.

Rules:
- Work BACKWARD from the test date.
- Reserve the final 2 days for light review only (no new material).
- Mix session types: 60% learn, 25% practice, 15% review.
- Schedule 1 mock test in the final week.
- Respect daily_minutes_available and study_days_per_week.
- Weight more study blocks/time toward topics with LOW user confidence.
- Include a clear weekly milestone focus.
- Ensure all scheduled_at timestamps are fully-formed ISO-8601 strings (e.g. 2026-05-20T18:00:00Z) distributed logically over study days.

Respond in this exact JSON shape:
{
  "weekly_milestones": [
    {"week": 1, "focus": "Foundations of cell biology", "goals": ["Master 3 core topics"]}
  ],
  "sessions": [
    {
      "scheduled_at": "2026-05-20T18:00:00Z",
      "duration_minutes": 45,
      "topic": "Cell membrane structure",
      "session_type": "learn" // learn | practice | review | mock_test
    }
  ],
  "reasoning": "Brief explanation of the plan structure"
}
"""

@router.post(
    "/plans/generate",
    summary="Generate a customized study plan based on a completed test profile.",
)
async def generate_plan(
    test_profile_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> Dict[str, Any]:
    # 1. Fetch test profile
    stmt = select(TestProfile).where(
        and_(TestProfile.id == test_profile_id, TestProfile.user_id == current_user.id)
    )
    result = await db.execute(stmt)
    profile = result.scalar_one_or_none()
    if not profile:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Test profile not found")
    if not profile.intake_complete:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail="Finish intake before generating plan")

    # Serialize profile context for LLM
    profile_ctx = {
        "subject": profile.subject,
        "test_date": str(profile.test_date),
        "test_format": profile.test_format,
        "topics": profile.topics,
        "baseline_confidence": profile.baseline_confidence,
        "daily_minutes_available": profile.daily_minutes_available,
        "study_days_per_week": profile.study_days_per_week,
        "stress_level": profile.stress_level,
    }

    # 2. Call resilient LLM Planner
    try:
        raw_res = await ai_resilience_manager.chat_completion(
            messages=[
                {"role": "system", "content": PLANNER_SYSTEM_PROMPT},
                {"role": "user", "content": json.dumps(profile_ctx)}
            ],
            temperature=0.4,
            response_format={"type": "json_object"}
        )
        plan_data = json.loads(raw_res.get("content", "{}"))
    except Exception as e:
        logger.error(f"Planner LLM call failed: {e}")
        # Standard fallback plan structure
        plan_data = {
            "weekly_milestones": [{"week": 1, "focus": f"Introductory review of {profile.subject}", "goals": ["Get started"]}],
            "sessions": [
                {
                    "scheduled_at": (datetime.utcnow() + timedelta(days=1)).replace(hour=17, minute=0, second=0).isoformat() + "Z",
                    "duration_minutes": profile.daily_minutes_available,
                    "topic": "General diagnostics review",
                    "session_type": "review"
                }
            ],
            "reasoning": "Standard baseline plan generated due to heavy service traffic."
        }

    # 3. Create StudyPlan in DB
    plan = StudyPlan(
        test_profile_id=test_profile_id,
        user_id=current_user.id,
        weekly_milestones=plan_data.get("weekly_milestones", []),
        total_sessions=len(plan_data.get("sessions", [])),
        generated_by_agent="planner_v2",
        generation_notes=plan_data.get("reasoning", "")[:500]
    )
    db.add(plan)
    await db.flush()  # Populate plan ID

    # 4. Insert study sessions and reminders
    sessions_to_insert = []
    reminders_to_insert = []
    
    for s_item in plan_data.get("sessions", []):
        try:
            sched_dt = datetime.fromisoformat(s_item["scheduled_at"].replace("Z", "+00:00"))
        except Exception:
            sched_dt = datetime.utcnow() + timedelta(days=1)
            
        session = StudySession(
            study_plan_id=plan.id,
            user_id=current_user.id,
            scheduled_at=sched_dt,
            duration_minutes=int(s_item.get("duration_minutes", profile.daily_minutes_available)),
            topic=s_item.get("topic", "Study Block"),
            session_type=s_item.get("session_type", "learn")
        )
        db.add(session)
        sessions_to_insert.append(session)
        
    await db.flush()  # Populate session IDs
    
    # Generate 3 reminders per session (night_before, thirty_min, checkin_after)
    for session in sessions_to_insert:
        sched = session.scheduled_at
        
        # 12 hours before
        reminders_to_insert.append(SessionReminder(
            session_id=session.id,
            user_id=current_user.id,
            fire_at=sched - timedelta(hours=12),
            reminder_type="night_before",
            payload={
                "title": "Study Session Tomorrow",
                "body": f"{session.topic} at {sched.strftime('%-I:%M %p')}",
                "deep_link": f"lyo://session/{session.id}"
            }
        ))
        
        # 30 min before
        reminders_to_insert.append(SessionReminder(
            session_id=session.id,
            user_id=current_user.id,
            fire_at=sched - timedelta(minutes=30),
            reminder_type="thirty_min",
            payload={
                "title": "Study in 30 minutes",
                "body": f"Ready for {session.topic}?",
                "deep_link": f"lyo://session/{session.id}"
            }
        ))
        
        # 5 minutes after session ends
        reminders_to_insert.append(SessionReminder(
            session_id=session.id,
            user_id=current_user.id,
            fire_at=sched + timedelta(minutes=session.duration_minutes + 5),
            reminder_type="checkin_after",
            payload={
                "title": "How'd it go?",
                "body": "Take 10 seconds to log your session",
                "deep_link": f"lyo://session/{session.id}/checkin"
            }
        ))
        
    for reminder in reminders_to_insert:
        db.add(reminder)

    # Log plan creation event
    event = PlanEvent(
        study_plan_id=plan.id,
        user_id=current_user.id,
        event_type="created",
        reasoning=plan.generation_notes,
        payload={"session_count": len(sessions_to_insert)}
    )
    db.add(event)
    
    await db.commit()
    await db.refresh(plan)

    return {"plan_id": plan.id, "total_sessions": len(sessions_to_insert)}

# ═══════════════════════════════════════════════════════════════════════════════════
# 🔄 GET active plans, update, and delete (Backward compatibility)
# ═══════════════════════════════════════════════════════════════════════════════════

@router.get(
    "",
    response_model=List[StudyPlanRead],
    summary="List the current user's study plans.",
)
async def list_plans(
    include_completed: bool = Query(default=False),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> List[StudyPlanRead]:
    stmt = select(StudyPlan).where(StudyPlan.user_id == current_user.id)
    if not include_completed:
        stmt = stmt.where(StudyPlan.status == "active")
    stmt = stmt.order_by(desc(StudyPlan.updated_at))

    result = await db.execute(stmt)
    plans = result.scalars().all()
    return [StudyPlanRead.model_validate(p) for p in plans]

@router.get(
    "/{plan_id}",
    response_model=StudyPlanRead,
    summary="Fetch a single plan by ID.",
)
async def get_plan(
    plan_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> StudyPlanRead:
    stmt = select(StudyPlan).where(and_(StudyPlan.id == plan_id, StudyPlan.user_id == current_user.id))
    result = await db.execute(stmt)
    plan = result.scalar_one_or_none()
    if not plan:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Plan not found")
    return StudyPlanRead.model_validate(plan)

@router.patch(
    "/{plan_id}",
    response_model=StudyPlanRead,
    summary="Partial update of a plan.",
)
async def update_plan(
    plan_id: str,
    payload: StudyPlanUpdate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> StudyPlanRead:
    stmt = select(StudyPlan).where(and_(StudyPlan.id == plan_id, StudyPlan.user_id == current_user.id))
    result = await db.execute(stmt)
    plan = result.scalar_one_or_none()
    if not plan:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Plan not found")
        
    if payload.status is not None:
        plan.status = payload.status
    if payload.version is not None:
        plan.version = payload.version
    if payload.weekly_milestones is not None:
        plan.weekly_milestones = payload.weekly_milestones
        
    await db.commit()
    await db.refresh(plan)
    return StudyPlanRead.model_validate(plan)

@router.delete(
    "/{plan_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Soft-delete a plan.",
)
async def delete_plan(
    plan_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> None:
    stmt = select(StudyPlan).where(and_(StudyPlan.id == plan_id, StudyPlan.user_id == current_user.id))
    result = await db.execute(stmt)
    plan = result.scalar_one_or_none()
    if not plan:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Plan not found")
        
    plan.status = "abandoned"
    await db.commit()

# ═══════════════════════════════════════════════════════════════════════════════════
# 📚 STUDY SESSION & TODAY LOOP
# ═══════════════════════════════════════════════════════════════════════════════════

@router.get(
    "/sessions/today",
    response_model=List[StudySessionRead],
    summary="Fetch all active study sessions for today.",
)
async def get_today_sessions(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> List[StudySessionRead]:
    # Start and end of the current day in UTC
    start = datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0)
    end = start + timedelta(days=1)
    
    stmt = select(StudySession).where(
        and_(
            StudySession.user_id == current_user.id,
            StudySession.scheduled_at >= start,
            StudySession.scheduled_at < end
        )
    ).order_by(StudySession.scheduled_at)
    
    result = await db.execute(stmt)
    sessions = result.scalars().all()
    return [StudySessionRead.model_validate(s) for s in sessions]

@router.post(
    "/sessions/{session_id}/complete",
    summary="Mark a study session completed with score and notes.",
)
async def complete_session(
    session_id: str,
    performance_score: float = Query(..., ge=0.0, le=1.0),
    user_notes: Optional[str] = Query(""),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> Dict[str, Any]:
    stmt = select(StudySession).where(
        and_(StudySession.id == session_id, StudySession.user_id == current_user.id)
    )
    result = await db.execute(stmt)
    session = result.scalar_one_or_none()
    if not session:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Study session not found")
        
    session.status = "completed"
    session.completed_at = datetime.utcnow()
    session.performance_score = performance_score
    session.user_notes = user_notes
    
    # Audit log of the event
    event = PlanEvent(
        study_plan_id=session.study_plan_id,
        user_id=current_user.id,
        event_type="session_completed",
        reasoning=f"Session on {session.topic} completed with score {performance_score}",
        payload={"session_id": session_id, "performance_score": performance_score}
    )
    db.add(event)
    
    await db.commit()
    return {"ok": True}

# ═══════════════════════════════════════════════════════════════════════════════════
# 📈 PROGRESS DASHBOARD STATS
# ═══════════════════════════════════════════════════════════════════════════════════

@router.get(
    "/plans/{plan_id}/stats",
    response_model=ProgressDashboardStats,
    summary="Get user performance stats, mastery heatmap details, and recent audit logs.",
)
async def get_plan_stats(
    plan_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> ProgressDashboardStats:
    # 1. Load sessions
    stmt_sessions = select(StudySession).where(
        and_(StudySession.study_plan_id == plan_id, StudySession.user_id == current_user.id)
    )
    result_s = await db.execute(stmt_sessions)
    sessions = result_s.scalars().all()
    
    # 2. Load events
    stmt_events = select(PlanEvent).where(
        and_(PlanEvent.study_plan_id == plan_id, PlanEvent.user_id == current_user.id)
    ).order_by(desc(PlanEvent.created_at)).limit(10)
    result_e = await db.execute(stmt_events)
    events = result_e.scalars().all()
    
    # 3. Compute topic mastery (average performance score)
    by_topic = {}
    for s in sessions:
        if s.status != "completed":
            continue
        score = float(s.performance_score) if s.performance_score is not None else 0.0
        by_topic.setdefault(s.topic, []).append(score)
        
    mastery = {topic: sum(scores)/len(scores) for topic, scores in by_topic.items()}
    completed_count = sum(1 for s in sessions if s.status == "completed")
    
    return ProgressDashboardStats(
        mastery_by_topic=mastery,
        sessions_completed=completed_count,
        sessions_total=len(sessions),
        recent_events=[PlanEventRead.model_validate(e) for e in events]
    )

# ═══════════════════════════════════════════════════════════════════════════════════
# 🤖 COACH AGENT (ADAPTIVE RE-PLANNING ROUTE)
# ═══════════════════════════════════════════════════════════════════════════════════

COACH_SYSTEM_PROMPT = """You are Lyo's daily study coach. You wake up each morning and review the user's progress.

You see:
- The test profile containing targets and stress levels
- All past sessions (completed, skipped) with performance scores
- The remaining plan
- Days until test

Your job: decide what to do today. Pick exactly ONE action:
1. HOLD — plan is on track, no changes needed.
2. ADJUST — small changes (e.g. reschedule tomorrow's session, shift a topic's emphasis).
3. REPLAN — significant rewrite needed (e.g. user skipped 3+ consecutive sessions, or averages a score < 0.4).
4. NUDGE_USER — send a direct encouraging message or stress alert without changing schedules.

Respond in this exact JSON shape:
{
  "action": "HOLD" | "ADJUST" | "REPLAN" | "NUDGE_USER",
  "reasoning": "Brief explanation of this decision (1-2 sentences)",
  "changes": [], // List of specific session adjustments: [{"session_id": "...", "updates": {"topic": "...", "duration_minutes": 30}}]
  "nudge_message": "Warm message here if NUDGE_USER"
}
"""

@router.post(
    "/plans/{plan_id}/coach",
    summary="Trigger the resilient Coach Agent to analyze progress and adapt the plan daily.",
)
async def coach_study_plan(
    plan_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> Dict[str, Any]:
    # 1. Load active plan
    stmt_plan = select(StudyPlan).where(
        and_(StudyPlan.id == plan_id, StudyPlan.user_id == current_user.id, StudyPlan.status == "active")
    )
    result_p = await db.execute(stmt_plan)
    plan = result_p.scalar_one_or_none()
    if not plan:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Active study plan not found")
        
    # 2. Load test profile
    stmt_prof = select(TestProfile).where(TestProfile.id == plan.test_profile_id)
    result_prof = await db.execute(stmt_prof)
    profile = result_prof.scalar_one_or_none()
    
    # 3. Load all sessions
    stmt_sessions = select(StudySession).where(StudySession.study_plan_id == plan_id)
    result_s = await db.execute(stmt_sessions)
    sessions = result_s.scalars().all()
    
    # Construct LLM context
    days_left = (profile.test_date - date.today()).days if profile else 30
    session_list_ctx = []
    for s in sessions:
        session_list_ctx.append({
            "id": s.id,
            "topic": s.topic,
            "session_type": s.session_type,
            "status": s.status,
            "performance_score": float(s.performance_score) if s.performance_score is not None else None,
            "scheduled_at": s.scheduled_at.isoformat()
        })
        
    context = {
        "days_until_test": days_left,
        "stress_level": profile.stress_level if profile else 5,
        "daily_minutes": profile.daily_minutes_available if profile else 45,
        "sessions": session_list_ctx
    }
    
    # 4. Call resilient LLM Coach
    try:
        raw_res = await ai_resilience_manager.chat_completion(
            messages=[
                {"role": "system", "content": COACH_SYSTEM_PROMPT},
                {"role": "user", "content": json.dumps(context)}
            ],
            temperature=0.3,
            response_format={"type": "json_object"}
        )
        decision = json.loads(raw_res.get("content", "{}"))
    except Exception as e:
        logger.error(f"Coach LLM call failed: {e}")
        decision = {
            "action": "HOLD",
            "reasoning": "Maintaining plan shape under heavy network loads.",
            "changes": [],
            "nudge_message": ""
        }
        
    action = decision.get("action", "HOLD")
    reasoning = decision.get("reasoning", "Plan reviewed.")
    
    # 5. Apply the Coach's Action
    if action == "ADJUST":
        for change in decision.get("changes", []):
            s_id = change.get("session_id")
            s_updates = change.get("updates", {})
            if s_id and s_updates:
                stmt_s = select(StudySession).where(StudySession.id == s_id)
                res_s = await db.execute(stmt_s)
                session_to_mod = res_s.scalar_one_or_none()
                if session_to_mod:
                    if "topic" in s_updates:
                        session_to_mod.topic = s_updates["topic"]
                    if "duration_minutes" in s_updates:
                        session_to_mod.duration_minutes = int(s_updates["duration_minutes"])
                        
    elif action == "REPLAN":
        # Archive current plan
        plan.status = "archived"
        await db.commit()
        # Trigger generation of a fresh plan
        new_plan_info = await generate_plan(plan.test_profile_id, current_user=current_user, db=db)
        return {
            "action": "REPLAN",
            "reasoning": "Plan completely rebuilt to better adapt to your pacing.",
            "new_plan_id": new_plan_info["plan_id"]
        }
        
    # Log the adaptation event
    event = PlanEvent(
        study_plan_id=plan.id,
        user_id=current_user.id,
        event_type="adapted",
        reasoning=reasoning[:500],
        payload=decision
    )
    db.add(event)
    await db.commit()
    
    return {
        "action": action,
        "reasoning": reasoning,
        "nudge_message": decision.get("nudge_message", "")
    }
