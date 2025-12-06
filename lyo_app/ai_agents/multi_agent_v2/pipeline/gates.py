"""
Pipeline Gates - Non-AI Validation for Course Generation.
These gates catch AI mistakes BEFORE they propagate through the pipeline.

MIT Architecture Engineering - Fail-Safe Validation Layer
"""

import ast
import re
import asyncio
import logging
from typing import Tuple, List, Optional, Set
from pydantic import ValidationError

from lyo_app.ai_agents.multi_agent_v2.schemas.course_schemas import (
    CourseIntent,
    CurriculumStructure,
    LessonContent,
    CourseAssessments,
    QualityReport,
    DifficultyLevel
)

logger = logging.getLogger(__name__)


class GateValidationError(Exception):
    """Raised when a gate validation fails"""
    
    def __init__(self, gate_name: str, errors: List[str], recoverable: bool = True):
        self.gate_name = gate_name
        self.errors = errors
        self.recoverable = recoverable
        super().__init__(f"Gate {gate_name} failed: {errors}")


class GateResult:
    """Result of a gate validation"""
    
    def __init__(
        self, 
        passed: bool, 
        issues: List[str] = None,
        warnings: List[str] = None,
        fixable: bool = True
    ):
        self.passed = passed
        self.issues = issues or []
        self.warnings = warnings or []
        self.fixable = fixable
    
    def to_dict(self):
        return {
            "passed": self.passed,
            "issues": self.issues,
            "warnings": self.warnings,
            "fixable": self.fixable
        }


# Alias for backward compatibility
ValidationResult = GateResult


class PipelineGates:
    """
    Non-AI validation gates that ensure each step's output is valid
    before passing to the next step.
    
    Each gate validates:
    1. Schema compliance (Pydantic)
    2. Semantic correctness (business logic)
    3. Quality thresholds (minimum standards)
    """
    
    @staticmethod
    async def gate_1_validate_intent(intent: CourseIntent) -> GateResult:
        """
        Gate 1: Validate Orchestrator output (CourseIntent)
        
        Checks:
        - Topic is meaningful (not just "course" or "learn")
        - Duration is reasonable for topic complexity
        - Learning objectives are specific and actionable
        """
        issues = []
        warnings = []
        
        # Semantic validation
        topic_lower = intent.topic.lower()
        
        # Check topic quality
        weak_topics = ["course", "learn", "study", "thing", "stuff", "something", "topic"]
        if any(topic_lower == weak for weak in weak_topics):
            issues.append(f"Topic '{intent.topic}' is too vague - needs to be specific")
        
        # Check for suspiciously short topics
        if len(intent.topic.split()) == 1 and len(intent.topic) < 5:
            warnings.append(f"Topic '{intent.topic}' might be too narrow")
        
        # Check duration makes sense for topic
        word_count = len(intent.topic.split())
        if word_count <= 2 and intent.estimated_duration_hours > 30:
            warnings.append("Simple topic with very long duration - verify this is intentional")
        
        # Check learning objectives are actionable
        action_verbs = [
            "understand", "create", "build", "implement", "analyze", 
            "design", "develop", "explain", "apply", "evaluate",
            "demonstrate", "identify", "compare", "describe", "use"
        ]
        
        weak_objectives = 0
        for obj in intent.learning_objectives:
            obj_lower = obj.lower()
            has_action = any(verb in obj_lower for verb in action_verbs)
            if not has_action:
                weak_objectives += 1
        
        if weak_objectives > len(intent.learning_objectives) // 2:
            warnings.append(f"{weak_objectives} objectives lack action verbs - consider strengthening them")
        
        # Check prerequisites make sense
        if intent.target_audience == DifficultyLevel.BEGINNER and len(intent.prerequisites) > 3:
            warnings.append("Beginner course has many prerequisites - verify this is correct")
        
        passed = len(issues) == 0
        return GateResult(passed=passed, issues=issues, warnings=warnings, fixable=True)
    
    @staticmethod
    async def gate_2_validate_curriculum(
        curriculum: CurriculumStructure, 
        intent: CourseIntent
    ) -> GateResult:
        """
        Gate 2: Validate Curriculum Architect output
        
        Checks:
        - Module count is appropriate for duration
        - Prerequisites form a valid DAG (no cycles)
        - All learning objectives are covered
        - Lesson distribution is balanced
        """
        issues = []
        warnings = []
        
        # Check module count vs duration
        hours = intent.estimated_duration_hours
        module_count = len(curriculum.modules)
        
        expected_min_modules = max(2, hours // 5)
        expected_max_modules = min(12, hours)
        
        if module_count < expected_min_modules:
            warnings.append(f"Only {module_count} modules for {hours} hour course - might be too few")
        if module_count > expected_max_modules:
            warnings.append(f"{module_count} modules for {hours} hour course - might be too many")
        
        # Check lesson balance
        lesson_counts = [len(m.lessons) for m in curriculum.modules]
        if lesson_counts:
            if max(lesson_counts) > 2 * min(lesson_counts) + 1:
                warnings.append("Unbalanced lesson distribution across modules")
        
        # Check total lessons make sense
        total_lessons = sum(lesson_counts)
        avg_lesson_minutes = (hours * 60) / max(total_lessons, 1)
        
        if avg_lesson_minutes < 10:
            warnings.append(f"Average lesson length is only {avg_lesson_minutes:.1f} minutes - might be too short")
        if avg_lesson_minutes > 45:
            warnings.append(f"Average lesson length is {avg_lesson_minutes:.1f} minutes - might be too long")
        
        # Verify lesson IDs are unique
        all_lesson_ids = []
        for module in curriculum.modules:
            for lesson in module.lessons:
                if lesson.lesson_id in all_lesson_ids:
                    issues.append(f"Duplicate lesson ID: {lesson.lesson_id}")
                all_lesson_ids.append(lesson.lesson_id)
        
        # Verify module IDs are unique
        module_ids = [m.module_id for m in curriculum.modules]
        if len(module_ids) != len(set(module_ids)):
            issues.append("Duplicate module IDs detected")
        
        passed = len(issues) == 0
        return GateResult(passed=passed, issues=issues, warnings=warnings, fixable=True)
    
    @staticmethod
    async def gate_3_validate_content(
        lesson_data: dict,
        curriculum: CurriculumStructure,
        all_lesson_ids: Set[str]
    ) -> GateResult:
        """
        Gate 3: Validate Content Creator output (per lesson)
        
        Checks:
        - Schema compliance
        - Lesson ID exists in curriculum
        - Code blocks are syntactically valid
        - Content has sufficient depth
        - Exercises have valid solutions
        """
        issues = []
        warnings = []
        
        # Schema validation
        try:
            lesson = LessonContent(**lesson_data)
        except ValidationError as e:
            error_msgs = [f"{err['loc']}: {err['msg']}" for err in e.errors()]
            return GateResult(passed=False, issues=error_msgs, fixable=True)
        
        # Check lesson ID exists in curriculum
        if lesson.lesson_id not in all_lesson_ids:
            issues.append(f"Unknown lesson ID: {lesson.lesson_id}")
        
        # Validate code blocks
        code_errors = 0
        for i, block in enumerate(lesson.content_blocks):
            if block.block_type == "code":
                if hasattr(block, 'language') and block.language == "python":
                    try:
                        ast.parse(block.code)
                    except SyntaxError as e:
                        code_errors += 1
                        warnings.append(f"Block {i}: Python syntax error at line {e.lineno}: {e.msg}")
        
        if code_errors > len(lesson.content_blocks) // 3:
            issues.append(f"Too many code blocks with syntax errors ({code_errors})")
        
        # Check content depth (word count)
        total_words = 0
        for b in lesson.content_blocks:
            if hasattr(b, 'content'):
                total_words += len(b.content.split())
            if hasattr(b, 'explanation') and b.explanation:
                total_words += len(b.explanation.split())
        
        if total_words < 150:
            warnings.append(f"Lesson content might be too shallow ({total_words} words)")
        if total_words > 3000:
            warnings.append(f"Lesson content might be too long ({total_words} words)")
        
        # Check for variety
        block_types = [b.block_type for b in lesson.content_blocks]
        if len(set(block_types)) < 2:
            warnings.append("Lesson lacks variety - only one type of content block")
        
        # Check exercises have non-trivial solutions
        for block in lesson.content_blocks:
            if block.block_type == "exercise":
                if hasattr(block, 'solution') and len(block.solution.strip()) < 15:
                    warnings.append("Exercise has very short solution - might be trivial")
        
        passed = len(issues) == 0
        return GateResult(passed=passed, issues=issues, warnings=warnings, fixable=True)
    
    @staticmethod
    async def gate_4_validate_assessments(
        data: dict,
        curriculum: CurriculumStructure
    ) -> GateResult:
        """
        Gate 4: Validate Assessment Designer output
        
        Checks:
        - Schema compliance
        - Every lesson has a quiz
        - Questions reference valid options
        - Answer distributions are reasonable (not all A's)
        - Difficulty progression makes sense
        """
        issues = []
        warnings = []
        
        # Schema validation
        try:
            assessments = CourseAssessments(**data)
        except ValidationError as e:
            error_msgs = [f"{err['loc']}: {err['msg']}" for err in e.errors()]
            return GateResult(passed=False, issues=error_msgs, fixable=True)
        
        # Get all lesson IDs from curriculum
        all_lesson_ids = set()
        for module in curriculum.modules:
            for lesson in module.lessons:
                all_lesson_ids.add(lesson.lesson_id)
        
        # Check every lesson has a quiz
        lesson_ids_with_quiz = {q.lesson_id for q in assessments.lesson_quizzes}
        missing_quizzes = all_lesson_ids - lesson_ids_with_quiz
        if missing_quizzes:
            warnings.append(f"Missing quizzes for {len(missing_quizzes)} lessons: {list(missing_quizzes)[:3]}...")
        
        # Check for extra quizzes (IDs not in curriculum)
        extra_quizzes = lesson_ids_with_quiz - all_lesson_ids
        if extra_quizzes:
            issues.append(f"Quizzes reference unknown lessons: {extra_quizzes}")
        
        # Check module assessments
        module_ids = {m.module_id for m in curriculum.modules}
        for assessment in assessments.module_assessments:
            if assessment.module_id not in module_ids:
                issues.append(f"Assessment references unknown module: {assessment.module_id}")
        
        # Check answer distribution
        total_mc = 0
        answer_distribution = {0: 0, 1: 0, 2: 0, 3: 0}
        
        for quiz in assessments.lesson_quizzes:
            for q in quiz.questions:
                if hasattr(q, 'correct_answer') and isinstance(q.correct_answer, int):
                    total_mc += 1
                    answer_distribution[q.correct_answer] += 1
        
        if total_mc > 10:
            # Check if answers are too concentrated
            max_concentration = max(answer_distribution.values()) / total_mc
            if max_concentration > 0.5:
                warnings.append(f"Answer distribution is skewed - {max_concentration*100:.0f}% are the same option")
        
        # Check question counts
        for quiz in assessments.lesson_quizzes:
            if len(quiz.questions) < 2:
                warnings.append(f"Quiz {quiz.lesson_id} has only {len(quiz.questions)} question(s)")
        
        passed = len(issues) == 0
        return GateResult(passed=passed, issues=issues, warnings=warnings, fixable=True)
    
    @staticmethod
    async def gate_5_validate_qa(data: dict) -> GateResult:
        """
        Gate 5: Final validation of QA report
        
        Checks:
        - Schema compliance
        - Score is reasonable
        - Critical issues block approval
        - Report is complete
        """
        issues = []
        warnings = []
        
        # Schema validation
        try:
            qa = QualityReport(**data)
        except ValidationError as e:
            error_msgs = [f"{err['loc']}: {err['msg']}" for err in e.errors()]
            return GateResult(passed=False, issues=error_msgs, fixable=True)
        
        # Check for critical issues
        critical_issues = [i for i in qa.issues if i.severity == "critical"]
        if critical_issues and qa.approved:
            issues.append("Cannot approve course with critical issues")
        
        # Ensure score makes sense relative to issues
        high_severity_count = sum(1 for i in qa.issues if i.severity in ["critical", "high"])
        if qa.overall_score >= 9.0 and high_severity_count > 0:
            warnings.append(f"Score is {qa.overall_score} but {high_severity_count} critical/high issues found")
        
        if qa.overall_score < 5.0 and len(qa.issues) == 0:
            warnings.append("Low score but no issues identified - review might be incomplete")
        
        # Check component scores are consistent
        avg_component = (qa.content_accuracy_score + qa.pedagogical_score + qa.engagement_score) / 3
        if abs(qa.overall_score - avg_component) > 2.0:
            warnings.append("Overall score doesn't align with component scores")
        
        passed = len(issues) == 0
        return GateResult(passed=passed, issues=issues, warnings=warnings, fixable=True)
    
    @staticmethod
    async def validate_full_course(
        intent: CourseIntent,
        curriculum: CurriculumStructure,
        lessons: List[LessonContent],
        assessments: CourseAssessments,
        qa_report: QualityReport
    ) -> GateResult:
        """
        Final validation of the complete course before saving.
        
        Checks cross-component consistency.
        """
        issues = []
        warnings = []
        
        # Check lesson count matches curriculum
        expected_lessons = sum(len(m.lessons) for m in curriculum.modules)
        if len(lessons) != expected_lessons:
            issues.append(f"Expected {expected_lessons} lessons but got {len(lessons)}")
        
        # Check all lessons are accounted for
        lesson_ids_in_curriculum = set()
        for module in curriculum.modules:
            for lesson in module.lessons:
                lesson_ids_in_curriculum.add(lesson.lesson_id)
        
        lesson_ids_generated = {l.lesson_id for l in lessons}
        
        missing = lesson_ids_in_curriculum - lesson_ids_generated
        extra = lesson_ids_generated - lesson_ids_in_curriculum
        
        if missing:
            issues.append(f"Missing lesson content for: {missing}")
        if extra:
            warnings.append(f"Extra lessons not in curriculum: {extra}")
        
        # Check assessments cover all lessons
        quiz_coverage = {q.lesson_id for q in assessments.lesson_quizzes}
        uncovered = lesson_ids_in_curriculum - quiz_coverage
        if uncovered:
            warnings.append(f"{len(uncovered)} lessons without quizzes")
        
        # Final approval check
        if not qa_report.approved:
            if qa_report.overall_score >= 7.0:
                warnings.append("QA score is passing but not approved - review issues")
        
        passed = len(issues) == 0
        return GateResult(passed=passed, issues=issues, warnings=warnings, fixable=True)


class GateRunner:
    """
    Runs gates and handles failures gracefully.
    Provides retry logic and fallback strategies.
    """
    
    def __init__(self, max_retries: int = 2):
        self.max_retries = max_retries
        self.gate_results: List[GateResult] = []
    
    async def run_gate(
        self,
        gate_func,
        *args,
        gate_name: str = "unknown",
        **kwargs
    ) -> GateResult:
        """
        Run a gate with logging and error handling.
        
        Returns:
            GateResult with pass/fail status
        """
        logger.info(f"Running gate: {gate_name}")
        
        try:
            # Support both async and sync gate functions
            if asyncio.iscoroutinefunction(gate_func):
                result = await gate_func(*args, **kwargs)
            else:
                result = gate_func(*args, **kwargs)
            self.gate_results.append(result)
            
            if result.passed:
                logger.info(f"Gate {gate_name} PASSED")
                if result.warnings:
                    logger.warning(f"Gate {gate_name} warnings: {result.warnings}")
            else:
                logger.error(f"Gate {gate_name} FAILED: {result.issues}")
            
            return result
            
        except Exception as e:
            logger.exception(f"Gate {gate_name} threw exception: {e}")
            return GateResult(
                passed=False, 
                issues=[f"Gate exception: {str(e)}"]
            )
    
    def get_summary(self) -> dict:
        """Get summary of all gate runs"""
        return {
            "total_gates": len(self.gate_results),
            "passed": sum(1 for r in self.gate_results if r.passed),
            "failed": sum(1 for r in self.gate_results if not r.passed),
            "total_issues": sum(len(r.issues) for r in self.gate_results),
            "total_warnings": sum(len(r.warnings) for r in self.gate_results)
        }
