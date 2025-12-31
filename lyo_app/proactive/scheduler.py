"""
Background scheduler for proactive interventions.

Runs periodic jobs to evaluate and deliver interventions to active users.
"""

import logging
import asyncio
from datetime import datetime, timedelta
from typing import List
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_, func

from lyo_app.core.database import AsyncSessionLocal
from lyo_app.auth.models import User
from .intervention_engine import intervention_engine
from .models import Intervention
from lyo_app.services.push_notifications import notification_service  # Assuming you have this

logger = logging.getLogger(__name__)


class ProactiveScheduler:
    """
    Scheduler for proactive intervention jobs.
    """

    def __init__(self):
        self.evaluation_interval_minutes = 5  # Run every 5 minutes
        self.daily_reset_hour = 0  # Reset counters at midnight

    async def run_intervention_evaluation(self):
        """
        Main job: Evaluate interventions for all active users.
        Runs every 5 minutes.
        """
        logger.info("Starting intervention evaluation job...")

        async with AsyncSessionLocal() as db:
            # Get active users (activity within last 24 hours)
            active_users = await self._get_active_users(db, last_activity_hours=24)

            logger.info(f"Evaluating interventions for {len(active_users)} active users")

            intervention_count = 0
            delivered_count = 0

            for user in active_users:
                try:
                    # Evaluate interventions for this user
                    interventions = await intervention_engine.evaluate_interventions(
                        user.id,
                        db
                    )

                    if interventions:
                        logger.info(
                            f"User {user.id}: {len(interventions)} interventions"
                        )
                        intervention_count += len(interventions)

                        # Deliver interventions
                        for intervention in interventions:
                            delivered = await self._deliver_intervention(
                                user,
                                intervention,
                                db
                            )
                            if delivered:
                                delivered_count += 1

                except Exception as e:
                    logger.error(
                        f"Intervention evaluation failed for user {user.id}: {e}"
                    )

        logger.info(
            f"Intervention evaluation complete: "
            f"{intervention_count} identified, {delivered_count} delivered"
        )

    async def _get_active_users(
        self,
        db: AsyncSession,
        last_activity_hours: int = 24
    ) -> List[User]:
        """
        Get users who were active within the specified time window.
        """
        # This is a simplified version - you might track last_activity in User model
        # or query from another table like LearnerState

        from lyo_app.personalization.models import LearnerState

        since_time = datetime.utcnow() - timedelta(hours=last_activity_hours)

        # Get user IDs with recent activity
        stmt = select(LearnerState.user_id).where(
            LearnerState.updated_at >= since_time
        ).distinct()

        result = await db.execute(stmt)
        user_ids = [row[0] for row in result.all()]

        if not user_ids:
            return []

        # Get User objects
        stmt = select(User).where(User.id.in_(user_ids))
        result = await db.execute(stmt)
        users = result.scalars().all()

        return list(users)

    async def _deliver_intervention(
        self,
        user: User,
        intervention: Intervention,
        db: AsyncSession
    ) -> bool:
        """
        Deliver an intervention to a user via push notification or in-app.
        """
        try:
            # Log the intervention
            organization_id = user.organization_id if hasattr(user, 'organization_id') else None
            log = await intervention_engine.log_intervention(
                user.id,
                intervention,
                db,
                organization_id
            )

            # Mark as delivered
            log.delivered_at = datetime.utcnow()
            await db.commit()

            # Send push notification if available
            # This depends on your push notification implementation
            try:
                # Example using a hypothetical notification service
                # await notification_service.send_notification(
                #     user_id=user.id,
                #     title=intervention.title,
                #     message=intervention.message,
                #     data={
                #         'action': intervention.action,
                #         'intervention_log_id': log.id
                #     }
                # )
                logger.info(
                    f"Delivered intervention to user {user.id}: {intervention.title}"
                )
            except Exception as e:
                logger.warning(f"Failed to send push notification: {e}")
                # Still count as delivered (will show in-app)

            return True

        except Exception as e:
            logger.error(f"Failed to deliver intervention to user {user.id}: {e}")
            return False

    async def run_daily_reset(self):
        """
        Reset daily counters at midnight.
        Resets inline help counts and prepares for new day.
        """
        logger.info("Running daily reset job...")

        async with AsyncSessionLocal() as db:
            try:
                # Reset ambient presence counters
                from lyo_app.ambient.presence_manager import presence_manager
                await presence_manager.reset_daily_counters(db)

                logger.info("Daily reset complete")

            except Exception as e:
                logger.error(f"Daily reset failed: {e}")

    async def start(self):
        """
        Start the scheduler (runs in background).
        """
        logger.info("Starting proactive intervention scheduler...")

        # Run both jobs concurrently
        await asyncio.gather(
            self._run_periodic_job(
                self.run_intervention_evaluation,
                interval_minutes=self.evaluation_interval_minutes
            ),
            self._run_daily_job(
                self.run_daily_reset,
                hour=self.daily_reset_hour
            )
        )

    async def _run_periodic_job(self, job_func, interval_minutes: int):
        """
        Run a job periodically at specified interval.
        """
        while True:
            try:
                await job_func()
            except Exception as e:
                logger.error(f"Periodic job error: {e}")

            # Wait for next interval
            await asyncio.sleep(interval_minutes * 60)

    async def _run_daily_job(self, job_func, hour: int = 0):
        """
        Run a job once per day at specified hour (UTC).
        """
        while True:
            try:
                # Calculate time until next run
                now = datetime.utcnow()
                next_run = now.replace(hour=hour, minute=0, second=0, microsecond=0)

                if next_run <= now:
                    # If time has passed today, schedule for tomorrow
                    next_run += timedelta(days=1)

                wait_seconds = (next_run - now).total_seconds()
                logger.info(f"Daily job scheduled for {next_run} (in {wait_seconds/3600:.1f} hours)")

                await asyncio.sleep(wait_seconds)

                # Run the job
                await job_func()

            except Exception as e:
                logger.error(f"Daily job error: {e}")
                # Wait 1 hour before retrying
                await asyncio.sleep(3600)


# Global singleton instance
proactive_scheduler = ProactiveScheduler()


# Convenience function to start scheduler
async def start_proactive_scheduler():
    """
    Start the proactive scheduler in background.
    Call this from your main application startup.
    """
    await proactive_scheduler.start()
