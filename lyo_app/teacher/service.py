"""Teacher-in-the-loop service.

Two workflows:
  1. Content review — AI drafts a course (unpublished); an instructor approves
     (publishes), flags, or requests changes.
  2. Student intervention — surface at-risk learners (reusing the plateau
     detector built for Parity F) as alerts an instructor can act on.
"""
import logging
from datetime import datetime
from typing import Any, Dict, List, Optional

from sqlalchemy import select, desc
from sqlalchemy.ext.asyncio import AsyncSession

from lyo_app.teacher.models import (
    ContentReview, ReviewStatus, StudentAlert, AlertStatus,
)

logger = logging.getLogger(__name__)


class TeacherService:
    # --------------------------------------------------------- content review
    async def submit_for_review(
        self, db: AsyncSession, *, course_id: str, submitted_by: int,
        qa_score: Optional[int] = None, qa_recommendation: Optional[str] = None,
    ) -> ContentReview:
        """Enqueue an AI-drafted course for instructor review.

        Idempotent: if an open (pending/changes_requested) review exists for the
        course it is returned instead of creating a duplicate. Looks up the
        course title and (best-effort) ensures the course starts unpublished.
        """
        existing = (await db.execute(
            select(ContentReview)
            .where(
                ContentReview.course_id == course_id,
                ContentReview.status.in_(
                    [ReviewStatus.PENDING, ReviewStatus.CHANGES_REQUESTED]),
            )
            .order_by(desc(ContentReview.created_at))
        )).scalars().first()
        if existing:
            return existing

        title = await self._course_title(db, course_id)
        # A draft must not be student-visible until approved.
        await self._set_course_published(db, course_id, False)

        review = ContentReview(
            course_id=course_id, course_title=title,
            status=ReviewStatus.PENDING, submitted_by=submitted_by,
            qa_score=qa_score, qa_recommendation=qa_recommendation,
        )
        db.add(review)
        await db.commit()
        await db.refresh(review)
        return review

    async def list_reviews(
        self, db: AsyncSession, *, status: Optional[ReviewStatus] = None,
        limit: int = 50,
    ) -> List[ContentReview]:
        stmt = select(ContentReview)
        if status is not None:
            stmt = stmt.where(ContentReview.status == status)
        stmt = stmt.order_by(desc(ContentReview.created_at)).limit(limit)
        return list((await db.execute(stmt)).scalars().all())

    async def act_on_review(
        self, db: AsyncSession, *, review_id: int, reviewer_id: int,
        action: ReviewStatus, notes: Optional[str] = None,
    ) -> ContentReview:
        """Apply an instructor decision. Approval publishes the course; flag /
        request-changes keep it unpublished."""
        review = (await db.execute(
            select(ContentReview).where(ContentReview.id == review_id)
        )).scalar_one_or_none()
        if review is None:
            raise ValueError(f"review {review_id} not found")

        review.status = action
        review.reviewer_id = reviewer_id
        review.notes = notes
        review.reviewed_at = datetime.utcnow()

        # The gate: only approval makes the course student-visible.
        await self._set_course_published(db, review.course_id,
                                          action == ReviewStatus.APPROVED)
        await db.commit()
        await db.refresh(review)
        return review

    # ------------------------------------------------------ student alerts
    async def scan_at_risk_students(
        self, db: AsyncSession, *, limit: int = 25, persist: bool = True,
    ) -> List[Dict[str, Any]]:
        """Find learners the AI flags as at-risk (plateau / performance drop) and
        optionally raise an OPEN alert for each. Reuses Parity-F detection."""
        from lyo_app.personalization.service import personalization_engine
        from lyo_app.ai_classroom.models import InteractionAttempt

        # Distinct learners with recent interaction history.
        rows = (await db.execute(
            select(InteractionAttempt.user_id)
            .order_by(desc(InteractionAttempt.created_at))
            .limit(limit * 8)
        )).scalars().all()
        seen: List[int] = []
        for uid in rows:
            try:
                iuid = int(uid)
            except (ValueError, TypeError):
                continue
            if iuid not in seen:
                seen.append(iuid)
            if len(seen) >= limit:
                break

        flagged: List[Dict[str, Any]] = []
        for uid in seen:
            try:
                plateau = await personalization_engine.detect_plateau(db, uid)
            except Exception as e:  # noqa: BLE001
                logger.warning(f"at-risk scan failed for {uid}: {e}")
                plateau = None
            if not plateau or plateau.get("trigger") == "consistent_success":
                continue
            entry = {
                "student_id": uid,
                "trigger": plateau["trigger"],
                "detail": plateau["reason"],
                "recommended_action": plateau["action"],
            }
            if persist:
                alert = await self._upsert_open_alert(
                    db, student_id=uid, trigger=plateau["trigger"],
                    detail=plateau["reason"])
                entry["alert_id"] = alert.id
            flagged.append(entry)
        if persist:
            await db.commit()
        return flagged

    async def list_alerts(
        self, db: AsyncSession, *, status: Optional[AlertStatus] = None,
        limit: int = 50,
    ) -> List[StudentAlert]:
        stmt = select(StudentAlert)
        if status is not None:
            stmt = stmt.where(StudentAlert.status == status)
        stmt = stmt.order_by(desc(StudentAlert.created_at)).limit(limit)
        return list((await db.execute(stmt)).scalars().all())

    async def resolve_alert(
        self, db: AsyncSession, *, alert_id: int, instructor_id: int,
        status: AlertStatus, notes: Optional[str] = None,
    ) -> StudentAlert:
        alert = (await db.execute(
            select(StudentAlert).where(StudentAlert.id == alert_id)
        )).scalar_one_or_none()
        if alert is None:
            raise ValueError(f"alert {alert_id} not found")
        alert.status = status
        alert.instructor_id = instructor_id
        if notes is not None:
            alert.resolution_notes = notes
        if status == AlertStatus.RESOLVED:
            alert.resolved_at = datetime.utcnow()
        await db.commit()
        await db.refresh(alert)
        return alert

    # ------------------------------------------------------------- helpers
    async def _upsert_open_alert(
        self, db: AsyncSession, *, student_id: int, trigger: str, detail: str,
    ) -> StudentAlert:
        """Avoid duplicate open alerts for the same student+trigger."""
        existing = (await db.execute(
            select(StudentAlert).where(
                StudentAlert.student_id == student_id,
                StudentAlert.trigger == trigger,
                StudentAlert.status == AlertStatus.OPEN,
            )
        )).scalars().first()
        if existing:
            existing.detail = detail
            return existing
        alert = StudentAlert(
            student_id=student_id, trigger=trigger, detail=detail,
            status=AlertStatus.OPEN)
        db.add(alert)
        await db.flush()
        return alert

    async def _course_title(self, db: AsyncSession, course_id: str) -> Optional[str]:
        try:
            from lyo_app.ai_classroom.models import GraphCourse
            course = (await db.execute(
                select(GraphCourse).where(GraphCourse.id == course_id)
            )).scalar_one_or_none()
            return course.title if course else None
        except Exception as e:  # noqa: BLE001
            logger.warning(f"course title lookup failed for {course_id}: {e}")
            return None

    async def _set_course_published(
        self, db: AsyncSession, course_id: str, published: bool,
    ) -> None:
        """Best-effort flip of GraphCourse.is_published (the student gate)."""
        try:
            from lyo_app.ai_classroom.models import GraphCourse
            course = (await db.execute(
                select(GraphCourse).where(GraphCourse.id == course_id)
            )).scalar_one_or_none()
            if course is not None:
                course.is_published = published
        except Exception as e:  # noqa: BLE001
            logger.warning(f"could not set is_published for {course_id}: {e}")


teacher_service = TeacherService()
