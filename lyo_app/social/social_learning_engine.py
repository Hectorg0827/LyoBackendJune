#!/usr/bin/env python3
"""
Social Learning Engine for Lyo Platform
Advanced social learning features including peer collaboration,
study groups, knowledge sharing, and community-driven learning
"""

from typing import Dict, List, Optional, Any, Set, Tuple
from dataclasses import dataclass, field
from enum import Enum
import asyncio
import json
import hashlib
from datetime import datetime, timedelta
from collections import defaultdict
import random


class CollaborationType(Enum):
    """Types of collaborative learning activities"""
    STUDY_GROUP = "study_group"
    PEER_REVIEW = "peer_review"
    DISCUSSION = "discussion"
    PROJECT_COLLABORATION = "project_collaboration"
    MENTORSHIP = "mentorship"
    KNOWLEDGE_SHARING = "knowledge_sharing"


class LearningRole(Enum):
    """Roles in social learning contexts"""
    LEARNER = "learner"
    MENTOR = "mentor"
    FACILITATOR = "facilitator"
    PEER = "peer"
    EXPERT = "expert"


class SocialInteractionType(Enum):
    """Types of social interactions"""
    MESSAGE = "message"
    COMMENT = "comment"
    LIKE = "like"
    SHARE = "share"
    COLLABORATION = "collaboration"
    HELP_REQUEST = "help_request"
    KNOWLEDGE_CONTRIBUTION = "knowledge_contribution"


@dataclass
class LearnerProfile:
    """Social learning profile for a user"""
    user_id: str
    display_name: str
    expertise_areas: List[str] = field(default_factory=list)
    interests: List[str] = field(default_factory=list)
    learning_goals: List[str] = field(default_factory=list)
    preferred_collaboration_types: List[CollaborationType] = field(default_factory=list)
    availability_schedule: Dict[str, List[str]] = field(default_factory=dict)
    timezone: str = "UTC"
    reputation_score: int = 0
    contribution_count: int = 0
    helpfulness_rating: float = 0.0
    languages: List[str] = field(default_factory=lambda: ["en"])
    created_at: datetime = field(default_factory=datetime.utcnow)


@dataclass
class StudyGroup:
    """Collaborative study group"""
    group_id: str
    name: str
    description: str
    subject_area: str
    creator_id: str
    members: List[str] = field(default_factory=list)
    max_members: int = 10
    privacy_level: str = "public"  # public, private, invite_only
    learning_objectives: List[str] = field(default_factory=list)
    scheduled_sessions: List[Dict[str, Any]] = field(default_factory=list)
    resources: List[Dict[str, Any]] = field(default_factory=list)
    discussion_threads: List[str] = field(default_factory=list)
    activity_log: List[Dict[str, Any]] = field(default_factory=list)
    created_at: datetime = field(default_factory=datetime.utcnow)
    is_active: bool = True


@dataclass
class CollaborationSession:
    """Real-time collaboration session"""
    session_id: str
    collaboration_type: CollaborationType
    participants: List[str]
    facilitator_id: Optional[str] = None
    topic: str = ""
    content: Dict[str, Any] = field(default_factory=dict)
    shared_resources: List[Dict[str, Any]] = field(default_factory=list)
    chat_messages: List[Dict[str, Any]] = field(default_factory=list)
    collaborative_notes: str = ""
    whiteboard_data: Dict[str, Any] = field(default_factory=dict)
    screen_sharing: Dict[str, Any] = field(default_factory=dict)
    started_at: datetime = field(default_factory=datetime.utcnow)
    ended_at: Optional[datetime] = None
    is_active: bool = True


@dataclass
class KnowledgeContribution:
    """User knowledge contribution"""
    contribution_id: str
    contributor_id: str
    content_type: str  # explanation, tutorial, solution, resource
    title: str
    content: str
    subject_area: str
    tags: List[str] = field(default_factory=list)
    difficulty_level: str = "intermediate"
    upvotes: int = 0
    downvotes: int = 0
    views: int = 0
    helpful_count: int = 0
    comments: List[Dict[str, Any]] = field(default_factory=list)
    created_at: datetime = field(default_factory=datetime.utcnow)
    updated_at: datetime = field(default_factory=datetime.utcnow)


@dataclass
class PeerReviewSession:
    """Peer review session for learning materials"""
    review_id: str
    content_id: str
    author_id: str
    reviewers: List[str]
    review_criteria: List[str]
    reviews: Dict[str, Dict[str, Any]] = field(default_factory=dict)
    overall_score: Optional[float] = None
    feedback_summary: str = ""
    status: str = "pending"  # pending, in_progress, completed
    deadline: Optional[datetime] = None
    created_at: datetime = field(default_factory=datetime.utcnow)


class SocialLearningEngine:
    """Core engine for social learning features"""

    def __init__(self):
        self.learner_profiles: Dict[str, LearnerProfile] = {}
        self.study_groups: Dict[str, StudyGroup] = {}
        self.collaboration_sessions: Dict[str, CollaborationSession] = {}
        self.knowledge_contributions: Dict[str, KnowledgeContribution] = {}
        self.peer_review_sessions: Dict[str, PeerReviewSession] = {}
        self.social_interactions: List[Dict[str, Any]] = []
        self.matching_engine = LearningMatchmaker()
        self.recommendation_engine = SocialRecommendationEngine()

    async def create_learner_profile(self, user_id: str, profile_data: Dict[str, Any]) -> LearnerProfile:
        """Create or update learner's social profile"""
        profile = LearnerProfile(
            user_id=user_id,
            display_name=profile_data.get("display_name", f"User_{user_id}"),
            expertise_areas=profile_data.get("expertise_areas", []),
            interests=profile_data.get("interests", []),
            learning_goals=profile_data.get("learning_goals", []),
            preferred_collaboration_types=[
                CollaborationType(ct) for ct in profile_data.get("preferred_collaboration_types", [])
            ],
            timezone=profile_data.get("timezone", "UTC"),
            languages=profile_data.get("languages", ["en"])
        )

        self.learner_profiles[user_id] = profile
        return profile

    async def create_study_group(self, creator_id: str, group_data: Dict[str, Any]) -> StudyGroup:
        """Create a new study group"""
        group_id = self._generate_id("group")

        study_group = StudyGroup(
            group_id=group_id,
            name=group_data["name"],
            description=group_data.get("description", ""),
            subject_area=group_data["subject_area"],
            creator_id=creator_id,
            max_members=group_data.get("max_members", 10),
            privacy_level=group_data.get("privacy_level", "public"),
            learning_objectives=group_data.get("learning_objectives", [])
        )

        # Add creator as first member
        study_group.members.append(creator_id)

        self.study_groups[group_id] = study_group

        # Log group creation
        await self._log_social_interaction(creator_id, SocialInteractionType.COLLABORATION, {
            "action": "created_study_group",
            "group_id": group_id,
            "group_name": study_group.name
        })

        return study_group

    async def join_study_group(self, user_id: str, group_id: str) -> bool:
        """Join an existing study group"""
        if group_id not in self.study_groups:
            return False

        study_group = self.study_groups[group_id]

        # Check if already a member
        if user_id in study_group.members:
            return True

        # Check capacity
        if len(study_group.members) >= study_group.max_members:
            return False

        # Check privacy settings
        if study_group.privacy_level == "private":
            return False  # Would need invitation system

        # Add member
        study_group.members.append(user_id)

        # Update activity log
        study_group.activity_log.append({
            "timestamp": datetime.utcnow().isoformat(),
            "action": "member_joined",
            "user_id": user_id,
            "member_count": len(study_group.members)
        })

        # Log social interaction
        await self._log_social_interaction(user_id, SocialInteractionType.COLLABORATION, {
            "action": "joined_study_group",
            "group_id": group_id,
            "group_name": study_group.name
        })

        return True

    async def start_collaboration_session(self, initiator_id: str,
                                        collaboration_type: CollaborationType,
                                        session_data: Dict[str, Any]) -> CollaborationSession:
        """Start a real-time collaboration session"""
        session_id = self._generate_id("session")

        session = CollaborationSession(
            session_id=session_id,
            collaboration_type=collaboration_type,
            participants=[initiator_id],
            facilitator_id=session_data.get("facilitator_id", initiator_id),
            topic=session_data.get("topic", ""),
            content=session_data.get("content", {})
        )

        # Invite additional participants
        invited_participants = session_data.get("participants", [])
        for participant_id in invited_participants:
            if participant_id != initiator_id:
                session.participants.append(participant_id)

        self.collaboration_sessions[session_id] = session

        # Notify participants
        await self._notify_collaboration_start(session)

        return session

    async def contribute_knowledge(self, contributor_id: str,
                                 contribution_data: Dict[str, Any]) -> KnowledgeContribution:
        """Add a knowledge contribution to the platform"""
        contribution_id = self._generate_id("knowledge")

        contribution = KnowledgeContribution(
            contribution_id=contribution_id,
            contributor_id=contributor_id,
            content_type=contribution_data["content_type"],
            title=contribution_data["title"],
            content=contribution_data["content"],
            subject_area=contribution_data["subject_area"],
            tags=contribution_data.get("tags", []),
            difficulty_level=contribution_data.get("difficulty_level", "intermediate")
        )

        self.knowledge_contributions[contribution_id] = contribution

        # Update contributor's profile
        if contributor_id in self.learner_profiles:
            profile = self.learner_profiles[contributor_id]
            profile.contribution_count += 1
            profile.reputation_score += 5  # Base points for contribution

        # Log knowledge sharing interaction
        await self._log_social_interaction(contributor_id, SocialInteractionType.KNOWLEDGE_CONTRIBUTION, {
            "contribution_id": contribution_id,
            "title": contribution.title,
            "subject_area": contribution.subject_area
        })

        return contribution

    async def initiate_peer_review(self, content_id: str, author_id: str,
                                 review_criteria: List[str],
                                 reviewer_count: int = 3) -> PeerReviewSession:
        """Initiate a peer review session"""
        review_id = self._generate_id("review")

        # Find suitable reviewers
        reviewers = await self._find_peer_reviewers(author_id, reviewer_count)

        review_session = PeerReviewSession(
            review_id=review_id,
            content_id=content_id,
            author_id=author_id,
            reviewers=reviewers,
            review_criteria=review_criteria,
            deadline=datetime.utcnow() + timedelta(days=7)  # 1 week deadline
        )

        self.peer_review_sessions[review_id] = review_session

        # Notify reviewers
        await self._notify_peer_reviewers(review_session)

        return review_session

    async def find_learning_partners(self, user_id: str,
                                   criteria: Dict[str, Any] = None) -> List[Dict[str, Any]]:
        """Find compatible learning partners"""
        if user_id not in self.learner_profiles:
            return []

        user_profile = self.learner_profiles[user_id]
        criteria = criteria or {}

        partners = await self.matching_engine.find_learning_matches(
            user_profile, list(self.learner_profiles.values()), criteria
        )

        return partners

    async def get_social_recommendations(self, user_id: str) -> Dict[str, List[Any]]:
        """Get personalized social learning recommendations"""
        if user_id not in self.learner_profiles:
            return {}

        recommendations = await self.recommendation_engine.generate_recommendations(
            user_id, self.learner_profiles[user_id], {
                "study_groups": self.study_groups,
                "knowledge_contributions": self.knowledge_contributions,
                "collaboration_sessions": self.collaboration_sessions
            }
        )

        return recommendations

    async def _find_peer_reviewers(self, author_id: str, count: int) -> List[str]:
        """Find suitable peer reviewers for content"""
        if author_id not in self.learner_profiles:
            return []

        author_profile = self.learner_profiles[author_id]
        potential_reviewers = []

        for user_id, profile in self.learner_profiles.items():
            if user_id == author_id:
                continue

            # Check for expertise overlap
            expertise_overlap = set(profile.expertise_areas) & set(author_profile.expertise_areas)
            if expertise_overlap:
                score = len(expertise_overlap) * profile.reputation_score
                potential_reviewers.append((user_id, score))

        # Sort by score and return top candidates
        potential_reviewers.sort(key=lambda x: x[1], reverse=True)
        return [user_id for user_id, _ in potential_reviewers[:count]]

    async def _notify_collaboration_start(self, session: CollaborationSession):
        """Notify participants about collaboration session start"""
        # In real implementation, this would send notifications
        # For now, just log the action
        for participant_id in session.participants:
            await self._log_social_interaction(participant_id, SocialInteractionType.COLLABORATION, {
                "action": "collaboration_invited",
                "session_id": session.session_id,
                "topic": session.topic
            })

    async def _notify_peer_reviewers(self, review_session: PeerReviewSession):
        """Notify selected peer reviewers"""
        for reviewer_id in review_session.reviewers:
            await self._log_social_interaction(reviewer_id, SocialInteractionType.PEER_REVIEW, {
                "action": "review_requested",
                "review_id": review_session.review_id,
                "content_id": review_session.content_id
            })

    async def _log_social_interaction(self, user_id: str,
                                    interaction_type: SocialInteractionType,
                                    metadata: Dict[str, Any]):
        """Log social learning interaction"""
        interaction = {
            "timestamp": datetime.utcnow().isoformat(),
            "user_id": user_id,
            "interaction_type": interaction_type.value,
            "metadata": metadata
        }

        self.social_interactions.append(interaction)

    def _generate_id(self, prefix: str) -> str:
        """Generate unique ID for entities"""
        timestamp = str(int(datetime.utcnow().timestamp()))
        random_part = str(random.randint(1000, 9999))
        return f"{prefix}_{timestamp}_{random_part}"

    async def get_social_analytics(self, user_id: str) -> Dict[str, Any]:
        """Get social learning analytics for a user"""
        if user_id not in self.learner_profiles:
            return {}

        profile = self.learner_profiles[user_id]

        # Count user's interactions
        user_interactions = [i for i in self.social_interactions if i["user_id"] == user_id]

        # Group memberships
        group_memberships = [
            group for group in self.study_groups.values()
            if user_id in group.members
        ]

        # Collaboration sessions
        collaborations = [
            session for session in self.collaboration_sessions.values()
            if user_id in session.participants
        ]

        # Knowledge contributions
        contributions = [
            contrib for contrib in self.knowledge_contributions.values()
            if contrib.contributor_id == user_id
        ]

        return {
            "profile": {
                "reputation_score": profile.reputation_score,
                "contribution_count": profile.contribution_count,
                "helpfulness_rating": profile.helpfulness_rating
            },
            "activity": {
                "total_interactions": len(user_interactions),
                "study_groups_joined": len(group_memberships),
                "collaboration_sessions": len(collaborations),
                "knowledge_contributions": len(contributions)
            },
            "engagement": {
                "active_groups": len([g for g in group_memberships if g.is_active]),
                "recent_interactions": len([
                    i for i in user_interactions
                    if datetime.fromisoformat(i["timestamp"]) > datetime.utcnow() - timedelta(days=7)
                ])
            }
        }


class LearningMatchmaker:
    """Intelligent matchmaking for learning partners and groups"""

    async def find_learning_matches(self, user_profile: LearnerProfile,
                                  all_profiles: List[LearnerProfile],
                                  criteria: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Find compatible learning partners"""
        matches = []

        for candidate in all_profiles:
            if candidate.user_id == user_profile.user_id:
                continue

            compatibility_score = self._calculate_compatibility(user_profile, candidate)

            if compatibility_score > 0.3:  # Minimum compatibility threshold
                matches.append({
                    "user_id": candidate.user_id,
                    "display_name": candidate.display_name,
                    "compatibility_score": compatibility_score,
                    "shared_interests": list(set(user_profile.interests) & set(candidate.interests)),
                    "complementary_expertise": list(set(candidate.expertise_areas) - set(user_profile.expertise_areas)),
                    "reputation_score": candidate.reputation_score
                })

        # Sort by compatibility score
        matches.sort(key=lambda x: x["compatibility_score"], reverse=True)
        return matches[:10]  # Return top 10 matches

    def _calculate_compatibility(self, profile1: LearnerProfile, profile2: LearnerProfile) -> float:
        """Calculate compatibility score between two learners"""
        score = 0.0

        # Interest overlap
        shared_interests = set(profile1.interests) & set(profile2.interests)
        if profile1.interests and profile2.interests:
            interest_score = len(shared_interests) / max(len(profile1.interests), len(profile2.interests))
            score += interest_score * 0.3

        # Complementary expertise
        complementary_expertise = (set(profile1.expertise_areas) - set(profile2.expertise_areas)) | \
                                (set(profile2.expertise_areas) - set(profile1.expertise_areas))
        if profile1.expertise_areas and profile2.expertise_areas:
            expertise_score = len(complementary_expertise) / (len(profile1.expertise_areas) + len(profile2.expertise_areas))
            score += expertise_score * 0.25

        # Learning goal alignment
        shared_goals = set(profile1.learning_goals) & set(profile2.learning_goals)
        if profile1.learning_goals and profile2.learning_goals:
            goal_score = len(shared_goals) / max(len(profile1.learning_goals), len(profile2.learning_goals))
            score += goal_score * 0.2

        # Collaboration type compatibility
        shared_collab_types = set(profile1.preferred_collaboration_types) & set(profile2.preferred_collaboration_types)
        if profile1.preferred_collaboration_types and profile2.preferred_collaboration_types:
            collab_score = len(shared_collab_types) / max(len(profile1.preferred_collaboration_types),
                                                        len(profile2.preferred_collaboration_types))
            score += collab_score * 0.15

        # Language compatibility
        shared_languages = set(profile1.languages) & set(profile2.languages)
        if shared_languages:
            score += 0.1

        return min(score, 1.0)


class SocialRecommendationEngine:
    """Generate personalized social learning recommendations"""

    async def generate_recommendations(self, user_id: str, user_profile: LearnerProfile,
                                     platform_data: Dict[str, Any]) -> Dict[str, List[Any]]:
        """Generate comprehensive social learning recommendations"""
        recommendations = {
            "study_groups": [],
            "knowledge_contributions": [],
            "collaboration_opportunities": [],
            "learning_partners": []
        }

        # Study group recommendations
        study_groups = platform_data.get("study_groups", {})
        for group in study_groups.values():
            if user_id not in group.members and group.is_active:
                relevance_score = self._calculate_group_relevance(user_profile, group)
                if relevance_score > 0.4:
                    recommendations["study_groups"].append({
                        "group_id": group.group_id,
                        "name": group.name,
                        "subject_area": group.subject_area,
                        "member_count": len(group.members),
                        "relevance_score": relevance_score
                    })

        # Knowledge contribution recommendations
        contributions = platform_data.get("knowledge_contributions", {})
        for contrib in contributions.values():
            if contrib.contributor_id != user_id:
                relevance_score = self._calculate_content_relevance(user_profile, contrib)
                if relevance_score > 0.3:
                    recommendations["knowledge_contributions"].append({
                        "contribution_id": contrib.contribution_id,
                        "title": contrib.title,
                        "content_type": contrib.content_type,
                        "subject_area": contrib.subject_area,
                        "upvotes": contrib.upvotes,
                        "relevance_score": relevance_score
                    })

        # Sort recommendations by relevance
        for category in recommendations:
            recommendations[category].sort(key=lambda x: x.get("relevance_score", 0), reverse=True)
            recommendations[category] = recommendations[category][:5]  # Top 5 per category

        return recommendations

    def _calculate_group_relevance(self, user_profile: LearnerProfile, group: StudyGroup) -> float:
        """Calculate how relevant a study group is to a user"""
        score = 0.0

        # Subject area alignment
        if group.subject_area in user_profile.interests or group.subject_area in user_profile.expertise_areas:
            score += 0.4

        # Learning objectives overlap
        shared_objectives = set(user_profile.learning_goals) & set(group.learning_objectives)
        if user_profile.learning_goals and group.learning_objectives:
            objective_score = len(shared_objectives) / len(user_profile.learning_goals)
            score += objective_score * 0.3

        # Group size factor (prefer moderately sized groups)
        ideal_size = 6
        size_factor = 1 - abs(len(group.members) - ideal_size) / ideal_size
        score += max(0, size_factor) * 0.2

        # Activity level
        recent_activity = len([log for log in group.activity_log
                             if datetime.fromisoformat(log["timestamp"]) > datetime.utcnow() - timedelta(days=7)])
        if recent_activity > 0:
            score += 0.1

        return min(score, 1.0)

    def _calculate_content_relevance(self, user_profile: LearnerProfile,
                                   contribution: KnowledgeContribution) -> float:
        """Calculate how relevant a knowledge contribution is to a user"""
        score = 0.0

        # Subject area alignment
        if contribution.subject_area in user_profile.interests:
            score += 0.4

        # Tag overlap with interests
        tag_overlap = set(contribution.tags) & set(user_profile.interests)
        if contribution.tags and user_profile.interests:
            tag_score = len(tag_overlap) / len(user_profile.interests)
            score += tag_score * 0.3

        # Quality indicators
        if contribution.upvotes > contribution.downvotes:
            quality_score = min(contribution.upvotes / (contribution.upvotes + contribution.downvotes + 1), 0.2)
            score += quality_score

        # Helpfulness rating
        if contribution.helpful_count > 0:
            score += min(contribution.helpful_count * 0.02, 0.1)

        return min(score, 1.0)


# Global social learning engine
social_learning_engine = SocialLearningEngine()


# Convenience functions
async def create_study_group(creator_id: str, group_data: Dict[str, Any]) -> StudyGroup:
    """Create a new study group"""
    return await social_learning_engine.create_study_group(creator_id, group_data)


async def find_learning_partners(user_id: str, criteria: Dict[str, Any] = None) -> List[Dict[str, Any]]:
    """Find compatible learning partners"""
    return await social_learning_engine.find_learning_partners(user_id, criteria)


async def contribute_knowledge(contributor_id: str, contribution_data: Dict[str, Any]) -> KnowledgeContribution:
    """Add knowledge contribution"""
    return await social_learning_engine.contribute_knowledge(contributor_id, contribution_data)


if __name__ == "__main__":
    # Example usage and testing
    async def demo_social_learning():
        print("🎯 SOCIAL LEARNING ENGINE DEMONSTRATION")
        print("=" * 70)

        engine = SocialLearningEngine()

        # Create learner profiles
        print("👥 Creating learner profiles...")
        learners = [
            {
                "user_id": "alice_123",
                "display_name": "Alice Johnson",
                "expertise_areas": ["python", "data_science"],
                "interests": ["machine_learning", "statistics"],
                "learning_goals": ["deep_learning", "nlp"],
                "preferred_collaboration_types": ["study_group", "peer_review"]
            },
            {
                "user_id": "bob_456",
                "display_name": "Bob Chen",
                "expertise_areas": ["javascript", "web_development"],
                "interests": ["react", "node_js"],
                "learning_goals": ["full_stack", "cloud_deployment"],
                "preferred_collaboration_types": ["project_collaboration", "mentorship"]
            },
            {
                "user_id": "carol_789",
                "display_name": "Carol Smith",
                "expertise_areas": ["machine_learning", "statistics"],
                "interests": ["data_science", "python"],
                "learning_goals": ["ai_research", "model_optimization"],
                "preferred_collaboration_types": ["discussion", "knowledge_sharing"]
            }
        ]

        profiles = []
        for learner_data in learners:
            profile = await engine.create_learner_profile(learner_data["user_id"], learner_data)
            profiles.append(profile)
            print(f"   ✅ Created profile: {profile.display_name}")

        # Create study groups
        print("\\n📚 Creating study groups...")
        group_data = {
            "name": "Deep Learning Study Group",
            "description": "Weekly sessions on deep learning fundamentals",
            "subject_area": "machine_learning",
            "learning_objectives": ["neural_networks", "backpropagation", "cnn"],
            "max_members": 8
        }

        study_group = await engine.create_study_group("alice_123", group_data)
        print(f"   ✅ Created group: {study_group.name}")

        # Join study group
        join_success = await engine.join_study_group("carol_789", study_group.group_id)
        print(f"   ✅ Carol joined group: {join_success}")

        # Start collaboration session
        print("\\n🤝 Starting collaboration session...")
        session_data = {
            "topic": "Neural Network Fundamentals",
            "participants": ["alice_123", "carol_789"],
            "content": {"lesson_plan": "Introduction to perceptrons"}
        }

        collab_session = await engine.start_collaboration_session(
            "alice_123", CollaborationType.STUDY_GROUP, session_data
        )
        print(f"   ✅ Started session: {collab_session.topic}")

        # Knowledge contribution
        print("\\n📖 Adding knowledge contribution...")
        contrib_data = {
            "content_type": "tutorial",
            "title": "Introduction to Gradient Descent",
            "content": "Gradient descent is an optimization algorithm...",
            "subject_area": "machine_learning",
            "tags": ["optimization", "gradient_descent", "mathematics"],
            "difficulty_level": "beginner"
        }

        contribution = await engine.contribute_knowledge("alice_123", contrib_data)
        print(f"   ✅ Added contribution: {contribution.title}")

        # Find learning partners
        print("\\n🔍 Finding learning partners...")
        partners = await engine.find_learning_partners("bob_456")
        for partner in partners[:3]:
            print(f"   👥 Partner: {partner['display_name']} (score: {partner['compatibility_score']:.2f})")
            if partner['shared_interests']:
                print(f"      Shared interests: {', '.join(partner['shared_interests'])}")

        # Get recommendations
        print("\\n💡 Getting social recommendations...")
        recommendations = await engine.get_social_recommendations("bob_456")

        print("   📚 Recommended study groups:")
        for group_rec in recommendations.get("study_groups", [])[:2]:
            print(f"      • {group_rec['name']} (relevance: {group_rec['relevance_score']:.2f})")

        print("   📖 Recommended content:")
        for content_rec in recommendations.get("knowledge_contributions", [])[:2]:
            print(f"      • {content_rec['title']} (relevance: {content_rec['relevance_score']:.2f})")

        # Peer review
        print("\\n📝 Initiating peer review...")
        review_session = await engine.initiate_peer_review(
            contribution.contribution_id,
            "alice_123",
            ["accuracy", "clarity", "helpfulness"],
            reviewer_count=2
        )
        print(f"   ✅ Review session created: {review_session.review_id}")
        print(f"      Reviewers: {', '.join(review_session.reviewers)}")

        # Social analytics
        print("\\n📊 Social learning analytics...")
        analytics = await engine.get_social_analytics("alice_123")
        print(f"   👤 Alice's Social Profile:")
        print(f"      Reputation: {analytics['profile']['reputation_score']}")
        print(f"      Contributions: {analytics['profile']['contribution_count']}")
        print(f"      Study Groups: {analytics['activity']['study_groups_joined']}")
        print(f"      Collaborations: {analytics['activity']['collaboration_sessions']}")

        print(f"\\n🎉 SOCIAL LEARNING ENGINE READY")
        print("   ✅ Learner profile management")
        print("   ✅ Study group creation and management")
        print("   ✅ Real-time collaboration sessions")
        print("   ✅ Knowledge sharing platform")
        print("   ✅ Intelligent peer matching")
        print("   ✅ Peer review system")
        print("   ✅ Social analytics and insights")

    # Run demo if called directly
    asyncio.run(demo_social_learning())