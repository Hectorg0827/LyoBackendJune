"""
Remediation Service - Generates targeted remediation content

This service handles the "controlled remediation" system:
1. Limits remediation attempts (max 2 hops per concept per session)
2. Uses templates first, then falls back to gold standard
3. Generates new analogies using LLM when needed
4. Tracks remediation effectiveness
"""

import logging
import uuid
from typing import Optional, List, Dict, Any
from datetime import datetime

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_, func

from lyo_app.ai_classroom.models import (
    LearningNode, Misconception, MasteryState, InteractionAttempt,
    NodeType, AssetTier
)

logger = logging.getLogger(__name__)


# =============================================================================
# REMEDIATION TEMPLATES
# =============================================================================

ANALOGY_TEMPLATES = {
    "math": [
        "Think of {concept} like {everyday_thing}. Just as {analogy_explanation}, {concept} works the same way.",
        "Imagine you're {scenario}. {concept} is like {comparison} - {explanation}.",
        "Picture {visual_metaphor}. That's exactly how {concept} works because {reason}.",
    ],
    "science": [
        "Consider {concept} as if it were {natural_example}. Both follow the same principle: {principle}.",
        "In everyday life, {concept} is similar to {daily_example}. When you {action}, {result}.",
        "Think about {familiar_thing}. {concept} operates on the same logic because {explanation}.",
    ],
    "language": [
        "{concept} is like {linguistic_parallel}. Just as {comparison}, {concept} follows the pattern.",
        "Imagine words as {metaphor}. {concept} helps us {purpose} by {mechanism}.",
        "Consider how {everyday_example} works. {concept} serves a similar role in language.",
    ],
    "general": [
        "Let me explain {concept} differently. Think of it as {alternative_explanation}.",
        "Here's another way to understand {concept}: {new_perspective}.",
        "Consider this analogy for {concept}: {analogy}.",
    ]
}

MISCONCEPTION_CORRECTIONS = {
    "division_makes_smaller": {
        "explanation": "Division by numbers less than 1 actually makes things bigger! When you divide by 0.5, you're asking 'how many halves?', which doubles the number.",
        "visual_prompt": "A pizza being divided into smaller and smaller pieces, showing more pieces appearing",
        "counter_example": "12 ÷ 0.5 = 24 (dividing by half means 'how many halves fit in 12?')"
    },
    "negative_times_negative": {
        "explanation": "Think of negatives as 'opposite'. The opposite of the opposite is the original direction. If 'not going backward' means going forward, then negative × negative = positive.",
        "visual_prompt": "A number line showing direction reversals",
        "counter_example": "Owing a debt (negative) that gets cancelled (negative) means you gain money (positive)"
    },
    "zero_exponent": {
        "explanation": "Any number to the 0 power equals 1 because of the pattern: 2³=8, 2²=4, 2¹=2... each time we divide by 2, so 2⁰=1",
        "visual_prompt": "A visual pattern showing exponents decreasing",
        "counter_example": "The pattern 2³, 2², 2¹, 2⁰ is 8, 4, 2, 1 - dividing by 2 each step"
    }
}


class RemediationService:
    """
    Service for generating targeted remediation content.
    
    Strategy:
    1. Check if template-based remediation exists
    2. If misconception detected, use specific correction
    3. Generate new analogy via LLM if budget allows
    4. Fall back to gold standard node
    """
    
    def __init__(self, db: AsyncSession):
        self.db = db
    
    async def generate_remediation(
        self,
        original_node: LearningNode,
        user_id: str,
        misconception_tag: Optional[str] = None,
        user_complaint: Optional[str] = None
    ) -> LearningNode:
        """
        Generate a remediation node for a concept the user struggled with.
        
        Args:
            original_node: The node the user failed
            user_id: User ID for personalization
            misconception_tag: Detected misconception, if any
            user_complaint: User's own words about confusion
        
        Returns:
            A new LearningNode with remediation content
        """
        # Get concept info
        concept_id = original_node.concept_id
        content = original_node.content or {}
        
        # Try template-based remediation first
        remediation_content = await self._get_template_remediation(
            concept_id, misconception_tag, content
        )
        
        # If no template, generate with LLM
        if not remediation_content:
            remediation_content = await self._generate_llm_remediation(
                original_node, user_id, misconception_tag, user_complaint
            )
        
        # Create remediation node (not persisted - ephemeral)
        remediation_node = LearningNode(
            id=str(uuid.uuid4()),
            course_id=original_node.course_id,
            node_type=NodeType.REMEDIATION.value,
            content=remediation_content,
            concept_id=concept_id,
            objective_id=original_node.objective_id,
            estimated_seconds=30,
            asset_tier=AssetTier.ABSTRACT.value,  # Use cheap visuals for remediation
            sequence_order=original_node.sequence_order,
            created_at=datetime.utcnow()
        )
        
        return remediation_node
    
    async def _get_template_remediation(
        self,
        concept_id: Optional[str],
        misconception_tag: Optional[str],
        original_content: Dict[str, Any]
    ) -> Optional[Dict[str, Any]]:
        """Get template-based remediation if available."""
        
        # Check for specific misconception correction
        if misconception_tag and misconception_tag in MISCONCEPTION_CORRECTIONS:
            correction = MISCONCEPTION_CORRECTIONS[misconception_tag]
            return {
                "type": "misconception_correction",
                "original_concept": original_content.get("prompt", ""),
                "misconception": misconception_tag,
                "explanation": correction["explanation"],
                "visual_prompt": correction["visual_prompt"],
                "counter_example": correction["counter_example"],
                "narration": f"I see where the confusion might be. {correction['explanation']}"
            }
        
        # Check for concept-specific templates in database
        if concept_id:
            result = await self.db.execute(
                select(Misconception)
                .where(
                    and_(
                        Misconception.concept_id == concept_id,
                        Misconception.remediation_strategy.isnot(None)
                    )
                )
                .limit(1)
            )
            misconception = result.scalar_one_or_none()
            
            if misconception:
                return {
                    "type": "concept_remediation",
                    "original_concept": original_content.get("prompt", ""),
                    "new_analogy": misconception.suggested_analogy or "",
                    "narration": misconception.remediation_strategy or "",
                    "visual_prompt": f"Visual representation of {misconception.label} concept",
                }
        
        return None
    
    async def _generate_llm_remediation(
        self,
        original_node: LearningNode,
        user_id: str,
        misconception_tag: Optional[str],
        user_complaint: Optional[str]
    ) -> Dict[str, Any]:
        """Generate remediation using LLM."""
        try:
            from lyo_app.ai.ai_resilience import get_ai_manager
            ai_manager = get_ai_manager()
            
            # Get user's mastery context
            mastery_context = await self._get_mastery_context(user_id, original_node.concept_id)
            
            # Build prompt
            prompt = self._build_remediation_prompt(
                original_node, mastery_context, misconception_tag, user_complaint
            )
            
            # Generate with LLM
            response = await ai_manager.generate_response(
                messages=[{"role": "user", "content": prompt}],
                use_flash_lite=True  # Use cheaper model for remediation
            )
            
            # Parse response
            return self._parse_remediation_response(response, original_node)
            
        except Exception as e:
            logger.error(f"LLM remediation generation failed: {e}")
            # Return generic fallback
            return self._get_generic_remediation(original_node)
    
    def _build_remediation_prompt(
        self,
        node: LearningNode,
        mastery_context: Dict[str, Any],
        misconception_tag: Optional[str],
        user_complaint: Optional[str]
    ) -> str:
        """Build the LLM prompt for remediation generation."""
        content = node.content or {}
        
        prompt = f"""You are an expert tutor helping a student who just got a question wrong.

ORIGINAL QUESTION:
{content.get('prompt', 'Unknown question')}

STUDENT'S CONTEXT:
- Mastery level: {mastery_context.get('mastery_score', 0.5):.0%}
- Attempts on this concept: {mastery_context.get('attempts', 0)}
- Learning trend: {mastery_context.get('trend', 'stable')}
"""

        if misconception_tag:
            prompt += f"\nDETECTED MISCONCEPTION: {misconception_tag}\n"
        
        if user_complaint:
            prompt += f"\nSTUDENT SAID: \"{user_complaint}\"\n"
        
        prompt += """
YOUR TASK:
Generate a new, DIFFERENT explanation using a fresh analogy. The student didn't understand the first explanation, so use a completely different approach.

OUTPUT FORMAT (JSON):
{
    "new_analogy": "A fresh analogy to explain the concept",
    "narration": "The spoken explanation (2-3 sentences, conversational)",
    "visual_prompt": "Description for image generation",
    "follow_up_hint": "A hint that might help without giving away the answer"
}

Be encouraging but not condescending. Use everyday examples the student can relate to.
"""
        return prompt
    
    async def _get_mastery_context(
        self,
        user_id: str,
        concept_id: Optional[str]
    ) -> Dict[str, Any]:
        """Get user's mastery context for personalization."""
        if not concept_id:
            return {"mastery_score": 0.5, "attempts": 0, "trend": "stable"}
        
        result = await self.db.execute(
            select(MasteryState)
            .where(
                and_(
                    MasteryState.user_id == user_id,
                    MasteryState.concept_id == concept_id
                )
            )
        )
        mastery = result.scalar_one_or_none()
        
        if not mastery:
            return {"mastery_score": 0.5, "attempts": 0, "trend": "stable"}
        
        return {
            "mastery_score": mastery.mastery_score,
            "attempts": mastery.attempts,
            "trend": mastery.trend,
            "confidence": mastery.confidence
        }
    
    def _parse_remediation_response(
        self,
        response: str,
        original_node: LearningNode
    ) -> Dict[str, Any]:
        """Parse LLM response into remediation content."""
        import json
        
        try:
            # Try to extract JSON from response
            if "{" in response and "}" in response:
                json_start = response.index("{")
                json_end = response.rindex("}") + 1
                json_str = response[json_start:json_end]
                data = json.loads(json_str)
                
                return {
                    "type": "llm_generated",
                    "original_concept": (original_node.content or {}).get("prompt", ""),
                    "new_analogy": data.get("new_analogy", ""),
                    "narration": data.get("narration", ""),
                    "visual_prompt": data.get("visual_prompt", ""),
                    "follow_up_hint": data.get("follow_up_hint", "")
                }
        except (json.JSONDecodeError, ValueError) as e:
            logger.warning(f"Failed to parse LLM response as JSON: {e}")
        
        # Fallback: use response as narration
        return {
            "type": "llm_generated",
            "original_concept": (original_node.content or {}).get("prompt", ""),
            "new_analogy": "",
            "narration": response[:500],  # Truncate if too long
            "visual_prompt": "Educational illustration explaining the concept",
            "follow_up_hint": ""
        }
    
    def _get_generic_remediation(self, node: LearningNode) -> Dict[str, Any]:
        """Get generic fallback remediation."""
        content = node.content or {}
        return {
            "type": "generic_fallback",
            "original_concept": content.get("prompt", ""),
            "new_analogy": "Let's look at this from a different angle.",
            "narration": "That's okay! Learning takes practice. Let me explain this differently. Take your time to think through each step.",
            "visual_prompt": "Encouraging educational illustration with step-by-step breakdown",
            "follow_up_hint": "Try breaking the problem into smaller parts."
        }
    
    async def check_remediation_budget(
        self,
        user_id: str,
        node_id: str
    ) -> tuple[bool, int]:
        """
        Check if user has remediation budget remaining for this node.
        
        Returns:
            (can_remediate, remaining_budget)
        """
        # Get the node's remediation budget
        result = await self.db.execute(
            select(LearningNode)
            .where(LearningNode.id == node_id)
        )
        node = result.scalar_one_or_none()
        
        if not node:
            return False, 0
        
        max_budget = node.remediation_budget or 2
        
        # Count remediation attempts
        count_result = await self.db.execute(
            select(func.count(InteractionAttempt.id))
            .where(
                and_(
                    InteractionAttempt.user_id == user_id,
                    InteractionAttempt.node_id == node_id,
                    InteractionAttempt.remediation_shown == True
                )
            )
        )
        used = count_result.scalar() or 0
        
        remaining = max_budget - used
        return remaining > 0, remaining
    
    async def mark_remediation_shown(
        self,
        user_id: str,
        node_id: str
    ) -> None:
        """Mark that remediation was shown for a node."""
        # Get the latest attempt
        result = await self.db.execute(
            select(InteractionAttempt)
            .where(
                and_(
                    InteractionAttempt.user_id == user_id,
                    InteractionAttempt.node_id == node_id
                )
            )
            .order_by(InteractionAttempt.created_at.desc())
            .limit(1)
        )
        attempt = result.scalar_one_or_none()
        
        if attempt:
            attempt.remediation_shown = True
            await self.db.commit()
    
    async def track_remediation_effectiveness(
        self,
        user_id: str,
        original_node_id: str,
        success_after_remediation: bool
    ) -> None:
        """
        Track whether remediation was effective.
        
        Used for A/B testing and improving remediation strategies.
        """
        # In production, this would log to analytics
        logger.info(
            f"Remediation effectiveness: user={user_id}, "
            f"node={original_node_id}, success={success_after_remediation}"
        )


def get_remediation_service(db: AsyncSession) -> RemediationService:
    """Factory function for dependency injection."""
    return RemediationService(db)
