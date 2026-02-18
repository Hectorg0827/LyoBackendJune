#!/usr/bin/env python3
"""Edge case / stress tests for A2UIProducer."""

import json, sys, time, concurrent.futures

sys.path.insert(0, "/Users/hectorgarcia/Desktop/LyoBackendJune")

from lyo_app.a2ui.a2ui_producer import a2ui_producer
from lyo_app.a2ui.models import A2UIComponent

passed = 0
failed = 0

def test(name, cond, detail=""):
    global passed, failed
    if cond:
        passed += 1
        print(f"  ✅ {name}")
    else:
        failed += 1
        print(f"  ❌ {name} — {detail}")

def section(t):
    print(f"\n{'='*60}\n  {t}\n{'='*60}")

# ═══ 1. JSON-embedded strings ═══
section("1. JSON-embedded strings in content")
json_str = '{"title": "Test", "nested": {"key": "value with \\"quotes\\" and \\nnewlines"}}'
r = a2ui_producer.produce_explanation(json_str, topic="JSON test")
test("JSON-embedded string", isinstance(r, A2UIComponent))
d = r.to_dict()
j = json.dumps(d)
test("Serializable with embedded JSON", len(j) > 50)

# ═══ 2. Deeply nested dict input ═══
section("2. Deeply nested dict")
deep = {"level": 0}
current = deep
for i in range(50):
    current["child"] = {"level": i + 1}
    current = current["child"]
r2 = a2ui_producer.produce_explanation(deep, topic="Deep nesting")
test("50-level nested dict", isinstance(r2, A2UIComponent))
test("Serializable", len(json.dumps(r2.to_dict())) > 50)

# ═══ 3. Massive payload ═══
section("3. Massive payload (1MB string)")
big = "A" * 1_000_000
r3 = a2ui_producer.produce_explanation(big, topic="Huge input")
test("1MB input handled", isinstance(r3, A2UIComponent))
d3 = r3.to_dict()
test("Output reasonable size", len(json.dumps(d3)) < 2_000_000)

# ═══ 4. Special characters ═══
section("4. Special characters")
special = "Line1\nLine2\tTabbed\r\nWindows\x00NullByte<html>&amp;\"quoted\""
r4 = a2ui_producer.produce_explanation(special, topic="Special chars")
test("Special chars handled", isinstance(r4, A2UIComponent))
test("Serializable", len(json.dumps(r4.to_dict())) > 50)

# ═══ 5. All-None fields ═══
section("5. All-None / empty fields")
r5 = a2ui_producer.produce_course(
    {"title": None, "modules": None, "description": None},
    topic=None
)
test("All-None course fields", isinstance(r5, dict))
test("Has a2ui_component", isinstance(r5.get("a2ui_component"), A2UIComponent))

# ═══ 6. Wrong types ═══
section("6. Wrong types")
r6a = a2ui_producer.produce_course([1, 2, 3], topic="List input")
test("List as course input", isinstance(r6a, dict))

r6b = a2ui_producer.produce_explanation(True, topic="Boolean input")
test("Boolean as explanation input", isinstance(r6b, A2UIComponent))

r6c = a2ui_producer.produce_quiz(3.14)
test("Float as quiz input", isinstance(r6c, A2UIComponent))

r6d = a2ui_producer.produce_study_plan(set(), topic="Set input")
test("Set as study plan input", isinstance(r6d, A2UIComponent))

# ═══ 7. Concurrent calls ═══
section("7. Concurrent calls (10 parallel)")
def call_producer(i):
    return a2ui_producer.produce_explanation(f"Concurrent input {i}", topic=f"Thread {i}")

with concurrent.futures.ThreadPoolExecutor(max_workers=10) as pool:
    futures = [pool.submit(call_producer, i) for i in range(10)]
    results = [f.result() for f in concurrent.futures.as_completed(futures)]

test("10 concurrent calls succeed", len(results) == 10)
test("All return A2UIComponent", all(isinstance(r, A2UIComponent) for r in results))
# Verify unique IDs (no cross-contamination)
ids = [r.to_dict()["id"] for r in results]
test("All have unique root IDs", len(set(ids)) == 10, f"only {len(set(ids))} unique")

# ═══ 8. Binary / bytes input ═══
section("8. Binary / bytes input")
try:
    r8 = a2ui_producer.produce_explanation(b"binary data \xff\xfe", topic="Bytes")
    test("Bytes input handled", isinstance(r8, A2UIComponent))
except Exception as e:
    test("Bytes input handled (exception caught)", False, str(e))

# ═══ 9. Produce course with JSON string ═══
section("9. Course from JSON string")
course_json = json.dumps({
    "title": "Algebra Basics",
    "modules": [{"title": "Linear Equations", "lessons": [{"title": "Solving for x"}]}]
})
r9 = a2ui_producer.produce_course(course_json, topic="Algebra")
test("JSON string course", isinstance(r9, dict))
test("Parsed correctly", r9.get("open_classroom", {}).get("course", {}).get("title") == "Algebra Basics")

# ═══ 10. Produce auto with unknown type ═══
section("10. produce_auto with unknown ui_type")
r10 = a2ui_producer.produce_auto("Some data", ui_type="nonexistent_type", topic="Unknown")
test("Unknown ui_type falls back to explanation", isinstance(r10, A2UIComponent))

# ═══ 11. Empty list of modules ═══
section("11. Course with empty modules list")
r11 = a2ui_producer.produce_course({"title": "Empty", "modules": []}, topic="Empty modules")
test("Empty modules list", isinstance(r11, dict))
test("Still produces A2UI", isinstance(r11.get("a2ui_component"), A2UIComponent))

# ═══ 12. Quiz with wrong correct_answer_index ═══
section("12. Quiz with out-of-range correct_answer_index")
r12 = a2ui_producer.produce_quiz({
    "question": "Test?",
    "options": ["A", "B"],
    "correct_answer_index": 999
})
test("Out-of-range index handled", isinstance(r12, A2UIComponent))

# ═══ 13. Very long topic string ═══
section("13. Very long topic string")
long_topic = "X" * 10000
r13 = a2ui_producer.produce_explanation("Content", topic=long_topic)
test("10K char topic", isinstance(r13, A2UIComponent))
d13 = r13.to_dict()
test("Serializable", len(json.dumps(d13)) > 50)

# ═══ 14. Performance benchmark ═══
section("14. Performance benchmark (100 explanations)")
start = time.time()
for i in range(100):
    a2ui_producer.produce_explanation(f"Content {i}", topic=f"Topic {i}")
elapsed = time.time() - start
test(f"100 explanations in {elapsed:.2f}s", elapsed < 10.0, f"too slow: {elapsed:.2f}s")
print(f"    Throughput: {100/elapsed:.1f} explanations/sec")

# ═══ SUMMARY ═══
print(f"\n{'='*60}")
print(f"  EDGE CASE TEST RESULTS")
print(f"{'='*60}")
print(f"  ✅ Passed: {passed}")
print(f"  ❌ Failed: {failed}")
print(f"{'='*60}")
sys.exit(0 if failed == 0 else 1)
