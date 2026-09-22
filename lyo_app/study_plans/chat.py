"""Chat presentation adapter for the account-owned Test Prep workflow."""
from fastapi import HTTPException

from lyo_app.study_plans import routes
from lyo_app.study_plans.schemas import IntakeMessage


async def process_chat_turn(request, current_user, db):
    """Use the same handlers as the dedicated clients; never keep a local plan."""
    reply = await routes.intake_turn(IntakeMessage(
        user_message=request.text or "I have a test",
        request_id=request.client_message_id,
        conversation_id=str(request.conversation_id),
        timezone=request.timezone,
        materials=[m.model_dump(mode="json") for m in (request.media or [])],
    ), current_user=current_user, db=db)
    text = reply.message_to_user
    if reply.intake_complete:
        try:
            await routes.generate_plan(reply.test_profile_id, current_user=current_user, db=db)
            text += "\n\nYour study plan is saved to your account. Open [Test Prep](https://lyoai.app/test-prep) for your schedule and lessons."
        except HTTPException:
            text += "\n\nYour answers are saved, but I couldn't build the schedule yet. Open [Test Prep](https://lyoai.app/test-prep) to retry without repeating intake."
    return text
