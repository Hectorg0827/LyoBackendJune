"""Interpret Community search text the same way on every platform.

"Spanish classes" is a topic (find learning about Spanish), "Queens" or
"10451" is a place (move the map), and "coding workshop in Brooklyn" is both.
Clients send the raw text; this module decides, so iOS, Android, and web can
never drift into three different search behaviours.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Iterable, Optional

from lyo_app.community.schemas import LearningNodeCategory

# Words that name a kind of learning opportunity. A token matches a node when
# the node's category is one of these, or when the word appears in its text.
_CATEGORY_WORDS: dict[str, frozenset[LearningNodeCategory]] = {}


def _register(words: Iterable[str], *categories: LearningNodeCategory) -> None:
    for word in words:
        _CATEGORY_WORDS[word] = frozenset(categories)


C = LearningNodeCategory
_register(["library", "libraries"], C.LIBRARY)
_register(["museum", "museums", "planetarium", "gallery"], C.MUSEUM)
_register(
    ["class", "classes", "course", "courses", "lesson", "lessons"],
    C.CLASS,
    C.WORKSHOP,
    C.TUTOR,
)
_register(["workshop", "workshops", "bootcamp", "bootcamps"], C.WORKSHOP, C.CLASS)
_register(["lecture", "lectures", "seminar", "seminars", "talk", "talks"], C.CLASS, C.EVENT)
_register(["event", "events", "meetup", "meetups"], C.EVENT, C.WORKSHOP, C.CLASS)
_register(["group", "groups", "club", "clubs", "circle"], C.STUDY_GROUP)
_register(["tutor", "tutors", "tutoring", "coach", "coaching", "mentor"], C.TUTOR)
_register(
    [
        "school",
        "schools",
        "university",
        "universities",
        "college",
        "colleges",
        "campus",
        "center",
        "centre",
        "centers",
        "centres",
        "institute",
    ],
    C.EDUCATIONAL_CENTER,
)

# Multi-word phrases are collapsed before tokenizing.
_PHRASES = {
    "study group": "group",
    "study groups": "groups",
    "learning center": "center",
    "learning centre": "centre",
    "community college": "college",
    "office hours": "lecture",
}

# Modifiers that describe intent but never need to appear in the text.
_STOPWORDS = frozenset(
    {
        "a", "an", "and", "the", "for", "of", "to", "with", "me", "my", "near", "nearby",
        "around", "in", "at", "on", "find", "show", "best", "good", "local", "free",
        "today", "tonight", "week", "this", "weekend", "prep", "help", "open", "now",
        "learn", "learning", "study", "studying", "place", "places", "spot", "spots",
    }
)

# Topic words that clearly mean "what to learn", never "where".
_TOPIC_HINTS = frozenset(
    {
        "sat", "act", "gre", "gmat", "lsat", "mcat", "ap", "esl", "coding", "code",
        "programming", "python", "javascript", "math", "algebra", "calculus",
        "physics", "chemistry", "biology", "science", "stem", "robotics", "art",
        "music", "piano", "guitar", "writing", "reading", "history", "spanish",
        "english", "french", "chinese", "mandarin", "japanese", "korean", "german",
        "italian", "arabic", "portuguese", "language", "languages", "career",
        "resume", "interview", "finance", "business", "design", "photography",
        "chess", "debate", "test", "exam", "homework",
    }
)

_POSTAL_CODE = re.compile(
    r"^(\d{5}(-\d{4})?|[a-z]\d[a-z] ?\d[a-z]\d|[a-z]{1,2}\d[a-z\d]? ?\d[a-z]{2})$",
    re.IGNORECASE,
)
_LOCATION_SPLIT = re.compile(r"\s+(?:in|near|around|at)\s+", re.IGNORECASE)
_TOKEN = re.compile(r"[a-z0-9À-ɏ]+", re.IGNORECASE)


def _stem(token: str) -> str:
    """Tiny, predictable plural folding: classes→class, libraries→library."""
    if len(token) > 4 and token.endswith("ies"):
        return token[:-3] + "y"
    if len(token) > 4 and token.endswith(("sses", "shes", "ches", "xes")):
        return token[:-2]
    if len(token) > 3 and token.endswith("s") and not token.endswith("ss"):
        return token[:-1]
    return token


def tokenize(text: str) -> list[str]:
    lowered = f" {text.lower()} "
    for phrase, replacement in _PHRASES.items():
        lowered = lowered.replace(f" {phrase} ", f" {replacement} ")
    return _TOKEN.findall(lowered)


@dataclass(frozen=True)
class TopicQuery:
    """A parsed topic search: category hints plus words the text must contain."""

    raw: str
    terms: tuple[str, ...] = ()
    category_words: tuple[str, ...] = ()
    categories: frozenset[LearningNodeCategory] = field(default_factory=frozenset)

    @property
    def is_empty(self) -> bool:
        return not self.terms and not self.category_words

    def matches(self, category: LearningNodeCategory, searchable_text: str) -> bool:
        """True when every topic term appears and every category word fits."""
        words = _word_forms(searchable_text)
        for term in self.terms:
            if not _term_in(term, words):
                return False
        for word in self.category_words:
            if category in _CATEGORY_WORDS.get(word, frozenset()):
                continue
            if not _term_in(word, words):
                return False
        return True


def _word_forms(text: str) -> set[str]:
    tokens = _TOKEN.findall(text.lower())
    return set(tokens) | {_stem(token) for token in tokens}


def _term_in(term: str, words: set[str]) -> bool:
    """Whole-word match; terms of 4+ letters may also match a word prefix.

    "sat" must not match "Saturday", but "calc" may match "calculus".
    """
    stem = _stem(term)
    if term in words or stem in words:
        return True
    if len(stem) >= 4:
        return any(word.startswith(stem) for word in words)
    return False


def parse_topic(text: Optional[str]) -> TopicQuery:
    raw = (text or "").strip()
    if not raw:
        return TopicQuery(raw="")
    terms: list[str] = []
    category_words: list[str] = []
    categories: set[LearningNodeCategory] = set()
    for token in tokenize(raw):
        if token in _STOPWORDS:
            continue
        if token in _CATEGORY_WORDS:
            category_words.append(token)
            categories.update(_CATEGORY_WORDS[token])
        else:
            terms.append(token)
    return TopicQuery(
        raw=raw,
        terms=tuple(dict.fromkeys(terms)),
        category_words=tuple(dict.fromkeys(category_words)),
        categories=frozenset(categories),
    )


@dataclass(frozen=True)
class SearchIntent:
    """How a search box entry should drive the map."""

    kind: str  # "topic", "place", or "mixed"
    topic: TopicQuery
    place_text: Optional[str]


def classify(text: str) -> SearchIntent:
    """Split a search into its topic and place parts without any network call.

    ``place_text`` is only a candidate; the caller confirms it with the
    geocoder and falls back to a topic search when nothing is found.
    """
    raw = " ".join((text or "").split())
    if not raw:
        return SearchIntent(kind="topic", topic=TopicQuery(raw=""), place_text=None)

    if _POSTAL_CODE.match(raw):
        return SearchIntent(kind="place", topic=TopicQuery(raw=""), place_text=raw)

    parts = _LOCATION_SPLIT.split(raw, maxsplit=1)
    if len(parts) == 2 and parts[0].strip() and parts[1].strip():
        topic = parse_topic(parts[0])
        if not topic.is_empty:
            return SearchIntent(kind="mixed", topic=topic, place_text=parts[1].strip())

    topic = parse_topic(raw)
    tokens = [token for token in tokenize(raw) if token not in _STOPWORDS]
    looks_like_topic = bool(topic.category_words) or any(
        token in _TOPIC_HINTS for token in tokens
    )
    if looks_like_topic:
        return SearchIntent(kind="topic", topic=topic, place_text=None)
    # Short, hint-free text such as "Bronx" or "Queens" is most likely a
    # place; the geocoder decides, and a miss becomes a topic search.
    if 0 < len(tokens) <= 4:
        return SearchIntent(kind="place", topic=topic, place_text=raw)
    return SearchIntent(kind="topic", topic=topic, place_text=None)
