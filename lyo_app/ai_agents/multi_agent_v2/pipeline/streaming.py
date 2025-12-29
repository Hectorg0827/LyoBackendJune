"""
Streaming support for real-time progress updates during course generation.
"""

from typing import AsyncIterator
from dataclasses import dataclass
import json


@dataclass
class ProgressEvent:
    """Progress event for streaming updates"""
    type: str  # "started", "agent_working", "lesson_complete", "progress", "cost_update", "completed", "error"
    progress_percent: int
    message: str
    data: dict = None
    
    def to_sse(self) -> str:
        """Convert to Server-Sent Events format"""
        event_data = {
            "type": self.type,
            "progress": self.progress_percent,
            "message": self.message
        }
        if self.data:
            event_data["data"] = self.data
        
        return f"data: {json.dumps(event_data)}\n\n"


class StreamingPipeline:
    """Mixin to add streaming capabilities to CourseGenerationPipeline"""
    
    async def generate_course_with_streaming(
        self,
        user_request: str,
        user_context: dict = None,
        job_id: str = None
    ) -> AsyncIterator[ProgressEvent]:
        """
        Generate course with real-time progress streaming.
        
        Yields ProgressEvent objects that can be sent as SSE to clients.
        """
        # Emit start event
        yield ProgressEvent(
            type="started",
            progress_percent=0,
            message=f"Starting course generation with {self.config.quality_tier.value} quality tier",
            data={"quality_tier": self.config.quality_tier.value}
        )
        
        try:
            # Initialize state (similar to generate_course but with streaming)
            if job_id and self.job_manager:
                state = await self._resume_state(job_id)
            else:
                job_id = await self._create_job(user_request, user_context) if self.job_manager else "local"
                state = PipelineState(
                    job_id=job_id,
                    current_step=PipelineStep.INTENT,
                    started_at=datetime.utcnow()
                )
            
            # Step 1: Intent Analysis
            if PipelineStep.INTENT not in state.completed_steps:
                yield ProgressEvent(
                    type="agent_working",
                    progress_percent=5,
                    message="Analyzing your request and planning the course structure...",
                    data={"agent": "orchestrator", "step": "intent"}
                )
                
                state = await self._execute_intent_step(state, user_request, user_context)
                
                yield ProgressEvent(
                    type="progress",
                    progress_percent=15,
                    message=f"Course plan created: {state.intent.topic}",
                    data={
                        "topic": state.intent.topic,
                        "estimated_duration": state.intent.estimated_duration_hours
                    }
                )
            
            # Step 2: Curriculum Design
            if PipelineStep.CURRICULUM not in state.completed_steps:
                yield ProgressEvent(
                    type="agent_working",
                    progress_percent=20,
                    message="Designing curriculum structure with modules and lessons...",
                    data={"agent": "curriculum_architect", "step": "curriculum"}
                )
                
                state = await self._execute_curriculum_step(state)
                
                yield ProgressEvent(
                    type="progress",
                    progress_percent=30,
                    message=f"Curriculum ready: {state.curriculum.module_count} modules, {state.curriculum.lesson_count} lessons",
                    data={
                        "modules": state.curriculum.module_count,
                        "lessons": state.curriculum.lesson_count
                    }
                )
            
            # Step 3: Content Generation (with per-lesson progress)
            if PipelineStep.CONTENT not in state.completed_steps:
                total_lessons = state.curriculum.lesson_count
                
                yield ProgressEvent(
                    type="agent_working",
                    progress_percent=35,
                    message=f"Generating {total_lessons} lessons in parallel...",
                    data={"agent": "content_creator", "step": "content", "total_lessons": total_lessons}
                )
                
                # Generate lessons with progress tracking
                contexts = self._build_lesson_contexts(state.curriculum, state.intent)
                lessons = []
                
                # Process in batches for progress updates
                batch_size = self.config.parallel_lesson_batch_size
                for i in range(0, len(contexts), batch_size):
                    batch = contexts[i:i + batch_size]
                    batch_lessons = await self.content_creator.generate_lessons_parallel(
                        batch,
                        max_concurrent=batch_size
                    )
                    lessons.extend(batch_lessons)
                    
                    # Update progress
                    completed = len(lessons)
                    progress = 35 + int((completed / total_lessons) * 35)  # 35-70% range
                    
                    yield ProgressEvent(
                        type="lesson_complete",
                        progress_percent=progress,
                        message=f"Generated lessons {completed}/{total_lessons}",
                        data={
                            "completed": completed,
                            "total": total_lessons,
                            "latest_lesson": batch_lessons[-1].title if batch_lessons else None
                        }
                    )
                
                # Validate lessons
                validated_lessons = []
                for lesson in lessons:
                    gate_result = await self.gates.gate_3_validate_content(lesson)
                    if not gate_result.passed and self.config.enable_auto_fix:
                        ctx = next(c for c in contexts if c.lesson_outline.lesson_id == lesson.lesson_id)
                        lesson = await self.content_creator.generate_lesson(ctx)
                    validated_lessons.append(lesson)
                
                state.lessons = validated_lessons
                state.completed_steps.append(PipelineStep.CONTENT)
            
            # Step 4: Assessments
            if PipelineStep.ASSESSMENTS not in state.completed_steps:
                yield ProgressEvent(
                    type="agent_working",
                    progress_percent=75,
                    message="Creating quizzes and assessments...",
                    data={"agent": "assessment_designer", "step": "assessments"}
                )
                
                state = await self._execute_assessment_step(state)
                
                yield ProgressEvent(
                    type="progress",
                    progress_percent=80,
                    message="Assessments created",
                    data={"quiz_count": len(state.assessments.quiz_questions) if state.assessments else 0}
                )
            
            # Step 5: QA Review
            if PipelineStep.QA_REVIEW not in state.completed_steps:
                yield ProgressEvent(
                    type="agent_working",
                    progress_percent=85,
                    message="Performing quality assurance review...",
                    data={"agent": "qa_agent", "step": "qa_review"}
                )
                
                state = await self._execute_qa_step(state)
                
                yield ProgressEvent(
                    type="progress",
                    progress_percent=92,
                    message=f"QA complete - Score: {state.qa_report.overall_score}/100",
                    data={
                        "qa_score": state.qa_report.overall_score,
                        "passed": state.qa_report.overall_score >= self.config.qa_min_score
                    }
                )
            
            # Step 6: Finalize
            yield ProgressEvent(
                type="agent_working",
                progress_percent=95,
                message="Finalizing course and saving...",
                data={"step": "finalize"}
            )
            
            result = await self._finalize(state)
            
            state.completed_at = datetime.utcnow()
            state.total_duration_seconds = (
                state.completed_at - state.started_at
            ).total_seconds()
            
            # Emit completion
            yield ProgressEvent(
                type="completed",
                progress_percent=100,
                message="Course generation complete!",
                data={
                    "course_id": result.course_id,
                    "generation_time_sec": state.total_duration_seconds,
                    "qa_score": state.qa_report.overall_score,
                    "lesson_count": len(state.lessons)
                }
            )
            
        except Exception as e:
            yield ProgressEvent(
                type="error",
                progress_percent=0,
                message=f"Generation failed: {str(e)}",
                data={"error": str(e)}
            )
            raise
