"""
Collaborative Learning Models for Phase 2
Social learning features and peer collaboration
"""

from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any
from enum import Enum
from sqlalchemy import Column, Integer, String, Float, DateTime, Boolean, Text, JSON, ForeignKey
from sqlalchemy.orm import relationship
from sqlalchemy.ext.hybrid import hybrid_property

from lyo_app.core.database import Base


class CollaborationType(str, Enum):
    """Types of collaborative learning"""
    STUDY_GROUP = "study_group"
    PEER_TUTORING = "peer_tutoring"
    PROJECT_TEAM = "project_team"
    DISCUSSION_FORUM = "discussion_forum"
    PEER_REVIEW = "peer_review"
    KNOWLEDGE_SHARING = "knowledge_sharing"


class GroupRole(str, Enum):
    """Roles within collaborative groups"""
    LEADER = "leader"
    FACILITATOR = "facilitator"
    PARTICIPANT = "participant"
    MENTOR = "mentor"
    MENTEE = "mentee"
    OBSERVER = "observer"


class InteractionType(str, Enum):
    """Types of peer interactions"""
    QUESTION = "question"
    ANSWER = "answer"
    EXPLANATION = "explanation"
    FEEDBACK = "feedback"
    ENCOURAGEMENT = "encouragement"
    COLLABORATION = "collaboration"
    PEER_ASSESSMENT = "peer_assessment"


class CollaborativeStudyGroup(Base):
    """Collaborative study groups"""
    __tablename__ = "collaborative_study_groups"
    
    id = Column(Integer, primary_key=True, index=True)
    
    # Group metadata
    title = Column(String, nullable=False)
    description = Column(Text)
    subject_area = Column(String, nullable=False, index=True)
    
    # Group configuration
    max_members = Column(Integer, default=8)
    skill_level_range = Column(JSON)  # Min/max skill levels
    collaboration_type = Column(String, nullable=False)  # CollaborationType enum
    
    # Learning focus
    target_skills = Column(JSON)  # List of skill IDs
    learning_objectives = Column(JSON)
    study_schedule = Column(JSON)  # Meeting times and frequency
    
    # Group dynamics
    matching_criteria = Column(JSON)  # Criteria for member matching
    interaction_rules = Column(JSON)  # Group interaction guidelines
    assessment_method = Column(String, default="peer_feedback")
    
    # Status and settings
    is_active = Column(Boolean, default=True, index=True)
    is_public = Column(Boolean, default=True)  # Can others discover and join?
    requires_approval = Column(Boolean, default=False)
    
    # Group metrics
    activity_score = Column(Float, default=0.0)  # How active the group is
    learning_effectiveness = Column(Float)  # Learning outcomes
    member_satisfaction = Column(Float)  # Average satisfaction score
    retention_rate = Column(Float)  # Member retention
    
    # Timestamps
    created_at = Column(DateTime, default=datetime.utcnow, index=True)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Creator
    created_by = Column(Integer, ForeignKey("users.id"), nullable=False)
    
    @hybrid_property
    def current_member_count(self) -> int:
        """Count current active members"""
        return len([m for m in self.memberships if m.is_active])


class CollaborativeGroupMembership(Base):
    """Membership in collaborative study groups (renamed from GroupMembership to avoid conflict)"""
    __tablename__ = "collaborative_group_memberships"
    
    id = Column(Integer, primary_key=True, index=True)
    
    # References
    group_id = Column(Integer, ForeignKey("collaborative_study_groups.id"), nullable=False, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    
    # Membership details
    role = Column(String, default=GroupRole.PARTICIPANT)  # GroupRole enum
    joined_at = Column(DateTime, default=datetime.utcnow, index=True)
    
    # Participation metrics
    participation_score = Column(Float, default=0.0)
    contributions_count = Column(Integer, default=0)
    help_provided_count = Column(Integer, default=0)
    help_received_count = Column(Integer, default=0)
    
    # Learning progress
    skill_improvement = Column(JSON)  # Skill improvements since joining
    learning_goals = Column(JSON)  # Personal goals within the group
    
    # Status
    is_active = Column(Boolean, default=True, index=True)
    left_at = Column(DateTime)
    
    # Feedback and ratings
    satisfaction_rating = Column(Float)  # Member's satisfaction with group
    peer_ratings = Column(JSON)  # Ratings from other members


class PeerInteraction(Base):
    """Individual peer learning interactions"""
    __tablename__ = "peer_interactions"
    
    id = Column(Integer, primary_key=True, index=True)
    
    # Participants
    initiator_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    recipient_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    group_id = Column(Integer, ForeignKey("collaborative_study_groups.id"), index=True)
    
    # Interaction details
    interaction_type = Column(String, nullable=False)  # InteractionType enum
    content = Column(Text, nullable=False)
    context_skill_id = Column(String, index=True)  # Skill being discussed
    
    # Quality and impact
    helpfulness_rating = Column(Float)  # How helpful was this interaction
    accuracy_rating = Column(Float)  # How accurate was the information
    learning_impact = Column(Float)  # Impact on recipient's learning
    
    # Engagement metrics
    response_time_minutes = Column(Float)  # How quickly was this responded to
    follow_up_questions = Column(Integer, default=0)
    thumbs_up_count = Column(Integer, default=0)
    
    # Timestamps
    created_at = Column(DateTime, default=datetime.utcnow, index=True)
    resolved_at = Column(DateTime)  # When question was resolved
    
    # Self-referential relationship - commented out due to configuration issue
    # follow_up_interactions = relationship("PeerInteraction", 
    #                                     primaryjoin="PeerInteraction.id==PeerInteraction.parent_interaction_id",
    #                                     backref="parent_interaction",
    #                                     remote_side="PeerInteraction.id")
    parent_interaction_id = Column(Integer, ForeignKey("peer_interactions.id"))


class KnowledgeExchange(Base):
    """Track knowledge sharing between peers"""
    __tablename__ = "knowledge_exchanges"
    
    id = Column(Integer, primary_key=True, index=True)
    
    # Exchange details
    teacher_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    learner_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    skill_id = Column(String, nullable=False, index=True)
    
    # Content
    topic = Column(String, nullable=False)
    explanation = Column(Text)
    resources_shared = Column(JSON)  # Links, documents, etc.
    
    # Effectiveness
    understanding_before = Column(Float)  # Learner's understanding before
    understanding_after = Column(Float)  # Learner's understanding after
    teaching_quality = Column(Float)  # Quality of teaching/explanation
    
    # Context
    exchange_medium = Column(String)  # chat, video, voice, document
    duration_minutes = Column(Float)
    group_context = Column(Integer, ForeignKey("collaborative_study_groups.id"))
    
    # Outcomes
    follow_up_needed = Column(Boolean, default=False)
    mastery_improvement = Column(Float)  # Measured improvement
    
    # Timestamps
    created_at = Column(DateTime, default=datetime.utcnow, index=True)
    completed_at = Column(DateTime)


class PeerAssessment(Base):
    """Peer assessment and feedback"""
    __tablename__ = "peer_assessments"
    
    id = Column(Integer, primary_key=True, index=True)
    
    # Assessment context
    assessor_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    assessed_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    group_id = Column(Integer, ForeignKey("collaborative_study_groups.id"), index=True)
    
    # What's being assessed
    skill_id = Column(String, nullable=False, index=True)
    assessment_type = Column(String, nullable=False)  # work_review, skill_demo, presentation
    submission_data = Column(JSON)  # What was submitted for assessment
    
    # Assessment criteria and scores
    criteria = Column(JSON, nullable=False)  # Assessment rubric
    scores = Column(JSON, nullable=False)  # Scores for each criterion
    overall_score = Column(Float, nullable=False)
    
    # Feedback
    strengths = Column(Text)
    areas_for_improvement = Column(Text)
    specific_suggestions = Column(Text)
    
    # Quality control
    assessment_quality = Column(Float)  # How good was this assessment
    agreement_with_expert = Column(Float)  # If expert also assessed
    
    # Status
    is_complete = Column(Boolean, default=False)
    requires_revision = Column(Boolean, default=False)
    
    # Timestamps
    created_at = Column(DateTime, default=datetime.utcnow, index=True)
    submitted_at = Column(DateTime)
    reviewed_at = Column(DateTime)


class CollaborativeLearningSession(Base):
    """Group learning sessions and activities"""
    __tablename__ = "collaborative_learning_sessions"
    
    id = Column(Integer, primary_key=True, index=True)
    
    # Session metadata
    group_id = Column(Integer, ForeignKey("collaborative_study_groups.id"), nullable=False, index=True)
    title = Column(String, nullable=False)
    description = Column(Text)
    
    # Session configuration
    session_type = Column(String, nullable=False)  # study_session, workshop, review, project
    target_skills = Column(JSON)  # Skills being worked on
    learning_objectives = Column(JSON)
    
    # Participants
    facilitator_id = Column(Integer, ForeignKey("users.id"), index=True)
    max_participants = Column(Integer, default=20)
    
    # Timing
    scheduled_start = Column(DateTime, nullable=False, index=True)
    scheduled_end = Column(DateTime, nullable=False)
    actual_start = Column(DateTime)
    actual_end = Column(DateTime)
    
    # Session structure
    agenda = Column(JSON)  # Session agenda and activities
    resources = Column(JSON)  # Materials needed for session
    
    # Outcomes
    attendance_count = Column(Integer, default=0)
    completion_rate = Column(Float)  # How much of agenda was completed
    learning_effectiveness = Column(Float)  # Overall learning outcomes
    participant_satisfaction = Column(Float)  # Average satisfaction
    
    # Status
    status = Column(String, default="scheduled")  # scheduled, in_progress, completed, cancelled
    is_recurring = Column(Boolean, default=False)
    recurrence_pattern = Column(JSON)  # If recurring, pattern details
    
    # Timestamps
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class SessionParticipation(Base):
    """Individual participation in collaborative sessions"""
    __tablename__ = "session_participations"
    
    id = Column(Integer, primary_key=True, index=True)
    
    # References
    session_id = Column(Integer, ForeignKey("collaborative_learning_sessions.id"), 
                       nullable=False, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    
    # Participation details
    joined_at = Column(DateTime)
    left_at = Column(DateTime)
    total_duration_minutes = Column(Float)
    
    # Engagement metrics
    messages_sent = Column(Integer, default=0)
    questions_asked = Column(Integer, default=0)
    answers_provided = Column(Integer, default=0)
    contributions_count = Column(Integer, default=0)
    
    # Learning outcomes
    pre_session_confidence = Column(Float)  # Confidence before session
    post_session_confidence = Column(Float)  # Confidence after session
    skill_demonstrations = Column(JSON)  # Skills demonstrated during session
    
    # Feedback
    session_rating = Column(Float)  # Rating of the session
    peer_interaction_rating = Column(Float)  # Quality of peer interactions
    learning_objectives_met = Column(JSON)  # Which objectives were achieved
    
    # Timestamps
    created_at = Column(DateTime, default=datetime.utcnow, index=True)


class PeerMentorship(Base):
    """Peer mentoring relationships"""
    __tablename__ = "peer_mentorships"
    
    id = Column(Integer, primary_key=True, index=True)
    
    # Mentorship relationship
    mentor_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    mentee_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    
    # Focus areas
    skill_focus = Column(JSON, nullable=False)  # Skills being mentored
    learning_goals = Column(JSON)  # Mentee's goals
    mentorship_plan = Column(JSON)  # Structured plan
    
    # Matching details
    matching_score = Column(Float)  # How well matched they are
    matching_criteria = Column(JSON)  # Criteria used for matching
    
    # Progress tracking
    sessions_completed = Column(Integer, default=0)
    progress_milestones = Column(JSON)  # Milestones and achievements
    skill_improvement = Column(JSON)  # Measured improvements
    
    # Relationship quality
    mentorship_effectiveness = Column(Float)  # Overall effectiveness
    mentor_rating = Column(Float)  # Mentee's rating of mentor
    mentee_engagement = Column(Float)  # Mentor's rating of mentee engagement
    
    # Status
    status = Column(String, default="active")  # active, paused, completed, terminated
    
    # Timestamps
    started_at = Column(DateTime, default=datetime.utcnow, index=True)
    last_interaction = Column(DateTime)
    ended_at = Column(DateTime)
    
    # Target duration
    target_duration_weeks = Column(Integer, default=8)


class CollaborationAnalytics(Base):
    """Analytics for collaborative learning effectiveness"""
    __tablename__ = "collaboration_analytics"
    
    id = Column(Integer, primary_key=True, index=True)
    
    # Scope
    user_id = Column(Integer, ForeignKey("users.id"), index=True)  # Individual analytics
    group_id = Column(Integer, ForeignKey("collaborative_study_groups.id"), index=True)  # Group analytics
    
    # Time period
    period_start = Column(DateTime, nullable=False, index=True)
    period_end = Column(DateTime, nullable=False, index=True)
    
    # Participation metrics
    sessions_attended = Column(Integer, default=0)
    total_interaction_time = Column(Float, default=0.0)  # Hours
    peer_interactions_count = Column(Integer, default=0)
    
    # Contribution metrics
    questions_asked = Column(Integer, default=0)
    answers_provided = Column(Integer, default=0)
    resources_shared = Column(Integer, default=0)
    peer_assessments_given = Column(Integer, default=0)
    
    # Learning outcomes
    skill_improvements = Column(JSON)  # Skills improved through collaboration
    collaborative_learning_gain = Column(Float)  # Learning attributed to collaboration
    knowledge_sharing_impact = Column(Float)  # Impact of sharing knowledge
    
    # Social learning metrics
    network_centrality = Column(Float)  # Position in learning network
    influence_score = Column(Float)  # How much they influence others' learning
    learning_from_peers_score = Column(Float)  # How much they learn from others
    
    # Quality metrics
    average_peer_rating = Column(Float)  # Average rating from peers
    helpfulness_score = Column(Float)  # How helpful they are to others
    collaboration_effectiveness = Column(Float)  # Overall collaboration effectiveness
    
    # Timestamps
    calculated_at = Column(DateTime, default=datetime.utcnow, index=True)
    
    @hybrid_property
    def collaboration_efficiency(self) -> float:
        """Calculate collaboration efficiency ratio"""
        if self.total_interaction_time == 0:
            return 0.0
        return self.collaborative_learning_gain / self.total_interaction_time
