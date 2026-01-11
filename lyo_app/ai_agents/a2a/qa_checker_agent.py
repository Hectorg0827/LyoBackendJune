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
    id: str
    category: IssueCategory
    severity: IssueSeverity
    location: str                       # Where in the content (scene_id, block_id, etc.)
    description: str                    # What's wrong
    evidence: str                       # Why it's wrong
    suggestion: str                     # How to fix it
    confidence: float                   # 0.0-1.0 confidence in the issue
    auto_fixable: bool                  # Can be automatically corrected
    references: List[str]               # Sources supporting the issue


class FactCheck(BaseModel):
    """Result of fact-checking a claim"""
    claim_id: str
    claim_text: str
    location: str
    is_accurate: bool
    confidence: float
    explanation: str
    sources: List[str]
    suggested_correction: Optional[str] = None


class PedagogyCheck(BaseModel):
    """Result of pedagogical review"""
    aspect: str                         # What was checked
    score: float                        # 0.0-1.0
    feedback: str
    suggestions: List[str]


class AccessibilityCheck(BaseModel):
    """Accessibility compliance check"""
    guideline: str                      # WCAG guideline
    passed: bool
    details: str
    remediation: Optional[str] = None


class ContentMetrics(BaseModel):
    """Quantitative metrics about content"""
    word_count: int
    avg_sentence_length: float
    readability_score: float            # 0-100 Flesch-Kincaid
    reading_level: str                  # Grade level
    technical_density: float            # Ratio of technical terms
    jargon_count: int
    image_alt_text_coverage: float      # % of images with alt text
    code_comment_density: float         # % of code with comments


class QAChecklistItem(BaseModel):
    """Item in QA checklist"""
    id: str
    category: str
    description: str
    passed: bool
    notes: Optional[str] = None


class QAOutput(BaseModel):
    """Output from the QA Checker Agent"""
    # Overall assessment - defaults for robustness
    overall_quality_score: float = 1.0        # 0.0-1.0
    approval_status: str = "approved"         # approved, needs_revision, rejected
    summary: str = "Content review completed."
    
    # Issue tracking (make list fields optional with defaults)
    issues: List[ContentIssue] = Field(default_factory=list)
    critical_issues_count: int = 0
    high_issues_count: int = 0
    medium_issues_count: int = 0
    low_issues_count: int = 0
    
    # Fact checking (optional with defaults)
    fact_checks: List[FactCheck] = Field(default_factory=list)
    factual_accuracy_score: float = 1.0       # 0.0-1.0
    hallucination_detected: bool = False
    hallucination_details: List[str] = Field(default_factory=list)
    
    # Pedagogical assessment (optional with defaults)
    pedagogy_checks: List[PedagogyCheck] = Field(default_factory=list)
    pedagogical_quality_score: float = 1.0    # 0.0-1.0
    bloom_alignment_score: float = 1.0        # How well objectives match Bloom's
    scaffolding_score: float = 1.0            # Quality of progressive support
    
    # Accessibility (optional with defaults)
    accessibility_checks: List[AccessibilityCheck] = Field(default_factory=list)
    accessibility_score: float = 1.0          # 0.0-1.0
    wcag_level: str = "AA"                    # A, AA, AAA
    
    # Content metrics (optional)
    content_metrics: Optional[ContentMetrics] = None
    
    # Consistency (optional with defaults)
    consistency_score: float = 1.0            # 0.0-1.0
    inconsistencies: List[str] = Field(default_factory=list)
    
    # Completeness (optional with defaults)
    completeness_score: float = 1.0           # 0.0-1.0
    missing_elements: List[str] = Field(default_factory=list)
    coverage_by_objective: Dict[str, float] = Field(default_factory=dict)  # objective_id -> coverage %
    
    # Checklist (optional with defaults)
    checklist: List[QAChecklistItem] = Field(default_factory=list)
    checklist_pass_rate: float = 1.0
    
    # Recommendations (optional with defaults)
    priority_fixes: List[str] = Field(default_factory=list)           # Top things to fix
    enhancement_suggestions: List[str] = Field(default_factory=list)  # Nice-to-haves
    
    # Metadata (optional with defaults)
    review_scope: ReviewScope = ReviewScope.FULL
    review_duration_estimate: str = "5-10 minutes"
    confidence_level: float = 0.9             # Overall confidence in assessment


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

## Output Standards

You must:
1. Be SPECIFIC - cite exact locations and text
2. Be ACTIONABLE - provide clear fix suggestions
3. Be CALIBRATED - severity matches actual impact
4. Be THOROUGH - check everything systematically
5. Be FAIR - acknowledge what's done well

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
        
        if pedagogy_output:
            content_sections.append(f"""
### Pedagogical Structure (from PedagogyAgent)
- Topic: {pedagogy_output.get('topic', 'N/A')}
- Learning Objectives: {len(pedagogy_output.get('learning_objectives', []))}
- Cognitive Chunks: {len(pedagogy_output.get('cognitive_chunks', []))}
- Key Misconceptions: {pedagogy_output.get('key_misconceptions', [])}
""")
        
        if cinematic_output:
            modules = cinematic_output.get('modules', [])
            total_scenes = sum(len(m.get('scenes', [])) for m in modules)
            content_sections.append(f"""
### Cinematic Structure (from CinematicDirector)
- Course Title: {cinematic_output.get('course_title', 'N/A')}
- Modules: {len(modules)}
- Total Scenes: {total_scenes}
- Narrative Arc: {cinematic_output.get('narrative_structure', {}).get('arc_type', 'N/A')}
""")
        
        if content_to_review:
            content_sections.append(f"""
### Raw Content for Review
```json
{str(content_to_review)[:4000]}...
```
""")
        
        content_text = "\n".join(content_sections) if content_sections else "No specific content provided for review."
        
        return f"""## Quality Assurance Review Task

Perform a comprehensive quality review of this educational content:

### Review Scope: {review_scope.value}

{content_text}

## Your Task

Conduct a thorough quality review covering:

### 1. Factual Accuracy Check
For each claim or fact:
- claim_id: "fact_1", "fact_2", etc.
- claim_text: The exact claim
- location: Where it appears (scene_id, block_id)
- is_accurate: true/false
- confidence: 0.0-1.0
- explanation: Why accurate or inaccurate
- sources: Supporting references
- suggested_correction: If inaccurate

### 2. Hallucination Detection
Look for AI-generated false content:
- Made-up statistics
- Fictional sources
- Non-existent technical terms
- False API/syntax
- Invented studies

Report in hallucination_detected and hallucination_details.

### 3. Issue Identification
For each issue found:
- id: "issue_1", etc.
- category: factual_error, hallucination, outdated, incomplete, unclear, 
  inconsistent, pedagogical, accessibility, bias, inappropriate, technical, formatting
- severity: critical, high, medium, low, info
- location: Specific location
- description: What's wrong
- evidence: Why it's wrong
- suggestion: How to fix
- confidence: 0.0-1.0
- auto_fixable: true/false
- references: Supporting sources

### 4. Pedagogical Assessment
Review teaching quality:
- aspect: What you're evaluating (e.g., "objective clarity")
- score: 0.0-1.0
- feedback: Assessment
- suggestions: Improvements

Check:
- Learning objective measurability
- Bloom's taxonomy alignment
- Scaffolding progression
- Active learning opportunities
- Assessment alignment

### 5. Accessibility Review
Check WCAG 2.1 compliance:
- guideline: The WCAG guideline
- passed: true/false
- details: Explanation
- remediation: How to fix (if failed)

### 6. Content Metrics
Calculate:
- word_count, avg_sentence_length
- readability_score (Flesch-Kincaid 0-100)
- reading_level (grade level)
- technical_density
- jargon_count
- image_alt_text_coverage
- code_comment_density

### 7. Consistency Check
- consistency_score: 0.0-1.0
- inconsistencies: List of found inconsistencies

### 8. Completeness Check
- completeness_score: 0.0-1.0
- missing_elements: What's missing
- coverage_by_objective: {{"obj_1": 0.8, ...}}

### 9. QA Checklist
Run through standard checklist:
- id, category, description
- passed: true/false
- notes: Any relevant notes

### 10. Overall Assessment
- overall_quality_score: 0.0-1.0
- approval_status: "approved", "needs_revision", or "rejected"
- summary: Executive summary
- priority_fixes: Top things that must be fixed
- enhancement_suggestions: Nice-to-have improvements

## Scoring Guidelines

| Score | Meaning |
|-------|---------|
| 0.9-1.0 | Exceptional - publish ready |
| 0.8-0.9 | Good - minor improvements |
| 0.7-0.8 | Acceptable - some fixes needed |
| 0.6-0.7 | Needs work - significant issues |
| <0.6 | Requires major revision |

## Approval Thresholds
- **Approved**: Quality score ≥ 0.85, no critical issues
- **Needs Revision**: Quality score 0.6-0.85 OR has high issues
- **Rejected**: Quality score < 0.6 OR has critical issues

## CRITICAL: JSON Output Format

You MUST return a single JSON object matching this EXACT structure (no markdown, no wrapping):

```json
{{
  "overall_quality_score": 0.85,
  "approval_status": "approved",
  "summary": "Executive summary of the review.",
  "issues": [],
  "critical_issues_count": 0,
  "high_issues_count": 0,
  "medium_issues_count": 0,
  "low_issues_count": 0,
  "fact_checks": [],
  "factual_accuracy_score": 1.0,
  "hallucination_detected": false,
  "hallucination_details": [],
  "pedagogy_checks": [],
  "pedagogical_quality_score": 1.0,
  "bloom_alignment_score": 1.0,
  "scaffolding_score": 1.0,
  "accessibility_checks": [],
  "accessibility_score": 1.0,
  "wcag_level": "AA",
  "content_metrics": null,
  "consistency_score": 1.0,
  "inconsistencies": [],
  "completeness_score": 1.0,
  "missing_elements": [],
  "coverage_by_objective": {{}},
  "checklist": [],
  "checklist_pass_rate": 1.0,
  "priority_fixes": [],
  "enhancement_suggestions": [],
  "review_scope": "full",
  "review_duration_estimate": "5-10 minutes",
  "confidence_level": 0.9
}}
```

Return ONLY valid JSON matching this structure. No markdown wrappers, no extra text."""
