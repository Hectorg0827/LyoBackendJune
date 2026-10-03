"""A second model reads the teaching, for the failures no string check can see.

`validate_semantic_content` and the generation contracts catch every meaning
failure that is mechanically decidable: the answer visible before it is asked
for, two options with one visible answer, two distractors claiming one
misconception, two options sharing one piece of feedback, a misconception that
only restates its option.

Three failures survive all of that, and they are the ones that matter most:

* **An implausible distractor.** Distinct from the answer, so the schema is
  satisfied, but nobody would ever pick it. A four-option probe with one real
  distractor measures nothing and starts the lesson in the wrong place.
* **A mislabelled gap.** `near_miss` and `fundamental` decide whether the
  learner gets one worked step or the whole example. The label is a claim the
  authoring model makes about its own distractor, and nothing checks it.
* **Teaching that is fluent and wrong.** The most expensive failure in the
  system, and completely invisible to a schema: every field present, every
  length right, the mathematics incorrect.

So this asks a model, and asks it only about those. It is deliberately not a
second opinion on the whole contract — re-litigating rules already enforced
deterministically would make the gate slower and less predictable without
making it stricter.

**It fails open.** An unreachable or unparseable judge returns "sound", and the
turn ships having passed the deterministic gate alone. That is the right way
round: a reviewer that is down is not evidence of bad content, and taking
teaching offline because a *reviewer* broke would turn one degraded dependency
into a learner staring at a retry button. A judge that answers and says the
content is unsound is a different matter, and rejects the turn.

**Enabled by default.** The first authenticated production teacher-quality run
showed why this guard exists: a fluent fraction explanation contradicted itself
while passing every structural check. `CLASSROOM_SEMANTIC_JUDGE=false` remains
an emergency cost/degradation switch, but correctness review is the safe default
for learner-facing authored turns. The judge still fails open when unavailable.
"""

from __future__ import annotations

import logging
import os
from typing import Literal

from pydantic import Field

from lyo_app.ai_classroom.adaptive_teaching import (
    LearningTurn, LearningUnit, StrictModel, model_json,
)

logger = logging.getLogger(__name__)

#: What the judge is allowed to object to. A closed set, so a judge cannot
#: invent a new reason to reject teaching that the deterministic gate has
#: already accepted, and so rejections can be counted by cause.
SemanticFailure = Literal[
    "implausible_distractor",
    "mislabelled_gap",
    "incorrect_teaching",
]


class SemanticVerdict(StrictModel):
    """One judgement about one turn."""

    sound: bool
    #: Set only when `sound` is false, and only to one of the three failures
    #: this review exists for.
    failure: SemanticFailure | None = None
    #: What specifically is wrong, in one sentence, quoting the offending text.
    #: Required on a rejection so a rejection can be audited rather than
    #: trusted, and so a repeated cause is visible in logs.
    reason: str = Field(default="", max_length=400)


JUDGE_PROMPT = """You are reviewing one turn of generated teaching before a learner sees it.

A deterministic checker has ALREADY verified all of the following. Do not
re-check them and do not mention them:
- every required field is present and within its length limits
- the answer does not appear in anything the learner reads before answering
- no two options share a visible answer, a misconception, or feedback
- no misconception merely restates its own option

Judge ONLY these three things, about the content itself. Read the teaching and
the task and decide for yourself; the authoring model's own labels are claims
to be checked, not facts.

1. implausible_distractor — Is every wrong option something a learner who
   misunderstands this skill would actually choose? A wrong option that no one
   would pick is filler: it makes a four-option question a two-option one and
   makes the diagnosis wrong. Judge plausibility for a learner, not whether the
   option is clearly wrong to an expert.

2. mislabelled_gap — Where an option carries a gap label, is it right?
   "near_miss" means the learner has the idea and slips on one step.
   "fundamental" means they are reasoning from a different model of the
   situation. This label decides how much re-teaching the learner is given, so
   a wrong one either wastes their time or leaves them behind.

3. incorrect_teaching — Is anything stated as fact actually false? Check the
   worked steps, the board content, the stated correct answer and the feedback.
   Fluent, well-formatted and wrong is the failure this exists to catch.

Set sound=false for any of the three, naming the failure and quoting the
offending text in reason. Set sound=true if the content is fit to teach, even
if you would have written it differently. Style, tone, wording and pedagogical
preference are not failures.
"""


def judge_enabled() -> bool:
    return os.getenv("CLASSROOM_SEMANTIC_JUDGE", "true").strip().lower() != "false"


async def model_semantic_judge(move: str, unit: LearningUnit, turn: LearningTurn) -> bool:
    """True when the turn is fit to teach, on the three counts above.

    Returns True on any failure to reach or read the judge — see the module
    docstring on why this fails open.
    """
    payload = {
        "move": move,
        "skill": unit.title,
        "objective": unit.objective,
        "material": unit.material,
        "turn": turn.model_dump(mode="json"),
    }
    try:
        verdict = await model_json(JUDGE_PROMPT, payload, SemanticVerdict)
    except Exception as exc:
        # A reviewer being down is not evidence about the content.
        logger.warning("Semantic review unavailable for %s; teaching unreviewed: %s",
                       move, type(exc).__name__)
        return True
    if verdict.sound:
        return True
    # A rejection with no named cause is not actionable and is not a rejection:
    # it is the shape a judge returns when it had nothing to say.
    if verdict.failure is None:
        logger.warning("Semantic review rejected %s without naming a cause; allowing", move)
        return True
    logger.info("Semantic review rejected %s (%s): %s", move, verdict.failure, verdict.reason[:200])
    return False
