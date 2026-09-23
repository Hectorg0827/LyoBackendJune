"""Chat presentation adapter for the account-owned Test Prep workflow."""
from dataclasses import dataclass
from typing import Any, Dict, Optional

from fastapi import HTTPException

from lyo_app.study_plans import routes
from lyo_app.study_plans.schemas import IntakeMessage

#: The in-app route, not an absolute URL.
#:
#: This used to be written as `https://lyoai.app/test-prep`. On the web that is
#: a full page load: the learner leaves the running app, loses the conversation
#: they are in, and waits for a cold start to reach a route the client router
#: opens instantly. Clients resolve a path against their own navigation.
TEST_PREP_PATH = "/test-prep"


@dataclass(frozen=True)
class ChatTurnResult:
    """What one Test Prep turn gives the chat surface.

    `text` is the reply every client can render. `handoff` is present only once
    a plan actually exists, and carries what a client needs to offer opening
    Test Prep or starting the next session without asking the learner anything
    again. A client that cannot render it loses nothing: the same link is in
    the text.
    """

    text: str
    handoff: Optional[Dict[str, Any]] = None


def _link_to_test_prep(text: str) -> str:
    """Make the first mention of Test Prep the link it is already promising.

    The reply already tells the learner to open Test Prep. It said so twice —
    once from the intake handler and once appended here — and neither was
    tappable. One sentence, one link.
    """
    return text.replace("Test Prep", f"[Test Prep]({TEST_PREP_PATH})", 1)


async def _handoff(current_user, db) -> Optional[Dict[str, Any]]:
    """What the learner can do next, read from the saved plan.

    Returns None rather than a partial shape when there is no plan: a client
    must not be handed a "start now" for a session that does not exist.
    """
    try:
        state = await routes.prep_state(current_user=current_user, db=db)
    except HTTPException:
        return None

    plan = state.get("plan")
    profile = state.get("profile")
    if not plan or not profile:
        return None

    # The soonest session the learner has not finished. Skipped and completed
    # ones are not something to start.
    upcoming = [
        session for session in (state.get("sessions") or [])
        if getattr(session, "status", None) not in ("completed", "skipped")
    ]
    next_session = upcoming[0] if upcoming else None

    handoff: Dict[str, Any] = {
        "plan_id": str(plan.id),
        "subject": profile.subject,
        "test_date": profile.test_date.isoformat() if profile.test_date else None,
        "path": TEST_PREP_PATH,
        "next_session": None,
    }
    if next_session is not None:
        topic = (getattr(next_session, "topic", "") or "").strip()
        # No topic means nothing to teach, so there is nothing to start. The
        # client is told about the plan and not offered a session.
        if topic:
            scheduled = getattr(next_session, "scheduled_at", None)
            handoff["next_session"] = {
                "id": str(next_session.id),
                "topic": topic,
                "session_type": getattr(next_session, "session_type", None),
                "scheduled_at": scheduled.isoformat() if scheduled else None,
            }
    return handoff


async def process_chat_turn(request, current_user, db) -> ChatTurnResult:
    """Use the same handlers as the dedicated clients; never keep a local plan."""
    reply = await routes.intake_turn(IntakeMessage(
        user_message=request.text or "I have a test",
        request_id=request.client_message_id,
        conversation_id=str(request.conversation_id),
        timezone=request.timezone,
        materials=[m.model_dump(mode="json") for m in (request.media or [])],
    ), current_user=current_user, db=db)

    text = reply.message_to_user
    if not reply.intake_complete:
        return ChatTurnResult(text=text)

    try:
        await routes.generate_plan(reply.test_profile_id, current_user=current_user, db=db)
    except HTTPException:
        # Say what is true: the answers are kept, the schedule is not built,
        # and reopening does not mean repeating intake.
        return ChatTurnResult(text=(
            f"{text}\n\nYour answers are saved, but I couldn't build the schedule yet. "
            f"Open [Test Prep]({TEST_PREP_PATH}) to retry without repeating intake."
        ))

    return ChatTurnResult(text=_link_to_test_prep(text), handoff=await _handoff(current_user, db))
