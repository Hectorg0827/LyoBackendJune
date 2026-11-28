"""Provider-free practice for the English two-sided linear-equation lesson."""

import re
from decimal import Decimal
from random import SystemRandom

from lyo_app.ai_classroom.adaptive_teaching import (
    CriterionResult, Evaluation, LearningTask, TeachingBeat, normalize_text,
    turn_schema, validate_evaluation, validate_semantic_content,
)

TITLE = "Linear equation practice"
QUESTION = ("Find x and check it by substituting into both sides. "
            "Enter two numbers: x, then the common value of the two sides.")
TRANSFER = ("For how many visits do both plans cost the same, and what is that cost? "
            "Enter the number of visits, then the cost.")
NUMBER = r"[+-]?(?:\d{1,8}(?:\.\d{1,8})?|\.\d{1,8})"
PAIR = re.compile(rf"\s*(?:x\s*=\s*)?({NUMBER})\s*[,;]\s*(?:check\s*=\s*)?({NUMBER})\s*", re.I)


async def recovery_turn(teacher, context, state, move):
    if not context.language_code.lower().startswith("en"):
        return None
    if state.unit.title.strip().casefold() not in {
        "isolating variables on one side of an equation",
        "solving linear equations with variables on both sides",
    }:
        return None

    if move in {"orient", "reteach", "prerequisite", "help", "clarify"}:
        beats = [
            TeachingBeat(speech="Subtract two x from each side. Equal changes preserve equality.",
                         board_title="Collect the variable", board_content="5x + 3 = 2x + 18 becomes 3x + 3 = 18."),
            TeachingBeat(speech="Subtract three and divide by three. Substitute back to check.",
                         board_title="Solve and check", board_content="3x = 15, so x = 5. Both sides equal 28."),
        ]
        return turn_schema(move)(speech="Follow this worked example, then try another equation.",
                                 board_title=TITLE, board_content="Worked example: 5x + 3 = 2x + 18.",
                                 demonstration=beats if move in {"orient", "reteach", "prerequisite"} else [])
    if move not in {"guided", "faded", "independent", "transfer", "closing_win"}:
        return None

    rng = SystemRandom()
    for _ in range(12):
        b, gap, constant, solution = (rng.randint(2, 9) for _ in range(4))
        a = b + gap
        right = constant + gap * solution
        common = a * solution + constant
        scenario = f"Solve the equation {a}x + {constant} = {b}x + {right}."
        question = QUESTION
        if move == "transfer":
            scenario = (f"Plan A charges {constant} dollars plus {a} dollars per visit. "
                        f"Plan B charges {right} dollars plus {b} dollars per visit.")
            question = TRANSFER
        task = LearningTask(kind="apply", target_index=state.target_index, scenario=scenario,
                            question=question, response_hint="Enter the two numbers separated by a comma.",
                            criteria=["Find the value that balances the two expressions.",
                                      "Evaluate the equal expressions at that value."],
                            example_answer=f"{solution}, {common}")
        if normalize_text(scenario + " " + question) in state.recent_questions:
            continue
        turn = turn_schema(move)(speech="Work through this example and check your result.",
                                 board_title=TITLE, board_content=scenario, task=task)
        validate_semantic_content(turn)
        if await teacher.claim_question(context, state, move, task):
            return turn
    return None


def is_recovery_question(pending):
    return pending.board_title == TITLE and pending.task.question in {QUESTION, TRANSFER}


def grade_recovery(pending, response):
    task = pending.task
    if not is_recovery_question(pending):
        return None
    key = PAIR.fullmatch(task.example_answer)
    answer = PAIR.fullmatch(response)
    if not key or not answer:
        # Other valid expressions and prose still use the ordinary semantic grader.
        return None
    matches = [Decimal(value) == Decimal(expected)
               for value, expected in zip(answer.groups(), key.groups())]
    if all(matches):
        verdict, feedback = "correct", "Your solution makes both expressions equal, and your check agrees."
    elif any(matches):
        verdict = "partial"
        feedback = ("Your first value balances the expressions. Recalculate their common value."
                    if matches[0] else "Your common value is right. Recheck the value of the variable.")
    else:
        verdict, feedback = "incorrect", "Collect the variable terms on one side, solve, and substitute back."
    result = Evaluation(verdict=verdict, confidence=1, question_clear=True, feedback=feedback,
                        follow_up="Enter your revised pair of numbers." if verdict == "partial" else "",
                        criteria=[CriterionResult(index=i, met=match, quote=answer.group(i + 1) if match else "")
                                  for i, match in enumerate(matches)])
    return validate_evaluation(result, task, [response])
