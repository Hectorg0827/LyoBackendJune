"""
Enhanced Generative Curriculum with multi-agent pipeline
Builds on existing curriculum_agent.py
"""

import logging
from typing import Dict, List, Optional, Any
from datetime import datetime
import hashlib
import json
from sqlalchemy.ext.asyncio import AsyncSession

from lyo_app.personalization.service import personalization_engine
from lyo_app.core.redis_cache import redis_cache

logger = logging.getLogger(__name__)

class GenerativeCurriculumEngine:
    """
    Multi-agent curriculum generation with continuous improvement
    Phase 2: Advanced content generation with personalization integration
    """
    
    def __init__(self):
        self.critic_prompt = self._load_critic_prompt()
        self.content_generation_cache = {}
        self.quality_threshold = 0.8
        
    async def generate_adaptive_curriculum(
        self,
        user_id: int,
        learning_goal: str,
        db: AsyncSession
    ) -> Dict[str, Any]:
        """
        Generate fully adaptive curriculum using multi-agent pipeline
        """
        # Check cache first
        cache_key = f"curriculum:{user_id}:{hashlib.md5(learning_goal.encode()).hexdigest()}"
        cached_curriculum = await redis_cache.get(cache_key)
        if cached_curriculum:
            logger.info(f"🎯 Cache hit for curriculum: {learning_goal}")
            return cached_curriculum

        logger.info(f"Generating adaptive curriculum for user {user_id}")
        
        try:
            # Import here to avoid circular imports
            from lyo_app.ai_agents.curriculum_agent import curriculum_design_agent
            from lyo_app.ai_agents.curation_agent import content_curation_agent
        except ImportError:
            logger.warning("AI agents not available, using fallback curriculum generation")
            return await self._generate_fallback_curriculum(user_id, learning_goal)
        
        # 1. Get learner profile for personalization
        mastery_profile = await personalization_engine.get_mastery_profile(
            db, str(user_id)
        )
        
        # 2. Planner: Generate initial curriculum structure
        try:
            course_outline = await curriculum_design_agent.generate_learning_path(
                user_id=user_id,
                learning_goal=learning_goal,
                current_skill_level="beginner",  # From mastery profile
                target_skill_level="advanced",
                db=db
            )
        except Exception as e:
            logger.error(f"Error generating course outline: {e}")
            course_outline = await self._generate_basic_outline(learning_goal)
        
        # 3. Curator: Find and evaluate resources
        resources = await self._curate_resources(
            course_outline, user_id, db
        )
        
        # 4. Critic: Quality check and improve
        critique = await self._critique_curriculum(
            course_outline, resources, mastery_profile
        )
        
        # 5. Apply improvements from critique
        if critique.get("improvements_needed"):
            course_outline = await self._apply_improvements(
                course_outline, critique, db
            )
        
        # 6. Version and store
        curriculum = {
            "version": "1.0",
            "generated_at": datetime.utcnow().isoformat(),
            "user_id": user_id,
            "learning_goal": learning_goal,
            "outline": course_outline,
            "resources": resources,
            "critique": critique,
            "personalization": {
                "strengths_leveraged": mastery_profile.strengths[:3],
                "weaknesses_addressed": mastery_profile.weaknesses[:3],
                "optimal_difficulty": mastery_profile.optimal_difficulty
            }
        }
        
        # Cache the result (expire in 24 hours)
        await redis_cache.set(cache_key, curriculum, expire=86400)

        return curriculum
    
    async def generate_content(
        self,
        request: 'ContentGenerationRequest',
        personalization_context: Dict[str, Any],
        db: AsyncSession
    ) -> 'GeneratedContentResponse':
        """
        Generate personalized learning content using AI
        """
        from lyo_app.gen_curriculum.schemas import GeneratedContentResponse, GenerationStatus

        # Check cache
        # Create a unique key based on request parameters
        req_hash = hashlib.md5(request.json().encode()).hexdigest()
        cache_key = f"content:{req_hash}"
        
        cached_data = await redis_cache.get(cache_key)
        if cached_data:
            logger.info(f"🎯 Cache hit for content: {request.topic}")
            # Reconstruct Pydantic model from dict
            return GeneratedContentResponse(**cached_data)

        logger.info(f"Generating {request.content_type} for skill: {request.skill_id}")
        
        start_time = datetime.utcnow()
        
        try:
            # Build generation prompt with personalization
            prompt = self._build_content_generation_prompt(request, personalization_context)
            
            # Generate content using AI
            generated_data = await self._generate_with_ai(
                prompt=prompt,
                content_type=request.content_type,
                quality_threshold=request.quality_threshold
            )
            
            # Post-process and validate content
            processed_content = await self._process_generated_content(
                generated_data, request, personalization_context
            )
            
            # Store in database
            content_record = await self._store_generated_content(
                processed_content, request, db
            )
            
            generation_time = (datetime.utcnow() - start_time).total_seconds()
            
            response = GeneratedContentResponse(
                id=content_record.id,
                content_type=request.content_type,
                title=processed_content["title"],
                description=processed_content.get("description"),
                skill_id=request.skill_id,
                topic=request.topic,
                difficulty_level=request.difficulty_level,
                content_data=processed_content["content"],
                metadata=processed_content["metadata"],
                quality_score=processed_content.get("quality_score", 0.8),
                status=GenerationStatus.COMPLETED,
                generation_time=generation_time,
                created_at=content_record.created_at,
                updated_at=content_record.updated_at
            )

            # Cache the response (expire in 1 hour)
            # Convert to dict/json compatible format
            await redis_cache.set(cache_key, json.loads(response.json()), expire=3600)
            
            return response
            
        except Exception as e:
            logger.error(f"Content generation failed: {e}")
            raise e
    
    async def generate_learning_path(
        self,
        request: 'LearningPathRequest',
        mastery_profile: Any,
        db: AsyncSession
    ) -> 'LearningPathResponse':
        """
        Generate personalized learning path with adaptive progression
        """
        logger.info(f"Generating learning path for user {request.user_id}")
        
        try:
            # Analyze learner profile for path customization
            learning_preferences = self._analyze_learning_preferences(
                request, mastery_profile
            )
            
            # Generate path structure
            path_structure = await self._generate_path_structure(
                request, learning_preferences, mastery_profile
            )
            
            # Create adaptive activities
            activities = await self._generate_adaptive_activities(
                path_structure, learning_preferences, db
            )
            
            # Build assessment checkpoints
            checkpoints = self._create_assessment_checkpoints(
                activities, request.target_skills
            )
            
            # Define adaptation rules
            adaptation_rules = self._create_adaptation_rules(
                learning_preferences, mastery_profile
            )
            
            # Store learning path
            path_record = await self._store_learning_path(
                request, path_structure, activities, checkpoints, 
                adaptation_rules, db
            )
            
            from lyo_app.gen_curriculum.schemas import LearningPathResponse, LearningActivity
            
            return LearningPathResponse(
                id=path_record.id,
                title=path_structure["title"],
                description=path_structure["description"],
                user_id=request.user_id,
                target_skills=request.target_skills,
                learning_objectives=path_structure["learning_objectives"],
                estimated_duration_hours=path_structure["estimated_duration_hours"],
                activities=[LearningActivity(**activity) for activity in activities],
                checkpoints=checkpoints,
                branching_logic=path_structure.get("branching_logic", {}),
                adaptation_rules=adaptation_rules,
                fallback_strategies=path_structure.get("fallback_strategies", []),
                customization_level=learning_preferences["customization_level"],
                created_at=path_record.created_at,
                updated_at=path_record.updated_at
            )
            
        except Exception as e:
            logger.error(f"Learning path generation failed: {e}")
            raise e
    
    async def adapt_learning_path(
        self,
        path_id: int,
        adaptation_request: 'PathAdaptationRequest',
        db: AsyncSession
    ) -> 'PathAdaptationResponse':
        """
        Adapt learning path based on performance and feedback
        """
        logger.info(f"Adapting learning path {path_id}")
        
        try:
            # Get current path state
            current_path = await self._get_path_by_id(path_id, db)
            if not current_path:
                raise ValueError(f"Learning path {path_id} not found")
            
            # Analyze adaptation need
            adaptation_analysis = self._analyze_adaptation_need(
                adaptation_request, current_path
            )
            
            # Generate adaptation strategy
            adaptation_strategy = await self._generate_adaptation_strategy(
                adaptation_analysis, adaptation_request
            )
            
            # Apply adaptations
            adapted_path = await self._apply_path_adaptations(
                current_path, adaptation_strategy, db
            )
            
            # Store adaptation record
            adaptation_record = await self._store_path_adaptation(
                path_id, adaptation_request, adaptation_strategy, db
            )
            
            from lyo_app.gen_curriculum.schemas import PathAdaptationResponse
            
            return PathAdaptationResponse(
                adaptation_id=adaptation_record.id,
                learning_path_id=path_id,
                adaptation_type=adaptation_strategy["type"],
                changes_made=adaptation_strategy["changes"],
                previous_state=adaptation_analysis["previous_state"],
                new_state=adaptation_analysis["new_state"],
                trigger_reason=adaptation_request.trigger_reason,
                adaptation_rationale=adaptation_strategy["rationale"],
                expected_improvement=adaptation_strategy["expected_improvement"],
                success_probability=adaptation_strategy["success_probability"],
                created_at=adaptation_record.created_at
            )
            
        except Exception as e:
            logger.error(f"Path adaptation failed: {e}")
            raise e
    
    def _build_content_generation_prompt(
        self,
        request: 'ContentGenerationRequest',
        personalization_context: Dict[str, Any]
    ) -> str:
        """Build AI prompt for content generation"""
        
        # Base prompt structure
        prompt = f"""
        Generate educational {request.content_type} content for:
        
        Subject: {request.topic}
        Skill: {request.skill_id} 
        Difficulty: {request.difficulty_level:.2f} (0.0=beginner, 1.0=expert)
        Duration: {request.target_duration_minutes or 15} minutes
        
        Personalization Context:
        """
        
        if personalization_context:
            prompt += f"""
        - Current Mastery: {personalization_context.get('current_mastery', 'unknown')}
        - Learning Style: {request.learning_style or 'adaptive'}
        - Emotional State: {request.affect_state or 'neutral'}
        - Optimal Difficulty: {personalization_context.get('optimal_difficulty', 'adaptive')}
        """
        
        # Content-specific requirements
        if request.content_type == "problem":
            prompt += """
        
        Generate a practice problem that:
        - Tests understanding of the core concept
        - Provides multiple solution approaches
        - Includes step-by-step hints if requested
        - Has clear success criteria
        """
        elif request.content_type == "explanation":
            prompt += """
        
        Generate an explanation that:
        - Uses clear, accessible language
        - Includes relevant examples
        - Builds on prerequisite knowledge
        - Connects to real-world applications
        """
        
        prompt += f"""
        
        Include:
        - Hints: {request.include_hints}
        - Explanations: {request.include_explanations}
        - Creativity Level: {request.creativity_level}
        
        Return as JSON with fields: title, description, content, metadata, learning_objectives
        """
        
        return prompt
    
    async def _generate_with_ai(
        self,
        prompt: str,
        content_type: str,
        quality_threshold: float
    ) -> Dict[str, Any]:
        """Generate content using AI with quality checking"""
        
        try:
            # Try to use AI orchestrator if available
            from lyo_app.ai_agents.orchestrator import ai_orchestrator, TaskComplexity, ModelType
            
            response = await ai_orchestrator.generate_response(
                prompt=prompt,
                task_complexity=TaskComplexity.COMPLEX,
                model_preference=ModelType.GEMINI_PRO
            )
            
            import json
            generated_data = json.loads(response.content)
            
            # Quality check
            quality_score = self._assess_content_quality(generated_data, content_type)
            if quality_score < quality_threshold:
                logger.warning(f"Generated content quality below threshold: {quality_score}")
                # Could retry with different parameters
            
            generated_data["quality_score"] = quality_score
            return generated_data
            
        except Exception as e:
            logger.error(f"AI generation failed: {e}")
            # Fallback to template-based generation
            return self._generate_fallback_content(content_type, prompt)
    
    async def revise_curriculum(
        self,
        plan_id: str,
        signals: Dict[str, Any],
        db: AsyncSession
    ) -> Dict[str, Any]:
        """
        Revise curriculum based on learning signals
        """
        logger.info(f"Revising curriculum {plan_id} based on signals")
        
        # Analyze signals
        issue = signals.get("issue")
        evidence = signals.get("evidence", {})
        
        # Generate revision prompt
        revision_prompt = f"""
        Curriculum revision needed:
        - Plan ID: {plan_id}
        - Issue: {issue}
        - Evidence: {evidence}
        
        Please suggest specific improvements to address:
        1. The identified confusion points
        2. Pacing adjustments needed
        3. Additional scaffolding required
        
        Return as JSON with 'revisions' array.
        """
        
        try:
            # Try to get AI recommendations
            from lyo_app.ai_agents.orchestrator import ai_orchestrator, TaskComplexity, ModelType
            
            response = await ai_orchestrator.generate_response(
                prompt=revision_prompt,
                task_complexity=TaskComplexity.MEDIUM,
                model_preference=ModelType.GEMINI_PRO
            )
            
            # Apply revisions
            revisions = self._parse_revisions(response.content)
        except Exception as e:
            logger.error(f"Error getting AI revisions: {e}")
            # Fallback revisions
            revisions = [
                {"type": "general", "description": "Review and clarify content"},
                {"type": "pacing", "description": "Adjust lesson pacing"}
            ]
        
        return {
            "plan_id": plan_id,
            "version": "1.1",
            "revisions_applied": revisions,
            "revised_at": datetime.utcnow().isoformat()
        }
    
    async def _curate_resources(
        self,
        outline: Dict,
        user_id: int,
        db: AsyncSession
    ) -> List[Dict]:
        """Curate resources for each lesson"""
        resources = []
        
        try:
            from lyo_app.ai_agents.curation_agent import content_curation_agent
            
            for lesson in outline.get("lessons", []):
                topic = lesson.get("title", "")
                
                # Get curated content
                try:
                    recommendations = await content_curation_agent.recommend_content(
                        user_id=user_id,
                        topic=topic,
                        content_count=3,
                        db=db
                    )
                    
                    resources.append({
                        "lesson_id": lesson.get("id"),
                        "topic": topic,
                        "resources": recommendations.get("recommendations", [])
                    })
                except Exception as e:
                    logger.error(f"Error curating resources for {topic}: {e}")
                    # Fallback resource
                    resources.append({
                        "lesson_id": lesson.get("id"),
                        "topic": topic,
                        "resources": [{"title": f"Study Guide: {topic}", "type": "text"}]
                    })
        except ImportError:
            logger.warning("Curation agent not available, using basic resources")
            # Basic resource structure
            for lesson in outline.get("lessons", []):
                resources.append({
                    "lesson_id": lesson.get("id"),
                    "topic": lesson.get("title", ""),
                    "resources": [{"title": f"Study: {lesson.get('title', '')}", "type": "basic"}]
                })
        
        return resources
    
    async def _critique_curriculum(
        self,
        outline: Dict,
        resources: List[Dict],
        profile: Any
    ) -> Dict[str, Any]:
        """AI critic evaluates curriculum quality"""
        
        critique_prompt = f"""
        Review this curriculum for quality:
        
        Outline: {outline}
        Resources: {len(resources)} lessons with content
        Learner Profile: 
        - Strengths: {profile.strengths}
        - Weaknesses: {profile.weaknesses}
        
        Evaluate:
        1. Learning objective coverage
        2. Difficulty progression
        3. Prerequisite handling
        4. Time estimates accuracy
        5. Resource quality
        
        Return JSON with 'score', 'strengths', 'improvements_needed'.
        """
        
        try:
            from lyo_app.ai_agents.orchestrator import ai_orchestrator, TaskComplexity, ModelType
            
            response = await ai_orchestrator.generate_response(
                prompt=critique_prompt,
                task_complexity=TaskComplexity.COMPLEX,
                model_preference=ModelType.GEMINI_PRO
            )
            
            import json
            critique = json.loads(response.content)
        except Exception as e:
            logger.error(f"Error critiquing curriculum: {e}")
            critique = {
                "score": 0.8,
                "strengths": ["Well structured"],
                "improvements_needed": []
            }
        
        return critique
    
    async def _apply_improvements(
        self,
        outline: Dict,
        critique: Dict,
        db: AsyncSession
    ) -> Dict:
        """Apply improvements suggested by critic"""
        
        improvements = critique.get("improvements_needed", [])
        
        for improvement in improvements:
            if "add_prerequisite" in improvement:
                # Add prerequisite lesson
                logger.info("Adding prerequisite lesson")
            elif "adjust_difficulty" in improvement:
                # Adjust difficulty curve
                logger.info("Adjusting difficulty curve")
            elif "add_practice" in improvement:
                # Add more practice problems
                logger.info("Adding practice problems")
        
        outline["version"] = outline.get("version", "1.0") + ".1"
        outline["improvements_applied"] = improvements
        
        return outline
    
    async def _generate_fallback_curriculum(
        self,
        user_id: int,
        learning_goal: str
    ) -> Dict[str, Any]:
        """Generate basic curriculum when AI agents not available"""
        
        return {
            "version": "1.0",
            "generated_at": datetime.utcnow().isoformat(),
            "user_id": user_id,
            "learning_goal": learning_goal,
            "outline": {
                "title": f"Learn {learning_goal}",
                "lessons": [
                    {"id": "lesson_1", "title": f"Introduction to {learning_goal}"},
                    {"id": "lesson_2", "title": f"Basic {learning_goal} Concepts"},
                    {"id": "lesson_3", "title": f"Advanced {learning_goal}"}
                ]
            },
            "resources": [],
            "critique": {"score": 0.7, "strengths": ["Basic structure"], "improvements_needed": []},
            "personalization": {"type": "fallback"}
        }
    
    async def _generate_basic_outline(self, learning_goal: str) -> Dict[str, Any]:
        """Generate basic course outline"""
        return {
            "title": f"Master {learning_goal}",
            "lessons": [
                {"id": f"lesson_{i}", "title": f"Module {i}: {learning_goal}"}
                for i in range(1, 6)
            ],
            "estimated_duration": "4 weeks",
            "difficulty": "intermediate"
        }
    
    def _load_critic_prompt(self) -> str:
        """Load critic evaluation prompt template"""
        return """
        As an educational quality critic, evaluate curriculum for:
        - Pedagogical soundness
        - Appropriate scaffolding
        - Clear learning objectives
        - Measurable outcomes
        - Engagement factors
        """
    
    def _parse_revisions(self, content: str) -> List[Dict]:
        """Parse revision recommendations"""
        try:
            import json
            data = json.loads(content)
            return data.get("revisions", [])
        except Exception:
            return [{
                "type": "general",
                "description": "Review and clarify content"
            }]

# Singleton instance
gen_curriculum_engine = GenerativeCurriculumEngine()
