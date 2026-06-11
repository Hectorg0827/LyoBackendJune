"""Cron worker for processing and dispatching scheduled session reminders."""
import asyncio
import logging
from datetime import datetime
from sqlalchemy import select, and_

from lyo_app.core.database import AsyncSessionLocal
from lyo_app.study_plans.models import SessionReminder
from lyo_app.services.push_notifications import push_service, PushNotification

logger = logging.getLogger(__name__)


async def fire_due_reminders():
    """Finds all pending reminders that are due and dispatches them via APNs/FCM."""
    logger.info("⏰ Starting reminder worker cycle...")
    
    async with AsyncSessionLocal() as db:
        now = datetime.utcnow()
        stmt = select(SessionReminder).where(
            and_(SessionReminder.status == "pending", SessionReminder.fire_at <= now)
        ).limit(100)
        
        result = await db.execute(stmt)
        due_reminders = result.scalars().all()
        
        if not due_reminders:
            logger.info("No due reminders found.")
            return
            
        logger.info(f"Processing {len(due_reminders)} due reminders...")
        for reminder in due_reminders:
            try:
                title = reminder.payload.get("title", "Lyo Prep")
                body = reminder.payload.get("body", "Time for your scheduled study session!")
                deep_link = reminder.payload.get("deep_link", "")
                
                notification = PushNotification(
                    title=title,
                    message=body,
                    data={"deep_link": deep_link} if deep_link else None
                )
                
                # Send push notification
                sent_count = await push_service.send_to_user(
                    user_id=reminder.user_id,
                    notification=notification,
                    db=db
                )
                
                # If we successfully sent or skipped (e.g. mock successful send)
                reminder.status = "sent"
                reminder.sent_at = datetime.utcnow()
                
            except Exception as e:
                logger.error(f"Error firing reminder {reminder.id}: {e}")
                reminder.status = "failed"
                
        await db.commit()
        logger.info("Reminder worker cycle finished successfully.")


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    asyncio.run(fire_due_reminders())
