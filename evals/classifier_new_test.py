"""Does `describes_a_different_test` judge real sentences correctly?

WHY THIS IS NOT A UNIT TEST

The unit tests pin what happens once the model has answered: a yes starts a
new intake, a no does not, and anything unclear is a no. They mock the model,
so they say nothing about whether it answers correctly — and the decision this
makes is not cosmetic. A wrong yes interrogates a learner about an exam they
never mentioned. A wrong no is the bug that was reported: saying "I also have
a social studies test" and being read the biology plan back, forever.

Judging that needs a real model, which needs a key, which a test suite must
not depend on. So it lives here and is run deliberately:

    python -m evals.classifier_new_test

The cases below include the exact phrasings from the bug report, typos and
all, because those are the sentences that failed.
"""

from __future__ import annotations

import asyncio
import sys
from datetime import date
from types import SimpleNamespace

PLANNED = SimpleNamespace(subject="Biology", test_date=date(2026, 9, 29))

#: (message, expected, why it is worth asking)
CASES: list[tuple[str, bool, str]] = [
    # ── From the bug report, verbatim ───────────────────────────────────────
    ("No i have also a social studies test", True, "the reported failure"),
    ("I have a social stufies tes next tuesday", True, "typos, still a second exam"),
    ("I have a test next tuesdya can you help me", True, "typo'd, and no exam planned yet in context"),

    # ── Plainly a second exam ───────────────────────────────────────────────
    ("I also have a chemistry final", True, "another subject"),
    ("what about my history exam", True, "another subject, phrased as a question"),
    ("i have another test in maths on friday", True, "explicit"),
    ("Biology on the 29th and physics on the 30th", True, "two named, one is new"),
    ("I have a second biology test in November", True,
     "same subject, different date, so a different sitting"),

    # ── The same exam ───────────────────────────────────────────────────────
    ("thanks!", False, "not an exam at all"),
    ("ok", False, "not an exam at all"),
    ("when is my biology test again?", False, "asking about the planned one"),
    ("can you move my study sessions later", False, "about the schedule, not a new exam"),
    ("actually the biology test is on the 30th not the 29th", False,
     "correcting the planned exam, not adding one"),
    ("I'm worried about biology", False, "about the planned exam"),
    ("make it harder", False, "about the plan"),

    # ── Deliberately ambiguous: must fall to False ──────────────────────────
    ("test", False, "one word, no exam described"),
    ("yes", False, "an answer to something, not an exam"),
    ("tuesday", False, "a date with no exam named"),
]


async def main() -> int:
    from lyo_app.study_plans.routes import describes_a_different_test

    wrong: list[str] = []
    unreadable = 0
    for message, expected, why in CASES:
        got = await describes_a_different_test(message, PLANNED)
        if got is None:
            unreadable += 1
            mark = "??  "
        else:
            mark = "ok  " if got == expected else "FAIL"
        if got is not None and got != expected:
            wrong.append(f"{message!r} -> {got}, wanted {expected} ({why})")
        print(f"{mark} {str(expected):5} {message!r}")

    if unreadable == len(CASES):
        # Not eighteen wrong answers — zero answers. Saying "0/18 correct"
        # here would report a model failure as a quality result.
        print("\nNo model was reachable: every case returned None and nothing "
              "was judged.\nSet a provider key and run this again.")
        return 2

    judged = len(CASES) - unreadable
    print(f"\n{judged - len(wrong)}/{judged} correct"
          + (f", {unreadable} unreadable" if unreadable else ""))
    for line in wrong:
        print("  -", line)

    # A wrong yes is the expensive one: it invents an exam and starts asking
    # about it. Report the two directions separately rather than one number.
    false_yes = [w for w in wrong if "-> True" in w]
    if false_yes:
        print(f"\n{len(false_yes)} invented an exam the learner never mentioned:")
        for line in false_yes:
            print("  -", line)
    return 1 if wrong else 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
