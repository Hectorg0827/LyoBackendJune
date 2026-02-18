#!/usr/bin/env python3
"""
Thorough A2UI Producer Test Suite
Tests every method, edge case, serialization rule, and conformance point.
"""

import json
import sys
import traceback
from uuid import UUID

# ─── Setup ───────────────────────────────────────────────────────────────────
sys.path.insert(0, "/Users/hectorgarcia/Desktop/LyoBackendJune")

passed = 0
failed = 0
errors = []

def test(name, condition, detail=""):
    global passed, failed, errors
    if condition:
        passed += 1
        print(f"  ✅ {name}")
    else:
        failed += 1
        errors.append(f"{name}: {detail}")
        print(f"  ❌ {name} — {detail}")

def section(title):
    print(f"\n{'='*60}")
    print(f"  {title}")
    print(f"{'='*60}")

# ─── Helper: deep validation ─────────────────────────────────────────────────
IOS_SNAKE_KEYS = {
    "foreground_color", "background_color", "font_size", "font_weight",
    "border_radius", "border_color", "border_width", "corner_radius",
    "padding_top", "padding_bottom", "padding_leading", "padding_trailing",
    "text_color", "min_height", "max_width", "line_limit",
    "image_url", "video_url", "correct_answer_index",
}
CAMEL_BANNED = {
    "foregroundColor", "backgroundColor", "fontSize", "fontWeight",
    "borderRadius", "borderColor", "borderWidth", "cornerRadius",
    "correctAnswerIndex", "imageUrl", "videoUrl",
}

def count_nodes(obj):
    c = 0
    if isinstance(obj, dict):
        if "type" in obj: c += 1
        for v in obj.values(): c += count_nodes(v)
    elif isinstance(obj, list):
        for v in obj: c += count_nodes(v)
    return c

def count_ids(obj):
    c = 0
    if isinstance(obj, dict):
        if "id" in obj: c += 1
        for v in obj.values(): c += count_ids(v)
    elif isinstance(obj, list):
        for v in obj: c += count_ids(v)
    return c

def find_camel_keys(obj, path=""):
    found = []
    if isinstance(obj, dict):
        for k, v in obj.items():
            if k in CAMEL_BANNED:
                found.append(f"{path}.{k}")
            found.extend(find_camel_keys(v, f"{path}.{k}"))
    elif isinstance(obj, list):
        for i, v in enumerate(obj):
            found.extend(find_camel_keys(v, f"{path}[{i}]"))
    return found

def validate_component_dict(d, label):
    """Validate a to_dict() output against all iOS conformance rules."""
    # 1. JSON serializable
    try:
        j = json.dumps(d)
        test(f"[{label}] JSON serializable", True)
    except (TypeError, ValueError) as e:
        test(f"[{label}] JSON serializable", False, str(e))
        return

    # 2. All nodes have id
    nodes = count_nodes(d)
    ids = count_ids(d)
    test(f"[{label}] All {nodes} nodes have id", nodes == ids, f"only {ids}/{nodes} have id")

    # 3. All ids are valid UUID strings
    def check_uuids(obj):
        bad = []
        if isinstance(obj, dict):
            if "id" in obj:
                try:
                    UUID(obj["id"])
                except:
                    bad.append(obj["id"])
            for v in obj.values():
                bad.extend(check_uuids(v))
        elif isinstance(obj, list):
            for v in obj:
                bad.extend(check_uuids(v))
        return bad
    bad_uuids = check_uuids(d)
    test(f"[{label}] All ids are valid UUIDs", len(bad_uuids) == 0, f"bad: {bad_uuids[:3]}")

    # 4. Root type is a string (not enum object)
    test(f"[{label}] Root type is str", isinstance(d.get("type"), str), f"got {type(d.get('type'))}")

    # 5. No camelCase keys (iOS expects snake_case)
    camel = find_camel_keys(d)
    test(f"[{label}] No camelCase keys", len(camel) == 0, f"found: {camel[:5]}")

    # 6. Check all nested type fields are strings
    def check_types_are_str(obj):
        bad = []
        if isinstance(obj, dict):
            if "type" in obj and not isinstance(obj["type"], str):
                bad.append(str(type(obj["type"])))
            for v in obj.values():
                bad.extend(check_types_are_str(v))
        elif isinstance(obj, list):
            for v in obj:
                bad.extend(check_types_are_str(v))
        return bad
    bad_types = check_types_are_str(d)
    test(f"[{label}] All type fields are str", len(bad_types) == 0, f"non-str: {bad_types[:3]}")

    # 7. JSON size reasonable (< 100KB)
    test(f"[{label}] JSON size < 100KB", len(j) < 100_000, f"size: {len(j)}")

    return d

# ═══════════════════════════════════════════════════════════════════════════════
# TEST 1: IMPORTS
# ═══════════════════════════════════════════════════════════════════════════════
section("1. IMPORTS")
try:
    from lyo_app.a2ui.a2ui_producer import a2ui_producer, A2UIProducer
    test("Import A2UIProducer", True)
except Exception as e:
    test("Import A2UIProducer", False, str(e))
    sys.exit(1)

try:
    from lyo_app.a2ui.models import A2UIComponent, A2UIElementType, A2UIProps
    test("Import A2UI models", True)
except Exception as e:
    test("Import A2UI models", False, str(e))

try:
    from lyo_app.a2ui.extractors import extract_course, extract_explanation, extract_quiz, extract_study_plan
    test("Import extractors", True)
except Exception as e:
    test("Import extractors", False, str(e))

try:
    from lyo_app.a2ui.normalized_models import NormalizedCourse, NormalizedExplanation, NormalizedQuiz, NormalizedStudyPlan
    test("Import normalized models", True)
except Exception as e:
    test("Import normalized models", False, str(e))

# ═══════════════════════════════════════════════════════════════════════════════
# TEST 2: PRODUCE COURSE (happy path)
# ═══════════════════════════════════════════════════════════════════════════════
section("2. PRODUCE COURSE — Happy Path")
course_input = {
    "title": "Python Fundamentals",
    "topic": "Python Programming",
    "description": "Learn Python from scratch",
    "difficulty": "Beginner",
    "duration": "~45 min",
    "objectives": ["Variables", "Functions", "Loops", "Data Structures"],
    "modules": [
        {
            "title": "Getting Started",
            "lessons": [
                {"title": "Installing Python", "content": "Download from python.org..."},
                {"title": "Hello World", "content": "print('Hello, world!')"}
            ]
        },
        {
            "title": "Core Concepts",
            "lessons": [
                {"title": "Variables & Types", "content": "x = 42; name = 'Lyo'"},
                {"title": "Control Flow", "content": "if/else, for, while"}
            ]
        }
    ]
}
result = a2ui_producer.produce_course(course_input, topic="Python")
test("produce_course returns dict", isinstance(result, dict))
test("Has a2ui_component key", "a2ui_component" in result)
test("Has open_classroom key", "open_classroom" in result)
test("a2ui_component is A2UIComponent", isinstance(result["a2ui_component"], A2UIComponent))
test("open_classroom is dict", isinstance(result.get("open_classroom"), dict))
test("open_classroom has 'course' wrapper key", "course" in result.get("open_classroom", {}))

oc = result["open_classroom"]["course"]
test("Course payload has id", "id" in oc)
test("Course payload has title", oc.get("title") == "Python Fundamentals")
test("Course payload has level", "level" in oc)
test("Course payload has objectives", isinstance(oc.get("objectives"), list))

d = result["a2ui_component"].to_dict()
validate_component_dict(d, "course-happy")

# ═══════════════════════════════════════════════════════════════════════════════
# TEST 3: PRODUCE COURSE — Minimal input
# ═══════════════════════════════════════════════════════════════════════════════
section("3. PRODUCE COURSE — Minimal Input")
min_result = a2ui_producer.produce_course({"title": "Math"}, topic="Math")
test("Minimal course returns dict", isinstance(min_result, dict))
test("Has a2ui_component", isinstance(min_result.get("a2ui_component"), A2UIComponent))
test("Has open_classroom", "open_classroom" in min_result)
validate_component_dict(min_result["a2ui_component"].to_dict(), "course-minimal")

# ═══════════════════════════════════════════════════════════════════════════════
# TEST 4: PRODUCE COURSE — From string (text fallback)
# ═══════════════════════════════════════════════════════════════════════════════
section("4. PRODUCE COURSE — String Input")
str_result = a2ui_producer.produce_course(
    "Here's a course about Biology with chapters on Cells, DNA, and Evolution",
    topic="Biology"
)
test("String course returns dict", isinstance(str_result, dict))
test("Has a2ui_component", isinstance(str_result.get("a2ui_component"), A2UIComponent))
validate_component_dict(str_result["a2ui_component"].to_dict(), "course-string")

# ═══════════════════════════════════════════════════════════════════════════════
# TEST 5: PRODUCE COURSE — Garbage input
# ═══════════════════════════════════════════════════════════════════════════════
section("5. PRODUCE COURSE — Garbage Input")
garbage_result = a2ui_producer.produce_course(12345, topic="Fallback Topic")
test("Garbage course returns dict", isinstance(garbage_result, dict))
test("Has a2ui_component", isinstance(garbage_result.get("a2ui_component"), A2UIComponent))
oc_g = garbage_result.get("open_classroom", {}).get("course", {})
test("Fallback title uses topic", "Fallback Topic" in str(oc_g.get("title", "")))
validate_component_dict(garbage_result["a2ui_component"].to_dict(), "course-garbage")

# ═══════════════════════════════════════════════════════════════════════════════
# TEST 6: PRODUCE COURSE — None input
# ═══════════════════════════════════════════════════════════════════════════════
section("6. PRODUCE COURSE — None Input")
none_result = a2ui_producer.produce_course(None, topic="Emergency")
test("None course returns dict", isinstance(none_result, dict))
test("Has a2ui_component", isinstance(none_result.get("a2ui_component"), A2UIComponent))
validate_component_dict(none_result["a2ui_component"].to_dict(), "course-none")

# ═══════════════════════════════════════════════════════════════════════════════
# TEST 7: PRODUCE EXPLANATION
# ═══════════════════════════════════════════════════════════════════════════════
section("7. PRODUCE EXPLANATION — Happy Path")
expl = a2ui_producer.produce_explanation(
    "Photosynthesis is the process by which green plants use sunlight, water, "
    "and carbon dioxide to create oxygen and energy in the form of sugar. "
    "Key points: 1) Chlorophyll absorbs light 2) Water is split 3) CO2 is fixed",
    topic="Biology"
)
test("produce_explanation returns A2UIComponent", isinstance(expl, A2UIComponent))
d_expl = expl.to_dict()
validate_component_dict(d_expl, "explanation-happy")
test("Explanation root type is card", d_expl["type"] == "card")
test("Has children", len(d_expl.get("children", [])) > 0)

# ═══════════════════════════════════════════════════════════════════════════════
# TEST 8: PRODUCE EXPLANATION — Dict input
# ═══════════════════════════════════════════════════════════════════════════════
section("8. PRODUCE EXPLANATION — Dict Input")
expl_dict = a2ui_producer.produce_explanation(
    {"topic": "Gravity", "content": "Gravity is a fundamental force", "key_points": ["F=ma", "Newton", "Einstein"]},
    topic="Physics"
)
test("Dict explanation returns A2UIComponent", isinstance(expl_dict, A2UIComponent))
validate_component_dict(expl_dict.to_dict(), "explanation-dict")

# ═══════════════════════════════════════════════════════════════════════════════
# TEST 9: PRODUCE EXPLANATION — Empty string
# ═══════════════════════════════════════════════════════════════════════════════
section("9. PRODUCE EXPLANATION — Empty String")
expl_empty = a2ui_producer.produce_explanation("", topic="Nothing")
test("Empty explanation returns A2UIComponent", isinstance(expl_empty, A2UIComponent))
validate_component_dict(expl_empty.to_dict(), "explanation-empty")

# ═══════════════════════════════════════════════════════════════════════════════
# TEST 10: PRODUCE QUIZ
# ═══════════════════════════════════════════════════════════════════════════════
section("10. PRODUCE QUIZ — Happy Path")
quiz = a2ui_producer.produce_quiz({
    "question": "What is the capital of France?",
    "options": ["London", "Paris", "Berlin", "Madrid"],
    "correct_answer_index": 1,
    "explanation": "Paris is the capital of France since the 10th century."
})
test("produce_quiz returns A2UIComponent", isinstance(quiz, A2UIComponent))
d_quiz = quiz.to_dict()
validate_component_dict(d_quiz, "quiz-happy")

# ═══════════════════════════════════════════════════════════════════════════════
# TEST 11: PRODUCE QUIZ — Minimal
# ═══════════════════════════════════════════════════════════════════════════════
section("11. PRODUCE QUIZ — Minimal")
quiz_min = a2ui_producer.produce_quiz({"question": "1+1=?"})
test("Minimal quiz returns A2UIComponent", isinstance(quiz_min, A2UIComponent))
validate_component_dict(quiz_min.to_dict(), "quiz-minimal")

# ═══════════════════════════════════════════════════════════════════════════════
# TEST 12: PRODUCE QUIZ — None
# ═══════════════════════════════════════════════════════════════════════════════
section("12. PRODUCE QUIZ — None Input")
quiz_none = a2ui_producer.produce_quiz(None)
test("None quiz returns A2UIComponent", isinstance(quiz_none, A2UIComponent))
validate_component_dict(quiz_none.to_dict(), "quiz-none")

# ═══════════════════════════════════════════════════════════════════════════════
# TEST 13: PRODUCE STUDY PLAN
# ═══════════════════════════════════════════════════════════════════════════════
section("13. PRODUCE STUDY PLAN — Happy Path")
plan = a2ui_producer.produce_study_plan({
    "title": "30-Day Python Mastery",
    "description": "Master Python in one month",
    "milestones": [
        {"title": "Week 1: Basics", "description": "Variables, types, control flow"},
        {"title": "Week 2: Functions", "description": "Functions, modules, packages"},
        {"title": "Week 3: OOP", "description": "Classes, inheritance, polymorphism"},
        {"title": "Week 4: Projects", "description": "Build 3 real projects"},
    ],
    "duration": "30 days",
    "daily_minutes": 45
}, topic="Python")
test("produce_study_plan returns A2UIComponent", isinstance(plan, A2UIComponent))
validate_component_dict(plan.to_dict(), "study-plan-happy")

# ═══════════════════════════════════════════════════════════════════════════════
# TEST 14: PRODUCE STUDY PLAN — Empty
# ═══════════════════════════════════════════════════════════════════════════════
section("14. PRODUCE STUDY PLAN — Empty Input")
plan_empty = a2ui_producer.produce_study_plan({}, topic="General")
test("Empty study plan returns A2UIComponent", isinstance(plan_empty, A2UIComponent))
validate_component_dict(plan_empty.to_dict(), "study-plan-empty")

# ═══════════════════════════════════════════════════════════════════════════════
# TEST 15: PRODUCE SKELETON
# ═══════════════════════════════════════════════════════════════════════════════
section("15. PRODUCE SKELETON")
skel = a2ui_producer.produce_skeleton(topic="Loading...")
test("produce_skeleton returns A2UIComponent", isinstance(skel, A2UIComponent))
d_skel = skel.to_dict()
validate_component_dict(d_skel, "skeleton")
test("Skeleton root type is vStack (container)", d_skel["type"] == "vStack")

# ═══════════════════════════════════════════════════════════════════════════════
# TEST 16: PRODUCE ERROR
# ═══════════════════════════════════════════════════════════════════════════════
section("16. PRODUCE ERROR")
err = a2ui_producer.produce_error("Something went terribly wrong")
test("produce_error returns A2UIComponent", isinstance(err, A2UIComponent))
d_err = err.to_dict()
validate_component_dict(d_err, "error")
test("Error contains message text", "Something went terribly wrong" in json.dumps(d_err))

# ═══════════════════════════════════════════════════════════════════════════════
# TEST 17: PRODUCE AUTO — dispatch
# ═══════════════════════════════════════════════════════════════════════════════
section("17. PRODUCE AUTO — Dispatch")
auto_expl = a2ui_producer.produce_auto("Explain quantum physics", ui_type="explanation", topic="Physics")
test("produce_auto explanation returns A2UIComponent", isinstance(auto_expl, A2UIComponent))
validate_component_dict(auto_expl.to_dict(), "auto-explanation")

auto_quiz = a2ui_producer.produce_auto({"question": "2+2=?", "options": ["3","4","5"]}, ui_type="quiz")
test("produce_auto quiz returns A2UIComponent", isinstance(auto_quiz, A2UIComponent))
validate_component_dict(auto_quiz.to_dict(), "auto-quiz")

auto_plan = a2ui_producer.produce_auto({"title": "Quick Plan"}, ui_type="study_plan", topic="Testing")
test("produce_auto study_plan returns A2UIComponent", isinstance(auto_plan, A2UIComponent))
validate_component_dict(auto_plan.to_dict(), "auto-study-plan")

# ═══════════════════════════════════════════════════════════════════════════════
# TEST 18: PRODUCE COURSE A2UI ONLY
# ═══════════════════════════════════════════════════════════════════════════════
section("18. PRODUCE COURSE A2UI ONLY")
a2ui_only = a2ui_producer.produce_course_a2ui_only(
    {"title": "Quick Course", "modules": [{"title": "M1", "lessons": [{"title": "L1"}]}]},
    topic="Test"
)
test("produce_course_a2ui_only returns A2UIComponent", isinstance(a2ui_only, A2UIComponent))
validate_component_dict(a2ui_only.to_dict(), "course-a2ui-only")

# ═══════════════════════════════════════════════════════════════════════════════
# TEST 19: EXTRACTOR UNIT TESTS
# ═══════════════════════════════════════════════════════════════════════════════
section("19. EXTRACTORS — Unit Tests")

# extract_course
c1 = extract_course({"title": "Algebra", "modules": []}, fallback_topic="Math")
test("extract_course from dict", c1.title == "Algebra")

c2 = extract_course("A course about History with introduction and key events", fallback_topic="History")
test("extract_course from string", c2.title != "" and c2.topic != "")

c3 = extract_course(None, fallback_topic="Fallback")
test("extract_course from None", c3.title == "Fallback" or c3.topic == "Fallback")

c4 = extract_course(42, fallback_topic="Numbers")
test("extract_course from int", c4.title != "")

# extract_explanation
e1 = extract_explanation({"topic": "Gravity", "content": "Force of attraction"}, fallback_topic="Physics")
test("extract_explanation from dict", e1.topic == "Gravity")

e2 = extract_explanation("Mitosis is cell division", fallback_topic="Biology")
test("extract_explanation from string", e2.content != "")

e3 = extract_explanation(None, fallback_topic="Empty")
test("extract_explanation from None", e3.topic == "Empty")

# extract_quiz
q1 = extract_quiz({"question": "What is 2+2?", "options": ["3","4","5"], "correct_answer_index": 1})
test("extract_quiz from dict", q1.question == "What is 2+2?")
test("extract_quiz options", len(q1.options) == 3)

q2 = extract_quiz(None)
test("extract_quiz from None", q2.question != "")

# extract_study_plan
p1 = extract_study_plan({"title": "Plan A", "milestones": [{"title": "Step 1"}]}, fallback_topic="Test")
test("extract_study_plan from dict", p1.title == "Plan A")

p2 = extract_study_plan(None, fallback_topic="Fallback Plan")
test("extract_study_plan from None", p2.title != "")

# ═══════════════════════════════════════════════════════════════════════════════
# TEST 20: NORMALIZED MODELS — Defaults
# ═══════════════════════════════════════════════════════════════════════════════
section("20. NORMALIZED MODELS — Defaults")

nc = NormalizedCourse()
test("NormalizedCourse default id", nc.id != "")
test("NormalizedCourse default title", nc.title != "")
test("NormalizedCourse default modules", isinstance(nc.modules, list))
test("NormalizedCourse flat_lessons", isinstance(nc.flat_lessons, list))

ne = NormalizedExplanation()
test("NormalizedExplanation default topic", ne.topic != "")
test("NormalizedExplanation default content", isinstance(ne.content, str))

nq = NormalizedQuiz()
test("NormalizedQuiz default question", nq.question != "")
test("NormalizedQuiz default options", isinstance(nq.options, list))

np = NormalizedStudyPlan()
test("NormalizedStudyPlan default title", np.title != "")
test("NormalizedStudyPlan default milestones", isinstance(np.milestones, list))

# ═══════════════════════════════════════════════════════════════════════════════
# TEST 21: to_dict() vs to_json() consistency
# ═══════════════════════════════════════════════════════════════════════════════
section("21. to_dict() vs to_json() Consistency")
comp = A2UIComponent(type=A2UIElementType.CARD, children=[
    A2UIComponent(type=A2UIElementType.TEXT, props=A2UIProps(text="Hello")),
    A2UIComponent(type=A2UIElementType.ACTION_BUTTON, props=A2UIProps(text="Click me")),
])
d = comp.to_dict()
j = comp.to_json()
test("to_dict produces dict", isinstance(d, dict))
test("to_json produces str", isinstance(j, str))
# Parse to_json and compare structure
j_parsed = json.loads(j)
test("to_json parses back", isinstance(j_parsed, dict))
test("Both have same keys", set(d.keys()) == set(j_parsed.keys()))

# ═══════════════════════════════════════════════════════════════════════════════
# TEST 22: UIBlock wrapping (simulates executor.py)
# ═══════════════════════════════════════════════════════════════════════════════
section("22. UIBlock Wrapping (Executor Simulation)")
try:
    from lyo_app.ai.schemas.lyo2 import UIBlock, UIBlockType
    comp_for_block = a2ui_producer.produce_explanation("Test content", topic="Test")
    block = UIBlock(
        type=UIBlockType.A2UI_COMPONENT,
        content={"component": comp_for_block.to_dict() if hasattr(comp_for_block, 'to_dict') else comp_for_block}
    )
    block_dump = block.model_dump()
    test("UIBlock model_dump succeeds", isinstance(block_dump, dict))
    test("UIBlock has type A2UIComponent", str(block_dump["type"]) == "A2UIComponent" or block_dump["type"].value == "A2UIComponent")
    test("UIBlock content has 'component' key", "component" in block_dump.get("content", {}))
    
    # Simulate SSE serialization
    sse_data = json.dumps({"type": "a2ui", "block": block_dump})
    test("SSE json.dumps succeeds", len(sse_data) > 100)
    sse_parsed = json.loads(sse_data)
    test("SSE parsed type is 'a2ui'", sse_parsed["type"] == "a2ui")
    test("SSE block has component", "component" in sse_parsed["block"]["content"])
    
    # Validate the component inside the SSE payload
    inner_comp = sse_parsed["block"]["content"]["component"]
    validate_component_dict(inner_comp, "sse-inner-component")
except Exception as e:
    test("UIBlock wrapping", False, traceback.format_exc())

# ═══════════════════════════════════════════════════════════════════════════════
# TEST 23: OpenClassroom payload (simulates stream_lyo2.py)
# ═══════════════════════════════════════════════════════════════════════════════
section("23. OpenClassroom Payload (Stream Simulation)")
oc_result = a2ui_producer.produce_course(
    {"title": "Geography 101", "modules": [{"title": "Maps", "lessons": [{"title": "Reading Maps"}]}]},
    topic="Geography"
)
oc_payload = oc_result.get("open_classroom", {})
test("open_classroom payload exists", bool(oc_payload))
test("Has 'course' wrapper key", "course" in oc_payload)

# Simulate stream_lyo2.py wrapping
oc_block = {
    "type": "OpenClassroomBlock",
    "content": {
        "type": "OPEN_CLASSROOM",
        **oc_payload
    }
}
oc_sse = json.dumps({"type": "open_classroom", "block": oc_block})
test("OpenClassroom SSE serializable", len(oc_sse) > 50)
oc_parsed = json.loads(oc_sse)
test("SSE type is 'open_classroom'", oc_parsed["type"] == "open_classroom")
test("Block type is OpenClassroomBlock", oc_parsed["block"]["type"] == "OpenClassroomBlock")
test("Content has OPEN_CLASSROOM type", oc_parsed["block"]["content"]["type"] == "OPEN_CLASSROOM")
test("Content has 'course' key", "course" in oc_parsed["block"]["content"])
test("Course has title", oc_parsed["block"]["content"]["course"].get("title") == "Geography 101")

# ═══════════════════════════════════════════════════════════════════════════════
# TEST 24: STRESS — Large course
# ═══════════════════════════════════════════════════════════════════════════════
section("24. STRESS — Large Course (20 modules, 100 lessons)")
big_course = {
    "title": "Comprehensive Computer Science",
    "topic": "CS",
    "objectives": [f"Objective {i}" for i in range(20)],
    "modules": [
        {
            "title": f"Module {m}",
            "lessons": [
                {"title": f"Lesson {m}.{l}", "content": f"Content for lesson {m}.{l} " * 50}
                for l in range(5)
            ]
        }
        for m in range(20)
    ]
}
big_result = a2ui_producer.produce_course(big_course, topic="CS")
test("Large course doesn't crash", isinstance(big_result, dict))
d_big = big_result["a2ui_component"].to_dict()
big_nodes = count_nodes(d_big)
test(f"Large course has {big_nodes} nodes", big_nodes > 5)
validate_component_dict(d_big, "course-large")

# ═══════════════════════════════════════════════════════════════════════════════
# TEST 25: STRESS — Unicode & special characters
# ═══════════════════════════════════════════════════════════════════════════════
section("25. STRESS — Unicode & Special Characters")
unicode_expl = a2ui_producer.produce_explanation(
    "数学は美しい。Einstein said E=mc². Thé café résumé naïve. 🧠💡📚 <script>alert('xss')</script>",
    topic="Ünïcödé"
)
test("Unicode explanation doesn't crash", isinstance(unicode_expl, A2UIComponent))
d_uni = unicode_expl.to_dict()
validate_component_dict(d_uni, "unicode")
j_uni = json.dumps(d_uni, ensure_ascii=False)
test("Unicode JSON valid", len(j_uni) > 50)

# ═══════════════════════════════════════════════════════════════════════════════
# TEST 26: IDEMPOTENCY — Same input produces valid output each time
# ═══════════════════════════════════════════════════════════════════════════════
section("26. IDEMPOTENCY — Repeated calls")
for i in range(5):
    r = a2ui_producer.produce_explanation("Same input every time", topic="Test")
    test(f"Idempotent call {i+1}", isinstance(r, A2UIComponent))

# ═══════════════════════════════════════════════════════════════════════════════
# TEST 27: PRODUCE_LESSON
# ═══════════════════════════════════════════════════════════════════════════════
section("27. PRODUCE LESSON")
try:
    lesson = a2ui_producer.produce_lesson(
        {"title": "Variables in Python", "content": "Variables store data. x = 5; name = 'Alice'"},
        index=0, total=10
    )
    test("produce_lesson returns A2UIComponent", isinstance(lesson, A2UIComponent))
    validate_component_dict(lesson.to_dict(), "lesson")
except Exception as e:
    test("produce_lesson", False, str(e))

# ═══════════════════════════════════════════════════════════════════════════════
# TEST 28: iOS A2UIElementType coverage
# ═══════════════════════════════════════════════════════════════════════════════
section("28. A2UIElementType — Used types exist")
used_types = set()
def collect_types(obj):
    if isinstance(obj, dict):
        if "type" in obj:
            used_types.add(obj["type"])
        for v in obj.values():
            collect_types(v)
    elif isinstance(obj, list):
        for v in obj:
            collect_types(v)

# Collect all types used across all outputs
for r in [d, d_expl, d_quiz, d_skel, d_err]:
    collect_types(r)

print(f"  Types used by producer: {sorted(used_types)}")
# Verify they're all valid A2UIElementType values
valid_types = {e.value for e in A2UIElementType}
for t in used_types:
    test(f"Type '{t}' is valid A2UIElementType", t in valid_types, f"not in enum")

# ═══════════════════════════════════════════════════════════════════════════════
# TEST 29: A2UIProps fields used by producer
# ═══════════════════════════════════════════════════════════════════════════════
section("29. A2UIProps — Used fields valid")
used_props = set()
def collect_props(obj):
    if isinstance(obj, dict):
        if "props" in obj and isinstance(obj["props"], dict):
            used_props.update(obj["props"].keys())
        for v in obj.values():
            collect_props(v)
    elif isinstance(obj, list):
        for v in obj:
            collect_props(v)

for r in [d, d_expl, d_quiz]:
    collect_props(r)

# These are the snake_case field names from backend models
print(f"  Props used: {sorted(used_props)}")
# Verify none are camelCase
for p in used_props:
    test(f"Prop '{p}' is not camelCase", p not in CAMEL_BANNED)


# ═══════════════════════════════════════════════════════════════════════════════
# SUMMARY
# ═══════════════════════════════════════════════════════════════════════════════
print(f"\n{'='*60}")
print(f"  FINAL RESULTS")
print(f"{'='*60}")
print(f"  ✅ Passed: {passed}")
print(f"  ❌ Failed: {failed}")
if errors:
    print(f"\n  FAILURES:")
    for e in errors:
        print(f"    • {e}")
print(f"{'='*60}")
sys.exit(0 if failed == 0 else 1)
