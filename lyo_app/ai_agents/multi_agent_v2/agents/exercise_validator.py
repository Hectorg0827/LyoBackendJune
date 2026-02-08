"""
Exercise Validator - Smart Answer Validation System

MIT Architecture Engineering - Comprehensive Exercise Validation

This module provides:
- Multiple answer type validation (text, code, multiple choice)
- Code execution in sandboxed environment
- Partial credit scoring
- Detailed feedback generation
"""

import logging
import re
import subprocess
import tempfile
import os
from typing import Optional, Dict, Any, List, Union
from enum import Enum
from pydantic import BaseModel, Field
from datetime import datetime
import google.generativeai as genai

from lyo_app.core.config import settings

logger = logging.getLogger(__name__)


class AnswerType(str, Enum):
    """Types of answers that can be validated"""
    MULTIPLE_CHOICE = "multiple_choice"
    TRUE_FALSE = "true_false"
    SHORT_ANSWER = "short_answer"
    CODE = "code"
    ESSAY = "essay"
    FILL_BLANK = "fill_blank"


class ValidationResult(BaseModel):
    """Result of validating an answer"""
    is_correct: bool
    score: float = Field(ge=0.0, le=1.0)
    feedback: str
    detailed_feedback: Optional[str] = None
    hints: List[str] = Field(default_factory=list)
    correct_answer: Optional[str] = None
    partial_credit_breakdown: Optional[Dict[str, float]] = None


class CodeExecutionResult(BaseModel):
    """Result of executing code"""
    success: bool
    output: str
    error: Optional[str] = None
    execution_time_ms: float
    memory_used_mb: Optional[float] = None


class ExerciseContext(BaseModel):
    """Context for an exercise being validated"""
    exercise_id: str
    exercise_type: AnswerType
    question: str
    expected_answer: Optional[str] = None
    expected_output: Optional[str] = None
    test_cases: Optional[List[Dict[str, Any]]] = None
    grading_rubric: Optional[Dict[str, Any]] = None
    max_points: int = 100
    language: Optional[str] = None  # For code exercises


class ExerciseValidator:
    """
    Validates exercise answers with support for multiple answer types.
    
    Features:
    - Multiple choice validation
    - Code execution and validation
    - AI-powered essay/short answer grading
    - Partial credit calculation
    - Detailed feedback generation
    """
    
    def __init__(self):
        self.name = "exercise_validator"
        self._available = False
        self.model = None
        
        # Initialize Gemini for AI-powered validation
        api_key = getattr(settings, 'google_api_key', None) or getattr(settings, 'gemini_api_key', None)
        if api_key:
            try:
                genai.configure(api_key=api_key)
                self.model = genai.GenerativeModel(
                    "gemini-2.0-flash",
                    generation_config={
                        "temperature": 0.3,
                        "max_output_tokens": 1024,
                    }
                )
                self._available = True
                logger.info("ExerciseValidator initialized successfully")
            except Exception as e:
                logger.warning(f"ExerciseValidator: Failed to initialize Gemini: {e}")
        else:
            logger.warning("ExerciseValidator: No API key found")
    
    @property
    def is_available(self) -> bool:
        return self._available
    
    async def validate(
        self,
        user_answer: str,
        context: ExerciseContext
    ) -> ValidationResult:
        """
        Validate an answer based on exercise type.
        """
        validators = {
            AnswerType.MULTIPLE_CHOICE: self._validate_multiple_choice,
            AnswerType.TRUE_FALSE: self._validate_true_false,
            AnswerType.SHORT_ANSWER: self._validate_short_answer,
            AnswerType.CODE: self._validate_code,
            AnswerType.ESSAY: self._validate_essay,
            AnswerType.FILL_BLANK: self._validate_fill_blank,
        }
        
        validator = validators.get(context.exercise_type)
        if validator:
            return await validator(user_answer, context)
        
        return ValidationResult(
            is_correct=False,
            score=0.0,
            feedback="Unknown exercise type",
            hints=[]
        )
    
    async def _validate_multiple_choice(
        self,
        user_answer: str,
        context: ExerciseContext
    ) -> ValidationResult:
        """Validate multiple choice answer"""
        expected = (context.expected_answer or "").strip().upper()
        given = user_answer.strip().upper()
        
        is_correct = given == expected
        
        return ValidationResult(
            is_correct=is_correct,
            score=1.0 if is_correct else 0.0,
            feedback="Correct!" if is_correct else f"Not quite. The correct answer is {expected}.",
            correct_answer=expected if not is_correct else None,
            hints=[] if is_correct else ["Review the options carefully."]
        )
    
    async def _validate_true_false(
        self,
        user_answer: str,
        context: ExerciseContext
    ) -> ValidationResult:
        """Validate true/false answer"""
        expected = (context.expected_answer or "").strip().lower()
        given = user_answer.strip().lower()
        
        # Normalize answers
        true_values = ["true", "t", "yes", "1"]
        false_values = ["false", "f", "no", "0"]
        
        expected_bool = expected in true_values
        given_bool = given in true_values
        
        is_correct = expected_bool == given_bool
        
        return ValidationResult(
            is_correct=is_correct,
            score=1.0 if is_correct else 0.0,
            feedback="Correct!" if is_correct else f"The answer is {'True' if expected_bool else 'False'}.",
            correct_answer=str(expected_bool) if not is_correct else None
        )
    
    async def _validate_short_answer(
        self,
        user_answer: str,
        context: ExerciseContext
    ) -> ValidationResult:
        """Validate short answer using AI"""
        if not self._available:
            # Fallback to simple string matching
            expected = (context.expected_answer or "").strip().lower()
            given = user_answer.strip().lower()
            is_correct = expected in given or given in expected
            
            return ValidationResult(
                is_correct=is_correct,
                score=1.0 if is_correct else 0.0,
                feedback="Your answer has been recorded." if is_correct else "Please review your answer."
            )
        
        try:
            prompt = f"""Evaluate this short answer response.

Question: {context.question}
Expected Answer: {context.expected_answer}
Student's Answer: {user_answer}

Evaluate on:
1. Correctness (0-100%)
2. Completeness
3. Accuracy of key concepts

Respond with:
SCORE: [0-100]
CORRECT: [YES/NO]
FEEDBACK: [brief feedback]
HINTS: [if incorrect, provide hint]"""

            response = self.model.generate_content(prompt)
            text = response.text
            
            # Parse response
            score_match = re.search(r'SCORE:\s*(\d+)', text)
            correct_match = re.search(r'CORRECT:\s*(YES|NO)', text, re.IGNORECASE)
            feedback_match = re.search(r'FEEDBACK:\s*(.+?)(?=HINTS:|$)', text, re.DOTALL)
            hints_match = re.search(r'HINTS:\s*(.+?)$', text, re.DOTALL)
            
            score = int(score_match.group(1)) / 100 if score_match else 0.5
            is_correct = correct_match.group(1).upper() == "YES" if correct_match else score >= 0.7
            feedback = feedback_match.group(1).strip() if feedback_match else "Answer evaluated."
            hints = [hints_match.group(1).strip()] if hints_match and not is_correct else []
            
            return ValidationResult(
                is_correct=is_correct,
                score=score,
                feedback=feedback,
                hints=hints
            )
            
        except Exception as e:
            logger.error(f"Short answer validation error: {e}")
            return ValidationResult(
                is_correct=False,
                score=0.5,
                feedback="Your answer has been recorded for review."
            )
    
    async def _validate_code(
        self,
        user_code: str,
        context: ExerciseContext
    ) -> ValidationResult:
        """Validate code by executing it"""
        language = context.language or "python"
        
        if language.lower() != "python":
            return ValidationResult(
                is_correct=False,
                score=0.0,
                feedback=f"Language '{language}' is not currently supported for execution.",
                hints=["Currently only Python is supported."]
            )
        
        # Execute the code
        execution_result = await self.execute_code(user_code, language)
        
        if not execution_result.success:
            return ValidationResult(
                is_correct=False,
                score=0.0,
                feedback=f"Code execution error: {execution_result.error}",
                hints=["Check your code for syntax errors."],
                detailed_feedback=execution_result.error
            )
        
        # Check against expected output
        if context.expected_output:
            expected = context.expected_output.strip()
            actual = execution_result.output.strip()
            
            is_correct = actual == expected
            
            if is_correct:
                return ValidationResult(
                    is_correct=True,
                    score=1.0,
                    feedback="Correct! Your code produces the expected output.",
                    detailed_feedback=f"Output: {actual}"
                )
            else:
                return ValidationResult(
                    is_correct=False,
                    score=0.3,  # Partial credit for running code
                    feedback="Your code runs but produces different output than expected.",
                    detailed_feedback=f"Expected: {expected}\nGot: {actual}",
                    hints=["Compare your output with the expected result."]
                )
        
        # Check against test cases
        if context.test_cases:
            passed = 0
            total = len(context.test_cases)
            failed_cases = []
            
            for i, test_case in enumerate(context.test_cases):
                test_input = test_case.get("input", "")
                expected_output = test_case.get("expected", "")
                
                # Create test code
                test_code = f"{user_code}\n\n# Test case {i+1}\n{test_input}"
                test_result = await self.execute_code(test_code, language)
                
                if test_result.success and test_result.output.strip() == expected_output.strip():
                    passed += 1
                else:
                    failed_cases.append(f"Test {i+1}: Expected '{expected_output}', got '{test_result.output}'")
            
            score = passed / total
            is_correct = passed == total
            
            return ValidationResult(
                is_correct=is_correct,
                score=score,
                feedback=f"Passed {passed}/{total} test cases.",
                detailed_feedback="\n".join(failed_cases) if failed_cases else None,
                hints=["Review the failing test cases."] if not is_correct else [],
                partial_credit_breakdown={"test_cases": score}
            )
        
        # No expected output or test cases - just check if it runs
        return ValidationResult(
            is_correct=True,
            score=0.8,
            feedback="Your code runs successfully!",
            detailed_feedback=f"Output: {execution_result.output}",
            hints=["Consider adding more test cases to verify correctness."]
        )
    
    async def execute_code(
        self,
        code: str,
        language: str = "python",
        timeout: int = 5
    ) -> CodeExecutionResult:
        """
        Execute code in a sandboxed environment.
        
        WARNING: This is a basic implementation. In production,
        use a proper sandbox like Docker or a code execution service.
        """
        if language.lower() != "python":
            return CodeExecutionResult(
                success=False,
                output="",
                error=f"Language '{language}' not supported",
                execution_time_ms=0
            )
        
        start_time = datetime.now()
        
        try:
            # Create a temporary file
            with tempfile.NamedTemporaryFile(
                mode='w',
                suffix='.py',
                delete=False
            ) as f:
                f.write(code)
                temp_file = f.name
            
            try:
                # Execute with timeout
                result = subprocess.run(
                    ['python3', temp_file],
                    capture_output=True,
                    text=True,
                    timeout=timeout,
                    env={**os.environ, 'PYTHONDONTWRITEBYTECODE': '1'}
                )
                
                execution_time = (datetime.now() - start_time).total_seconds() * 1000
                
                if result.returncode == 0:
                    return CodeExecutionResult(
                        success=True,
                        output=result.stdout,
                        execution_time_ms=execution_time
                    )
                else:
                    return CodeExecutionResult(
                        success=False,
                        output=result.stdout,
                        error=result.stderr,
                        execution_time_ms=execution_time
                    )
                    
            finally:
                # Clean up temp file
                os.unlink(temp_file)
                
        except subprocess.TimeoutExpired:
            return CodeExecutionResult(
                success=False,
                output="",
                error=f"Code execution timed out after {timeout} seconds",
                execution_time_ms=timeout * 1000
            )
        except Exception as e:
            return CodeExecutionResult(
                success=False,
                output="",
                error=str(e),
                execution_time_ms=0
            )
    
    async def _validate_essay(
        self,
        user_answer: str,
        context: ExerciseContext
    ) -> ValidationResult:
        """Validate essay using AI"""
        if not self._available:
            return ValidationResult(
                is_correct=True,
                score=0.7,
                feedback="Your essay has been submitted for review."
            )
        
        try:
            rubric = context.grading_rubric or {
                "content": 40,
                "organization": 30,
                "clarity": 30
            }
            
            prompt = f"""Grade this essay response.

Question/Prompt: {context.question}
Student's Essay: {user_answer}

Grading Rubric:
{rubric}

Provide:
1. Overall score (0-100)
2. Breakdown by rubric criteria
3. Constructive feedback
4. Suggestions for improvement

Format:
SCORE: [0-100]
BREAKDOWN: [criteria: score]
FEEDBACK: [main feedback]
SUGGESTIONS: [list of suggestions]"""

            response = self.model.generate_content(prompt)
            text = response.text
            
            # Parse response
            score_match = re.search(r'SCORE:\s*(\d+)', text)
            feedback_match = re.search(r'FEEDBACK:\s*(.+?)(?=SUGGESTIONS:|$)', text, re.DOTALL)
            suggestions_match = re.search(r'SUGGESTIONS:\s*(.+?)$', text, re.DOTALL)
            
            score = int(score_match.group(1)) / 100 if score_match else 0.7
            feedback = feedback_match.group(1).strip() if feedback_match else "Essay evaluated."
            suggestions = suggestions_match.group(1).strip() if suggestions_match else ""
            
            return ValidationResult(
                is_correct=score >= 0.6,
                score=score,
                feedback=feedback,
                detailed_feedback=suggestions,
                hints=[]
            )
            
        except Exception as e:
            logger.error(f"Essay validation error: {e}")
            return ValidationResult(
                is_correct=True,
                score=0.7,
                feedback="Your essay has been submitted for review."
            )
    
    async def _validate_fill_blank(
        self,
        user_answer: str,
        context: ExerciseContext
    ) -> ValidationResult:
        """Validate fill-in-the-blank answer"""
        expected = (context.expected_answer or "").strip().lower()
        given = user_answer.strip().lower()
        
        # Allow for minor variations
        is_correct = (
            given == expected or
            given.replace(" ", "") == expected.replace(" ", "") or
            given in expected or
            expected in given
        )
        
        if not is_correct and self._available:
            # Use AI to check semantic equivalence
            try:
                prompt = f"""Are these two answers semantically equivalent?
Expected: {expected}
Given: {given}

Answer YES or NO, followed by a brief explanation."""

                response = self.model.generate_content(prompt)
                is_correct = "YES" in response.text.upper()
            except:
                pass
        
        return ValidationResult(
            is_correct=is_correct,
            score=1.0 if is_correct else 0.0,
            feedback="Correct!" if is_correct else f"The expected answer was: {context.expected_answer}",
            correct_answer=context.expected_answer if not is_correct else None,
            hints=[] if is_correct else ["Check your spelling and try again."]
        )
    
    async def get_hint(
        self,
        context: ExerciseContext,
        previous_attempts: List[str] = None,
        hint_level: int = 1
    ) -> str:
        """Generate a hint for an exercise"""
        if not self._available:
            return "Think carefully about the question and what you've learned."
        
        try:
            attempts_text = ""
            if previous_attempts:
                attempts_text = f"\nStudent's previous attempts: {previous_attempts}"
            
            prompt = f"""Generate a hint for this exercise.

Question: {context.question}
Exercise Type: {context.exercise_type.value}
Hint Level: {hint_level} (1=subtle, 2=moderate, 3=strong)
{attempts_text}

Provide a helpful hint that guides without giving away the answer.
Make it appropriate for the hint level."""

            response = self.model.generate_content(prompt)
            return response.text
            
        except Exception as e:
            logger.error(f"Hint generation error: {e}")
            return "Consider reviewing the relevant concepts from the lesson."


# Singleton instance
_validator: Optional[ExerciseValidator] = None


def get_exercise_validator() -> ExerciseValidator:
    """Get or create the singleton ExerciseValidator instance"""
    global _validator
    if _validator is None:
        _validator = ExerciseValidator()
    return _validator
