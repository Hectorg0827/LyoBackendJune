"""
Lightweight skill/subject extraction and content-timing utilities.

These helpers replace two long-standing server-side placeholders:

  * a hardcoded ``"general"`` skill/subject tag returned for AI study
    sessions and generated courses, which degraded lesson recommendations; and
  * a hardcoded ~15-second lesson duration that produced inaccurate progress
    tracking.

Both are derived from the actual content instead. There is intentionally no
heavyweight NLP dependency here: a curated keyword taxonomy plus a small
heuristic phrase extractor keeps this cheap enough to run inline during
course / study-session creation.
"""

from __future__ import annotations

import re
from typing import Optional

DEFAULT_SUBJECT = "General"

# Canonical subject -> trigger keywords (lowercased, word-boundary matched).
# Ordered roughly from most specific to most general so that, e.g., a course
# titled "Deep Learning with Python" prefers "Data Science" over "Python"
# only when the data-science signal is stronger.
_SUBJECT_KEYWORDS = {
    "Data Science": [
        "data science", "machine learning", "deep learning", "neural network",
        "data analysis", "data analytics", "statistics", "pandas", "numpy",
    ],
    "Artificial Intelligence": [
        "artificial intelligence", "generative ai", "llm", "nlp",
        "natural language processing", "reinforcement learning",
    ],
    "Python": ["python", "django", "flask", "fastapi"],
    "JavaScript": ["javascript", "typescript", "node", "react", "vue", "angular"],
    "Web Development": [
        "html", "css", "frontend", "front-end", "backend", "back-end",
        "web development", "web dev",
    ],
    "Computer Science": [
        "computer science", "algorithm", "data structure", "programming",
        "coding", "software engineering", "operating system",
    ],
    "Mathematics": [
        "mathematics", "algebra", "calculus", "geometry", "trigonometry",
        "linear algebra", "probability", "discrete math",
    ],
    "Physics": ["physics", "mechanics", "thermodynamics", "quantum", "relativity"],
    "Chemistry": [
        "chemistry", "organic chemistry", "molecule", "chemical reaction",
        "periodic table",
    ],
    "Biology": [
        "biology", "genetics", "cell biology", "evolution", "anatomy", "ecology",
    ],
    "History": [
        "history", "ancient", "medieval", "world war", "civilization",
        "revolution",
    ],
    "Geography": ["geography", "climate", "continent", "geology"],
    "Language Arts": [
        "grammar", "creative writing", "literature", "essay writing", "poetry",
        "english language",
    ],
    "Spanish": ["spanish", "espanol", "español"],
    "French": ["french", "francais", "français"],
    "Economics": [
        "economics", "microeconomics", "macroeconomics", "supply and demand",
    ],
    "Business": [
        "business", "marketing", "management", "entrepreneurship", "finance",
        "accounting",
    ],
    "Art": [
        "painting", "drawing", "sketching", "watercolor", "sculpture",
        "art history", "illustration",
    ],
    "Music": ["music theory", "guitar", "piano", "composition", "songwriting"],
    "Health": ["nutrition", "fitness", "wellness", "medicine", "first aid"],
    "Philosophy": ["philosophy", "ethics", "logic", "metaphysics"],
    "Psychology": ["psychology", "cognitive", "behavioral", "neuroscience"],
}

# Filler words stripped before falling back to a salient-phrase subject.
_STOPWORDS = {
    "introduction", "intro", "complete", "guide", "to", "the", "a", "an",
    "learn", "learning", "course", "fundamentals", "basics", "basic",
    "beginner", "beginners", "advanced", "intermediate", "mastering",
    "master", "ultimate", "crash", "for", "of", "and", "with", "your",
    "essential", "essentials", "from", "scratch", "step", "by", "study",
    "topic", "lesson", "module", "in", "on",
}


def infer_subject(*texts: Optional[str], default: str = DEFAULT_SUBJECT) -> str:
    """Infer a human-readable subject/skill tag from one or more text snippets.

    Strategy:
      1. Score the curated keyword taxonomy against all provided text and
         return the best-matching canonical subject.
      2. If nothing matches, fall back to the most salient phrase in the first
         usable text (filler words stripped, Title Cased) so recommendations
         still receive a meaningful tag instead of ``"General"``.
      3. Only return ``default`` when there is no usable text at all.
    """
    blob = " ".join(t for t in texts if t).lower()
    if not blob.strip():
        return default

    best_subject: Optional[str] = None
    best_score = 0
    for subject, keywords in _SUBJECT_KEYWORDS.items():
        score = 0
        for kw in keywords:
            if re.search(r"\b" + re.escape(kw) + r"\b", blob):
                # Multi-word keywords are more specific, so weight them higher.
                score += 1 + kw.count(" ")
        if score > best_score:
            best_score = score
            best_subject = subject
    if best_subject:
        return best_subject

    # Salient-phrase fallback from the first usable text.
    first = next((t for t in texts if t and t.strip()), "")
    tokens = [
        w for w in re.findall(r"[A-Za-z][A-Za-z+#-]*", first)
        if w.lower() not in _STOPWORDS
    ]
    if tokens:
        return " ".join(tokens[:3]).title()

    return default


# Average narration/speaking rate (words per minute) used to translate script
# length into a realistic on-screen duration.
_WORDS_PER_MINUTE = 150
_MIN_SECONDS = 8


def estimate_reading_seconds(
    text: Optional[str],
    *,
    words_per_minute: int = _WORDS_PER_MINUTE,
    extra_seconds: int = 0,
    minimum: int = _MIN_SECONDS,
) -> int:
    """Estimate how long a narration/script should stay on screen.

    Based on a configurable speaking rate plus optional ``extra_seconds``
    (e.g. thinking time for an interactive question). Always returns at least
    ``minimum`` seconds.
    """
    words = len((text or "").split())
    seconds = (words / max(1, words_per_minute)) * 60
    return max(minimum, int(round(seconds)) + max(0, extra_seconds))
