"""
QA Checker Agent - Expert in content validation and fact-checking.

A2A-compliant agent responsible for:
- Fact verification and accuracy checking
- Hallucination detection
- Pedagogical quality assessment
- Consistency validation
- Accessibility compliance
- Age-appropriateness verification

The Guardian of Quality - No errors shall pass.
"""

from typing import Optional, Dict, Any, List
from pydantic import BaseModel, Field
from enum import Enum

from .base import A2ABaseAgent
from .schemas import (
    AgentCapability,
    AgentSkill,
    TaskInput,
    ArtifactType,
)
from lyo_app.ai_agents.multi_agent_v2.model_manager import ModelTier


# ============================================================
# QA-SPECIFIC SCHEMAS
# ============================================================

class IssueSeverity(str, Enum):
    """Severity levels for identified issues"""
    CRITICAL = "critical"       # Must fix - factual errors, safety issues
    HIGH = "high"               # Should fix - significant quality issues
    MEDIUM = "medium"           # Recommend fix - notable improvements
    LOW = "low"                 # Nice to have - minor enhancements
    INFO = "info"               # Observation only - no action needed


class IssueCategory(str, Enum):
    """Categories of issues"""
    FACTUAL_ERROR = "factual_error"           # Incorrect information
    HALLUCINATION = "hallucination"           # AI made something up
    OUTDATED = "outdated"                     # Information is old
    INCOMPLETE = "incomplete"                 # Missing important info
    UNCLEAR = "unclear"                       # Confusing or ambiguous
    INCONSISTENT = "inconsistent"             # Contradicts other content
    PEDAGOGICAL = "pedagogical"               # Teaching issue
    ACCESSIBILITY = "accessibility"           # Accessibility concern
    BIAS = "bias"                             # Potential bias
    INAPPROPRIATE = "inappropriate"           # Age/audience issue
    TECHNICAL = "technical"                   # Technical error (code, etc.)
    FORMATTING = "formatting"                 # Presentation issue


class ReviewScope(str, Enum):
    """What aspects to review"""
    FULL = "full"                   # Complete review
    FACTUAL_ONLY = "factual_only"   # Just fact checking
    PEDAGOGY_ONLY = "pedagogy_only" # Just teaching quality
    TECHNICAL_ONLY = "technical_only" # Just code/technical
    ACCESSIBILITY = "accessibility"  # Accessibility focus


class ContentIssue(BaseModel):
    """A specific issue found in content"""
    category: str
    description: str

class QAOutput(BaseModel):
    """Output from the QA Checker Agent - Optimized for ultra-low latency"""
    approval_status: str = "approved"         # approved, needs_revision, rejected
    issues: List[ContentIssue] = Field(default_factory=list)
    critical_issues_count: int = 0


# ============================================================
# QA CHECKER AGENT
# ============================================================

class QACheckerAgent(A2ABaseAgent[QAOutput]):
    """
    Guardian of quality who validates all content.
    
    Reviews content for factual accuracy, pedagogical soundness,
    accessibility, and overall quality before it reaches learners.
    
    Capabilities:
    - Fact verification
    - Hallucination detection
    - Pedagogical assessment
    - Accessibility checking
    - Consistency validation
    """
    
    def __init__(self):
        super().__init__(
            name="qa_checker",
            description="Expert in content validation, fact-checking, and quality assurance",
            output_schema=QAOutput,
            capabilities=[
                AgentCapability.QUALITY_ASSURANCE,
            ],
            skills=[
                AgentSkill(
                    id="fact_checking",
                    name="Fact Verification",
                    description="Verifies accuracy of claims and information"
                ),
                AgentSkill(
                    id="hallucination_detection",
                    name="Hallucination Detection",
                    description="Identifies AI-generated false information"
                ),
                AgentSkill(
                    id="pedagogy_review",
                    name="Pedagogical Review",
                    description="Assesses teaching quality and learning design"
                ),
                AgentSkill(
                    id="accessibility_audit",
                    name="Accessibility Audit",
                    description="Checks WCAG compliance and accessibility"
                ),
                AgentSkill(
                    id="consistency_check",
                    name="Consistency Check",
                    description="Validates internal consistency across content"
                ),
            ],
            temperature=0.2,  # Low temperature for precise analysis
            max_tokens=24576,
            timeout_seconds=150.0,
            force_model_tier=ModelTier.PREMIUM  # Critical for accuracy
        )
    
    def get_output_artifact_type(self) -> ArtifactType:
        return ArtifactType.QA_REPORT
    
    def get_system_prompt(self) -> str:
        return """You are an elite content quality assurance specialist with expertise in:

## Your Credentials
- Former Fact-Checker at The New York Times
- PhD in Educational Assessment from Columbia
- Certified Web Accessibility Specialist (WCAG 2.1)
- Lead QA Reviewer at major online learning platforms
- Published researcher in AI hallucination detection

## Your Mission
You are the LAST LINE OF DEFENSE before content reaches learners. Your job is to 
catch errors, inaccuracies, and quality issues that could harm the learning experience.

## Core Principles

### 1. ACCURACY IS NON-NEGOTIABLE
- Every factual claim must be verifiable
- Technical information must be current and correct
- Code examples must work as intended
- Statistics must be accurate and properly sourced

### 2. HALLUCINATION DETECTION
AI can confidently generate false information. Watch for:
- Made-up statistics or studies
- Fictional historical events or people
- Non-existent API methods or functions
- Incorrect definitions presented confidently
- Plausible-sounding but wrong explanations

### 3. PEDAGOGICAL SOUNDNESS
- Learning objectives must be measurable
- Content must align with stated objectives
- Scaffolding must be progressive
- Bloom's taxonomy must be applied correctly
- Prerequisites must be accurate

### 4. ACCESSIBILITY (WCAG 2.1)
- Level A: Minimum (must have)
- Level AA: Standard (should have)
- Level AAA: Enhanced (nice to have)

Check for:
- Alt text for all images
- Proper heading hierarchy
- Sufficient color contrast
- Keyboard navigability
- Screen reader compatibility

### 5. CONSISTENCY
- Terminology must be consistent throughout
- Style and tone should match
- Cross-references must be accurate
- No contradictions between sections

## Issue Severity Guide

### CRITICAL (must fix before publishing)
- Factual errors that could cause harm
- Security vulnerabilities in code
- Accessibility failures for Level A
- Grossly incorrect information
- Safety concerns

### HIGH (should fix)
- Significant factual inaccuracies
- Code that won't work
- Missing critical prerequisites
- Accessibility Level AA failures
- Major pedagogical issues

### MEDIUM (recommended fix)
- Minor inaccuracies
- Unclear explanations
- Missing helpful context
- Suboptimal teaching approaches
- Style inconsistencies

### LOW (nice to fix)
- Minor formatting issues
- Enhancement opportunities
- Stylistic preferences
- Minor clarity improvements

### INFO (observation only)
- Neutral observations
- Optional enhancements
- Alternative approaches

## Review Checklist

### Factual Accuracy
□ All statistics verified
□ Dates and events correct
□ Technical information accurate
□ Code examples tested/validated
□ Sources are credible

### Hallucination Checks
□ No made-up citations
□ No fictional examples
□ No incorrect API/syntax
□ No false claims of studies
□ No invented terminology

### Pedagogical Quality
□ Clear learning objectives
□ Appropriate difficulty progression
□ Good scaffolding design
□ Active learning opportunities
□ Assessment alignment

### Accessibility
□ Image alt text
□ Color contrast
□ Heading structure
□ Link clarity
□ Language clarity

### Consistency
□ Terminology consistent
□ Style consistent
□ No contradictions
□ Cross-references valid

### Output Standards

You must:
1. ONLY return issues if there are critical errors that prevent publishing.
2. The schema has been aggressively minimized to prioritize low latency. Do not generate verbose explanations unless necessary.

CRITICAL: Return valid JSON matching the QAOutput schema exactly."""
    
    def build_prompt(
        self, 
        task_input: TaskInput,
        content_to_review: Optional[Dict[str, Any]] = None,
        cinematic_output: Optional[Dict[str, Any]] = None,
        pedagogy_output: Optional[Dict[str, Any]] = None,
        review_scope: ReviewScope = ReviewScope.FULL,
        **kwargs
    ) -> str:
        # Build content section from available inputs
        content_sections = []
        
        if content_to_review:
            content_sections.append(f"""
### Raw Content for Review
```json
{str(content_to_review)[:4000]}...
```
""")
        
        content_text = "\n".join(content_sections) if content_sections else "No specific content provided for review."
        
        return f"""## Quality Assurance Review Task

Perform a rapid, latency-optimized critical review:

{content_text}

## Your Task:
Output a single JSON object with EXACTLY these schema fields—no others:
- `approval_status`: "approved", "needs_revision", or "rejected"
- `issues`: List of dicts `[{{"category": "factual", "description": "What's wrong"}}]` (Return empty list [] if approved)
- `critical_issues_count`: integer

## CRITICAL: JSON Output Format

You MUST return a single JSON object matching this EXACT structure (no markdown, no wrapping):

```json
{{
  "approval_status": "approved",
  "issues": [],
  "critical_issues_count": 0
}}
```

Return ONLY valid JSON matching this structure. No markdown wrappers, no extra text."""
