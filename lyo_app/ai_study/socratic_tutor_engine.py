"""Advanced Socratic Tutor Engine
Enhances the baseline Socratic implementation with:
 - Structured questioning taxonomies (clarification, probing, assumptions, evidence, perspective, implications, meta-cognitive)
 - Dynamic strategy selection based on recent user input & conversation state
 - Reflection prompt generation to encourage self-explanation
 - Gentle constraint to avoid revealing full answers prematurely

This engine is intentionally lightweight (no external deps) and can be
invoked by the study service to enrich system prompts or supply
post‑response reflective follow ups.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import List, Optional, Dict, Any
import re


@dataclass
class SocraticStrategy:
    category: str
    rationale: str
    questions: List[str]


class SocraticTutorEngine:
    """Encapsulates advanced Socratic guidance logic."""

    def __init__(self):
        # Core strategy bank
        self._strategies: Dict[str, SocraticStrategy] = {
            "clarification": SocraticStrategy(
                category="clarification",
                rationale="Ensure we share precise understanding of the learner's terms.",
                questions=[
                    "What do you mean exactly by '{focus}'?",
                    "Could you restate '{focus}' in your own words?",
                    "Can you give a concrete example of '{focus}'?",
                ],
            ),
            "assumptions": SocraticStrategy(
                category="assumptions",
                rationale="Surface hidden assumptions that may limit understanding.",
                questions=[
                    "What are you assuming about '{focus}'?",
                    "Is there a case where '{focus}' would not hold?",
                    "What would change if the opposite of '{focus}' were true?",
                ],
            ),
            "evidence": SocraticStrategy(
                category="evidence",
                rationale="Probe for justification and supporting reasoning.",
                questions=[
                    "What evidence supports that '{focus}'?",
                    "How did you arrive at that conclusion about '{focus}'?",
                    "Can you connect '{focus}' to a principle or prior concept?",
                ],
            ),
            "perspective": SocraticStrategy(
                category="perspective",
                rationale="Promote flexible thinking by viewing from multiple angles.",
                questions=[
                    "How might someone who disagrees about '{focus}' respond?",
                    "What is an alternative explanation for '{focus}'?",
                    "How would this look in a different context or domain?",
                ],
            ),
            "implications": SocraticStrategy(
                category="implications",
                rationale="Explore consequences and downstream effects.",
                questions=[
                    "If '{focus}' is true, what follows next?",
                    "What are the practical consequences of '{focus}'?",
                    "How does '{focus}' connect to the bigger picture?",
                ],
            ),
            "metacognitive": SocraticStrategy(
                category="metacognitive",
                rationale="Encourage reflection on the learning process itself.",
                questions=[
                    "What part of this feels clear vs. uncertain?",
                    "How did your understanding of '{focus}' change just now?",
                    "What strategy helped you reason about this?",
                ],
            ),
        }

        # Simple keyword to strategy bias mapping
        self._keyword_bias = {
            "because": ["evidence"],
            "why": ["evidence", "assumptions"],
            "think": ["evidence", "clarification"],
            "maybe": ["assumptions", "clarification"],
            "always": ["assumptions", "implications"],
            "never": ["assumptions", "perspective"],
            "therefore": ["implications"],
            "example": ["clarification"],
        }

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------
    def plan(self, last_user_input: str, history: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Return a plan dict with selected strategy, candidate questions, and reflection prompt.

        Parameters
        ----------
        last_user_input: str
            The most recent learner utterance.
        history: List[dict]
            Simplified conversation history entries with keys role/content.
        """
        focus_term = self._extract_focus(last_user_input)
        strategy_key = self._select_strategy(last_user_input, history)
        strat = self._strategies[strategy_key]

        # Fill focus placeholder
        questions = [q.format(focus=focus_term) for q in strat.questions]

        reflection = self._build_reflection_prompt(focus_term)

        return {
            "strategy": strat.category,
            "rationale": strat.rationale,
            "candidate_questions": questions,
            "reflection_prompt": reflection,
            "focus_term": focus_term,
        }

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------
    def _extract_focus(self, text: str) -> str:
        # Heuristic: choose the longest noun-like token (fallback to a keyword or 'this concept').
        tokens = re.findall(r"[A-Za-z][A-Za-z0-9_-]{2,}", text)
        if not tokens:
            return "this concept"
        # Prefer tokens not in stoplist
        stop = {"the", "and", "about", "with", "that", "this", "from", "into", "have", "has"}
        filtered = [t for t in tokens if t.lower() not in stop]
        candidate_pool = filtered or tokens
        # Longest reasonable token
    return max(candidate_pool, key=len)[:40]

    def _select_strategy(self, last_input: str, history: List[Dict[str, Any]]) -> str:
        lowered = last_input.lower()
        # Keyword bias
        for kw, strat_list in self._keyword_bias.items():
            if kw in lowered:
                return strat_list[0]
        # If user asked a direct question ending with '?', probe evidence/clarification
        if lowered.strip().endswith('?'):
            return "clarification"
        # If conversation is short, start with clarification; later, diversify
    user_turns = sum(m.get("role") == "user" for m in history)
        if user_turns < 3:
            return "clarification"
        # Otherwise cycle through categories based on parity
        categories = list(self._strategies.keys())
        return categories[user_turns % len(categories)]

    def _build_reflection_prompt(self, focus: str) -> str:
        return (
            f"Take 20 seconds to summarize—in your own words—how '{focus}' connects "
            "to what you already knew. What still feels uncertain?"
        )


# Singleton instance (import-friendly)
socratic_tutor_engine = SocraticTutorEngine()
