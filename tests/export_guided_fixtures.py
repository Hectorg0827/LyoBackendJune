"""Export authored, deterministic client fixtures through the production runner.

python -m tests.export_guided_fixtures /path/to/GuidedTeaching.json
These are contract examples, not claims about live model output.
"""

import asyncio
import json
import sys
from pathlib import Path

from lyo_app.ai_classroom.adaptive_session import AdaptiveSession
from lyo_app.ai_classroom.adaptive_teaching import LearningTask, LearningTurn, TeachingBeat
from lyo_app.ai_classroom.sdui_models import ActionIntent
from lyo_app.ai_classroom.teaching_visuals import TeachingVisual
from tests.adaptive_fixtures import ScriptedTeacher, action, context


def visuals():
    return [
        TeachingVisual(kind="fraction_bar", title="One whole. Equal parts.",
            caption="Shade one part, then another. Each part is the same size; the whole stays fixed.",
            description="A 12 cm bar is divided into four equal parts. Each part measures 3 cm.",
            parts=4, whole=12, value=1, unit="cm"),
        TeachingVisual(kind="comparison", title="Same whole, different cuts",
            caption="Compare the cuts. Notice what happens to each piece when there are more pieces.",
            description="Half and a third come from identical pizzas. Half is larger because there are fewer equal pieces.",
            entries=[{"label": "2 equal pieces", "detail": "Each piece is one half. Fewer cuts make a larger piece."},
                     {"label": "3 equal pieces", "detail": "Each piece is one third. More cuts make a smaller piece."}]),
        TeachingVisual(kind="sequence", title="A method you can reuse",
            caption="Tap a step to see why it matters when comparing parts.",
            description="First check the wholes match. Then check the cuts are equal. Finally compare how many pieces each whole has.",
            entries=[{"label": "Match the wholes", "detail": "Both pizzas must be the same size before we compare their pieces."},
                     {"label": "Check equal cuts", "detail": "Each pizza must be cut into equal-sized pieces."},
                     {"label": "Compare the pieces", "detail": "For the same whole, fewer equal pieces means each piece is larger."}]),
        TeachingVisual(kind="graph", title="See how slope changes",
            caption="Increase a. Watch the line become steeper while the axes stay fixed.",
            description="The line y = a times x passes through the origin. When a increases from 1 to 2, y at x = 1 increases from 1 to 2.",
            expression="a*x", params=[{"name": "a", "min": -3, "max": 3, "initial": 1, "step": 0.1}],
            x_min=-5, x_max=5, y_min=-10, y_max=10),
    ]


class FixtureTeacher(ScriptedTeacher):
    def _turn(self, ctx, state, move, learner_input=""):
        turn = super()._turn(ctx, state, move, learner_input)
        tools = visuals()
        if move == "orient":
            return LearningTurn(
                speech="Imagine sharing a snack with a friend. Today we'll find which fraction gives the larger piece. I'll show you one example, then we'll try the next step together.",
                board_title="Our goal: compare equal parts",
                board_content="By the end, you can compare a half and a third of the same whole. Start by exploring equal parts of this bar.",
                visual=tools[0], demonstration=[
                    TeachingBeat(speech="First, I check that both pizzas are the same size. That's essential: half of a tiny pizza could be smaller than a third of a huge one.",
                        board_title="Step 1 · Match the wholes", board_content="Two identical pizzas. One will have 2 equal pieces; the other will have 3.", visual=tools[1]),
                    TeachingBeat(speech="Now I compare one piece from each pizza. Cutting the same whole into more pieces makes each piece smaller. So one half is larger than one third.",
                        board_title="Step 2 · Compare one piece", board_content="Same whole: 1/2 > 1/3. Fewer equal pieces → a larger piece.", visual=tools[2]),
                ])
        if move == "guided":
            turn.visual = tools[1]
            turn.task.question = "Which single piece is larger?"
            turn.task.response_hint = "Tap one piece. We can work through it together."
            turn.task.criteria = ["Identifies one half as larger"]
        if move in ("faded", "independent"):
            turn.board_title = "Finish just the last step" if move == "faded" else "Use the same idea"
            turn.board_content = ("The bars are identical. All cuts are equal. The first bar has 4 pieces; the second has 8. Fewer pieces means each piece is larger." if move == "faded" else "Check that the wholes match, then compare the number of equal pieces.")
            turn.speech = ("You've got the comparison. I've checked the wholes and cuts in this next example. You only need to finish the last step." if move == "faded" else "Now try a fresh example using the same method. A short answer is enough. You can ask for help at any time.")
            turn.task = LearningTask(kind="apply", response_format="completion" if move == "faded" else "short_answer",
                target_index=state.target_index,
                scenario="Two identical bars are divided into 4 and 8 equal pieces." if move == "faded" else "Two identical pies are divided into 3 and 6 equal slices.",
                question="Finish: the larger piece is 1/__." if move == "faded" else "Which slice is larger: 1/3 or 1/6?",
                response_hint="Write just the missing number." if move == "faded" else "Write the larger fraction.",
                criteria=["Answers 4" if move == "faded" else "Answers one third"],
                example_answer="4" if move == "faded" else "1/3")
        return turn


async def export():
    teacher, ctx, progress = FixtureTeacher(), context(target_duration_minutes=8), {}
    runner = AdaptiveSession(teacher)
    scenes = {}
    scenes["orientation"] = await runner.run(ctx, progress, action(welcome=True))
    for name in ("model_1", "model_2", "guided"):
        scenes[name] = await runner.run(ctx, progress, action(component_id=progress["guided_state"]["step_id"]))
    for name, response in (("faded", "One half"), ("independent", "4"), ("summary", "1/3")):
        pending = progress["guided_state"]["pending"]
        intent = ActionIntent.SUBMIT_ANSWER if pending["task"]["response_format"] == "choice" else ActionIntent.SUBMIT_TRANSFER
        scenes[name] = await runner.run(ctx, progress, action(intent, pending["id"], answer_data={"selected_option_id": "a", "response": response}))
    return {"scenes": {name: scene.model_dump(mode="json") for name, scene in scenes.items()},
            "visuals": [visual.model_dump(mode="json") for visual in visuals()]}


if __name__ == "__main__":
    destination = Path(sys.argv[1])
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(json.dumps(asyncio.run(export()), indent=2, ensure_ascii=False) + "\n")
