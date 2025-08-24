"""
Collaborative Learning Service for Phase 2
Manages peer learning, study groups, and knowledge sharing
"""

import logging
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any, Tuple
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, and_, or_
from sqlalchemy.orm import selectinload

from lyo_app.collaboration.models import (
    StudyGroup, GroupMembership, PeerInteraction, KnowledgeExchange,
    PeerAssessment, CollaborativeLearningSession, SessionParticipation,
    PeerMentorship, CollaborationAnalytics,
    CollaborationType, GroupRole, InteractionType
)
from lyo_app.personalization.service import personalization_engine

logger = logging.getLogger(__name__)


class CollaborativeLearningEngine:
    """
    Engine for managing collaborative learning experiences
    """
    
    def __init__(self):
        self.matching_algorithms = {
            "skill_based": self._skill_based_matching,
            "learning_style": self._learning_style_matching,
            "availability": self._availability_matching,
            "mixed": self._mixed_matching
        }
    
    async def create_study_group(
        self,
        creator_id: int,
        title: str,
        subject_area: str,
        collaboration_type: CollaborationType,
        target_skills: List[str],
        max_members: int,
        db: AsyncSession
    ) -> StudyGroup:
        """Create a new collaborative study group"""
        
        logger.info(f"Creating study group: {title}")
        
        try:
            # Get creator's profile for group configuration
            creator_profile = await personalization_engine.get_mastery_profile(creator_id)
            
            # Configure group based on creator's learning preferences
            group_config = await self._configure_group_settings(
                creator_profile, collaboration_type, target_skills
            )
            
            study_group = StudyGroup(
                title=title,
                description=f"Collaborative learning group for {subject_area}",
                subject_area=subject_area,
                max_members=max_members,
                collaboration_type=collaboration_type,
                target_skills=target_skills,
                learning_objectives=group_config["learning_objectives"],
                matching_criteria=group_config["matching_criteria"],
                interaction_rules=group_config["interaction_rules"],
                created_by=creator_id
            )
            
            db.add(study_group)
            await db.flush()  # Get the ID
            
            # Add creator as first member with leader role
            membership = GroupMembership(
                group_id=study_group.id,
                user_id=creator_id,
                role=GroupRole.LEADER
            )
            db.add(membership)
            
            await db.commit()
            
            logger.info(f"Study group created: ID {study_group.id}")
            return study_group
            
        except Exception as e:
            await db.rollback()
            logger.error(f"Failed to create study group: {e}")
            raise
    
    async def find_suitable_groups(
        self,
        user_id: int,
        subject_area: str,
        skill_interests: List[str],
        db: AsyncSession
    ) -> List[Dict[str, Any]]:
        """Find study groups suitable for a learner"""
        
        logger.info(f"Finding suitable groups for user {user_id}")
        
        try:
            # Get user's learning profile
            user_profile = await personalization_engine.get_mastery_profile(user_id)
            
            # Query available groups
            query = select(StudyGroup).where(
                and_(
                    StudyGroup.is_active == True,
                    StudyGroup.is_public == True,
                    StudyGroup.subject_area == subject_area
                )
            ).options(selectinload(StudyGroup.memberships))
            
            result = await db.execute(query)
            available_groups = result.scalars().all()
            
            # Score and rank groups
            group_recommendations = []
            for group in available_groups:
                if group.current_member_count >= group.max_members:
                    continue  # Skip full groups
                
                match_score = await self._calculate_group_match_score(
                    user_profile, group, skill_interests
                )
                
                if match_score > 0.5:  # Minimum match threshold
                    group_recommendations.append({
                        "group": group,
                        "match_score": match_score,
                        "reasons": self._explain_match_reasons(user_profile, group),
                        "current_members": group.current_member_count,
                        "activity_level": group.activity_score
                    })
            
            # Sort by match score
            group_recommendations.sort(key=lambda x: x["match_score"], reverse=True)
            
            logger.info(f"Found {len(group_recommendations)} suitable groups")
            return group_recommendations[:10]  # Return top 10
            
        except Exception as e:
            logger.error(f"Error finding suitable groups: {e}")
            return []
    
    async def join_study_group(
        self,
        user_id: int,
        group_id: int,
        db: AsyncSession
    ) -> GroupMembership:
        """Join a study group"""
        
        logger.info(f"User {user_id} joining group {group_id}")
        
        try:
            # Check if group exists and has space
            group = await db.get(StudyGroup, group_id)
            if not group:
                raise ValueError("Study group not found")
            
            if group.current_member_count >= group.max_members:
                raise ValueError("Study group is full")
            
            # Check if user is already a member
            existing_membership = await db.execute(
                select(GroupMembership).where(
                    and_(
                        GroupMembership.group_id == group_id,
                        GroupMembership.user_id == user_id,
                        GroupMembership.is_active == True
                    )
                )
            )
            if existing_membership.scalar_one_or_none():
                raise ValueError("User is already a member of this group")
            
            # Create membership
            membership = GroupMembership(
                group_id=group_id,
                user_id=user_id,
                role=GroupRole.PARTICIPANT
            )
            
            # Set learning goals based on group objectives
            user_profile = await personalization_engine.get_mastery_profile(user_id)
            learning_goals = await self._set_individual_learning_goals(
                user_profile, group, db
            )
            membership.learning_goals = learning_goals
            
            db.add(membership)
            await db.commit()
            
            # Update group activity score
            await self._update_group_activity_score(group_id, db)
            
            logger.info(f"User {user_id} successfully joined group {group_id}")
            return membership
            
        except Exception as e:
            await db.rollback()
            logger.error(f"Failed to join study group: {e}")
            raise
    
    async def facilitate_peer_interaction(
        self,
        initiator_id: int,
        recipient_id: int,
        interaction_type: InteractionType,
        content: str,
        skill_id: str,
        group_id: Optional[int] = None,
        db: AsyncSession = None
    ) -> PeerInteraction:
        """Facilitate peer learning interaction"""
        
        logger.info(f"Peer interaction: {initiator_id} -> {recipient_id} ({interaction_type})")
        
        try:
            interaction = PeerInteraction(
                initiator_id=initiator_id,
                recipient_id=recipient_id,
                group_id=group_id,
                interaction_type=interaction_type,
                content=content,
                context_skill_id=skill_id
            )
            
            db.add(interaction)
            await db.flush()
            
            # Update participation scores
            await self._update_participation_scores(
                initiator_id, recipient_id, interaction_type, group_id, db
            )
            
            await db.commit()
            
            # Trigger learning impact assessment
            await self._assess_interaction_impact(interaction.id, db)
            
            logger.info(f"Peer interaction recorded: ID {interaction.id}")
            return interaction
            
        except Exception as e:
            await db.rollback()
            logger.error(f"Failed to record peer interaction: {e}")
            raise
    
    async def create_peer_mentorship(
        self,
        mentor_id: int,
        mentee_id: int,
        skill_focus: List[str],
        db: AsyncSession
    ) -> PeerMentorship:
        """Create peer mentoring relationship"""
        
        logger.info(f"Creating mentorship: {mentor_id} mentoring {mentee_id}")
        
        try:
            # Get profiles to assess mentorship viability
            mentor_profile = await personalization_engine.get_mastery_profile(mentor_id)
            mentee_profile = await personalization_engine.get_mastery_profile(mentee_id)
            
            # Calculate matching score
            matching_score = await self._calculate_mentorship_match(
                mentor_profile, mentee_profile, skill_focus
            )
            
            if matching_score < 0.6:
                logger.warning(f"Low mentorship match score: {matching_score}")
            
            # Create mentorship plan
            mentorship_plan = await self._create_mentorship_plan(
                mentor_profile, mentee_profile, skill_focus
            )
            
            mentorship = PeerMentorship(
                mentor_id=mentor_id,
                mentee_id=mentee_id,
                skill_focus=skill_focus,
                matching_score=matching_score,
                mentorship_plan=mentorship_plan
            )
            
            db.add(mentorship)
            await db.commit()
            
            logger.info(f"Mentorship created: ID {mentorship.id}")
            return mentorship
            
        except Exception as e:
            await db.rollback()
            logger.error(f"Failed to create mentorship: {e}")
            raise
    
    async def schedule_collaborative_session(
        self,
        group_id: int,
        facilitator_id: int,
        title: str,
        session_type: str,
        scheduled_start: datetime,
        duration_minutes: int,
        target_skills: List[str],
        db: AsyncSession
    ) -> CollaborativeLearningSession:
        """Schedule collaborative learning session"""
        
        logger.info(f"Scheduling session: {title} for group {group_id}")
        
        try:
            scheduled_end = scheduled_start + timedelta(minutes=duration_minutes)
            
            # Generate session agenda based on skills and participants
            agenda = await self._generate_session_agenda(
                group_id, session_type, target_skills, duration_minutes, db
            )
            
            session = CollaborativeLearningSession(
                group_id=group_id,
                facilitator_id=facilitator_id,
                title=title,
                session_type=session_type,
                target_skills=target_skills,
                scheduled_start=scheduled_start,
                scheduled_end=scheduled_end,
                agenda=agenda
            )
            
            db.add(session)
            await db.commit()
            
            # Notify group members
            await self._notify_group_members(group_id, session, db)
            
            logger.info(f"Session scheduled: ID {session.id}")
            return session
            
        except Exception as e:
            await db.rollback()
            logger.error(f"Failed to schedule session: {e}")
            raise
    
    async def conduct_peer_assessment(
        self,
        assessor_id: int,
        assessed_id: int,
        skill_id: str,
        assessment_type: str,
        criteria: Dict[str, Any],
        submission_data: Dict[str, Any],
        db: AsyncSession
    ) -> PeerAssessment:
        """Conduct peer assessment"""
        
        logger.info(f"Peer assessment: {assessor_id} assessing {assessed_id}")
        
        try:
            # Generate assessment using AI if available
            assessment_scores = await self._ai_assisted_assessment(
                criteria, submission_data, skill_id
            )
            
            assessment = PeerAssessment(
                assessor_id=assessor_id,
                assessed_id=assessed_id,
                skill_id=skill_id,
                assessment_type=assessment_type,
                criteria=criteria,
                submission_data=submission_data,
                scores=assessment_scores["scores"],
                overall_score=assessment_scores["overall_score"],
                strengths=assessment_scores.get("strengths", ""),
                areas_for_improvement=assessment_scores.get("improvements", ""),
                specific_suggestions=assessment_scores.get("suggestions", "")
            )
            
            db.add(assessment)
            await db.commit()
            
            # Update mastery levels based on assessment
            await personalization_engine.update_mastery_from_assessment(
                assessed_id, skill_id, assessment_scores["overall_score"], db
            )
            
            logger.info(f"Peer assessment completed: ID {assessment.id}")
            return assessment
            
        except Exception as e:
            await db.rollback()
            logger.error(f"Failed to conduct peer assessment: {e}")
            raise
    
    async def get_collaboration_analytics(
        self,
        user_id: int,
        period_days: int = 30,
        db: AsyncSession = None
    ) -> Dict[str, Any]:
        """Get comprehensive collaboration analytics"""
        
        logger.info(f"Getting collaboration analytics for user {user_id}")
        
        try:
            end_date = datetime.utcnow()
            start_date = end_date - timedelta(days=period_days)
            
            # Query collaboration data
            analytics_data = await self._calculate_collaboration_metrics(
                user_id, start_date, end_date, db
            )
            
            # Calculate derived metrics
            analytics_data.update({
                "collaboration_efficiency": self._calculate_efficiency_score(analytics_data),
                "learning_network_position": await self._calculate_network_position(user_id, db),
                "peer_influence_score": await self._calculate_influence_score(user_id, db),
                "knowledge_sharing_impact": await self._calculate_sharing_impact(user_id, db)
            })
            
            # Store analytics record
            await self._store_analytics_record(
                user_id, start_date, end_date, analytics_data, db
            )
            
            return analytics_data
            
        except Exception as e:
            logger.error(f"Error calculating collaboration analytics: {e}")
            return {}
    
    # Helper methods
    
    async def _configure_group_settings(
        self,
        creator_profile: Any,
        collaboration_type: CollaborationType,
        target_skills: List[str]
    ) -> Dict[str, Any]:
        """Configure group settings based on creator profile"""
        
        # Base configuration
        config = {
            "learning_objectives": [
                f"Master {skill}" for skill in target_skills[:5]
            ],
            "matching_criteria": {
                "skill_level_range": [
                    max(0.0, creator_profile.overall_mastery - 0.3),
                    min(1.0, creator_profile.overall_mastery + 0.3)
                ],
                "learning_style_compatibility": True,
                "timezone_compatibility": True
            },
            "interaction_rules": {
                "respectful_communication": True,
                "constructive_feedback": True,
                "regular_participation": True,
                "knowledge_sharing": True
            }
        }
        
        # Customize based on collaboration type
        if collaboration_type == CollaborationType.STUDY_GROUP:
            config["interaction_rules"]["study_schedule_commitment"] = True
        elif collaboration_type == CollaborationType.PEER_TUTORING:
            config["matching_criteria"]["expertise_gap_required"] = True
        
        return config
    
    async def _calculate_group_match_score(
        self,
        user_profile: Any,
        group: StudyGroup,
        skill_interests: List[str]
    ) -> float:
        """Calculate how well a group matches a user"""
        
        score_components = []
        
        # Skill alignment
        skill_overlap = set(skill_interests) & set(group.target_skills or [])
        skill_score = len(skill_overlap) / max(len(skill_interests), 1)
        score_components.append(("skill_alignment", skill_score, 0.4))
        
        # Group activity level
        activity_score = min(group.activity_score or 0.0, 1.0)
        score_components.append(("activity_level", activity_score, 0.2))
        
        # Group size (not too empty, not too full)
        ideal_size = group.max_members * 0.6
        size_score = 1.0 - abs(group.current_member_count - ideal_size) / ideal_size
        score_components.append(("group_size", size_score, 0.2))
        
        # Learning effectiveness
        effectiveness = group.learning_effectiveness or 0.7
        score_components.append(("effectiveness", effectiveness, 0.2))
        
        # Calculate weighted score
        total_score = sum(score * weight for _, score, weight in score_components)
        
        return min(total_score, 1.0)
    
    async def _ai_assisted_assessment(
        self,
        criteria: Dict[str, Any],
        submission_data: Dict[str, Any],
        skill_id: str
    ) -> Dict[str, Any]:
        """Use AI to assist with peer assessment"""
        
        try:
            # Try to use AI orchestrator for assessment
            from lyo_app.ai_agents.orchestrator import ai_orchestrator, TaskComplexity, ModelType
            
            assessment_prompt = f"""
            Assess the following submission based on these criteria:
            
            Criteria: {criteria}
            Submission: {submission_data}
            Skill: {skill_id}
            
            Provide:
            1. Scores for each criterion (0.0-1.0)
            2. Overall score
            3. Key strengths
            4. Areas for improvement
            5. Specific suggestions
            
            Return as JSON with fields: scores, overall_score, strengths, improvements, suggestions
            """
            
            response = await ai_orchestrator.generate_response(
                prompt=assessment_prompt,
                task_complexity=TaskComplexity.MEDIUM,
                model_preference=ModelType.GEMINI_PRO
            )
            
            import json
            assessment_data = json.loads(response.content)
            return assessment_data
            
        except Exception as e:
            logger.warning(f"AI assessment failed, using fallback: {e}")
            # Fallback to basic assessment
            return {
                "scores": {criterion: 0.7 for criterion in criteria.keys()},
                "overall_score": 0.7,
                "strengths": "Good effort demonstrated",
                "improvements": "Continue practicing to improve mastery",
                "suggestions": "Focus on core concepts and practice regularly"
            }


# Singleton instance
collaborative_learning_engine = CollaborativeLearningEngine()
