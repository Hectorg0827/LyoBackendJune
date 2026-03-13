
import logging
from datetime import datetime, timedelta
from typing import List, Dict, Any, Optional
import re
from uuid import uuid4

from lyo_app.services.push_notifications import push_service, PushNotification
from lyo_app.tasks.notifications import send_push_notification_task
from lyo_app.core.celery_app import celery_app

logger = logging.getLogger(__name__)

class ProactiveDispatcher:
    """
    Dispatcher for proactive engagement and study reminders.
    Handles scheduling of notifications based on Study Plans and Exam Dates.
    """
    
    def schedule_study_plan_notifications(self, user_id: int, study_plan: Dict[str, Any]):
        """
        Schedule reminders for each session in a study plan.
        """
        sessions = study_plan.get("sessions", [])
        title = study_plan.get("title", "Study Session")
        
        for session in sessions:
            session_title = session.get("title", "Study Time")
            session_date_str = session.get("date")
            
            if not session_date_str:
                continue
                
            try:
                # Parse date
                session_time = datetime.fromisoformat(session_date_str.replace('Z', '+00:00'))
                
                # Schedule reminder 10 minutes before
                reminder_time = session_time - timedelta(minutes=10)
                
                if reminder_time > datetime.now(session_time.tzinfo):
                    self.schedule_notification(
                        user_id=user_id,
                        title=f"Ready to study? 📚",
                        body=f"Your session '{session_title}' starts in 10 minutes.",
                        eta=reminder_time,
                        data={
                            "type": "study_reminder",
                            "session_title": session_title,
                            "study_plan_title": title
                        }
                    )
                    logger.info(f"Scheduled study reminder for user {user_id} at {reminder_time}")
            except Exception as e:
                logger.error(f"Failed to schedule study reminder: {e}")

    def schedule_exam_motivation(self, user_id: int, topic: str, exam_date_str: str):
        """
        Schedule a motivational message for the morning of the exam.
        """
        if not exam_date_str:
            return
            
        try:
            exam_date = datetime.fromisoformat(exam_date_str.replace('Z', '+00:00'))
            
            # Schedule for 8:00 AM on the day of the exam
            motivation_time = exam_date.replace(hour=8, minute=0, second=0)
            
            if motivation_time > datetime.now(exam_date.tzinfo):
                self.schedule_notification(
                    user_id=user_id,
                    title=f"You've got this! 🚀",
                    body=f"Today is the day for your {topic} exam. Believe in yourself and stay focused. You're ready!",
                    eta=motivation_time,
                    data={
                        "type": "exam_motivation",
                        "topic": topic
                    }
                )
                logger.info(f"Scheduled exam motivation for user {user_id} at {motivation_time}")
        except Exception as e:
            logger.error(f"Failed to schedule exam motivation: {e}")

    def schedule_notification(self, user_id: int, title: str, body: str, eta: datetime, data: Optional[Dict] = None):
        """
        Queue a delayed push notification task.
        """
        send_push_notification_task.apply_async(
            kwargs={
                "user_id": str(user_id),
                "title": title,
                "body": body,
                "data": data
            },
            eta=eta
        )

    def parse_smart_block(self, block_type: str, text: str) -> List[Dict[str, Any]]:
        """
        Extract data from :::block_type blocks in text.
        """
        pattern = rf":::{block_type}\n(.*?)\n:::"
        matches = re.findall(pattern, text, re.DOTALL)
        
        results = []
        for content in matches:
            data = {}
            # Basic YAML-like parser for simple blocks
            lines = content.strip().split('\n')
            current_list_key = None
            
            for line in lines:
                line = line.strip()
                if not line: continue
                
                if line.startswith('- ') and current_list_key:
                    # List item
                    item_val = line[2:].strip()
                    if ":" in item_val:
                        # Nested dict in list (like sessions)
                        pass # Handling this below
                    else:
                        data.setdefault(current_list_key, []).append(item_val)
                    continue

                if ':' in line:
                    key, val = line.split(':', 1)
                    key = key.strip()
                    val = val.strip()
                    
                    if not val and (line.endswith(':')):
                        # Start of a list
                        current_list_key = key
                        data[key] = []
                    else:
                        data[key] = val
                        current_list_key = None
            
            # Special handling for sessions in study_plan
            if block_type == "study_plan" and "sessions" in content:
                sessions = []
                current_session = None
                for line in lines:
                    if line.strip().startswith("- title:"):
                        if current_session: sessions.append(current_session)
                        current_session = {"title": line.split(":", 1)[1].strip()}
                    elif current_session and ":" in line:
                        k, v = line.split(":", 1)
                        current_session[k.strip().replace("- ", "")] = v.strip()
                if current_session: sessions.append(current_session)
                data["sessions"] = sessions

            results.append(data)
        return results

    def extract_and_schedule_from_text(self, user_id: int, text: str):
        """
        Scan AI response for study plans and exam dates to trigger scheduling.
        """
        # 1. Handle Study Plans
        plans = self.parse_smart_block("study_plan", text)
        for plan in plans:
            self.schedule_study_plan_notifications(user_id, plan)
            
            # Also schedule exam day motivation if exam_date is present
            if plan.get("exam_date"):
                topic = plan.get("title", "your exam").replace("Study Plan for ", "")
                self.schedule_exam_motivation(user_id, topic, plan["exam_date"])

        # 2. Handle Test Prep (Initial setup)
        preps = self.parse_smart_block("test_prep", text)
        for prep in preps:
            if prep.get("date"):
                self.schedule_exam_motivation(user_id, prep.get("topic", "Exam"), prep["date"])

proactive_dispatcher = ProactiveDispatcher()
