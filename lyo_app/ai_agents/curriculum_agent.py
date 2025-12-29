"""
Curriculum Agent - AI-driven Course Creation

This agent provides intelligent curriculum and course creation capabilities:
- Dynamic course generation based on learning goals
- Learning path optimization
- Content sequencing for optimal knowledge acquisition
- Skill progression mapping
- Auto-generated quizzes and assessments
- Adaptive course difficulty adjustment
"""

import asyncio
import logging
import time
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any, Tuple, Set
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_, desc, func, or_
from sqlalchemy.orm import selectinload
import json
import re

from .models import AIConversationLog, AIModelTypeEnum, UserEngagementState
from .orchestrator import ai_orchestrator, ModelType, TaskComplexity, LanguageCode
from lyo_app.learning.models import Course, Lesson, DifficultyLevel, ContentType
from lyo_app.learning.models import CourseEnrollment, LessonCompletion
from lyo_app.models.enhanced import User

logger = logging.getLogger(__name__)


class CurriculumDesignAgent:
    """
    AI agent for intelligent curriculum and course creation.
    """
    
    def __init__(self):
        self.content_templates = {}
        self.skill_taxonomy = {}
        self.last_model_update = datetime.utcnow()
    
    async def generate_course_outline(
        self, 
        title: str, 
        description: str,
        target_audience: str,
        learning_objectives: List[str],
        difficulty_level: DifficultyLevel,
        estimated_duration_hours: int,
        db: AsyncSession,
        user_id: Optional[int] = None,
        language: Optional[LanguageCode] = None
    ) -> Dict[str, Any]:
        """
        Generate a comprehensive course outline based on the provided parameters.
        Uses advanced optimization and personalization for enhanced results.
        
        Args:
            title: Course title
            description: Course description
            target_audience: Description of target learners
            learning_objectives: List of learning objectives
            difficulty_level: Course difficulty level
            estimated_duration_hours: Estimated course duration in hours
            db: Database session
            user_id: Optional user ID for personalization
            language: Target language for the course content
            
        Returns:
            Dictionary containing the generated course outline with optimization metadata
        """
        start_time = time.time()
        logger.info(f"Generating optimized course outline for '{title}' with {len(learning_objectives)} learning objectives")
        
        try:
            # 1. Prepare prompt for the AI model with personalization context
            context = await self._prepare_course_context(
                title=title,
                description=description,
                target_audience=target_audience,
                learning_objectives=learning_objectives,
                difficulty_level=difficulty_level,
                estimated_duration_hours=estimated_duration_hours,
                user_id=user_id,
                language=language,
                db=db
            )
            
            # 2. Generate course structure using AI orchestrator with optimization
            prompt = self._build_course_generation_prompt(context)
            
            ai_response = await ai_orchestrator.generate_response(
                prompt=prompt,
                task_complexity=TaskComplexity.COMPLEX,
                model_preference=ModelType.GEMMA_4_CLOUD,
                max_tokens=2000,
                language=language or LanguageCode.ENGLISH,
                user_id=user_id,  # Enable personalization
                agent_type="curriculum"  # Enable agent-specific optimizations
            )
            
            # 3. Parse AI response into structured outline
            course_outline = self._parse_course_outline(ai_response.content)
            
            # 4. Apply post-processing optimizations
            if user_id:
                course_outline = await self._apply_personalization_optimizations(
                    course_outline, user_id, context
                )
            
            # 5. Log the AI conversation with optimization metadata
            await self._log_ai_conversation(
                user_id=user_id,
                context=context,
                ai_response=ai_response,
                result=course_outline,
                db=db
            )
            
            # 6. Return the structured course outline with optimization info
            processing_time = time.time() - start_time
            logger.info(f"Optimized course outline generated in {processing_time:.2f}s with {len(course_outline.get('lessons', []))} lessons")
            
            return {
                "title": title,
                "description": description,
                "difficulty_level": difficulty_level,
                "estimated_duration_hours": estimated_duration_hours,
                "target_audience": target_audience,
                "learning_objectives": learning_objectives,
                "outline": course_outline,
                "processing_time_ms": processing_time * 1000,
                "model_used": ai_response.model_used.value,
                "timestamp": datetime.utcnow().isoformat()
            }
            
        except Exception as e:
            logger.error(f"Error generating course outline: {e}")
            return {
                "error": f"Failed to generate course outline: {str(e)}",
                "title": title,
                "timestamp": datetime.utcnow().isoformat()
            }

    async def generate_lesson_content(
        self,
        course_id: int,
        lesson_title: str,
        lesson_description: str,
        learning_objectives: List[str],
        content_type: ContentType,
        difficulty_level: DifficultyLevel,
        db: AsyncSession,
        user_id: Optional[int] = None
    ) -> Dict[str, Any]:
        """
        Generate detailed lesson content for a specific lesson.
        
        Args:
            course_id: ID of the parent course
            lesson_title: Title of the lesson
            lesson_description: Description of the lesson
            learning_objectives: List of learning objectives for the lesson
            content_type: Type of content (text, video, interactive, etc.)
            difficulty_level: Difficulty level of the lesson
            db: Database session
            user_id: Optional user ID for personalization
            
        Returns:
            Dictionary containing the generated lesson content
        """
        start_time = time.time()
        logger.info(f"Generating lesson content for '{lesson_title}' in course {course_id}")
        
        try:
            # 1. Get course context
            course = await self._get_course_by_id(course_id, db)
            if not course:
                return {"error": f"Course with ID {course_id} not found"}
            
            # 2. Prepare lesson generation context
            context = await self._prepare_lesson_context(
                course=course,
                lesson_title=lesson_title,
                lesson_description=lesson_description,
                learning_objectives=learning_objectives,
                content_type=content_type,
                difficulty_level=difficulty_level,
                db=db
            )
            
            # 3. Generate lesson content using AI orchestrator
            prompt = self._build_lesson_generation_prompt(context)
            
            ai_response = await ai_orchestrator.generate_response(
                prompt=prompt,
                task_complexity=TaskComplexity.COMPLEX,
                model_preference=ModelType.HYBRID,
                max_tokens=3000
            )
            
            # 4. Parse and structure the lesson content
            lesson_content = self._parse_lesson_content(ai_response.content, content_type)
            
            # 5. Generate assessment questions if appropriate
            assessment_questions = []
            if content_type not in [ContentType.VIDEO, ContentType.ASSIGNMENT]:
                assessment_questions = await self._generate_assessment_questions(
                    lesson_title=lesson_title,
                    lesson_content=lesson_content,
                    learning_objectives=learning_objectives,
                    difficulty_level=difficulty_level,
                    db=db
                )
            
            # 6. Log the AI conversation
            await self._log_ai_conversation(
                user_id=user_id,
                context=context,
                ai_response=ai_response,
                result={"lesson_content": lesson_content, "assessment_questions": assessment_questions},
                db=db
            )
            
            # 7. Return the structured lesson content
            processing_time = time.time() - start_time
            logger.info(f"Lesson content generated in {processing_time:.2f}s")
            
            return {
                "title": lesson_title,
                "description": lesson_description,
                "content": lesson_content,
                "content_type": content_type,
                "difficulty_level": difficulty_level,
                "assessment_questions": assessment_questions,
                "course_id": course_id,
                "processing_time_ms": processing_time * 1000,
                "model_used": ai_response.model_used.value,
                "timestamp": datetime.utcnow().isoformat()
            }
            
        except Exception as e:
            logger.error(f"Error generating lesson content: {e}")
            return {
                "error": f"Failed to generate lesson content: {str(e)}",
                "lesson_title": lesson_title,
                "course_id": course_id,
                "timestamp": datetime.utcnow().isoformat()
            }
    
    async def generate_learning_path(
        self,
        user_id: int,
        learning_goal: str,
        current_skill_level: DifficultyLevel,
        target_skill_level: DifficultyLevel,
        time_constraint_hours: Optional[int] = None,
        include_existing_courses: bool = True,
        db: AsyncSession = None
    ) -> Dict[str, Any]:
        """
        Generate a personalized learning path to achieve a specific learning goal.
        
        Args:
            user_id: User ID for personalization
            learning_goal: The learning goal to achieve
            current_skill_level: User's current skill level
            target_skill_level: Target skill level to achieve
            time_constraint_hours: Optional time constraint in hours
            include_existing_courses: Whether to include existing courses in the path
            db: Database session
            
        Returns:
            Dictionary containing the personalized learning path
        """
        start_time = time.time()
        logger.info(f"Generating learning path for user {user_id} to achieve goal: '{learning_goal}'")
        
        try:
            # 1. Fetch user data and course history
            user_data = await self._get_user_learning_data(user_id, db)
            
            # 2. Identify existing relevant courses if needed
            existing_courses = []
            if include_existing_courses:
                existing_courses = await self._find_relevant_courses(
                    learning_goal=learning_goal,
                    difficulty_range=(current_skill_level, target_skill_level),
                    db=db
                )
            
            # 3. Prepare learning path generation context
            context = {
                "user_data": user_data,
                "learning_goal": learning_goal,
                "current_skill_level": current_skill_level,
                "target_skill_level": target_skill_level,
                "time_constraint_hours": time_constraint_hours,
                "existing_courses": existing_courses
            }
            
            # 4. Generate learning path using AI orchestrator
            prompt = self._build_learning_path_prompt(context)
            
            ai_response = await ai_orchestrator.generate_response(
                prompt=prompt,
                task_complexity=TaskComplexity.COMPLEX,
                model_preference=ModelType.GEMMA_4_CLOUD,
                max_tokens=2500
            )
            
            # 5. Parse and structure the learning path
            learning_path = self._parse_learning_path(ai_response.content)
            
            # 6. Log the AI conversation
            await self._log_ai_conversation(
                user_id=user_id,
                context=context,
                ai_response=ai_response,
                result=learning_path,
                db=db
            )
            
            # 7. Return the structured learning path
            processing_time = time.time() - start_time
            logger.info(f"Learning path generated in {processing_time:.2f}s with {len(learning_path.get('steps', []))} steps")
            
            return {
                "user_id": user_id,
                "learning_goal": learning_goal,
                "current_skill_level": current_skill_level,
                "target_skill_level": target_skill_level,
                "time_constraint_hours": time_constraint_hours,
                "learning_path": learning_path,
                "processing_time_ms": processing_time * 1000,
                "model_used": ai_response.model_used.value,
                "timestamp": datetime.utcnow().isoformat()
            }
            
        except Exception as e:
            logger.error(f"Error generating learning path: {e}")
            return {
                "error": f"Failed to generate learning path: {str(e)}",
                "user_id": user_id,
                "learning_goal": learning_goal,
                "timestamp": datetime.utcnow().isoformat()
            }
            
    # Helper methods
    async def _prepare_course_context(self, title, description, target_audience, 
                                     learning_objectives, difficulty_level, 
                                     estimated_duration_hours, user_id, language, db):
        """Prepare context for course generation."""
        context = {
            "title": title,
            "description": description,
            "target_audience": target_audience,
            "learning_objectives": learning_objectives,
            "difficulty_level": difficulty_level.value,
            "estimated_duration_hours": estimated_duration_hours,
            "content_types": [t.value for t in ContentType],
            "language": language.value if language else "en",
            "timestamp": datetime.utcnow().isoformat()
        }
        
        # Add user context if available
        if user_id:
            user_data = await self._get_user_learning_data(user_id, db)
            if user_data:
                context["user_data"] = user_data
                
        return context
    
    def _build_course_generation_prompt(self, context):
        """Build AI prompt for course generation."""
        prompt = f"""
        You are an expert curriculum designer with experience in creating educational courses.
        
        Create a detailed course outline for a course with the following information:
        
        Title: {context["title"]}
        Description: {context["description"]}
        Target Audience: {context["target_audience"]}
        Difficulty Level: {context["difficulty_level"]}
        Estimated Duration: {context["estimated_duration_hours"]} hours
        
        Learning Objectives:
        {self._format_list_items(context["learning_objectives"])}
        
        Your task is to create a comprehensive course outline that includes:
        1. 5-10 modules/lessons with titles and brief descriptions
        2. Key topics to be covered in each lesson
        3. The content type for each lesson (choose from: {', '.join(context["content_types"])})
        4. Learning outcomes for each lesson
        5. Suggested activities or exercises for each lesson
        
        The course should progress logically, building skills incrementally, and effectively address all learning objectives.
        Format your response as structured JSON that can be parsed programmatically.
        """
        return prompt
    
    def _parse_course_outline(self, ai_content):
        """Parse AI response into structured course outline."""
        try:
            # Try to extract JSON from the response
            json_pattern = r'```json(.*?)```|{.*}'
            json_match = re.search(json_pattern, ai_content, re.DOTALL)
            
            if json_match:
                json_str = json_match.group(1) if json_match.group(1) else json_match.group(0)
                # Clean up the JSON string
                json_str = json_str.strip()
                course_data = json.loads(json_str)
                return course_data
            else:
                # Fallback to structured parsing
                return self._structured_parse_course_outline(ai_content)
        except Exception as e:
            logger.error(f"Error parsing course outline: {e}")
            return {"error": f"Failed to parse course outline: {str(e)}", "raw_content": ai_content}
    
    def _structured_parse_course_outline(self, content):
        """Fallback parsing for non-JSON responses."""
        lessons = []
        current_lesson = None
        
        for line in content.split('\n'):
            line = line.strip()
            
            # Try to identify lesson headers
            if re.match(r'^(Lesson|Module)\s+\d+:', line, re.IGNORECASE):
                if current_lesson:
                    lessons.append(current_lesson)
                    
                title_match = re.search(r'(Lesson|Module)\s+\d+:\s*(.*)', line, re.IGNORECASE)
                if title_match:
                    lesson_title = title_match.group(2).strip()
                    current_lesson = {
                        "title": lesson_title,
                        "description": "",
                        "topics": [],
                        "activities": [],
                        "content_type": "text",  # Default
                        "outcomes": []
                    }
            
            # Add content to current lesson
            if current_lesson:
                if line.lower().startswith('description:'):
                    current_lesson["description"] = line[12:].strip()
                elif line.lower().startswith('topics:') or line.lower().startswith('key topics:'):
                    topic_text = line.split(':', 1)[1].strip()
                    current_lesson["topics"] = [t.strip() for t in topic_text.split(',') if t.strip()]
                elif line.lower().startswith('content type:'):
                    content_type = line.split(':', 1)[1].strip().lower()
                    current_lesson["content_type"] = content_type
                elif line.lower().startswith('activities:') or line.lower().startswith('exercises:'):
                    activities_text = line.split(':', 1)[1].strip()
                    current_lesson["activities"] = [a.strip() for a in activities_text.split(',') if a.strip()]
                elif line.lower().startswith('outcomes:') or line.lower().startswith('learning outcomes:'):
                    outcomes_text = line.split(':', 1)[1].strip()
                    current_lesson["outcomes"] = [o.strip() for o in outcomes_text.split(',') if o.strip()]
                elif current_lesson["description"] and not line.lower().startswith(('topics:', 'content type:', 'activities:', 'outcomes:')):
                    # Append to description if not a special field
                    current_lesson["description"] += " " + line
        
        # Add the last lesson if exists
        if current_lesson:
            lessons.append(current_lesson)
            
        return {
            "lessons": lessons
        }
    
    def _format_list_items(self, items):
        """Format list items for prompt."""
        return '\n'.join([f"- {item}" for item in items])
        
    async def _log_ai_conversation(self, user_id, context, ai_response, result, db):
        """Log the AI conversation for analytics and debugging."""
        if not db:
            return
            
        try:
            log_entry = AIConversationLog(
                user_id=user_id if user_id else None,
                session_id=f"curriculum_{int(time.time())}",
                agent_type="curriculum",
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
            
    async def _get_course_by_id(self, course_id, db):
        """Get course details by ID."""
        if not db:
            return None
            
        query = select(Course).where(Course.id == course_id)
        result = await db.execute(query)
        course = result.scalar_one_or_none()
        return course
        
    async def _prepare_lesson_context(self, course, lesson_title, lesson_description, 
                                     learning_objectives, content_type, difficulty_level, db):
        """Prepare context for lesson generation."""
        # Get other lessons in the course for continuity
        query = select(Lesson).where(Lesson.course_id == course.id)
        result = await db.execute(query)
        other_lessons = result.scalars().all()
        
        other_lesson_titles = [lesson.title for lesson in other_lessons]
        
        return {
            "course_title": course.title,
            "course_description": course.description,
            "lesson_title": lesson_title,
            "lesson_description": lesson_description,
            "learning_objectives": learning_objectives,
            "content_type": content_type.value,
            "difficulty_level": difficulty_level.value,
            "other_lesson_titles": other_lesson_titles
        }
        
    def _build_lesson_generation_prompt(self, context):
        """Build AI prompt for lesson content generation."""
        prompt = f"""
        You are an expert educational content creator specializing in {context['content_type']} content.
        
        Create detailed lesson content for:
        
        Course: {context['course_title']}
        Lesson: {context['lesson_title']}
        Description: {context['lesson_description']}
        Content Type: {context['content_type']}
        Difficulty Level: {context['difficulty_level']}
        
        Learning Objectives:
        {self._format_list_items(context['learning_objectives'])}
        
        This lesson fits into a course with other lessons including:
        {self._format_list_items(context['other_lesson_titles'])}
        
        Your task is to create comprehensive, engaging, and educational content that:
        1. Addresses all learning objectives
        2. Is appropriate for the {context['difficulty_level']} level
        3. Uses the {context['content_type']} format effectively
        4. Builds on previous knowledge while preparing for upcoming lessons
        5. Includes examples, analogies, and explanations where appropriate
        6. Has a clear structure with introduction, main content, and conclusion
        
        Format your response as structured content that can be directly presented to learners.
        """
        
        # Add specific instructions based on content type
        if context['content_type'] == ContentType.QUIZ.value:
            prompt += """
            For this quiz content, include:
            - 5-10 questions with varying difficulty
            - A mix of multiple choice, true/false, and short answer questions
            - Correct answers and explanations for each question
            - Clear instructions for the learner
            """
        elif context['content_type'] == ContentType.VIDEO.value:
            prompt += """
            For this video script content, include:
            - A complete script with narration text
            - Description of visuals/graphics to show at each point
            - Timing suggestions for different segments
            - Points where interaction or questions could be included
            - Summary of key points for video description
            """
        elif context['content_type'] == ContentType.INTERACTIVE.value:
            prompt += """
            For this interactive content, include:
            - Step-by-step guidance for the interactive elements
            - Clear instructions for user interactions
            - Feedback to provide for different user actions
            - Learning checkpoints throughout the content
            - A clear goal or outcome for the interactive session
            """
        
        return prompt
    
    def _parse_lesson_content(self, ai_content, content_type):
        """Parse AI response into structured lesson content based on content type."""
        # Basic structure for all content types
        content_structure = {
            "introduction": "",
            "main_content": [],
            "conclusion": "",
            "additional_resources": []
        }
        
        # Content-type specific parsing
        if content_type == ContentType.QUIZ:
            return self._parse_quiz_content(ai_content)
        elif content_type == ContentType.VIDEO:
            return self._parse_video_script(ai_content)
        elif content_type == ContentType.INTERACTIVE:
            return self._parse_interactive_content(ai_content)
        else:
            # Default parsing for text and assignments
            return self._parse_text_content(ai_content)
    
    def _parse_text_content(self, content):
        """Parse text-based lesson content."""
        sections = {
            "introduction": "",
            "main_content": [],
            "conclusion": "",
            "additional_resources": []
        }
        
        current_section = "introduction"
        current_heading = ""
        current_content = []
        
        for line in content.split('\n'):
            line = line.strip()
            
            # Skip empty lines
            if not line:
                continue
                
            # Detect section headers
            if line.lower() == "introduction" or re.match(r'^#+\s+introduction', line, re.IGNORECASE):
                current_section = "introduction"
                continue
            elif line.lower() == "conclusion" or re.match(r'^#+\s+conclusion', line, re.IGNORECASE):
                # Save any current main content section
                if current_heading and current_content:
                    sections["main_content"].append({
                        "heading": current_heading,
                        "content": "\n".join(current_content)
                    })
                    current_heading = ""
                    current_content = []
                current_section = "conclusion"
                continue
            elif line.lower().startswith("additional resources") or re.match(r'^#+\s+additional resources', line, re.IGNORECASE):
                current_section = "additional_resources"
                continue
            elif re.match(r'^#+\s+', line) and current_section != "additional_resources":
                # This is a heading within main content
                if current_section == "main_content" and current_heading and current_content:
                    sections["main_content"].append({
                        "heading": current_heading,
                        "content": "\n".join(current_content)
                    })
                
                current_section = "main_content"
                current_heading = re.sub(r'^#+\s+', '', line)
                current_content = []
                continue
            
            # Add line to appropriate section
            if current_section == "introduction":
                sections["introduction"] += line + "\n"
            elif current_section == "conclusion":
                sections["conclusion"] += line + "\n"
            elif current_section == "additional_resources" and line.startswith("- "):
                sections["additional_resources"].append(line[2:].strip())
            elif current_section == "main_content":
                current_content.append(line)
        
        # Add the last main content section if there is one
        if current_section == "main_content" and current_heading and current_content:
            sections["main_content"].append({
                "heading": current_heading,
                "content": "\n".join(current_content)
            })
        
        # Clean up
        sections["introduction"] = sections["introduction"].strip()
        sections["conclusion"] = sections["conclusion"].strip()
        
        return sections
    
    async def _generate_assessment_questions(self, lesson_title, lesson_content, learning_objectives, difficulty_level, db):
        """Generate assessment questions for a lesson."""
        # Create context for question generation
        context = {
            "lesson_title": lesson_title,
            "lesson_content": str(lesson_content),
            "learning_objectives": learning_objectives,
            "difficulty_level": difficulty_level.value
        }
        
        # Create prompt for question generation
        prompt = f"""
        Generate 5 assessment questions for the following lesson:
        
        Lesson: {context['lesson_title']}
        Difficulty: {context['difficulty_level']}
        
        Learning Objectives:
        {self._format_list_items(context['learning_objectives'])}
        
        Create a mix of question types (multiple choice, true/false, short answer) that:
        1. Test understanding of key concepts in the lesson
        2. Address the learning objectives
        3. Vary in difficulty but are appropriate for {context['difficulty_level']} level
        4. Include correct answers and explanations
        
        Format each question as a JSON object with question, type, options (if applicable), 
        correct_answer, and explanation fields.
        """
        
        # Generate questions using AI orchestrator
        ai_response = await ai_orchestrator.generate_response(
            prompt=prompt,
            task_complexity=TaskComplexity.MEDIUM,
            model_preference=ModelType.HYBRID,
            max_tokens=1500
        )
        
        # Parse questions from response
        try:
            # Try to extract JSON array from response
            json_pattern = r'\[\s*{.*}\s*\]'
            json_match = re.search(json_pattern, ai_response.content, re.DOTALL)
            
            if json_match:
                questions_json = json_match.group(0)
                questions = json.loads(questions_json)
                return questions
            else:
                # Fallback to structured parsing
                return self._structured_parse_questions(ai_response.content)
        except Exception as e:
            logger.error(f"Error parsing assessment questions: {e}")
            # Return a simplified structure on parsing failure
            return [{"question": "Error generating questions", "type": "error", "error": str(e)}]
    
    def _structured_parse_questions(self, content):
        """Fallback parsing for assessment questions when JSON parsing fails."""
        questions = []
        current_question = None
        
        for line in content.split('\n'):
            line = line.strip()
            
            # Skip empty lines
            if not line:
                continue
                
            # Try to identify question headers
            if re.match(r'^(Question|Q)\s*\d+:', line, re.IGNORECASE):
                # Save previous question if exists
                if current_question and "question" in current_question:
                    questions.append(current_question)
                
                # Start new question
                question_text = re.sub(r'^(Question|Q)\s*\d+:\s*', '', line, flags=re.IGNORECASE)
                current_question = {
                    "question": question_text,
                    "type": "unknown",
                    "options": [],
                    "correct_answer": "",
                    "explanation": ""
                }
            elif current_question:
                # Process question details
                if line.lower().startswith("type:"):
                    current_question["type"] = line.split(":", 1)[1].strip().lower()
                elif re.match(r'^[a-d][.)]\s', line, re.IGNORECASE):
                    # This is a multiple choice option
                    current_question["type"] = "multiple_choice"
                    option_text = re.sub(r'^[a-d][.)]\s', '', line)
                    current_question["options"].append(option_text.strip())
                elif line.lower().startswith("correct answer:"):
                    current_question["correct_answer"] = line.split(":", 1)[1].strip()
                elif line.lower().startswith("explanation:"):
                    current_question["explanation"] = line.split(":", 1)[1].strip()
                elif "explanation" in current_question and current_question["explanation"]:
                    # Add to existing explanation
                    current_question["explanation"] += " " + line
        
        # Add the last question if exists
        if current_question and "question" in current_question:
            questions.append(current_question)
            
        return questions
        
    async def _get_user_learning_data(self, user_id, db):
        """Get user learning data for personalization."""
        if not user_id or not db:
            return None
            
        try:
            # Get basic user info
            user_query = select(User).where(User.id == user_id)
            result = await db.execute(user_query)
            user = result.scalar_one_or_none()
            
            if not user:
                return None
                
            # Get learning progress
            enrollment_query = select(CourseEnrollment).where(CourseEnrollment.user_id == user_id)
            result = await db.execute(enrollment_query)
            enrollments = result.scalars().all()
            
            completion_query = select(LessonCompletion).where(LessonCompletion.user_id == user_id)
            result = await db.execute(completion_query)
            completions = result.scalars().all()
            
            # Get engagement state
            state_query = select(UserEngagementState).where(UserEngagementState.user_id == user_id)
            result = await db.execute(state_query)
            engagement_state = result.scalar_one_or_none()
            
            # Compile user data
            user_data = {
                "user_id": user_id,
                "name": user.username,
                "learning_records": len(enrollments),
                "engagement_state": engagement_state.state.value if engagement_state else "unknown",
                "completed_courses": [e.course_id for e in enrollments if e.progress_percentage >= 100]
            }
            
            return user_data
            
        except Exception as e:
            logger.error(f"Error retrieving user learning data: {e}")
            return None
            
    async def _find_relevant_courses(self, learning_goal, difficulty_range, db):
        """Find existing courses relevant to a learning goal."""
        if not db:
            return []
            
        try:
            # Extract keywords from learning goal
            keywords = set(re.findall(r'\w+', learning_goal.lower()))
            keywords = {k for k in keywords if len(k) > 3}  # Filter short words
            
            if not keywords:
                return []
                
            # Build query with keyword search in title and description
            conditions = []
            for keyword in keywords:
                conditions.append(Course.title.ilike(f"%{keyword}%"))
                conditions.append(Course.description.ilike(f"%{keyword}%"))
                
            query = select(Course).where(
                or_(*conditions),
                Course.is_published == True,
                Course.difficulty_level.in_([d.value for d in difficulty_range])
            ).limit(5)
            
            result = await db.execute(query)
            courses = result.scalars().all()
            
            # Format courses for response
            formatted_courses = []
            for course in courses:
                formatted_courses.append({
                    "id": course.id,
                    "title": course.title,
                    "description": course.short_description or course.description[:100],
                    "difficulty_level": course.difficulty_level,
                    "estimated_duration_hours": course.estimated_duration_hours
                })
                
            return formatted_courses
            
        except Exception as e:
            logger.error(f"Error finding relevant courses: {e}")
            return []
    
    def _build_learning_path_prompt(self, context):
        """Build AI prompt for learning path generation."""
        prompt = f"""
        Create a personalized learning path for a user with the following details:
        
        Learning Goal: {context['learning_goal']}
        Current Skill Level: {context['current_skill_level'].value}
        Target Skill Level: {context['target_skill_level'].value}
        """
        
        if context['time_constraint_hours']:
            prompt += f"\nTime Available: {context['time_constraint_hours']} hours"
            
        if context.get('user_data'):
            prompt += f"\n\nUser Background:"
            prompt += f"\n- Completed {len(context['user_data'].get('completed_courses', []))} courses"
            prompt += f"\n- Current engagement state: {context['user_data'].get('engagement_state', 'unknown')}"
        
        if context.get('existing_courses'):
            prompt += "\n\nRelevant Available Courses:"
            for course in context['existing_courses']:
                prompt += f"\n- {course['title']} ({course['difficulty_level']}): {course['description']}"
        
        prompt += """
        
        Create a step-by-step learning path that:
        1. Breaks down the learning goal into manageable steps
        2. Progresses logically from the current to target skill level
        3. Includes specific resources and activities for each step
        4. Provides estimated time commitments for each step
        5. Includes milestones to track progress
        6. Recommends existing courses where appropriate
        
        Format your response as structured JSON that can be parsed programmatically.
        """
        
        return prompt
    
    def _parse_learning_path(self, ai_content):
        """Parse AI response into structured learning path."""
        try:
            # Try to extract JSON from the response
            json_pattern = r'```json(.*?)```|{.*}'
            json_match = re.search(json_pattern, ai_content, re.DOTALL)
            
            if json_match:
                json_str = json_match.group(1) if json_match.group(1) else json_match.group(0)
                # Clean up the JSON string
                json_str = json_str.strip()
                path_data = json.loads(json_str)
                return path_data
            else:
                # Fallback to structured parsing
                return self._structured_parse_learning_path(ai_content)
        except Exception as e:
            logger.error(f"Error parsing learning path: {e}")
            return {"error": f"Failed to parse learning path: {str(e)}", "raw_content": ai_content}
    
    def _structured_parse_learning_path(self, content):
        """Fallback parsing for learning path when JSON parsing fails."""
        steps = []
        current_step = None
        milestones = []
        
        for line in content.split('\n'):
            line = line.strip()
            
            # Skip empty lines
            if not line:
                continue
                
            # Try to identify step headers
            if re.match(r'^(Step|Phase)\s+\d+:', line, re.IGNORECASE):
                if current_step:
                    steps.append(current_step)
                    
                step_title = re.sub(r'^(Step|Phase)\s+\d+:\s*', '', line, flags=re.IGNORECASE)
                current_step = {
                    "title": step_title,
                    "description": "",
                    "resources": [],
                    "activities": [],
                    "time_hours": 0,
                    "courses": []
                }
            elif re.match(r'^Milestone\s+\d+:', line, re.IGNORECASE):
                milestone_text = re.sub(r'^Milestone\s+\d+:\s*', '', line, flags=re.IGNORECASE)
                milestones.append({"description": milestone_text})
            elif current_step:
                # Process step details
                if line.lower().startswith("description:"):
                    current_step["description"] = line.split(":", 1)[1].strip()
                elif line.lower().startswith("time:") or line.lower().startswith("duration:"):
                    time_text = line.split(":", 1)[1].strip()
                    hours_match = re.search(r'(\d+)\s*hours?', time_text)
                    if hours_match:
                        current_step["time_hours"] = int(hours_match.group(1))
                elif line.lower().startswith("resources:"):
                    resources_text = line.split(":", 1)[1].strip()
                    current_step["resources"] = [r.strip() for r in resources_text.split(',') if r.strip()]
                elif line.lower().startswith("activities:"):
                    activities_text = line.split(":", 1)[1].strip()
                    current_step["activities"] = [a.strip() for a in activities_text.split(',') if a.strip()]
                elif line.lower().startswith("courses:"):
                    courses_text = line.split(":", 1)[1].strip()
                    current_step["courses"] = [c.strip() for c in courses_text.split(',') if c.strip()]
                elif line.startswith("- "):
                    # This is likely a list item - add to most appropriate field
                    item = line[2:].strip()
                    if "resources" in line.lower():
                        current_step["resources"].append(item)
                    elif "activities" in line.lower() or "exercise" in line.lower():
                        current_step["activities"].append(item)
                    elif "course" in line.lower():
                        current_step["courses"].append(item)
                    else:
                        # Default to description
                        current_step["description"] += "\n" + line
                else:
                    # Add to description
                    current_step["description"] += "\n" + line
        
        # Add the last step if exists
        if current_step:
            steps.append(current_step)
            
        return {
            "steps": steps,
            "milestones": milestones
        }
    
    async def _apply_personalization_optimizations(
        self, 
        course_outline: Dict[str, Any], 
        user_id: int, 
        context: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Apply personalization optimizations to the course outline."""
        try:
            # Import optimization modules if available
            try:
                from .optimization.personalization_engine import personalization_engine
                
                # Get user profile for personalization
                user_profile = await personalization_engine.get_user_profile(user_id)
                
                # Adjust lesson structure based on learning style
                if user_profile.learning_style.value == "visual":
                    # Emphasize visual content and diagrams
                    for lesson in course_outline.get("lessons", []):
                        lesson["content_format"] = "video_heavy"
                        lesson["visual_aids"] = "emphasized"
                
                elif user_profile.learning_style.value == "kinesthetic":
                    # Add more hands-on activities
                    for lesson in course_outline.get("lessons", []):
                        lesson["interactive_elements"] = "hands_on_projects"
                        lesson["practical_exercises"] = "required"
                
                elif user_profile.learning_style.value == "reading_writing":
                    # Emphasize text-based learning
                    for lesson in course_outline.get("lessons", []):
                        lesson["content_format"] = "text_rich"
                        lesson["written_assignments"] = "emphasized"
                
                # Adjust difficulty based on user preference
                if user_profile.difficulty_preference > 0.7:
                    course_outline["enhanced_challenges"] = True
                    course_outline["advanced_topics"] = "included"
                elif user_profile.difficulty_preference < 0.3:
                    course_outline["simplified_explanations"] = True
                    course_outline["extra_support"] = "provided"
                
                # Adjust session length based on user preference
                optimal_session = user_profile.optimal_session_length
                for lesson in course_outline.get("lessons", []):
                    original_duration = lesson.get("estimated_duration", 30)
                    lesson["recommended_duration"] = min(optimal_session, original_duration)
                    if original_duration > optimal_session:
                        lesson["suggested_breaks"] = "frequent"
                
                # Add personalization metadata
                course_outline["personalization_applied"] = {
                    "learning_style": user_profile.learning_style.value,
                    "difficulty_adjusted": user_profile.difficulty_preference,
                    "session_optimized": True,
                    "timestamp": datetime.utcnow().isoformat()
                }
                
                logger.info(f"Applied personalization for user {user_id}: {user_profile.learning_style.value} style")
                
            except ImportError:
                logger.warning("Personalization engine not available")
                
        except Exception as e:
            logger.error(f"Personalization optimization failed: {e}")
            # Continue without personalization if it fails
        
        return course_outline


# Initialize the agent
curriculum_design_agent = CurriculumDesignAgent()
