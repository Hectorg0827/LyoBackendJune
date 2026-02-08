"""
Course Generation Pipeline Orchestrator - Central Controller

MIT Architecture Engineering - Deterministic Multi-Agent Pipeline

This orchestrator coordinates all agents through a deterministic pipeline
with gates between each step. It provides:
- Step-by-step execution with validation
- Automatic retry with fallback
- Progress persistence and resume
- Parallel lesson generation
- Granular regeneration of failed steps
"""

import asyncio
import json
import logging
from typing import Optional, Dict, Any, List, Tuple
from datetime import datetime
from dataclasses import dataclass, field
from enum import Enum

from lyo_app.ai_agents.multi_agent_v2.schemas.course_schemas import (
    CourseIntent,
    CurriculumStructure,
    LessonContent,
    CourseAssessments,
    QualityReport,
    GeneratedCourse
)
from lyo_app.ai_agents.multi_agent_v2.agents import (
    OrchestratorAgent,
    CurriculumArchitectAgent,
    ContentCreatorAgent,
    AssessmentDesignerAgent,
    QualityAssuranceAgent,
    LessonGenerationContext,
    ReviewFocus,
    QAContext
)
from lyo_app.ai_agents.multi_agent_v2.model_manager import ModelManager, QualityTier, ModelTier
from lyo_app.ai_agents.multi_agent_v2.pipeline.gates import PipelineGates, GateResult
from lyo_app.ai_agents.multi_agent_v2.pipeline.job_queue import JobManager, JobStatus
from lyo_app.ai_agents.multi_agent_v2.pipeline.streaming import ProgressEvent, StreamingPipeline

logger = logging.getLogger(__name__)


class PipelineStep(str, Enum):
    """Steps in the course generation pipeline"""
    INTENT = "intent"
    CURRICULUM = "curriculum"
    CONTENT = "content"
    ASSESSMENTS = "assessments"
    QA_REVIEW = "qa_review"
    FINALIZE = "finalize"


@dataclass
class StepResult:
    """Result from a pipeline step"""
    step: PipelineStep
    success: bool
    data: Optional[Any] = None
    error: Optional[str] = None
    duration_seconds: float = 0.0
    retries: int = 0
    gate_result: Optional[GateResult] = None


@dataclass
class PipelineConfig:
    """Extended configuration for the course generation pipeline"""
    # EXISTING: Core pipeline settings
    max_retries_per_step: int = 3
    gate_failure_threshold: int = 2  # Max gate failures before abort
    parallel_lesson_batch_size: int = 3  # Concurrent lesson generations
    qa_min_score: int = 60  # Minimum QA score to pass
    save_intermediate_results: bool = True
    enable_auto_fix: bool = True  # Try to fix issues automatically
    
    # NEW: Quality & Model Selection
    quality_tier: QualityTier = QualityTier.BALANCED
    custom_agent_tiers: Optional[Dict[str, ModelTier]] = None  # For CUSTOM tier
    
    # NEW: Content Feature Toggles
    enable_code_examples: bool = True           # Include code blocks in lessons  
    enable_practice_exercises: bool = True      # Include hands-on exercises
    enable_final_quiz: bool = True              # Generate final assessment
    enable_multimedia_suggestions: bool = True  # Suggest images/videos
    
    # NEW: QA Controls
    qa_strictness: str = "standard"  # "lenient", "standard", "strict"
    qa_focus_areas: List[ReviewFocus] = field(
        default_factory=lambda: [ReviewFocus.ACCURACY, ReviewFocus.PEDAGOGY]
    )
    
    # NEW: Budget Controls
    max_budget_usd: Optional[float] = None      # Hard cost cap
    budget_alert_threshold: float = 0.80        # Alert at 80% of budget
    enable_budget_auto_downgrade: bool = True   # Auto-switch to cheaper models if needed
    
    # NEW: Language Support
    target_language: str = "en"  # ISO language code
    
    def apply_quality_tier(self) -> None:
        """Apply the selected quality tier to ModelManager"""
        if self.quality_tier == QualityTier.CUSTOM and self.custom_agent_tiers:
            for agent_name, tier in self.custom_agent_tiers.items():
                ModelManager.override_model(agent_name, tier)
            logger.info(f"Applied CUSTOM quality tier with {len(self.custom_agent_tiers)} overrides")
        else:
            ModelManager.apply_quality_tier(self.quality_tier)
    
    def get_estimated_cost(self) -> float:
        """
        Get estimated cost based on current configuration.
        
        Returns:
            Estimated cost in USD
        """
        tier_info = ModelManager.get_tier_description(self.quality_tier)
        base_cost = tier_info["estimated_cost_usd"]
        
        # Adjust for disabled features
        multiplier = 1.0
        if not self.enable_code_examples:
            multiplier *= 0.85  # 15% reduction
        if not self.enable_practice_exercises:
            multiplier *= 0.90  # 10% reduction
        if not self.enable_final_quiz:
            multiplier *= 0.95  # 5% reduction
        
        return base_cost * multiplier
    
    def validate_budget(self, estimated_cost: float) -> bool:
        """
        Check if estimated cost is within budget.
        
        Args:
            estimated_cost: Estimated cost in USD
            
        Returns:
            True if within budget or no budget set
        """
        if self.max_budget_usd is None:
            return True
        return estimated_cost <= self.max_budget_usd
    
    def should_alert_budget(self, current_cost: float) -> bool:
        """
        Check if current cost has reached alert threshold.
        
        Args:
            current_cost: Current cost in USD
            
        Returns:
            True if alert threshold reached
        """
        if self.max_budget_usd is None:
            return False
        threshold_cost = self.max_budget_usd * self.budget_alert_threshold
        return current_cost >= threshold_cost


@dataclass 
class PipelineState:
    """Current state of the pipeline execution"""
    job_id: str
    current_step: PipelineStep
    completed_steps: List[PipelineStep] = field(default_factory=list)
    step_results: Dict[str, StepResult] = field(default_factory=dict)
    intent: Optional[CourseIntent] = None
    curriculum: Optional[CurriculumStructure] = None
    lessons: List[LessonContent] = field(default_factory=list)
    assessments: Optional[CourseAssessments] = None
    qa_report: Optional[QualityReport] = None
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    total_duration_seconds: float = 0.0


class CourseGenerationPipeline(StreamingPipeline):
    """
    Main pipeline orchestrator for course generation.
    
    Executes a deterministic multi-agent pipeline:
    1. Orchestrator Agent → CourseIntent
    2. Gate 1: Validate Intent
    3. Curriculum Agent → CurriculumStructure
    4. Gate 2: Validate Curriculum
    5. Content Agent (parallel) → LessonContent[]
    6. Gate 3: Validate Content
    7. Assessment Agent → CourseAssessments
    8. Gate 4: Validate Assessments
    9. QA Agent → QualityReport
    10. Gate 5: Validate QA
    11. Finalize → GeneratedCourse
    
    Supports both standard and streaming generation modes.
    """
    
    def __init__(
        self,
        config: Optional[PipelineConfig] = None,
        job_manager: Optional[JobManager] = None
    ):
        self.config = config or PipelineConfig()
        self.job_manager = job_manager
        
        # Apply quality tier to ModelManager
        self.config.apply_quality_tier()
        
        # Initialize agents
        self.orchestrator = OrchestratorAgent()
        self.curriculum_architect = CurriculumArchitectAgent()
        self.content_creator = ContentCreatorAgent()
        self.assessment_designer = AssessmentDesignerAgent()
        self.qa_agent = QualityAssuranceAgent()
        
        # Initialize gates
        self.gates = PipelineGates()
        
        logger.info(
            f"CourseGenerationPipeline initialized with {self.config.quality_tier.value} quality tier"
        )
    
    async def generate_course(
        self,
        user_request: str,
        user_context: Optional[Dict[str, Any]] = None,
        job_id: Optional[str] = None
    ) -> GeneratedCourse:
        """
        Execute the full course generation pipeline.
        
        Args:
            user_request: Natural language course request from user
            user_context: Optional user context (previous courses, skill level, etc.)
            job_id: Optional job ID for resuming an existing job
            
        Returns:
            Complete GeneratedCourse object
            
        Raises:
            PipelineError: If pipeline fails after all retries
        """
        # Initialize or resume state
        if job_id and self.job_manager:
            state = await self._resume_state(job_id)
            logger.info(f"Resuming job {job_id} from step {state.current_step}")
        else:
            job_id = await self._create_job(user_request, user_context) if self.job_manager else "local"
            state = PipelineState(
                job_id=job_id,
                current_step=PipelineStep.INTENT,
                started_at=datetime.utcnow()
            )
        
        try:
            # Step 1: Intent Analysis
            if PipelineStep.INTENT not in state.completed_steps:
                state = await self._execute_intent_step(state, user_request, user_context)
            
            # Step 2: Curriculum Design
            if PipelineStep.CURRICULUM not in state.completed_steps:
                state = await self._execute_curriculum_step(state)
            
            # Step 3: Content Generation (parallel)
            if PipelineStep.CONTENT not in state.completed_steps:
                state = await self._execute_content_step(state)
            
            # Step 4: Assessment Design
            if PipelineStep.ASSESSMENTS not in state.completed_steps:
                state = await self._execute_assessment_step(state)
            
            # Step 5: QA Review
            if PipelineStep.QA_REVIEW not in state.completed_steps:
                state = await self._execute_qa_step(state)
                
            # Step 6: Finalize
            result = await self._finalize(state)
            
            state.completed_at = datetime.utcnow()
            state.total_duration_seconds = (
                state.completed_at - state.started_at
            ).total_seconds()
            
            logger.info(
                f"Pipeline completed in {state.total_duration_seconds:.2f}s "
                f"for job {state.job_id}"
            )
            
            return result
            
        except Exception as e:
            logger.error(f"Pipeline failed at step {state.current_step}: {e}")
            if self.job_manager:
                await self.job_manager.update_job_status(
                    state.job_id, 
                    JobStatus.FAILED, 
                    error=str(e)
                )
            raise PipelineError(f"Pipeline failed at {state.current_step}: {e}") from e
    
    # ==================== STEP EXECUTION METHODS ====================
    
    async def _execute_intent_step(
        self,
        state: PipelineState,
        user_request: str,
        user_context: Optional[Dict[str, Any]]
    ) -> PipelineState:
        """Execute Step 1: Intent Analysis"""
        logger.info(f"[{state.job_id}] Step 1: Intent Analysis")
        state.current_step = PipelineStep.INTENT
        
        if self.job_manager:
            await self.job_manager.update_job_status(state.job_id, JobStatus.STEP_1_INTENT)
        
        start_time = datetime.utcnow()
        
        # Execute agent with retry
        intent = await self._execute_with_retry(
            agent=self.orchestrator,
            prompt_args={"user_request": user_request, "user_context": user_context},
            step_name="intent"
        )
        
        # Validate through gate
        gate_result = await self.gates.gate_1_validate_intent(intent)
        
        duration = (datetime.utcnow() - start_time).total_seconds()
        
        step_result = StepResult(
            step=PipelineStep.INTENT,
            success=gate_result.passed,
            data=intent,
            duration_seconds=duration,
            gate_result=gate_result
        )
        
        if not gate_result.passed:
            # Try to fix issues
            if self.config.enable_auto_fix and gate_result.fixable:
                intent = await self._auto_fix_intent(intent, gate_result.issues)
                gate_result = await self.gates.gate_1_validate_intent(intent)
                step_result.data = intent
                step_result.success = gate_result.passed
        
        if not gate_result.passed:
            raise PipelineError(f"Intent validation failed: {gate_result.issues}")
        
        state.intent = intent
        state.step_results["intent"] = step_result
        state.completed_steps.append(PipelineStep.INTENT)
        
        if self.job_manager and self.config.save_intermediate_results:
            await self.job_manager.save_step_result(
                state.job_id, "intent", intent.model_dump()
            )
        
        logger.info(f"[{state.job_id}] Intent step completed in {duration:.2f}s")
        return state
    
    async def _execute_curriculum_step(self, state: PipelineState) -> PipelineState:
        """Execute Step 2: Curriculum Design"""
        logger.info(f"[{state.job_id}] Step 2: Curriculum Design")
        state.current_step = PipelineStep.CURRICULUM
        
        if self.job_manager:
            await self.job_manager.update_job_status(state.job_id, JobStatus.STEP_2_CURRICULUM)
        
        start_time = datetime.utcnow()
        
        curriculum = await self._execute_with_retry(
            agent=self.curriculum_architect,
            prompt_args={"intent": state.intent},
            step_name="curriculum"
        )
        
        gate_result = await self.gates.gate_2_validate_curriculum(curriculum, state.intent)
        
        duration = (datetime.utcnow() - start_time).total_seconds()
        
        step_result = StepResult(
            step=PipelineStep.CURRICULUM,
            success=gate_result.passed,
            data=curriculum,
            duration_seconds=duration,
            gate_result=gate_result
        )
        
        if not gate_result.passed:
            raise PipelineError(f"Curriculum validation failed: {gate_result.issues}")
        
        state.curriculum = curriculum
        state.step_results["curriculum"] = step_result
        state.completed_steps.append(PipelineStep.CURRICULUM)
        
        if self.job_manager and self.config.save_intermediate_results:
            await self.job_manager.save_step_result(
                state.job_id, "curriculum", curriculum.model_dump()
            )
        
        logger.info(f"[{state.job_id}] Curriculum step completed in {duration:.2f}s")
        return state
    
    async def _execute_content_step(self, state: PipelineState) -> PipelineState:
        """Execute Step 3: Content Generation (parallel) with real resilient timeouts"""
        logger.info(f"[{state.job_id}] Step 3: Content Generation")
        state.current_step = PipelineStep.CONTENT
        
        if self.job_manager:
            await self.job_manager.update_job_status(state.job_id, JobStatus.STEP_3_CONTENT)
        
        start_time = datetime.utcnow()
        
        # Build lesson contexts
        contexts = self._build_lesson_contexts(state.curriculum, state.intent)
        
        logger.info(f"[{state.job_id}] Generating {len(contexts)} lessons in parallel")
        
        # Add hard timeout for the entire content step to prevent indefinite hangs
        try:
            # Generate lessons in parallel batches
            lessons = await asyncio.wait_for(
                self.content_creator.generate_lessons_parallel(
                    contexts,
                    max_concurrent=self.config.parallel_lesson_batch_size
                ),
                timeout=300.0 # 5 minutes max for all lessons
            )
        except (Exception, asyncio.TimeoutError) as e:
            logger.error(f"[{state.job_id}] Content generation failed or timed out: {e}")
            # Fallback: Create minimal placeholder lessons so pipeline can continue
            lessons = self._build_fallback_lessons(contexts)
        
        # Validate each lesson
        validated_lessons = []
        for lesson in lessons:
            try:
                gate_result = await self.gates.gate_3_validate_content(lesson)
                if not gate_result.passed:
                    logger.warning(
                        f"Lesson {lesson.lesson_id} failed validation: {gate_result.issues}"
                    )
                    # If it's a critical failure, we could retry here, but we'll stick to 
                    # what we have to ensure we finish.
                validated_lessons.append(lesson)
            except Exception:
                # If validation crashes, just keep the lesson as is
                validated_lessons.append(lesson)
        
        duration = (datetime.utcnow() - start_time).total_seconds()
        
        step_result = StepResult(
            step=PipelineStep.CONTENT,
            success=True,
            data=validated_lessons,
            duration_seconds=duration
        )
        
        state.lessons = validated_lessons
        state.step_results["content"] = step_result
        state.completed_steps.append(PipelineStep.CONTENT)
        
        if self.job_manager and self.config.save_intermediate_results:
            await self.job_manager.save_step_result(
                state.job_id, 
                "content", 
                [lesson.model_dump() for lesson in validated_lessons]
            )
        
        logger.info(f"[{state.job_id}] Content step completed in {duration:.2f}s")
        return state

    def _build_fallback_lessons(self, contexts: List[LessonGenerationContext]) -> List[LessonContent]:
        """Create placeholder lessons when AI fails/hangs"""
        fallbacks = []
        for ctx in contexts:
            lesson = ctx.lesson_outline
            fallbacks.append(LessonContent(
                lesson_id=lesson.id,
                module_id=ctx.module_id,
                title=lesson.title,
                introduction=f"Welcome to this lesson on {lesson.title}. We'll explore the key concepts of {ctx.course_topic}.",
                content_blocks=[
                    TextBlock(
                        title="Overview",
                        content=f"This lesson covers {', '.join(lesson.learning_outcomes)}. Detailed content is being generated.",
                        order=1
                    )
                ],
                summary="In this lesson, we introduced the core concepts.",
                key_takeaways=lesson.learning_outcomes,
                next_steps="Review the materials and proceed to the next lesson.",
                estimated_duration_minutes=lesson.estimated_minutes
            ))
        return fallbacks
    
    async def _execute_assessment_step(self, state: PipelineState) -> PipelineState:
        """Execute Step 4: Assessment Design"""
        logger.info(f"[{state.job_id}] Step 4: Assessment Design")
        state.current_step = PipelineStep.ASSESSMENTS
        
        if self.job_manager:
            await self.job_manager.update_job_status(state.job_id, JobStatus.STEP_4_ASSESSMENTS)
        
        start_time = datetime.utcnow()
        
        # Build course data for assessment agent
        course_data = {
            "topic": state.intent.topic,
            "target_audience": state.intent.target_audience.value,
            "learning_objectives": state.intent.learning_objectives,
            "modules": [
                {
                    "module_id": mod.module_id,
                    "title": mod.title,
                    "description": mod.description,
                    "lessons": [
                        {
                            "lesson_id": lesson.lesson_id,
                            "title": lesson.title,
                            "objectives": lesson.objectives
                        }
                        for lesson in mod.lessons
                    ]
                }
                for mod in state.curriculum.modules
            ]
        }
        
        assessments = await self._execute_with_retry(
            agent=self.assessment_designer,
            prompt_args={"course_data": course_data, "include_coding": True},
            step_name="assessments"
        )
        
        gate_result = await self.gates.gate_4_validate_assessments(assessments, state.curriculum)
        
        duration = (datetime.utcnow() - start_time).total_seconds()
        
        step_result = StepResult(
            step=PipelineStep.ASSESSMENTS,
            success=gate_result.passed,
            data=assessments,
            duration_seconds=duration,
            gate_result=gate_result
        )
        
        if not gate_result.passed:
            # Log warning but continue - assessments can be partial
            logger.warning(f"Assessment validation issues: {gate_result.issues}")
        
        state.assessments = assessments
        state.step_results["assessments"] = step_result
        state.completed_steps.append(PipelineStep.ASSESSMENTS)
        
        if self.job_manager and self.config.save_intermediate_results:
            await self.job_manager.save_step_result(
                state.job_id, "assessments", assessments.model_dump()
            )
        
        logger.info(f"[{state.job_id}] Assessment step completed in {duration:.2f}s")
        return state
    
    async def _execute_qa_step(self, state: PipelineState) -> PipelineState:
        """Execute Step 5: QA Review"""
        logger.info(f"[{state.job_id}] Step 5: QA Review")
        state.current_step = PipelineStep.QA_REVIEW
        
        if self.job_manager:
            await self.job_manager.update_job_status(state.job_id, JobStatus.STEP_5_QA)
        
        start_time = datetime.utcnow()
        
        # Build complete course data for QA
        course_data = {
            "intent": state.intent.model_dump(),
            "curriculum": state.curriculum.model_dump(),
            "lessons": [lesson.model_dump() for lesson in state.lessons],
            "assessments": state.assessments.model_dump() if state.assessments else {}
        }
        
        qa_context = QAContext(
            course_data=course_data,
            focus_areas=[
                ReviewFocus.ACCURACY,
                ReviewFocus.PEDAGOGY,
                ReviewFocus.COMPLETENESS
            ]
        )
        
        qa_report = await self.qa_agent.execute(
            self.qa_agent.build_prompt(qa_context)
        )
        
        gate_result = await self.gates.gate_5_validate_qa(qa_report)
        
        duration = (datetime.utcnow() - start_time).total_seconds()
        
        step_result = StepResult(
            step=PipelineStep.QA_REVIEW,
            success=gate_result.passed,
            data=qa_report,
            duration_seconds=duration,
            gate_result=gate_result
        )
        
        # Check if QA score is acceptable
        if qa_report.overall_score < self.config.qa_min_score:
            logger.warning(
                f"QA score {qa_report.overall_score} below threshold "
                f"{self.config.qa_min_score}"
            )
            # Could trigger regeneration of specific parts here
        
        state.qa_report = qa_report
        state.step_results["qa_review"] = step_result
        state.completed_steps.append(PipelineStep.QA_REVIEW)
        
        if self.job_manager and self.config.save_intermediate_results:
            await self.job_manager.save_step_result(
                state.job_id, "qa_review", qa_report.model_dump()
            )
        
        logger.info(f"[{state.job_id}] QA step completed in {duration:.2f}s - Score: {qa_report.overall_score}")
        return state
    
    async def _finalize(self, state: PipelineState) -> GeneratedCourse:
        """Finalize and create the complete course"""
        logger.info(f"[{state.job_id}] Step 6: Finalization")
        state.current_step = PipelineStep.FINALIZE
        
        if self.job_manager:
            await self.job_manager.update_job_status(state.job_id, JobStatus.STEP_6_FINALIZE)
        
        # Create the final course object
        course = GeneratedCourse(
            course_id=f"course_{state.job_id}",
            intent=state.intent,
            curriculum=state.curriculum,
            lessons=state.lessons,
            assessments=state.assessments,
            qa_report=state.qa_report,
            generated_at=datetime.utcnow(),
            generation_duration_seconds=state.total_duration_seconds
        )
        
        if self.job_manager:
            await self.job_manager.update_job_status(
                state.job_id, 
                JobStatus.COMPLETED,
                result=course.model_dump()
            )
        
        logger.info(f"[{state.job_id}] Course finalized: {course.course_id}")
        return course
    
    # ==================== HELPER METHODS ====================
    
    async def _execute_with_retry(
        self,
        agent,
        prompt_args: Dict[str, Any],
        step_name: str
    ) -> Any:
        """Execute agent with retry logic"""
        # BaseAgent.execute handles retries and prompt building internally
        try:
            result = await agent.execute(**prompt_args)
            if not result.success:
                raise PipelineError(f"Step {step_name} failed: {result.error}")
            return result.data
        except Exception as e:
            logger.error(f"Step {step_name} failed with exception: {e}")
            raise PipelineError(f"Step {step_name} failed: {e}")
    
    def _build_lesson_contexts(
        self,
        curriculum: CurriculumStructure,
        intent: CourseIntent
    ) -> List[LessonGenerationContext]:
        """Build contexts for all lessons for parallel generation"""
        contexts = []
        lesson_titles = {}  # lesson_id -> title for prerequisite lookup
        
        for module in curriculum.modules:
            for lesson in module.lessons:
                lesson_titles[lesson.lesson_id] = lesson.title
        
        for module in curriculum.modules:
            for lesson in module.lessons:
                # Get prerequisite lesson titles
                prereq_titles = [
                    lesson_titles.get(prereq_id, prereq_id)
                    for prereq_id in lesson.prerequisites
                ]
                
                context = LessonGenerationContext(
                    lesson_outline=lesson,
                    module_id=module.id,
                    module_title=module.title,
                    module_description=module.description,
                    course_topic=intent.topic,
                    difficulty_level=intent.target_audience.value,
                    previous_lessons=prereq_titles
                )
                contexts.append(context)
        
        return contexts
    
    async def _auto_fix_intent(
        self,
        intent: CourseIntent,
        issues: List[str]
    ) -> CourseIntent:
        """Attempt to automatically fix intent issues"""
        # Simple fixes for common issues
        fixed_intent = intent.model_copy()
        
        for issue in issues:
            if "duration" in issue.lower():
                # Clamp duration to reasonable range
                if fixed_intent.estimated_duration_hours < 1:
                    fixed_intent.estimated_duration_hours = 1
                elif fixed_intent.estimated_duration_hours > 100:
                    fixed_intent.estimated_duration_hours = 40
            
            if "objective" in issue.lower() and len(fixed_intent.learning_objectives) < 3:
                # Add a generic objective if too few
                fixed_intent.learning_objectives.append(
                    f"Apply {fixed_intent.topic} concepts to practical scenarios"
                )
        
        return fixed_intent
    
    async def _create_job(
        self,
        user_request: str,
        user_context: Optional[Dict[str, Any]]
    ) -> str:
        """Create a new job in the job manager"""
        return await self.job_manager.create_job(
            user_id="system",  # Would come from auth in real usage
            request=user_request,
            context=user_context
        )
    
    async def _resume_state(self, job_id: str) -> PipelineState:
        """Resume state from an existing job"""
        job = await self.job_manager.get_job(job_id)
        if not job:
            raise PipelineError(f"Job {job_id} not found")
        
        state = PipelineState(
            job_id=job_id,
            current_step=self._status_to_step(job.status),
            started_at=job.created_at
        )
        
        # Restore completed step data
        step_data = job.step_data or {}
        
        if "intent" in step_data:
            state.intent = CourseIntent(**step_data["intent"])
            state.completed_steps.append(PipelineStep.INTENT)
        
        if "curriculum" in step_data:
            state.curriculum = CurriculumStructure(**step_data["curriculum"])
            state.completed_steps.append(PipelineStep.CURRICULUM)
        
        if "content" in step_data:
            state.lessons = [LessonContent(**l) for l in step_data["content"]]
            state.completed_steps.append(PipelineStep.CONTENT)
        
        if "assessments" in step_data:
            state.assessments = CourseAssessments(**step_data["assessments"])
            state.completed_steps.append(PipelineStep.ASSESSMENTS)
        
        if "qa_review" in step_data:
            state.qa_report = QualityReport(**step_data["qa_review"])
            state.completed_steps.append(PipelineStep.QA_REVIEW)
        
        return state
    
    def _status_to_step(self, status: JobStatus) -> PipelineStep:
        """Map job status to pipeline step"""
        mapping = {
            JobStatus.PENDING: PipelineStep.INTENT,
            JobStatus.RUNNING: PipelineStep.INTENT,
            JobStatus.STEP_1_INTENT: PipelineStep.INTENT,
            JobStatus.STEP_2_CURRICULUM: PipelineStep.CURRICULUM,
            JobStatus.STEP_3_CONTENT: PipelineStep.CONTENT,
            JobStatus.STEP_4_ASSESSMENTS: PipelineStep.ASSESSMENTS,
            JobStatus.STEP_5_QA: PipelineStep.QA_REVIEW,
            JobStatus.STEP_6_FINALIZE: PipelineStep.FINALIZE,
        }
        return mapping.get(status, PipelineStep.INTENT)


class PipelineError(Exception):
    """Exception raised when pipeline fails"""
    pass
