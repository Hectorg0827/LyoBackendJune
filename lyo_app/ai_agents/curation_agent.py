"""
Content Curation Agent - AI-driven Educational Content Curation

This agent provides intelligent content curation capabilities:
- Educational resource discovery and evaluation
- Content quality assessment
- Learning material organization and tagging
- Personalized content recommendations
- Gap analysis in educational material
- Content refresh and update suggestions
"""

import asyncio
import logging
import time
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any, Tuple, Set
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_, desc, func, or_, not_
from sqlalchemy.orm import selectinload
import json
import re

from .models import AIConversationLog, AIModelTypeEnum, UserEngagementState
from .orchestrator import ai_orchestrator, ModelType, TaskComplexity
from lyo_app.learning.models import Course, Lesson, DifficultyLevel, ContentType
from lyo_app.learning.models import CourseEnrollment, LessonCompletion
from lyo_app.models.enhanced import User
from lyo_app.feeds.models import Post, Comment, FeedItem

logger = logging.getLogger(__name__)


class ContentRating:
    """Content quality rating scale."""
    EXCELLENT = 5
    GOOD = 4
    AVERAGE = 3
    BELOW_AVERAGE = 2
    POOR = 1


class ContentCurationAgent:
    """
    AI agent for intelligent educational content curation.
    """
    
    def __init__(self):
        self.content_cache = {}
        self.source_reliability_scores = {}
        self.content_evaluation_criteria = {
            "accuracy": 0.25,
            "completeness": 0.2,
            "clarity": 0.2,
            "engagement": 0.15,
            "relevance": 0.2
        }
    
    async def evaluate_content_quality(
        self, 
        content_text: str,
        content_type: str,
        topic: str,
        target_audience: Optional[str] = None,
        difficulty_level: Optional[DifficultyLevel] = None,
        db: AsyncSession = None
    ) -> Dict[str, Any]:
        """
        Evaluate the quality of educational content.
        
        Args:
            content_text: The content to evaluate
            content_type: Type of content (article, video transcript, etc.)
            topic: The educational topic of the content
            target_audience: Target audience description
            difficulty_level: Content difficulty level
            db: Database session
            
        Returns:
            Dictionary containing quality evaluation results
        """
        start_time = time.time()
        logger.info(f"Evaluating {content_type} content on topic: {topic}")
        
        try:
            # 1. Prepare context for evaluation
            context = {
                "content_text": content_text[:5000],  # Limit size for performance
                "content_type": content_type,
                "topic": topic,
                "target_audience": target_audience,
                "difficulty_level": difficulty_level.value if difficulty_level else None,
                "evaluation_criteria": self.content_evaluation_criteria
            }
            
            # 2. Generate evaluation using AI orchestrator
            prompt = self._build_content_evaluation_prompt(context)
            
            ai_response = await ai_orchestrator.generate_response(
                prompt=prompt,
                task_complexity=TaskComplexity.MEDIUM,
                model_preference=ModelType.HYBRID,
                max_tokens=1000
            )
            
            # 3. Parse evaluation results
            evaluation_results = self._parse_content_evaluation(ai_response.content)
            
            # 4. Log the AI conversation
            await self._log_ai_conversation(
                user_id=None,  # Content evaluation is not user-specific
                context=context,
                ai_response=ai_response,
                result=evaluation_results,
                db=db
            )
            
            # 5. Return structured evaluation results
            processing_time = time.time() - start_time
            logger.info(f"Content evaluation completed in {processing_time:.2f}s")
            
            return {
                "topic": topic,
                "content_type": content_type,
                "evaluation": evaluation_results,
                "overall_score": evaluation_results.get("overall_score", 0),
                "processing_time_ms": processing_time * 1000,
                "model_used": ai_response.model_used.value,
                "timestamp": datetime.utcnow().isoformat()
            }
            
        except Exception as e:
            logger.error(f"Error evaluating content quality: {e}")
            return {
                "error": f"Failed to evaluate content: {str(e)}",
                "topic": topic,
                "content_type": content_type,
                "timestamp": datetime.utcnow().isoformat()
            }

    async def recommend_content(
        self,
        user_id: int,
        topic: str,
        content_count: int = 5,
        existing_content_ids: Optional[List[int]] = None,
        db: AsyncSession = None
    ) -> Dict[str, Any]:
        """
        Recommend educational content for a user based on their profile and interests.
        
        Args:
            user_id: User ID to personalize recommendations for
            topic: Content topic to focus on
            content_count: Number of content items to recommend
            existing_content_ids: IDs of content items to exclude
            db: Database session
            
        Returns:
            Dictionary containing recommended content items
        """
        start_time = time.time()
        logger.info(f"Finding content recommendations for user {user_id} on topic: {topic}")
        
        try:
            # 1. Get user data for personalization
            user_data = await self._get_user_data(user_id, db)
            if not user_data:
                return {"error": f"User with ID {user_id} not found"}
                
            # 2. Find relevant content in the database
            content_items = await self._find_relevant_content(
                topic=topic,
                user_data=user_data,
                content_count=content_count,
                existing_content_ids=existing_content_ids or [],
                db=db
            )
            
            # 3. If insufficient content found, generate additional recommendations
            if len(content_items) < content_count:
                additional_items = await self._generate_content_recommendations(
                    topic=topic,
                    user_data=user_data,
                    count_needed=content_count - len(content_items),
                    db=db
                )
                content_items.extend(additional_items)
            
            # 4. Sort and rank the recommendations
            ranked_items = await self._rank_recommendations(
                content_items=content_items,
                user_data=user_data,
                db=db
            )
            
            # 5. Return the recommendations
            processing_time = time.time() - start_time
            logger.info(f"Content recommendations generated in {processing_time:.2f}s")
            
            return {
                "user_id": user_id,
                "topic": topic,
                "recommendations": ranked_items[:content_count],
                "processing_time_ms": processing_time * 1000,
                "timestamp": datetime.utcnow().isoformat()
            }
            
        except Exception as e:
            logger.error(f"Error generating content recommendations: {e}")
            return {
                "error": f"Failed to generate recommendations: {str(e)}",
                "user_id": user_id,
                "topic": topic,
                "timestamp": datetime.utcnow().isoformat()
            }

    async def identify_content_gaps(
        self,
        course_id: int,
        db: AsyncSession = None
    ) -> Dict[str, Any]:
        """
        Analyze a course to identify content gaps that should be filled.
        
        Args:
            course_id: ID of the course to analyze
            db: Database session
            
        Returns:
            Dictionary containing identified content gaps
        """
        start_time = time.time()
        logger.info(f"Analyzing course {course_id} for content gaps")
        
        try:
            # 1. Get course data with lessons
            course = await self._get_course_with_lessons(course_id, db)
            if not course:
                return {"error": f"Course with ID {course_id} not found"}
            
            # 2. Prepare course data for analysis
            course_data = {
                "id": course.id,
                "title": course.title,
                "description": course.description,
                "difficulty_level": course.difficulty_level,
                "lessons": []
            }
            
            for lesson in course.lessons:
                course_data["lessons"].append({
                    "id": lesson.id,
                    "title": lesson.title,
                    "description": lesson.description,
                    "content_type": lesson.content_type
                })
                
            # 3. Generate gap analysis using AI orchestrator
            prompt = self._build_gap_analysis_prompt(course_data)
            
            ai_response = await ai_orchestrator.generate_response(
                prompt=prompt,
                task_complexity=TaskComplexity.COMPLEX,
                model_preference=ModelType.GEMMA_4_CLOUD,
                max_tokens=2000
            )
            
            # 4. Parse gap analysis results
            gap_analysis = self._parse_gap_analysis(ai_response.content)
            
            # 5. Log the AI conversation
            await self._log_ai_conversation(
                user_id=None,  # Course gap analysis is not user-specific
                context=course_data,
                ai_response=ai_response,
                result=gap_analysis,
                db=db
            )
            
            # 6. Return structured gap analysis
            processing_time = time.time() - start_time
            logger.info(f"Content gap analysis completed in {processing_time:.2f}s")
            
            return {
                "course_id": course_id,
                "course_title": course.title,
                "gap_analysis": gap_analysis,
                "processing_time_ms": processing_time * 1000,
                "model_used": ai_response.model_used.value,
                "timestamp": datetime.utcnow().isoformat()
            }
            
        except Exception as e:
            logger.error(f"Error analyzing content gaps: {e}")
            return {
                "error": f"Failed to analyze content gaps: {str(e)}",
                "course_id": course_id,
                "timestamp": datetime.utcnow().isoformat()
            }

    async def suggest_content_updates(
        self,
        content_id: int,
        content_type: str,
        content_text: str,
        last_updated: datetime,
        db: AsyncSession = None
    ) -> Dict[str, Any]:
        """
        Analyze content and suggest updates to keep it current and relevant.
        
        Args:
            content_id: ID of the content to analyze
            content_type: Type of content
            content_text: The content to analyze
            last_updated: When the content was last updated
            db: Database session
            
        Returns:
            Dictionary containing suggested updates
        """
        start_time = time.time()
        logger.info(f"Analyzing {content_type} content {content_id} for update suggestions")
        
        try:
            # Calculate content age in days
            content_age_days = (datetime.utcnow() - last_updated).days
            
            # 1. Prepare context for update analysis
            context = {
                "content_id": content_id,
                "content_type": content_type,
                "content_text": content_text[:5000],  # Limit size for performance
                "last_updated": last_updated.isoformat(),
                "content_age_days": content_age_days
            }
            
            # 2. Generate update suggestions using AI orchestrator
            prompt = self._build_update_suggestions_prompt(context)
            
            ai_response = await ai_orchestrator.generate_response(
                prompt=prompt,
                task_complexity=TaskComplexity.MEDIUM,
                model_preference=ModelType.HYBRID,
                max_tokens=1500
            )
            
            # 3. Parse update suggestions
            update_suggestions = self._parse_update_suggestions(ai_response.content)
            
            # 4. Log the AI conversation
            await self._log_ai_conversation(
                user_id=None,
                context=context,
                ai_response=ai_response,
                result=update_suggestions,
                db=db
            )
            
            # 5. Return structured update suggestions
            processing_time = time.time() - start_time
            logger.info(f"Update suggestions generated in {processing_time:.2f}s")
            
            return {
                "content_id": content_id,
                "content_type": content_type,
                "last_updated": last_updated.isoformat(),
                "content_age_days": content_age_days,
                "update_needed": update_suggestions.get("update_needed", False),
                "suggestions": update_suggestions.get("suggestions", []),
                "processing_time_ms": processing_time * 1000,
                "model_used": ai_response.model_used.value,
                "timestamp": datetime.utcnow().isoformat()
            }
            
        except Exception as e:
            logger.error(f"Error generating update suggestions: {e}")
            return {
                "error": f"Failed to generate update suggestions: {str(e)}",
                "content_id": content_id,
                "content_type": content_type,
                "timestamp": datetime.utcnow().isoformat()
            }

    async def tag_and_categorize_content(
        self,
        content_text: str,
        content_type: str,
        content_title: Optional[str] = None,
        db: AsyncSession = None
    ) -> Dict[str, Any]:
        """
        Automatically tag and categorize educational content.
        
        Args:
            content_text: The content to tag and categorize
            content_type: Type of content
            content_title: Optional content title
            db: Database session
            
        Returns:
            Dictionary containing tags, categories, and metadata
        """
        start_time = time.time()
        logger.info(f"Tagging and categorizing {content_type} content")
        
        try:
            # 1. Prepare context for tagging
            context = {
                "content_text": content_text[:5000],  # Limit size for performance
                "content_type": content_type,
                "content_title": content_title
            }
            
            # 2. Generate tags and categories using AI orchestrator
            prompt = self._build_tagging_prompt(context)
            
            ai_response = await ai_orchestrator.generate_response(
                prompt=prompt,
                task_complexity=TaskComplexity.MEDIUM,
                model_preference=ModelType.HYBRID,
                max_tokens=1000
            )
            
            # 3. Parse tagging results
            tagging_results = self._parse_tagging_results(ai_response.content)
            
            # 4. Log the AI conversation
            await self._log_ai_conversation(
                user_id=None,
                context=context,
                ai_response=ai_response,
                result=tagging_results,
                db=db
            )
            
            # 5. Return structured tagging results
            processing_time = time.time() - start_time
            logger.info(f"Content tagging completed in {processing_time:.2f}s")
            
            return {
                "content_type": content_type,
                "content_title": content_title,
                "tags": tagging_results.get("tags", []),
                "categories": tagging_results.get("categories", []),
                "topics": tagging_results.get("topics", []),
                "difficulty_level": tagging_results.get("difficulty_level"),
                "estimated_read_time_minutes": tagging_results.get("estimated_read_time_minutes"),
                "processing_time_ms": processing_time * 1000,
                "model_used": ai_response.model_used.value,
                "timestamp": datetime.utcnow().isoformat()
            }
            
        except Exception as e:
            logger.error(f"Error tagging content: {e}")
            return {
                "error": f"Failed to tag and categorize content: {str(e)}",
                "content_type": content_type,
                "content_title": content_title,
                "timestamp": datetime.utcnow().isoformat()
            }

    # Helper methods
    def _build_content_evaluation_prompt(self, context):
        """Build AI prompt for content quality evaluation."""
        prompt = f"""
        You are an expert educational content evaluator with deep knowledge in various subjects.
        
        Evaluate the quality of the following {context["content_type"]} on the topic of {context["topic"]}.
        
        Content snippet:
        {context["content_text"][:1000]}...
        
        Evaluate the content on these criteria:
        - Accuracy (factual correctness): Weight {context["evaluation_criteria"]["accuracy"]}
        - Completeness (comprehensive coverage): Weight {context["evaluation_criteria"]["completeness"]}
        - Clarity (easy to understand): Weight {context["evaluation_criteria"]["clarity"]}
        - Engagement (interesting and motivating): Weight {context["evaluation_criteria"]["engagement"]}
        - Relevance (appropriate for the topic): Weight {context["evaluation_criteria"]["relevance"]}
        """
        
        if context.get("target_audience"):
            prompt += f"\n\nTarget audience: {context['target_audience']}"
            
        if context.get("difficulty_level"):
            prompt += f"\nDifficulty level: {context['difficulty_level']}"
        
        prompt += """
        
        For each criterion, provide:
        1. A score from 1-5 (1=poor, 5=excellent)
        2. A brief justification for the score
        3. Specific examples from the content
        
        Also provide:
        - An overall weighted score (based on the criterion weights)
        - Key strengths of the content
        - Areas for improvement
        - Whether you recommend this content (yes/no)
        
        Format your response as JSON that can be parsed programmatically.
        """
        
        return prompt
    
    def _parse_content_evaluation(self, ai_content):
        """Parse AI response into structured content evaluation."""
        try:
            # Try to extract JSON from the response
            json_pattern = r'```json(.*?)```|{.*}'
            json_match = re.search(json_pattern, ai_content, re.DOTALL)
            
            if json_match:
                json_str = json_match.group(1) or json_match.group(0)
                json_str = json_str.strip()
                evaluation_data = json.loads(json_str)
                return evaluation_data
            else:
                # Fallback to structured parsing
                return self._structured_parse_evaluation(ai_content)
        except Exception as e:
            logger.error(f"Error parsing content evaluation: {e}")
            return {
                "error": f"Failed to parse evaluation: {str(e)}",
                "overall_score": 0,
                "recommendation": "no"
            }
    
    def _structured_parse_evaluation(self, content):
        """Fallback parsing for evaluation when JSON parsing fails."""
        evaluation = {
            "accuracy": {"score": 0, "justification": ""},
            "completeness": {"score": 0, "justification": ""},
            "clarity": {"score": 0, "justification": ""},
            "engagement": {"score": 0, "justification": ""},
            "relevance": {"score": 0, "justification": ""},
            "overall_score": 0,
            "strengths": [],
            "areas_for_improvement": [],
            "recommendation": "no"
        }
        
        # Extract scores
        for criterion in evaluation.keys():
            if criterion in ["strengths", "areas_for_improvement", "recommendation", "overall_score"]:
                continue
                
            pattern = fr'{criterion}.*?(\d+)[/\s]5'
            score_match = re.search(pattern, content, re.IGNORECASE)
            if score_match:
                try:
                    evaluation[criterion]["score"] = int(score_match.group(1))
                except ValueError:
                    pass
        
        # Extract overall score
        overall_match = re.search(r'overall.*?(\d+\.?\d*)', content, re.IGNORECASE)
        if overall_match:
            try:
                evaluation["overall_score"] = float(overall_match.group(1))
            except ValueError:
                # Try to calculate from individual scores
                scores = [item["score"] for item in evaluation.values() if isinstance(item, dict) and "score" in item]
                if scores:
                    evaluation["overall_score"] = sum(scores) / len(scores)
        
        # Extract recommendation
        if "recommend" in content.lower():
            if "yes" in content.lower() or "recommend" in content.lower() and not "not recommend" in content.lower():
                evaluation["recommendation"] = "yes"
            else:
                evaluation["recommendation"] = "no"
                
        # Extract strengths
        strengths_match = re.search(r'strengths?:(.*?)(?:areas|improvements|overall|$)', content, re.IGNORECASE | re.DOTALL)
        if strengths_match:
            strengths_text = strengths_match.group(1)
            strengths = re.findall(r'[-*]\s*(.*?)(?:[-*]|$)', strengths_text)
            if strengths:
                evaluation["strengths"] = [s.strip() for s in strengths if s.strip()]
                
        # Extract areas for improvement
        improvements_match = re.search(r'(?:areas|improvements):(.*?)(?:strengths|overall|recommendation|$)', content, re.IGNORECASE | re.DOTALL)
        if improvements_match:
            improvements_text = improvements_match.group(1)
            improvements = re.findall(r'[-*]\s*(.*?)(?:[-*]|$)', improvements_text)
            if improvements:
                evaluation["areas_for_improvement"] = [i.strip() for i in improvements if i.strip()]
                
        return evaluation
        
    async def _log_ai_conversation(self, user_id, context, ai_response, result, db):
        """Log the AI conversation for analytics and debugging."""
        if not db:
            return
            
        try:
            log_entry = AIConversationLog(
                user_id=user_id or None,
                session_id=f"curation_{int(time.time())}",
                agent_type="curation",
                input_prompt=str(context),
                ai_response=ai_response.content,
                processed_response=str(result),
                model_used=ai_response.model_used.value,
                tokens_used=ai_response.tokens_used,
                cost_estimate=ai_response.cost_estimate,
                processing_time_ms=ai_response.response_time_ms,
                error_occurred=bool(ai_response.error),
                error_message=ai_response.error,
                timestamp=datetime.utcnow()
            )
            
            db.add(log_entry)
            await db.commit()
        except Exception as e:
            logger.error(f"Failed to log AI conversation: {e}")
            # Don't raise the exception - logging failure shouldn't break the main flow
    
    async def _get_user_data(self, user_id, db):
        """Get user data for content personalization."""
        if not user_id or not db:
            return None
            
        try:
            # Get basic user info
            user_query = select(User).where(User.id == user_id)
            result = await db.execute(user_query)
            user = result.scalar_one_or_none()
            
            if not user:
                return None
                
            # Get engagement state
            state_query = select(UserEngagementState).where(UserEngagementState.user_id == user_id)
            result = await db.execute(state_query)
            engagement_state = result.scalar_one_or_none()
            
            # Get learning progress
            enrollment_query = select(CourseEnrollment).where(CourseEnrollment.user_id == user_id)
            result = await db.execute(enrollment_query)
            enrollments = result.scalars().all()
            
            completion_query = select(LessonCompletion).where(LessonCompletion.user_id == user_id)
            result = await db.execute(completion_query)
            completions = result.scalars().all()
            
            # Compile user data
            user_data = {
                "user_id": user_id,
                "name": user.username,
                "engagement_state": engagement_state.state.value if engagement_state else "unknown",
                "completed_courses": [e.course_id for e in enrollments if e.progress_percentage >= 100],
                "in_progress_courses": [e.course_id for e in enrollments if 0 < e.progress_percentage < 100]
            }
            
            return user_data
            
        except Exception as e:
            logger.error(f"Error retrieving user data: {e}")
            return None
            
    async def _find_relevant_content(self, topic, user_data, content_count, existing_content_ids, db):
        """Find relevant content items in the database."""
        if not db:
            return []
            
        try:
            # Extract keywords from topic
            keywords = set(re.findall(r'\w+', topic.lower()))
            keywords = {k for k in keywords if len(k) > 3}  # Filter short words
            
            if not keywords:
                return []
                
            # Build query with keyword search in content
            conditions = []
            for keyword in keywords:
                conditions.append(Post.content.ilike(f"%{keyword}%"))
                
            # Exclude existing content
            exclude_condition = not_(Post.id.in_(existing_content_ids)) if existing_content_ids else True
            
            query = select(Post).where(
                or_(*conditions),
                exclude_condition,
                Post.is_published == True
            ).order_by(desc(Post.created_at)).limit(content_count)
            
            result = await db.execute(query)
            content_items = result.scalars().all()
            
            # Format content items for response
            formatted_items = []
            for item in content_items:
                formatted_items.append({
                    "id": item.id,
                    "content": item.content[:200] + "..." if len(item.content or "") > 200 else item.content,
                    "post_type": item.post_type.value,
                    "author_id": item.author_id,
                    "created_at": item.created_at.isoformat(),
                    "is_published": item.is_published
                })
                
            return formatted_items
            
        except Exception as e:
            logger.error(f"Error finding relevant content: {e}")
            return []
    
    async def _generate_content_recommendations(self, topic, user_data, count_needed, db):
        """Generate external content recommendations when database content is insufficient."""
        if count_needed <= 0:
            return []
            
        try:
            # Create prompt for content recommendations
            prompt = f"""
            Recommend {count_needed} high-quality educational resources on the topic of {topic}.
            
            For each resource, provide:
            1. Title
            2. Brief description
            3. Type (article, video, tutorial, etc.)
            4. Source name
            5. Estimated quality score (1-5)
            6. URL (hypothetical if needed)
            
            Format your response as JSON that can be parsed programmatically.
            """
            
            # Generate recommendations using AI orchestrator
            ai_response = await ai_orchestrator.generate_response(
                prompt=prompt,
                task_complexity=TaskComplexity.MEDIUM,
                model_preference=ModelType.HYBRID,
                max_tokens=1500
            )
            
            # Parse recommendations
            try:
                # Try to extract JSON from the response
                json_pattern = r'```json(.*?)```|{.*}'
                json_match = re.search(json_pattern, ai_response.content, re.DOTALL)
                
                if json_match:
                    json_str = json_match.group(1) or json_match.group(0)
                    json_str = json_str.strip()
                    recommendations = json.loads(json_str)
                    
                    # Format recommendations to match database content structure
                    formatted_items = []
                    for item in recommendations.get("recommendations", []):
                        formatted_items.append({
                            "id": f"gen_{int(time.time())}_{len(formatted_items)}",  # Generate temporary ID
                            "title": item.get("title", "Untitled resource"),
                            "description": item.get("description", ""),
                            "content_type": item.get("type", "article"),
                            "quality_score": float(item.get("quality_score", 3)),
                            "source_url": item.get("url", ""),
                            "source_name": item.get("source", "AI recommended resource"),
                            "is_generated": True  # Flag to indicate this is a generated recommendation
                        })
                        
                    return formatted_items
                    
                return []  # Failed to extract JSON
                    
            except Exception as e:
                logger.error(f"Error parsing content recommendations: {e}")
                return []
                
        except Exception as e:
            logger.error(f"Error generating content recommendations: {e}")
            return []
    
    async def _rank_recommendations(self, content_items, user_data, db):
        """Rank and score content recommendations."""
        if not content_items:
            return []
            
        try:
            # Apply personalized ranking based on user data
            for item in content_items:
                # Start with the base quality score
                personalized_score = item.get("quality_score", 3.0)
                
                # Apply adjustments based on user data if available
                if user_data:
                    # Adjust based on engagement state
                    engagement_state = user_data.get("engagement_state")
                    if engagement_state == "struggling":
                        # Boost simpler content for struggling users
                        if item.get("content_type") in ["tutorial", "explainer"]:
                            personalized_score += 0.5
                    elif engagement_state == "bored":
                        # Boost more engaging content for bored users
                        if item.get("content_type") in ["interactive", "video"]:
                            personalized_score += 0.5
                
                # Add the personalized score
                item["personalized_score"] = round(personalized_score, 2)
            
            # Sort by personalized score
            sorted_items = sorted(content_items, key=lambda x: x.get("personalized_score", 0), reverse=True)
            
            return sorted_items
            
        except Exception as e:
            logger.error(f"Error ranking recommendations: {e}")
            return content_items  # Return unranked items as fallback
    
    async def _get_course_with_lessons(self, course_id, db):
        """Get course details with lessons."""
        if not db:
            return None
            
        query = select(Course).where(Course.id == course_id).options(selectinload(Course.lessons))
        result = await db.execute(query)
        course = result.scalar_one_or_none()
        return course
    
    def _build_gap_analysis_prompt(self, course_data):
        """Build AI prompt for content gap analysis."""
        lesson_text = "\n".join([
            f"- Lesson {i+1}: {lesson['title']} ({lesson['content_type']})" 
            for i, lesson in enumerate(course_data["lessons"])
        ])
        
        prompt = f"""
        You are an expert curriculum designer with deep knowledge of instructional design.
        
        Analyze the following course for content gaps:
        
        Course: {course_data['title']}
        Description: {course_data['description']}
        Difficulty: {course_data['difficulty_level']}
        
        Current lessons:
        {lesson_text}
        
        Identify the following:
        
        1. Content gaps - important topics that are missing from the curriculum
        2. Sequencing issues - problems with the order of lessons
        3. Content type balance - is there a good mix of content types?
        4. Skill development coverage - are all necessary skills addressed?
        5. Assessment coverage - are there sufficient opportunities for assessment?
        
        For each issue identified, provide:
        - Description of the gap/issue
        - Why it's important to address
        - Specific recommendations to fix it
        
        Format your response as JSON that can be parsed programmatically.
        """
        
        return prompt
    
    def _parse_gap_analysis(self, ai_content):
        """Parse AI response into structured gap analysis."""
        try:
            # Try to extract JSON from the response
            json_pattern = r'```json(.*?)```|{.*}'
            json_match = re.search(json_pattern, ai_content, re.DOTALL)
            
            if json_match:
                json_str = json_match.group(1) or json_match.group(0)
                json_str = json_str.strip()
                analysis_data = json.loads(json_str)
                return analysis_data
            else:
                # Fallback to structured parsing
                return self._structured_parse_gap_analysis(ai_content)
        except Exception as e:
            logger.error(f"Error parsing gap analysis: {e}")
            return {
                "error": f"Failed to parse gap analysis: {str(e)}",
                "content_gaps": [],
                "sequencing_issues": [],
                "content_type_balance": {},
                "skill_coverage": {},
                "assessment_coverage": {}
            }
    
    def _structured_parse_gap_analysis(self, content):
        """Fallback parsing for gap analysis when JSON parsing fails."""
        analysis = {
            "content_gaps": [],
            "sequencing_issues": [],
            "content_type_balance": {},
            "skill_coverage": {},
            "assessment_coverage": {}
        }
        
        # Extract content gaps
        gaps_match = re.search(r'content gaps?:(.*?)(?:sequencing issues|$)', content, re.IGNORECASE | re.DOTALL)
        if gaps_match:
            gaps_text = gaps_match.group(1)
            # Look for bullet points or numbered items
            gaps = re.findall(r'[-*\d+][.)]\s*(.*?)(?:[-*\d+][.)]|$)', gaps_text)
            if gaps:
                analysis["content_gaps"] = [g.strip() for g in gaps if g.strip()]
                
        # Extract sequencing issues
        seq_match = re.search(r'sequencing issues?:(.*?)(?:content type balance|$)', content, re.IGNORECASE | re.DOTALL)
        if seq_match:
            seq_text = seq_match.group(1)
            issues = re.findall(r'[-*\d+][.)]\s*(.*?)(?:[-*\d+][.)]|$)', seq_text)
            if issues:
                analysis["sequencing_issues"] = [i.strip() for i in issues if i.strip()]
                
        # Extract content type balance
        balance_match = re.search(r'content type balance:(.*?)(?:skill development|$)', content, re.IGNORECASE | re.DOTALL)
        if balance_match:
            balance_text = balance_match.group(1).strip()
            analysis["content_type_balance"]["description"] = balance_text
                
        # Extract skill coverage
        skill_match = re.search(r'skill development coverage:(.*?)(?:assessment coverage|$)', content, re.IGNORECASE | re.DOTALL)
        if skill_match:
            skill_text = skill_match.group(1).strip()
            analysis["skill_coverage"]["description"] = skill_text
                
        # Extract assessment coverage
        assessment_match = re.search(r'assessment coverage:(.*?)(?:$)', content, re.IGNORECASE | re.DOTALL)
        if assessment_match:
            assessment_text = assessment_match.group(1).strip()
            analysis["assessment_coverage"]["description"] = assessment_text
                
        return analysis
    
    def _build_update_suggestions_prompt(self, context):
        """Build AI prompt for content update suggestions."""
        prompt = f"""
        You are an expert in educational content maintenance and updating.
        
        Analyze the following {context['content_type']} content that was last updated {context['content_age_days']} days ago:
        
        Content snippet:
        {context['content_text'][:1000]}...
        
        Determine if this content needs updates, considering:
        
        1. Accuracy - is any information outdated or incorrect?
        2. Relevance - is the content still relevant to today's learners?
        3. Completeness - are there new developments that should be included?
        4. Format/style - could the presentation be improved?
        
        For each issue found:
        - Describe the issue
        - Explain why it needs updating
        - Provide specific recommendations for updates
        
        Also indicate whether an update is urgently needed or optional.
        
        Format your response as JSON that can be parsed programmatically.
        """
        
        return prompt
    
    def _parse_update_suggestions(self, ai_content):
        """Parse AI response into structured update suggestions."""
        try:
            # Try to extract JSON from the response
            json_pattern = r'```json(.*?)```|{.*}'
            json_match = re.search(json_pattern, ai_content, re.DOTALL)
            
            if json_match:
                json_str = json_match.group(1) or json_match.group(0)
                json_str = json_str.strip()
                suggestions_data = json.loads(json_str)
                return suggestions_data
            else:
                # Fallback to structured parsing
                return self._structured_parse_update_suggestions(ai_content)
        except Exception as e:
            logger.error(f"Error parsing update suggestions: {e}")
            return {
                "error": f"Failed to parse update suggestions: {str(e)}",
                "update_needed": False,
                "suggestions": []
            }
    
    def _structured_parse_update_suggestions(self, content):
        """Fallback parsing for update suggestions when JSON parsing fails."""
        suggestions = {
            "update_needed": False,
            "urgency": "low",
            "suggestions": []
        }
        
        # Determine if update is needed
        if re.search(r'update.*?(needed|required|necessary)', content, re.IGNORECASE):
            suggestions["update_needed"] = True
            
            # Determine urgency
            if re.search(r'urgent|immediate|critical', content, re.IGNORECASE):
                suggestions["urgency"] = "high"
            elif re.search(r'moderate|medium', content, re.IGNORECASE):
                suggestions["urgency"] = "medium"
            else:
                suggestions["urgency"] = "low"
        
        # Extract suggestions
        for category in ["accuracy", "relevance", "completeness", "format", "style"]:
            category_match = re.search(fr'{category}.*?:(.*?)(?:{"|".join(["accuracy", "relevance", "completeness", "format", "style", "conclusion", "summary"])}|$)', content, re.IGNORECASE | re.DOTALL)
            if category_match:
                category_text = category_match.group(1).strip()
                if category_text and not category_text.lower().startswith(("no issues", "up to date")):
                    suggestions["suggestions"].append({
                        "category": category,
                        "description": category_text
                    })
        
        return suggestions
    
    def _build_tagging_prompt(self, context):
        """Build AI prompt for content tagging."""
        prompt = f"""
        You are an expert in educational content tagging and categorization.
        
        Analyze the following {context['content_type']} content:
        """
        
        if context.get('content_title'):
            prompt += f"\nTitle: {context['content_title']}"
            
        prompt += f"""
        
        Content snippet:
        {context['content_text'][:1500]}...
        
        Generate the following metadata:
        
        1. Tags: 5-10 specific tags relevant to the content
        2. Categories: 1-3 broad educational categories
        3. Topics: 3-5 specific educational topics covered
        4. Difficulty level (beginner, intermediate, advanced)
        5. Estimated read/watch time in minutes
        
        Format your response as JSON that can be parsed programmatically.
        """
        
        return prompt
    
    def _parse_tagging_results(self, ai_content):
        """Parse AI response into structured tagging results."""
        try:
            # Try to extract JSON from the response
            json_pattern = r'```json(.*?)```|{.*}'
            json_match = re.search(json_pattern, ai_content, re.DOTALL)
            
            if json_match:
                json_str = json_match.group(1) or json_match.group(0)
                json_str = json_str.strip()
                tagging_data = json.loads(json_str)
                return tagging_data
            else:
                # Fallback to structured parsing
                return self._structured_parse_tagging(ai_content)
        except Exception as e:
            logger.error(f"Error parsing tagging results: {e}")
            return {
                "error": f"Failed to parse tagging results: {str(e)}",
                "tags": [],
                "categories": [],
                "topics": [],
                "difficulty_level": "intermediate",
                "estimated_read_time_minutes": 10
            }
    
    def _structured_parse_tagging(self, content):
        """Fallback parsing for tagging when JSON parsing fails."""
        tagging = {
            "tags": [],
            "categories": [],
            "topics": [],
            "difficulty_level": "intermediate",
            "estimated_read_time_minutes": 10
        }
        
        # Extract tags
        tags_match = re.search(r'tags?:(.*?)(?:categories|$)', content, re.IGNORECASE | re.DOTALL)
        if tags_match:
            tags_text = tags_match.group(1)
            tags = re.findall(r'[-*]\s*(.*?)(?:[-*]|$)', tags_text)
            if not tags:
                tags = [t.strip() for t in tags_text.split(',')]
            tagging["tags"] = [t.strip() for t in tags if t.strip()]
                
        # Extract categories
        categories_match = re.search(r'categories?:(.*?)(?:topics|$)', content, re.IGNORECASE | re.DOTALL)
        if categories_match:
            categories_text = categories_match.group(1)
            categories = re.findall(r'[-*]\s*(.*?)(?:[-*]|$)', categories_text)
            if not categories:
                categories = [c.strip() for c in categories_text.split(',')]
            tagging["categories"] = [c.strip() for c in categories if c.strip()]
                
        # Extract topics
        topics_match = re.search(r'topics?:(.*?)(?:difficulty|$)', content, re.IGNORECASE | re.DOTALL)
        if topics_match:
            topics_text = topics_match.group(1)
            topics = re.findall(r'[-*]\s*(.*?)(?:[-*]|$)', topics_text)
            if not topics:
                topics = [t.strip() for t in topics_text.split(',')]
            tagging["topics"] = [t.strip() for t in topics if t.strip()]
                
        # Extract difficulty level
        difficulty_match = re.search(r'difficulty level:?\s*(beginner|intermediate|advanced)', content, re.IGNORECASE)
        if difficulty_match:
            tagging["difficulty_level"] = difficulty_match.group(1).lower()
                
        # Extract read time
        time_match = re.search(r'estimated\s*(?:read|watch)?\s*time:?\s*(\d+)', content, re.IGNORECASE)
        if time_match:
            try:
                tagging["estimated_read_time_minutes"] = int(time_match.group(1))
            except ValueError:
                pass
                
        return tagging


# Initialize the agent
content_curation_agent = ContentCurationAgent()
