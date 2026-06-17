"""Teacher-in-the-loop API (instructor-gated).

  POST   /api/v1/teacher/reviews                      submit a draft for review
  GET    /api/v1/teacher/reviews?status=pending       instructor review queue
  POST   /api/v1/teacher/reviews/{id}/approve         publish to students
  POST   /api/v1/teacher/reviews/{id}/flag            hold back (quality concern)
  POST   /api/v1/teacher/reviews/{id}/request-changes needs revision
  POST   /api/v1/teacher/students/scan-at-risk        AI flags at-risk learners
  GET    /api/v1/teacher/students/alerts?status=open  intervention queue
  POST   /api/v1/teacher/students/alerts/{id}/resolve resolve/acknowledge
"""
from typing import Annotated, Optional

from fastapi import APIRouter, Body, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from lyo_app.core.database import get_db
from lyo_app.models.enhanced import User
from lyo_app.teacher.dependencies import require_instructor
from lyo_app.teacher.models import AlertStatus, ReviewStatus
from lyo_app.teacher.service import teacher_service

router = APIRouter(prefix="/api/v1/teacher", tags=["teacher-in-the-loop"])


def _review_dto(r) -> dict:
    return {
        "id": r.id, "course_id": r.course_id, "course_title": r.course_title,
        "status": r.status.value if hasattr(r.status, "value") else r.status,
        "submitted_by": r.submitted_by, "reviewer_id": r.reviewer_id,
        "notes": r.notes, "qa_score": r.qa_score,
        "qa_recommendation": r.qa_recommendation,
        "created_at": r.created_at.isoformat() if r.created_at else None,
        "reviewed_at": r.reviewed_at.isoformat() if r.reviewed_at else None,
    }


def _alert_dto(a) -> dict:
    return {
        "id": a.id, "student_id": a.student_id, "instructor_id": a.instructor_id,
        "trigger": a.trigger, "detail": a.detail, "skill_id": a.skill_id,
        "course_id": a.course_id,
        "status": a.status.value if hasattr(a.status, "value") else a.status,
        "resolution_notes": a.resolution_notes,
        "created_at": a.created_at.isoformat() if a.created_at else None,
        "resolved_at": a.resolved_at.isoformat() if a.resolved_at else None,
    }


# ----------------------------------------------------------- content review
@router.post("/reviews")
async def submit_for_review(
    instructor: Annotated[User, Depends(require_instructor)],
    db: Annotated[AsyncSession, Depends(get_db)],
    course_id: str = Body(..., embed=True),
    qa_score: Optional[int] = Body(None, embed=True),
    qa_recommendation: Optional[str] = Body(None, embed=True),
):
    review = await teacher_service.submit_for_review(
        db, course_id=course_id, submitted_by=instructor.id,
        qa_score=qa_score, qa_recommendation=qa_recommendation)
    return _review_dto(review)


@router.get("/reviews")
async def list_reviews(
    instructor: Annotated[User, Depends(require_instructor)],
    db: Annotated[AsyncSession, Depends(get_db)],
    status: Optional[ReviewStatus] = Query(None),
    limit: int = Query(50, le=200),
):
    reviews = await teacher_service.list_reviews(db, status=status, limit=limit)
    return {"reviews": [_review_dto(r) for r in reviews]}


async def _act(db, review_id, reviewer_id, action, notes):
    try:
        review = await teacher_service.act_on_review(
            db, review_id=review_id, reviewer_id=reviewer_id,
            action=action, notes=notes)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    return _review_dto(review)


@router.post("/reviews/{review_id}/approve")
async def approve_review(
    review_id: int,
    instructor: Annotated[User, Depends(require_instructor)],
    db: Annotated[AsyncSession, Depends(get_db)],
    notes: Optional[str] = Body(None, embed=True),
):
    return await _act(db, review_id, instructor.id, ReviewStatus.APPROVED, notes)


@router.post("/reviews/{review_id}/flag")
async def flag_review(
    review_id: int,
    instructor: Annotated[User, Depends(require_instructor)],
    db: Annotated[AsyncSession, Depends(get_db)],
    notes: Optional[str] = Body(None, embed=True),
):
    return await _act(db, review_id, instructor.id, ReviewStatus.FLAGGED, notes)


@router.post("/reviews/{review_id}/request-changes")
async def request_changes(
    review_id: int,
    instructor: Annotated[User, Depends(require_instructor)],
    db: Annotated[AsyncSession, Depends(get_db)],
    notes: Optional[str] = Body(None, embed=True),
):
    return await _act(db, review_id, instructor.id,
                      ReviewStatus.CHANGES_REQUESTED, notes)


# -------------------------------------------------------- student intervention
@router.post("/students/scan-at-risk")
async def scan_at_risk(
    instructor: Annotated[User, Depends(require_instructor)],
    db: Annotated[AsyncSession, Depends(get_db)],
    limit: int = Query(25, le=100),
):
    flagged = await teacher_service.scan_at_risk_students(db, limit=limit)
    return {"at_risk": flagged, "count": len(flagged)}


@router.get("/students/alerts")
async def list_alerts(
    instructor: Annotated[User, Depends(require_instructor)],
    db: Annotated[AsyncSession, Depends(get_db)],
    status: Optional[AlertStatus] = Query(None),
    limit: int = Query(50, le=200),
):
    alerts = await teacher_service.list_alerts(db, status=status, limit=limit)
    return {"alerts": [_alert_dto(a) for a in alerts]}


@router.post("/students/alerts/{alert_id}/resolve")
async def resolve_alert(
    alert_id: int,
    instructor: Annotated[User, Depends(require_instructor)],
    db: Annotated[AsyncSession, Depends(get_db)],
    status: AlertStatus = Body(AlertStatus.RESOLVED, embed=True),
    notes: Optional[str] = Body(None, embed=True),
):
    try:
        alert = await teacher_service.resolve_alert(
            db, alert_id=alert_id, instructor_id=instructor.id,
            status=status, notes=notes)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    return _alert_dto(alert)
