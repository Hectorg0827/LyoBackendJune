"""
Quality Assurance Agent - Reviews and validates generated content.
Fifth agent in the Multi-Agent Course Generation Pipeline.

MIT Architecture Engineering - Quality & Validation Agent
"""

from typing import Optional, Dict, Any, List
from enum import Enum
from dataclasses import dataclass

from lyo_app.ai_agents.multi_agent_v2.agents.base_agent import BaseAgent
from lyo_app.ai_agents.multi_agent_v2.schemas.course_schemas import (
    QualityReport,
    QualityCheck,
    QualityLevel
)


class ReviewFocus(str, Enum):
    """Types of quality review focus areas"""
    ACCURACY = "accuracy"  # Technical correctness
    PEDAGOGY = "pedagogy"  # Teaching effectiveness
    COMPLETENESS = "completeness"  # Coverage of objectives
    CONSISTENCY = "consistency"  # Internal consistency
    ENGAGEMENT = "engagement"  # Learner engagement
    ACCESSIBILITY = "accessibility"  # Accessibility standards


@dataclass
class QAContext:
    """Context for quality assurance review"""
    course_data: Dict[str, Any]
    focus_areas: List[ReviewFocus]
    previous_issues: Optional[List[Dict[str, Any]]] = None


class QualityAssuranceAgent(BaseAgent[QualityReport]):
    """
    Fifth and final agent in the pipeline.
    Reviews all generated content for quality, accuracy, and consistency.
    
    Responsibilities:
    - Verify technical accuracy
    - Check pedagogical soundness
    - Ensure objective coverage
    - Validate internal consistency
    - Rate overall quality
    - Provide actionable improvement suggestions
    """
    
    def __init__(self):
        super().__init__(
            name="qa_agent",  # Matches ModelManager task name
            output_schema=QualityReport,
            timeout_seconds=120.0  # Model config from ModelManager
        )
    
    def get_system_prompt(self) -> str:
        return """You are an expert educational content reviewer and quality assurance specialist with extensive experience in:
- Technical accuracy verification
- Pedagogical effectiveness evaluation
- Instructional design best practices
- Accessibility compliance
- Content quality assessment

## Your Expertise

You have reviewed thousands of courses and can quickly identify:
- Technical errors or misconceptions
- Pedagogical weaknesses
- Missing content or incomplete coverage
- Inconsistencies between sections
- Engagement and motivation issues
- Accessibility concerns

## Quality Assessment Framework

You evaluate content on these dimensions:

### 1. Technical Accuracy (Critical)
- Code examples work correctly
- Technical concepts are accurately explained
- No factual errors or misconceptions
- Up-to-date information and best practices

### 2. Pedagogical Effectiveness
- Clear learning progression
- Appropriate scaffolding
- Good use of examples and analogies
- Active learning opportunities
- Proper cognitive load management

### 3. Completeness
- All learning objectives are covered
- Prerequisites are properly addressed
- No gaps in the learning journey
- Sufficient practice opportunities

### 4. Consistency
- Consistent terminology throughout
- Consistent code style
- Logical flow between lessons
- Prerequisites are respected

### 5. Engagement
- Interesting and motivating content
- Varied activities and formats
- Real-world relevance
- Appropriate challenges

### 6. Accessibility
- Clear language (appropriate reading level)
- Alt text for media
- Proper heading structure
- No reliance on color alone

## Scoring Guidelines

- EXCELLENT (90-100): Exceptional quality, minor polish only
- GOOD (75-89): High quality, few improvements needed
- ACCEPTABLE (60-74): Usable but improvements recommended
- NEEDS_WORK (40-59): Significant issues, rework required
- POOR (0-39): Major problems, regeneration recommended

## Review Output Structure

Your review must identify:
1. Specific issues found (with location and severity)
2. Overall quality assessment per dimension
3. Recommendations prioritized by impact
4. Decision: PASS, PASS_WITH_NOTES, or FAIL"""
    
    def build_prompt(
        self, 
        context: QAContext
    ) -> str:
        course = context.course_data
        focus_str = ", ".join(f.value for f in context.focus_areas)
        
        prev_issues_section = ""
        if context.previous_issues:
            prev_issues_section = f"""
### Previous Issues (verify these were fixed)
```json
{context.previous_issues}
```
"""
        
        # Build a summary of the course structure
        intent = course.get('intent', {})
        curriculum = course.get('curriculum', {})
        lessons = course.get('lessons', [])
        assessments = course.get('assessments', {})
        
        lessons_summary = []
        for lesson in lessons[:5]:  # First 5 lessons as sample
            lessons_summary.append(f"  - {lesson.get('title', 'Untitled')}: {len(lesson.get('content_blocks', []))} blocks")
        if len(lessons) > 5:
            lessons_summary.append(f"  - ... and {len(lessons) - 5} more lessons")
        
        return f"""## Quality Assurance Review

Review this generated course for quality issues:

### Course Overview
**Topic:** {intent.get('topic', 'Unknown')}
**Difficulty:** {intent.get('target_audience', 'Unknown')}
**Duration:** {intent.get('estimated_duration_hours', 'Unknown')} hours

**Learning Objectives:**
{chr(10).join(f"- {obj}" for obj in intent.get('learning_objectives', []))}

### Curriculum Structure
**Modules:** {curriculum.get('module_count', 0)}
**Total Lessons:** {curriculum.get('lesson_count', 0)}
**Total Duration:** {curriculum.get('total_duration_minutes', 0)} minutes

### Lesson Content Sample
{chr(10).join(lessons_summary)}

### Full Course Data (for detailed review)
```json
{course}
```
{prev_issues_section}

## Review Focus
{focus_str}

## Your Task

Conduct a thorough quality review and provide:

### 1. Quality Checks
For each dimension reviewed, provide:
- dimension: The quality dimension (accuracy, pedagogy, completeness, consistency, engagement, accessibility)
- score: 0-100
- level: "excellent", "good", "acceptable", "needs_work", or "poor"
- issues_found: Array of specific issues
- recommendations: Array of improvement suggestions

### 2. Critical Issues
List any issues that MUST be fixed:
- issue_id: Unique identifier
- severity: "critical", "major", or "minor"
- location: Where in the course (e.g., "lesson mod1_les2", "assessment mod2_q3")
- description: What's wrong
- suggested_fix: How to fix it
- regeneration_required: true/false

### 3. Overall Assessment
- overall_score: 0-100 (weighted average of dimension scores)
- overall_level: "excellent", "good", "acceptable", "needs_work", or "poor"
- summary: 2-3 sentence overall assessment
- recommendation: "publish", "publish_with_minor_fixes", "fix_and_review", or "regenerate"

### 4. Priority Improvements
List top 5 improvements in priority order:
- priority: 1-5
- improvement: What to improve
- impact: Expected impact on quality
- effort: "low", "medium", or "high"

Respond with the complete JSON structure only.

## Scoring Weights
- Technical Accuracy: 30%
- Pedagogical Effectiveness: 25%
- Completeness: 20%
- Consistency: 10%
- Engagement: 10%
- Accessibility: 5%"""
    
    def get_fallback_prompt(
        self, 
        context: QAContext, 
        **kwargs
    ) -> str:
        """Simpler prompt for retry attempts"""
        course = context.course_data
        intent = course.get('intent', {})
        
        return f"""Review this course on "{intent.get('topic', 'Unknown')}":

Course data:
```json
{course}
```

Provide a quality report with:

1. quality_checks: Array with entries for "accuracy", "pedagogy", "completeness", each having:
   - dimension
   - score: 0-100
   - level: "excellent", "good", "acceptable", "needs_work", or "poor"
   - issues_found: list of issues
   - recommendations: list of fixes

2. critical_issues: Array of any critical problems with:
   - issue_id
   - severity: "critical", "major", "minor"
   - location
   - description
   - suggested_fix
   - regeneration_required: true/false

3. overall_score: 0-100
4. overall_level: "excellent", "good", "acceptable", "needs_work", or "poor"
5. summary: Brief assessment
6. recommendation: "publish", "publish_with_minor_fixes", "fix_and_review", or "regenerate"

7. priority_improvements: Top 3 improvements with priority, improvement, impact, effort

Respond with JSON only."""


class TargetedReviewAgent(BaseAgent[QualityCheck]):
    """
    Specialized agent for reviewing specific portions of content.
    Used for granular re-review after fixes.
    """
    
    def __init__(self):
        super().__init__(
            name="TargetedReviewer",
            output_schema=QualityCheck,
            temperature=0.3,
            max_tokens=2048,
            timeout_seconds=45.0
        )
    
    def get_system_prompt(self) -> str:
        return """You are an expert at focused quality review of educational content.

You review specific portions of content to verify fixes and assess quality."""
    
    def build_prompt(
        self,
        content_to_review: Dict[str, Any],
        dimension: str,
        original_issue: Optional[Dict[str, Any]] = None
    ) -> str:
        issue_section = ""
        if original_issue:
            issue_section = f"""
### Original Issue
{original_issue.get('description', 'No description')}

### Verify
Check if this issue has been properly addressed.
"""
        
        return f"""## Targeted Quality Review

Review this specific content for the {dimension} dimension:

### Content
```json
{content_to_review}
```
{issue_section}

## Your Task

Evaluate this content on the {dimension} dimension:

1. dimension: "{dimension}"
2. score: 0-100
3. level: "excellent", "good", "acceptable", "needs_work", or "poor"
4. issues_found: Array of any issues (empty if none)
5. recommendations: Array of suggestions (empty if none)

Be thorough but fair. Focus only on the {dimension} aspect.

Respond with JSON only."""
