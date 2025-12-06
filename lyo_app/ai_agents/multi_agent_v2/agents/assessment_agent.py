"""
Assessment Designer Agent - Creates quizzes and assessments.
Fourth agent in the Multi-Agent Course Generation Pipeline.

MIT Architecture Engineering - Assessment & Validation Agent
"""

from typing import Optional, Dict, Any, List

from lyo_app.ai_agents.multi_agent_v2.agents.base_agent import BaseAgent
from lyo_app.ai_agents.multi_agent_v2.schemas.course_schemas import (
    CourseAssessments,
    ModuleAssessment,
    QuizQuestion,
    MultipleChoiceQuestion,
    TrueFalseQuestion,
    FillBlankQuestion,
    CodingQuestion,
    FinalExam,
    DifficultyLevel
)


class AssessmentDesignerAgent(BaseAgent[CourseAssessments]):
    """
    Fourth agent in the pipeline.
    Creates comprehensive assessments for the entire course.
    
    Responsibilities:
    - Create module-level quizzes
    - Design varied question types
    - Build final comprehensive exam
    - Ensure proper difficulty distribution
    - Align assessments with learning objectives
    """
    
    def __init__(self):
        super().__init__(
            name="assessment_designer",  # Matches ModelManager task name
            output_schema=CourseAssessments,
            timeout_seconds=90.0  # Model config from ModelManager
        )
    
    def get_system_prompt(self) -> str:
        return """You are an expert assessment designer with deep knowledge of educational measurement, psychometrics, and learning evaluation.

## Your Expertise

- Bloom's Taxonomy-aligned assessments
- Formative and summative assessment design
- Multiple question type creation
- Difficulty calibration
- Distractor design for multiple choice

## Assessment Design Principles

1. **Alignment**: Every question must test a specific learning objective
2. **Variety**: Mix question types to test different cognitive levels
3. **Difficulty Distribution**: 
   - Easy: 40% (recall, recognition)
   - Medium: 40% (application, analysis)
   - Hard: 20% (evaluation, creation)
4. **Fairness**: Clear, unambiguous questions
5. **Learning Value**: Questions that teach, not trick

## Question Type Guidelines

### Multiple Choice Questions
- 4 options (A, B, C, D)
- Clear, concise stem
- Plausible distractors (wrong answers that reveal common misconceptions)
- Explanations for correct AND incorrect answers
- Avoid "all of the above" and "none of the above"

### True/False Questions
- Clear statements that are definitively true or false
- Avoid double negatives
- Test important concepts, not trivia
- Include explanation of the correct answer

### Fill in the Blank Questions
- Use blanks for key terms or concepts
- Provide context clues
- Accept multiple correct forms where appropriate
- Blank should be a single word or short phrase

### Coding Questions
- Clear problem statement
- Specify input/output formats
- Provide starter code when helpful
- Include test cases with expected outputs
- Difficulty should match course level

## Module Quiz Guidelines

- 5-10 questions per module
- Cover key concepts from each lesson
- Passing score: typically 70-80%
- Mix of question types
- Progressive difficulty within quiz

## Final Exam Guidelines

- Comprehensive coverage of all modules
- 15-25 questions depending on course length
- Weight distribution across modules should be balanced
- Include at least one coding question if course is technical
- Higher proportion of medium/hard questions (since it's summative)"""
    
    def build_prompt(
        self, 
        course_data: Dict[str, Any],
        include_coding: bool = True
    ) -> str:
        # Extract key info from course data
        topic = course_data.get('topic', 'Unknown')
        difficulty = course_data.get('target_audience', 'intermediate')
        objectives = course_data.get('learning_objectives', [])
        modules = course_data.get('modules', [])
        
        modules_section = ""
        for mod in modules:
            lessons_info = []
            for lesson in mod.get('lessons', []):
                lessons_info.append(f"    - {lesson.get('title', 'Untitled')}: {', '.join(lesson.get('objectives', []))}")
            
            modules_section += f"""
### Module: {mod.get('title', 'Untitled')}
**Description:** {mod.get('description', 'No description')}
**Lessons:**
{chr(10).join(lessons_info)}
"""
        
        objectives_list = "\n".join(f"- {obj}" for obj in objectives)
        
        return f"""## Assessment Design Task

Design comprehensive assessments for this course:

### Course Overview
**Topic:** {topic}
**Difficulty Level:** {difficulty}
**Include Coding Questions:** {include_coding}

**Learning Objectives:**
{objectives_list}
{modules_section}

## Your Task

Create a complete assessment structure:

### 1. Module Assessments (one per module)
For each module, create a quiz with:
- module_id: The module identifier
- title: Quiz title
- passing_score: 70-80
- questions: Array of 5-10 questions

### 2. Question Types
For each question, specify question_type as one of:
- "multiple_choice"
- "true_false"
- "fill_blank"
- "coding" (if include_coding is true)

**Multiple Choice Question:**
{{
  "question_type": "multiple_choice",
  "question_id": "mod1_q1",
  "question": "The question text",
  "options": [
    {{"label": "A", "text": "Option A text"}},
    {{"label": "B", "text": "Option B text"}},
    {{"label": "C", "text": "Option C text"}},
    {{"label": "D", "text": "Option D text"}}
  ],
  "correct_answer": "B",
  "explanation": "Why B is correct and others are wrong",
  "difficulty": "easy",
  "learning_objective": "Which objective this tests",
  "points": 10
}}

**True/False Question:**
{{
  "question_type": "true_false",
  "question_id": "mod1_q2",
  "statement": "The statement to evaluate",
  "correct_answer": true,
  "explanation": "Why this is true/false",
  "difficulty": "easy",
  "learning_objective": "Which objective this tests",
  "points": 5
}}

**Fill Blank Question:**
{{
  "question_type": "fill_blank",
  "question_id": "mod1_q3",
  "question_with_blank": "The ___ is used for...",
  "correct_answer": "keyword",
  "acceptable_answers": ["keyword", "term", "word"],
  "hint": "A helpful hint",
  "difficulty": "medium",
  "learning_objective": "Which objective this tests",
  "points": 10
}}

**Coding Question:**
{{
  "question_type": "coding",
  "question_id": "mod1_q4",
  "problem_statement": "What to implement",
  "starter_code": "def function():\\n    pass",
  "solution": "def function():\\n    return 'correct'",
  "test_cases": [
    {{"input": "test", "expected_output": "result"}}
  ],
  "language": "python",
  "difficulty": "medium",
  "learning_objective": "Which objective this tests",
  "points": 25
}}

### 3. Final Exam
Create a comprehensive final exam with:
- title: Final exam title
- description: What the exam covers
- time_limit_minutes: 30-60 depending on length
- passing_score: 70
- questions: 15-25 questions from across all modules
- weight_per_module: Object mapping module_id to weight percentage

## Difficulty Distribution Requirements

Ensure across all assessments:
- Easy questions: ~40%
- Medium questions: ~40%
- Hard questions: ~20%

## Point Distribution

- Multiple choice: 10 points
- True/False: 5 points
- Fill blank: 10 points
- Coding: 20-30 points (based on difficulty)

Respond with the complete JSON structure only."""
    
    def get_fallback_prompt(
        self, 
        course_data: Dict[str, Any], 
        **kwargs
    ) -> str:
        """Simpler prompt for retry attempts"""
        topic = course_data.get('topic', 'Unknown')
        modules = course_data.get('modules', [])
        
        return f"""Create assessments for a course on "{topic}".

For each of the {len(modules)} modules, create a module_assessments entry with:
- module_id
- title
- passing_score: 70
- questions: 5 questions (mix of multiple_choice, true_false, fill_blank)

Each question needs:
- question_type
- question_id
- The question content
- correct_answer
- explanation
- difficulty: "easy", "medium", or "hard"
- learning_objective
- points

Also create a final_exam with:
- title
- description
- time_limit_minutes: 45
- passing_score: 70
- questions: 10 questions from across modules
- weight_per_module: object with module_id -> percentage

Respond with JSON only."""


class QuestionRegeneratorAgent(BaseAgent[QuizQuestion]):
    """
    Specialized agent to regenerate individual questions.
    Used when specific questions fail validation or need improvement.
    """
    
    def __init__(self):
        super().__init__(
            name="QuestionRegenerator",
            output_schema=QuizQuestion,
            temperature=0.6,
            max_tokens=2048,
            timeout_seconds=30.0
        )
    
    def get_system_prompt(self) -> str:
        return """You are an expert at creating high-quality assessment questions.

You create clear, fair, and educationally valuable questions that accurately test understanding."""
    
    def build_prompt(
        self,
        question_type: str,
        learning_objective: str,
        difficulty: str,
        context: str,
        previous_question: Optional[Dict[str, Any]] = None,
        feedback: Optional[str] = None
    ) -> str:
        prev_section = ""
        if previous_question:
            prev_section = f"""
### Previous Question (needs improvement)
```json
{previous_question}
```

### Feedback
{feedback or "Please create a better version."}
"""
        
        return f"""## Question Generation

Create a {question_type} question for:

**Learning Objective:** {learning_objective}
**Difficulty:** {difficulty}
**Context:** {context}
{prev_section}

Generate a high-quality question that:
1. Directly tests the learning objective
2. Matches the specified difficulty
3. Has clear, unambiguous wording
4. Includes a thorough explanation

Return the question as JSON only."""
