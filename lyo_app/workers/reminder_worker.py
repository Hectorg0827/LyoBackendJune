"""Cron worker for processing and dispatching scheduled session reminders."""
import asyncio
import logging
from datetime import datetime, timedelta
from sqlalchemy import select, and_

from lyo_app.core.database import AsyncSessionLocal
from lyo_app.auth.models import User
from lyo_app.study_plans.workflow import quiet_until
from lyo_app.study_plans.models import SessionReminder, StudySession, StudyPlan
from lyo_app.services.push_notifications import push_service, PushNotification

logger = logging.getLogger(__name__)


async def fire_due_reminders():
    """Finds all pending reminders that are due and dispatches them via APNs/FCM."""
    logger.info("⏰ Starting reminder worker cycle...")
    
    async with AsyncSessionLocal() as db:
        now = datetime.utcnow()
        stmt = select(SessionReminder).where(
            and_(SessionReminder.status == "pending", SessionReminder.fire_at <= now)
        ).order_by(SessionReminder.fire_at).limit(100).with_for_update(skip_locked=True)
        
        result = await db.execute(stmt)
        due_reminders = result.scalars().all()
        
        if not due_reminders:
            logger.info("No due reminders found.")
            return
            
        logger.info(f"Processing {len(due_reminders)} due reminders...")
        for reminder in due_reminders:
            try:
                session = await db.get(StudySession, reminder.session_id)
                plan = await db.get(StudyPlan, session.study_plan_id) if session else None
                if (not session or not plan or plan.status != "active"
                        or session.status in {"completed", "skipped"}
                        or reminder.fire_at < now - timedelta(hours=2)):
                    reminder.status = "cancelled"
                    continue
                learner = await db.get(User, reminder.user_id)
                preferences = ((learner.learning_profile or {}).get("notification_preferences", {}) if learner else {})
                if preferences.get("course_reminders") is False:
                    reminder.status = "cancelled"
                    continue
                quiet_end = quiet_until(now, preferences)
                if quiet_end:
                    if quiet_end > reminder.fire_at + timedelta(hours=2):
                        reminder.status = "cancelled"
                    else:
                        reminder.fire_at = quiet_end
                    continue
                title = reminder.payload.get("title", "Lyo Prep")
                body = reminder.payload.get("body", "Time for your scheduled study session!")
                deep_link = reminder.payload.get("deep_link", "")
                
                notification = PushNotification(
                    title=title,
                    message=body,
                    data={"deep_link": deep_link, "reminder_id": reminder.id, "action": "open_test_prep"}
                )
                
                # Send push notification
                sent_count = await push_service.send_to_user(
                    user_id=reminder.user_id,
                    notification=notification,
                    db=db
                )
                
                if sent_count > 0:
                    reminder.status = "sent"
                    reminder.sent_at = datetime.utcnow()
                else:
                    # No devices/provider acceptance is not a successful delivery.
                    payload = dict(reminder.payload or {})
                    payload["attempts"] = payload.get("attempts", 0) + 1
                    reminder.payload = payload
                    if payload["attempts"] >= 3:
                        reminder.status = "failed"
                
            except Exception as e:
                logger.error(f"Error firing reminder {reminder.id}: {e}")
                reminder.status = "failed"
                
        await db.commit()
        logger.info("Reminder worker cycle finished successfully.")


async def reminder_loop():
    """Run in the application lifecycle; row locks coordinate multiple replicas."""
    while True:
        try:
            await fire_due_reminders()
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception("Reminder cycle failed; will retry")
        await asyncio.sleep(60)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    asyncio.run(fire_due_reminders())
