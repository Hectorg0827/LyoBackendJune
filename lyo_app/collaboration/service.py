"""
Collaborative Learning Engine.

Implements the full peer-collaboration API consumed by
lyo_app/collaboration/routes.py: study groups, membership, peer interactions,
collaborative sessions, peer mentorship, peer assessment, and analytics.

All methods are async and operate on the SQLAlchemy models in
lyo_app.collaboration.models. Response objects are constructed explicitly to
match the Pydantic schemas (which include joined fields such as usernames and
computed member counts that aren't columns on the ORM models).
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta
from typing import Dict, List, Optional

from sqlalchemy import select, func, or_
from sqlalchemy.ext.asyncio import AsyncSession

from lyo_app.auth.models import User
from lyo_app.collaboration.models import (
    CollaborativeStudyGroup,
    CollaborativeGroupMembership,
    PeerInteraction,
    CollaborativeLearningSession,
    SessionParticipation,
    PeerMentorship,
    PeerAssessment,
)
from lyo_app.collaboration.schemas import (
    StudyGroupResponse,
    StudyGroupMemberResponse,
    PeerInteractionResponse,
    CollaborativeLearningSessionResponse,
    PeerMentorshipResponse,
    PeerAssessmentResponse,
    GroupRecommendationResponse,
    CollaborationAnalyticsResponse,
    CollaborationMetrics,
    LearningNetworkStats,
)

logger = logging.getLogger(__name__)

# Roles valid in the response schema (UserRole). The ORM GroupRole also has
# leader/observer which the response enum doesn't accept, so we normalize.
_SCHEMA_ROLES = {"participant", "facilitator", "admin", "mentor", "mentee"}


def _norm_role(role: Optional[str]) -> str:
    role = (role or "participant").lower()
    if role == "leader":
        return "facilitator"
    return role if role in _SCHEMA_ROLES else "participant"


class CollaborativeLearningEngine:
    """Service layer for collaborative learning features."""

    # ------------------------------------------------------------------ utils
    async def _usernames(self, db: AsyncSession, ids) -> Dict[int, str]:
        ids = {i for i in ids if i is not None}
        if not ids:
            return {}
        rows = await db.execute(select(User.id, User.username).where(User.id.in_(ids)))
        return {r[0]: r[1] for r in rows.all()}

    async def _member_count(self, db: AsyncSession, group_id: int) -> int:
        return (
            await db.execute(
                select(func.count())
                .select_from(CollaborativeGroupMembership)
                .where(
                    CollaborativeGroupMembership.group_id == group_id,
                    CollaborativeGroupMembership.is_active == True,  # noqa: E712
                )
            )
        ).scalar() or 0

    def _group_response(self, g: CollaborativeStudyGroup, member_count: int) -> StudyGroupResponse:
        return StudyGroupResponse(
            id=g.id,
            title=g.title,
            description=g.description,
            subject_area=g.subject_area,
            max_members=g.max_members or 8,
            current_member_count=member_count,
            skill_level_range=g.skill_level_range or {},
            collaboration_type=g.collaboration_type,
            target_skills=g.target_skills or [],
            learning_objectives=g.learning_objectives or [],
            study_schedule=g.study_schedule or {},
            is_active=bool(g.is_active),
            is_public=bool(g.is_public),
            requires_approval=bool(g.requires_approval),
            activity_score=g.activity_score or 0.0,
            learning_effectiveness=g.learning_effectiveness,
            member_satisfaction=g.member_satisfaction,
            created_at=g.created_at,
            created_by=g.created_by,
        )

    # ------------------------------------------------------------ study groups
    async def create_study_group(self, group_data, creator_id: int, db: AsyncSession) -> StudyGroupResponse:
        group = CollaborativeStudyGroup(
            title=group_data.title,
            description=group_data.description,
            subject_area=group_data.subject_area,
            max_members=group_data.max_members,
            skill_level_range=group_data.skill_level_range,
            collaboration_type=group_data.collaboration_type.value,
            target_skills=group_data.target_skills,
            learning_objectives=group_data.learning_objectives,
            study_schedule=group_data.study_schedule,
            matching_criteria=group_data.matching_criteria,
            interaction_rules=group_data.interaction_rules,
            assessment_method=group_data.assessment_method,
            is_public=group_data.is_public,
            requires_approval=group_data.requires_approval,
            created_by=creator_id,
        )
        db.add(group)
        await db.flush()
        # Creator becomes the first (facilitator) member.
        db.add(CollaborativeGroupMembership(
            group_id=group.id, user_id=creator_id, role="facilitator",
        ))
        await db.commit()
        await db.refresh(group)
        return self._group_response(group, await self._member_count(db, group.id))

    async def list_study_groups(self, subject_area, skill_level, is_public, limit, offset, db: AsyncSession):
        stmt = select(CollaborativeStudyGroup).where(CollaborativeStudyGroup.is_active == True)  # noqa: E712
        if is_public is not None:
            stmt = stmt.where(CollaborativeStudyGroup.is_public == is_public)
        if subject_area:
            stmt = stmt.where(CollaborativeStudyGroup.subject_area == subject_area)
        stmt = stmt.order_by(CollaborativeStudyGroup.created_at.desc()).limit(limit).offset(offset)
        groups = (await db.execute(stmt)).scalars().all()
        out = []
        for g in groups:
            out.append(self._group_response(g, await self._member_count(db, g.id)))
        return out

    async def get_study_group(self, group_id: int, db: AsyncSession) -> Optional[StudyGroupResponse]:
        g = await db.get(CollaborativeStudyGroup, group_id)
        if not g:
            return None
        return self._group_response(g, await self._member_count(db, group_id))

    async def update_study_group(self, group_id: int, group_data, user_id: int, db: AsyncSession) -> StudyGroupResponse:
        from fastapi import HTTPException
        g = await db.get(CollaborativeStudyGroup, group_id)
        if not g:
            raise HTTPException(status_code=404, detail="Study group not found")
        if g.created_by != user_id:
            raise HTTPException(status_code=403, detail="Only the group creator can update it")
        for field in ("title", "description", "max_members", "study_schedule",
                      "interaction_rules", "is_active", "requires_approval"):
            val = getattr(group_data, field, None)
            if val is not None:
                setattr(g, field, val)
        g.updated_at = datetime.utcnow()
        await db.commit()
        await db.refresh(g)
        return self._group_response(g, await self._member_count(db, group_id))

    async def join_study_group(self, group_id: int, user_id: int, db: AsyncSession) -> dict:
        from fastapi import HTTPException
        g = await db.get(CollaborativeStudyGroup, group_id)
        if not g or not g.is_active:
            raise HTTPException(status_code=404, detail="Study group not found")
        existing = (await db.execute(
            select(CollaborativeGroupMembership).where(
                CollaborativeGroupMembership.group_id == group_id,
                CollaborativeGroupMembership.user_id == user_id,
            )
        )).scalar_one_or_none()
        if existing and existing.is_active:
            raise HTTPException(status_code=400, detail="Already a member of this group")
        if await self._member_count(db, group_id) >= (g.max_members or 8):
            raise HTTPException(status_code=400, detail="Study group is full")
        if existing:  # rejoin
            existing.is_active = True
            existing.left_at = None
            existing.joined_at = datetime.utcnow()
        else:
            db.add(CollaborativeGroupMembership(group_id=group_id, user_id=user_id, role="participant"))
        await db.commit()
        return {"status": "joined", "group_id": group_id, "user_id": user_id}

    async def leave_study_group(self, group_id: int, user_id: int, db: AsyncSession) -> dict:
        from fastapi import HTTPException
        m = (await db.execute(
            select(CollaborativeGroupMembership).where(
                CollaborativeGroupMembership.group_id == group_id,
                CollaborativeGroupMembership.user_id == user_id,
                CollaborativeGroupMembership.is_active == True,  # noqa: E712
            )
        )).scalar_one_or_none()
        if not m:
            raise HTTPException(status_code=404, detail="You are not a member of this group")
        m.is_active = False
        m.left_at = datetime.utcnow()
        await db.commit()
        return {"status": "left", "group_id": group_id, "user_id": user_id}

    async def get_group_members(self, group_id: int, db: AsyncSession) -> List[StudyGroupMemberResponse]:
        members = (await db.execute(
            select(CollaborativeGroupMembership).where(
                CollaborativeGroupMembership.group_id == group_id,
                CollaborativeGroupMembership.is_active == True,  # noqa: E712
            ).order_by(CollaborativeGroupMembership.joined_at)
        )).scalars().all()
        names = await self._usernames(db, [m.user_id for m in members])
        return [
            StudyGroupMemberResponse(
                id=m.id, user_id=m.user_id,
                username=names.get(m.user_id, f"user_{m.user_id}"),
                role=_norm_role(m.role), joined_at=m.joined_at,
                participation_score=m.participation_score or 0.0,
                contributions_count=m.contributions_count or 0,
                help_provided_count=m.help_provided_count or 0,
                help_received_count=m.help_received_count or 0,
                skill_improvement=m.skill_improvement or {},
                is_active=bool(m.is_active),
            ) for m in members
        ]

    # ----------------------------------------------------- matching (heuristic)
    async def get_group_recommendations(self, user_id: int, matching_criteria, db: AsyncSession):
        subjects = matching_criteria.subject_areas or []
        stmt = select(CollaborativeStudyGroup).where(
            CollaborativeStudyGroup.is_active == True,  # noqa: E712
            CollaborativeStudyGroup.is_public == True,  # noqa: E712
        )
        if subjects:
            stmt = stmt.where(CollaborativeStudyGroup.subject_area.in_(subjects))
        groups = (await db.execute(stmt.limit(20))).scalars().all()
        recs = []
        for g in groups:
            count = await self._member_count(db, g.id)
            reasons = []
            score = 0.5
            if g.subject_area in subjects:
                score += 0.3
                reasons.append(f"Matches your interest in {g.subject_area}")
            if count < (g.max_members or 8):
                score += 0.1
                reasons.append("Has room for new members")
            recs.append(GroupRecommendationResponse(
                group_id=g.id, group_title=g.title, match_score=round(min(score, 1.0), 2),
                compatibility_reasons=reasons or ["Open collaborative group"],
                estimated_learning_benefit=round(min(score, 1.0), 2),
                member_count=count,
                activity_level=("high" if (g.activity_score or 0) > 0.6 else "moderate"),
                learning_effectiveness=g.learning_effectiveness,
            ))
        recs.sort(key=lambda r: r.match_score, reverse=True)
        return recs

    async def create_optimal_group(self, creator_id: int, matching_criteria, db: AsyncSession) -> dict:
        subject = (matching_criteria.subject_areas or ["General"])[0]
        ctype = matching_criteria.preferred_collaboration_type
        group = CollaborativeStudyGroup(
            title=f"{subject} Study Group",
            description=f"Auto-matched group for {subject}",
            subject_area=subject,
            max_members=matching_criteria.max_group_size,
            collaboration_type=(ctype.value if ctype else "study_group"),
            target_skills=matching_criteria.learning_goals,
            learning_objectives=matching_criteria.learning_goals,
            matching_criteria=matching_criteria.collaboration_preferences,
            created_by=creator_id,
        )
        db.add(group)
        await db.flush()
        db.add(CollaborativeGroupMembership(group_id=group.id, user_id=creator_id, role="facilitator"))
        await db.commit()
        await db.refresh(group)
        return {
            "status": "created",
            "group": self._group_response(group, 1).model_dump(mode="json"),
        }

    # ------------------------------------------------------ peer interactions
    def _interaction_response(self, pi, names, responses=None) -> PeerInteractionResponse:
        return PeerInteractionResponse(
            id=pi.id, initiator_id=pi.initiator_id,
            initiator_username=names.get(pi.initiator_id, f"user_{pi.initiator_id}"),
            recipient_id=pi.recipient_id,
            recipient_username=(names.get(pi.recipient_id) if pi.recipient_id else None),
            group_id=pi.group_id, interaction_type=pi.interaction_type, content=pi.content,
            context_skill_id=pi.context_skill_id, helpfulness_rating=pi.helpfulness_rating,
            accuracy_rating=pi.accuracy_rating, learning_impact=pi.learning_impact,
            response_time_minutes=pi.response_time_minutes,
            follow_up_questions=pi.follow_up_questions or 0,
            thumbs_up_count=pi.thumbs_up_count or 0, created_at=pi.created_at,
            resolved_at=pi.resolved_at, parent_interaction_id=pi.parent_interaction_id,
            responses=responses or [],
        )

    async def create_peer_interaction(self, interaction_data, initiator_id: int, db: AsyncSession) -> PeerInteractionResponse:
        pi = PeerInteraction(
            initiator_id=initiator_id,
            recipient_id=interaction_data.recipient_id,
            group_id=interaction_data.group_id,
            interaction_type=interaction_data.interaction_type.value,
            content=interaction_data.content,
            context_skill_id=interaction_data.context_skill_id,
            parent_interaction_id=interaction_data.parent_interaction_id,
        )
        db.add(pi)
        await db.commit()
        await db.refresh(pi)
        names = await self._usernames(db, [pi.initiator_id, pi.recipient_id])
        return self._interaction_response(pi, names)

    async def get_peer_interactions(self, user_id, group_id, interaction_type, skill_id, limit, offset, db: AsyncSession):
        stmt = select(PeerInteraction).where(PeerInteraction.parent_interaction_id.is_(None))
        if group_id is not None:
            stmt = stmt.where(PeerInteraction.group_id == group_id)
        else:
            stmt = stmt.where(or_(
                PeerInteraction.initiator_id == user_id,
                PeerInteraction.recipient_id == user_id,
            ))
        if interaction_type:
            stmt = stmt.where(PeerInteraction.interaction_type == interaction_type)
        if skill_id:
            stmt = stmt.where(PeerInteraction.context_skill_id == skill_id)
        stmt = stmt.order_by(PeerInteraction.created_at.desc()).limit(limit).offset(offset)
        rows = (await db.execute(stmt)).scalars().all()
        # Fetch direct responses (one level deep) for each.
        ids = [r.id for r in rows]
        resp_map: Dict[int, list] = {}
        if ids:
            children = (await db.execute(
                select(PeerInteraction).where(PeerInteraction.parent_interaction_id.in_(ids))
            )).scalars().all()
            for ch in children:
                resp_map.setdefault(ch.parent_interaction_id, []).append(ch)
        all_ids = set()
        for r in rows:
            all_ids.add(r.initiator_id); all_ids.add(r.recipient_id)
        for chs in resp_map.values():
            for ch in chs:
                all_ids.add(ch.initiator_id); all_ids.add(ch.recipient_id)
        names = await self._usernames(db, all_ids)
        return [
            self._interaction_response(
                r, names,
                [self._interaction_response(ch, names) for ch in resp_map.get(r.id, [])],
            ) for r in rows
        ]

    async def respond_to_interaction(self, interaction_id, response_content, responder_id, db: AsyncSession):
        from fastapi import HTTPException
        parent = await db.get(PeerInteraction, interaction_id)
        if not parent:
            raise HTTPException(status_code=404, detail="Interaction not found")
        elapsed = (datetime.utcnow() - parent.created_at).total_seconds() / 60.0 if parent.created_at else None
        reply = PeerInteraction(
            initiator_id=responder_id,
            recipient_id=parent.initiator_id,
            group_id=parent.group_id,
            interaction_type="answer",
            content=response_content,
            context_skill_id=parent.context_skill_id,
            parent_interaction_id=parent.id,
            response_time_minutes=elapsed,
        )
        parent.follow_up_questions = (parent.follow_up_questions or 0) + 1
        if parent.resolved_at is None:
            parent.resolved_at = datetime.utcnow()
        db.add(reply)
        await db.commit()
        await db.refresh(reply)
        names = await self._usernames(db, [reply.initiator_id, reply.recipient_id])
        return self._interaction_response(reply, names)

    async def rate_interaction(self, interaction_id, helpfulness_rating, accuracy_rating, rater_id, db: AsyncSession):
        from fastapi import HTTPException
        pi = await db.get(PeerInteraction, interaction_id)
        if not pi:
            raise HTTPException(status_code=404, detail="Interaction not found")
        pi.helpfulness_rating = helpfulness_rating
        pi.accuracy_rating = accuracy_rating
        pi.learning_impact = round((helpfulness_rating + accuracy_rating) / 2.0, 2)
        await db.commit()
        return {"status": "rated", "interaction_id": interaction_id,
                "helpfulness_rating": helpfulness_rating, "accuracy_rating": accuracy_rating}

    # --------------------------------------------------- collaborative sessions
    def _session_response(self, s, names) -> CollaborativeLearningSessionResponse:
        return CollaborativeLearningSessionResponse(
            id=s.id, group_id=s.group_id, title=s.title, description=s.description,
            session_type=s.session_type, target_skills=s.target_skills or [],
            learning_objectives=s.learning_objectives or [],
            facilitator_id=s.facilitator_id,
            facilitator_username=(names.get(s.facilitator_id) if s.facilitator_id else None),
            max_participants=s.max_participants or 20,
            scheduled_start=s.scheduled_start, scheduled_end=s.scheduled_end,
            actual_start=s.actual_start, actual_end=s.actual_end,
            agenda=s.agenda or {}, resources=s.resources or {},
            attendance_count=s.attendance_count or 0, completion_rate=s.completion_rate,
            learning_effectiveness=s.learning_effectiveness,
            participant_satisfaction=s.participant_satisfaction,
            status=s.status or "scheduled", is_recurring=bool(s.is_recurring),
            created_at=s.created_at,
        )

    async def create_learning_session(self, session_data, facilitator_id: int, db: AsyncSession):
        s = CollaborativeLearningSession(
            group_id=session_data.group_id, title=session_data.title,
            description=session_data.description, session_type=session_data.session_type.value,
            target_skills=session_data.target_skills, learning_objectives=session_data.learning_objectives,
            facilitator_id=facilitator_id, max_participants=session_data.max_participants,
            scheduled_start=session_data.scheduled_start, scheduled_end=session_data.scheduled_end,
            agenda=session_data.agenda, resources=session_data.resources,
            is_recurring=session_data.is_recurring, recurrence_pattern=session_data.recurrence_pattern,
            status="scheduled",
        )
        db.add(s)
        await db.commit()
        await db.refresh(s)
        names = await self._usernames(db, [facilitator_id])
        return self._session_response(s, names)

    async def list_learning_sessions(self, group_id, session_type, upcoming_only, limit, db: AsyncSession):
        stmt = select(CollaborativeLearningSession)
        if group_id is not None:
            stmt = stmt.where(CollaborativeLearningSession.group_id == group_id)
        if session_type:
            stmt = stmt.where(CollaborativeLearningSession.session_type == session_type)
        if upcoming_only:
            stmt = stmt.where(CollaborativeLearningSession.scheduled_start >= datetime.utcnow())
        stmt = stmt.order_by(CollaborativeLearningSession.scheduled_start).limit(limit)
        sessions = (await db.execute(stmt)).scalars().all()
        names = await self._usernames(db, [s.facilitator_id for s in sessions])
        return [self._session_response(s, names) for s in sessions]

    async def join_learning_session(self, session_id, user_id, db: AsyncSession):
        from fastapi import HTTPException
        s = await db.get(CollaborativeLearningSession, session_id)
        if not s:
            raise HTTPException(status_code=404, detail="Session not found")
        existing = (await db.execute(
            select(SessionParticipation).where(
                SessionParticipation.session_id == session_id,
                SessionParticipation.user_id == user_id,
            )
        )).scalar_one_or_none()
        if not existing:
            db.add(SessionParticipation(session_id=session_id, user_id=user_id, joined_at=datetime.utcnow()))
            s.attendance_count = (s.attendance_count or 0) + 1
            await db.commit()
        return {"status": "joined", "session_id": session_id, "user_id": user_id}

    async def start_learning_session(self, session_id, facilitator_id, db: AsyncSession):
        from fastapi import HTTPException
        s = await db.get(CollaborativeLearningSession, session_id)
        if not s:
            raise HTTPException(status_code=404, detail="Session not found")
        if s.facilitator_id and s.facilitator_id != facilitator_id:
            raise HTTPException(status_code=403, detail="Only the facilitator can start this session")
        s.status = "in_progress"
        s.actual_start = datetime.utcnow()
        await db.commit()
        return {"status": "in_progress", "session_id": session_id, "started_at": s.actual_start.isoformat()}

    async def end_learning_session(self, session_id, facilitator_id, completion_notes, db: AsyncSession):
        from fastapi import HTTPException
        s = await db.get(CollaborativeLearningSession, session_id)
        if not s:
            raise HTTPException(status_code=404, detail="Session not found")
        if s.facilitator_id and s.facilitator_id != facilitator_id:
            raise HTTPException(status_code=403, detail="Only the facilitator can end this session")
        s.status = "completed"
        s.actual_end = datetime.utcnow()
        await db.commit()
        return {"status": "completed", "session_id": session_id,
                "ended_at": s.actual_end.isoformat(), "completion_notes": completion_notes}

    # ------------------------------------------------------------- mentorship
    def _mentorship_response(self, m, names) -> PeerMentorshipResponse:
        return PeerMentorshipResponse(
            id=m.id, mentor_id=m.mentor_id,
            mentor_username=names.get(m.mentor_id, f"user_{m.mentor_id}"),
            mentee_id=m.mentee_id,
            mentee_username=names.get(m.mentee_id, f"user_{m.mentee_id}"),
            skill_focus=m.skill_focus or [], learning_goals=m.learning_goals or [],
            mentorship_plan=m.mentorship_plan or {}, matching_score=m.matching_score,
            sessions_completed=m.sessions_completed or 0,
            progress_milestones=m.progress_milestones or {},
            skill_improvement=m.skill_improvement or {},
            mentorship_effectiveness=m.mentorship_effectiveness,
            mentor_rating=m.mentor_rating, mentee_engagement=m.mentee_engagement,
            status=m.status or "pending", started_at=m.started_at,
            last_interaction=m.last_interaction, ended_at=m.ended_at,
            target_duration_weeks=m.target_duration_weeks or 8,
        )

    async def create_mentorship(self, mentorship_data, requestor_id: int, db: AsyncSession):
        m = PeerMentorship(
            mentor_id=mentorship_data.mentor_id,
            mentee_id=requestor_id,
            skill_focus=mentorship_data.skill_focus,
            learning_goals=mentorship_data.learning_goals,
            mentorship_plan=mentorship_data.mentorship_plan,
            target_duration_weeks=mentorship_data.target_duration_weeks,
            status="pending",
        )
        db.add(m)
        await db.commit()
        await db.refresh(m)
        names = await self._usernames(db, [m.mentor_id, m.mentee_id])
        return self._mentorship_response(m, names)

    async def _list_mentorships(self, column, value, status, db):
        stmt = select(PeerMentorship).where(column == value)
        if status:
            stmt = stmt.where(PeerMentorship.status == status)
        stmt = stmt.order_by(PeerMentorship.started_at.desc())
        ms = (await db.execute(stmt)).scalars().all()
        names = await self._usernames(db, [i for m in ms for i in (m.mentor_id, m.mentee_id)])
        return [self._mentorship_response(m, names) for m in ms]

    async def get_mentorships_as_mentor(self, mentor_id, status, db: AsyncSession):
        return await self._list_mentorships(PeerMentorship.mentor_id, mentor_id, status, db)

    async def get_mentorships_as_mentee(self, mentee_id, status, db: AsyncSession):
        return await self._list_mentorships(PeerMentorship.mentee_id, mentee_id, status, db)

    async def accept_mentorship(self, mentorship_id, mentor_id, db: AsyncSession):
        from fastapi import HTTPException
        m = await db.get(PeerMentorship, mentorship_id)
        if not m:
            raise HTTPException(status_code=404, detail="Mentorship not found")
        if m.mentor_id != mentor_id:
            raise HTTPException(status_code=403, detail="Only the requested mentor can accept")
        m.status = "active"
        m.last_interaction = datetime.utcnow()
        await db.commit()
        await db.refresh(m)
        names = await self._usernames(db, [m.mentor_id, m.mentee_id])
        return self._mentorship_response(m, names)

    async def complete_mentorship(self, mentorship_id, user_id, completion_notes, db: AsyncSession):
        from fastapi import HTTPException
        m = await db.get(PeerMentorship, mentorship_id)
        if not m:
            raise HTTPException(status_code=404, detail="Mentorship not found")
        if user_id not in (m.mentor_id, m.mentee_id):
            raise HTTPException(status_code=403, detail="Only participants can complete this mentorship")
        m.status = "completed"
        m.ended_at = datetime.utcnow()
        await db.commit()
        return {"status": "completed", "mentorship_id": mentorship_id, "completion_notes": completion_notes}

    # ------------------------------------------------------------ assessments
    def _assessment_response(self, a, names) -> PeerAssessmentResponse:
        sub = a.submission_data or {}
        return PeerAssessmentResponse(
            id=a.id, assessor_id=a.assessor_id,
            assessor_username=names.get(a.assessor_id, f"user_{a.assessor_id}"),
            assessee_id=a.assessed_id,
            assessee_username=names.get(a.assessed_id, f"user_{a.assessed_id}"),
            skill_id=a.skill_id,
            assessment_context=sub.get("assessment_context", ""),
            skill_demonstration=sub.get("skill_demonstration", ""),
            mastery_rating=sub.get("mastery_rating", a.overall_score or 0.0),
            confidence_rating=sub.get("confidence_rating", 0.0),
            assessment_criteria=a.criteria or {},
            feedback_text=a.strengths, suggestions=a.specific_suggestions,
            validity_score=a.assessment_quality,
            agreement_with_self_assessment=a.agreement_with_expert,
            learning_impact=sub.get("learning_impact"),
            created_at=a.created_at,
        )

    async def create_peer_assessment(self, assessment_data, assessor_id: int, db: AsyncSession):
        a = PeerAssessment(
            assessor_id=assessor_id,
            assessed_id=assessment_data.assessee_id,
            skill_id=assessment_data.skill_id,
            assessment_type="peer_review",
            submission_data={
                "assessment_context": assessment_data.assessment_context,
                "skill_demonstration": assessment_data.skill_demonstration,
                "mastery_rating": assessment_data.mastery_rating,
                "confidence_rating": assessment_data.confidence_rating,
            },
            criteria=assessment_data.assessment_criteria or {},
            scores={"mastery": assessment_data.mastery_rating,
                    "confidence": assessment_data.confidence_rating},
            overall_score=assessment_data.mastery_rating,
            strengths=assessment_data.feedback_text,
            specific_suggestions=assessment_data.suggestions,
            is_complete=True,
            submitted_at=datetime.utcnow(),
        )
        db.add(a)
        await db.commit()
        await db.refresh(a)
        names = await self._usernames(db, [a.assessor_id, a.assessed_id])
        return self._assessment_response(a, names)

    async def get_received_assessments(self, assessee_id, skill_id, limit, db: AsyncSession):
        stmt = select(PeerAssessment).where(PeerAssessment.assessed_id == assessee_id)
        if skill_id:
            stmt = stmt.where(PeerAssessment.skill_id == skill_id)
        stmt = stmt.order_by(PeerAssessment.created_at.desc()).limit(limit)
        rows = (await db.execute(stmt)).scalars().all()
        names = await self._usernames(db, [i for a in rows for i in (a.assessor_id, a.assessed_id)])
        return [self._assessment_response(a, names) for a in rows]

    async def get_given_assessments(self, assessor_id, limit, db: AsyncSession):
        rows = (await db.execute(
            select(PeerAssessment).where(PeerAssessment.assessor_id == assessor_id)
            .order_by(PeerAssessment.created_at.desc()).limit(limit)
        )).scalars().all()
        names = await self._usernames(db, [i for a in rows for i in (a.assessor_id, a.assessed_id)])
        return [self._assessment_response(a, names) for a in rows]

    # -------------------------------------------------------------- analytics
    async def get_personal_collaboration_analytics(self, user_id, timeframe_days, db: AsyncSession):
        since = datetime.utcnow() - timedelta(days=timeframe_days)

        async def _count(stmt):
            return (await db.execute(stmt)).scalar() or 0

        questions = await _count(select(func.count()).select_from(PeerInteraction).where(
            PeerInteraction.initiator_id == user_id,
            PeerInteraction.interaction_type == "question",
            PeerInteraction.created_at >= since))
        answers = await _count(select(func.count()).select_from(PeerInteraction).where(
            PeerInteraction.initiator_id == user_id,
            PeerInteraction.interaction_type == "answer",
            PeerInteraction.created_at >= since))
        total_interactions = await _count(select(func.count()).select_from(PeerInteraction).where(
            or_(PeerInteraction.initiator_id == user_id, PeerInteraction.recipient_id == user_id),
            PeerInteraction.created_at >= since))
        active_groups = await _count(select(func.count()).select_from(CollaborativeGroupMembership).where(
            CollaborativeGroupMembership.user_id == user_id,
            CollaborativeGroupMembership.is_active == True))  # noqa: E712
        mentorships = await _count(select(func.count()).select_from(PeerMentorship).where(
            or_(PeerMentorship.mentor_id == user_id, PeerMentorship.mentee_id == user_id)))
        avg_rating = (await db.execute(select(func.avg(PeerInteraction.helpfulness_rating)).where(
            PeerInteraction.initiator_id == user_id,
            PeerInteraction.helpfulness_rating.isnot(None)))).scalar() or 0.0

        metrics = CollaborationMetrics(
            total_interactions=total_interactions, questions_asked=questions,
            answers_provided=answers, help_requests_fulfilled=answers,
            peer_satisfaction_rating=round(float(avg_rating), 2),
            learning_impact_score=round(float(avg_rating) / 5.0, 2),
            knowledge_sharing_score=float(answers),
        )
        network = LearningNetworkStats(
            active_study_groups=active_groups, mentorship_relationships=mentorships,
            total_connections=active_groups + mentorships,
        )
        recs = []
        if questions > answers * 2:
            recs.append("Try answering peers' questions to reinforce your own learning.")
        if active_groups == 0:
            recs.append("Join a study group to accelerate learning through collaboration.")
        if not recs:
            recs.append("Great collaboration balance — keep it up!")
        return CollaborationAnalyticsResponse(
            user_id=user_id, timeframe_days=timeframe_days,
            collaboration_metrics=metrics, learning_network_stats=network,
            skill_improvement_through_collaboration={},
            top_collaboration_partners=[], learning_achievements=[], recommendations=recs,
        )

    async def get_group_analytics(self, group_id, user_id, timeframe_days, db: AsyncSession):
        from fastapi import HTTPException
        member = (await db.execute(select(CollaborativeGroupMembership).where(
            CollaborativeGroupMembership.group_id == group_id,
            CollaborativeGroupMembership.user_id == user_id,
            CollaborativeGroupMembership.is_active == True))).scalar_one_or_none()  # noqa: E712
        if not member:
            raise HTTPException(status_code=403, detail="Group members only")
        since = datetime.utcnow() - timedelta(days=timeframe_days)
        member_count = await self._member_count(db, group_id)
        interactions = (await db.execute(select(func.count()).select_from(PeerInteraction).where(
            PeerInteraction.group_id == group_id, PeerInteraction.created_at >= since))).scalar() or 0
        sessions = (await db.execute(select(func.count()).select_from(CollaborativeLearningSession).where(
            CollaborativeLearningSession.group_id == group_id))).scalar() or 0
        return {
            "group_id": group_id, "timeframe_days": timeframe_days,
            "member_count": member_count, "interactions": interactions,
            "sessions": sessions,
            "activity_level": "high" if interactions > member_count * 3 else "moderate",
        }

    async def get_contribution_leaderboard(self, skill_area, timeframe_days, limit, db: AsyncSession):
        since = datetime.utcnow() - timedelta(days=timeframe_days)
        stmt = select(
            PeerInteraction.initiator_id, func.count().label("contributions")
        ).where(PeerInteraction.created_at >= since)
        if skill_area:
            stmt = stmt.where(PeerInteraction.context_skill_id == skill_area)
        stmt = stmt.group_by(PeerInteraction.initiator_id).order_by(func.count().desc()).limit(limit)
        rows = (await db.execute(stmt)).all()
        names = await self._usernames(db, [r[0] for r in rows])
        return {
            "skill_area": skill_area, "timeframe_days": timeframe_days,
            "leaderboard": [
                {"rank": i + 1, "user_id": r[0],
                 "username": names.get(r[0], f"user_{r[0]}"), "contributions": r[1]}
                for i, r in enumerate(rows)
            ],
        }

    async def get_learning_network_insights(self, user_id, db: AsyncSession):
        groups = (await db.execute(select(func.count()).select_from(CollaborativeGroupMembership).where(
            CollaborativeGroupMembership.user_id == user_id,
            CollaborativeGroupMembership.is_active == True))).scalar() or 0  # noqa: E712
        # Distinct peers interacted with.
        peer_rows = (await db.execute(
            select(PeerInteraction.recipient_id).where(PeerInteraction.initiator_id == user_id).distinct()
        )).all()
        peers = {r[0] for r in peer_rows if r[0]}
        mentorships = (await db.execute(select(func.count()).select_from(PeerMentorship).where(
            or_(PeerMentorship.mentor_id == user_id, PeerMentorship.mentee_id == user_id),
            PeerMentorship.status == "active"))).scalar() or 0
        return {
            "user_id": user_id,
            "active_groups": groups,
            "unique_peers": len(peers),
            "active_mentorships": mentorships,
            "network_size": len(peers) + groups,
            "insights": [
                f"You're connected to {len(peers)} peers across {groups} groups.",
                ("Consider joining another study group to broaden your network."
                 if groups < 2 else "You have a healthy collaborative network."),
            ],
        }


# Module-level singleton (routes also instantiate their own; both are fine).
collaborative_learning_engine = CollaborativeLearningEngine()
