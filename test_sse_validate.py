#!/usr/bin/env python3
"""Validate SSE stream format matches iOS SmartBlock expectations."""
import subprocess, json, sys

BASE = "http://localhost:8001"

def curl_stream(path, payload, timeout=90):
    cmd = [
        "curl", "-s", "--max-time", str(timeout),
        "-N", "-X", "POST", f"{BASE}{path}",
        "-H", "Content-Type: application/json",
        "-H", "X-API-Key: test-key",
        "-H", "Accept: text/event-stream",
        "-d", json.dumps(payload)
    ]
    result = subprocess.run(cmd, capture_output=True, text=True)
    return result.stdout

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

print("=== AI Chat SSE Stream Test ===")
raw = curl_stream("/api/v1/lyo2/chat/stream", {
    "text": "Explain gravity to me briefly",
    "user_id": "test-user"
})

events = []
for line in raw.strip().split("\n"):
    line = line.strip()
    if line.startswith("data: ") and line != "data: [DONE]":
        try:
            events.append(json.loads(line[6:]))
        except:
            pass

etypes = [e.get("type") for e in events]
print(f"  Event types: {etypes}")

test("SSE returns events", len(events) > 0, f"raw: {raw[:200]}")
test("Has skeleton event", "skeleton" in etypes)
test("Has answer event", "answer" in etypes)
test("Has smart_blocks event", "smart_blocks" in etypes)
test("Has actions event", "actions" in etypes)
test("Stream has [DONE]", "[DONE]" in raw)

# Validate answer content
answer_evts = [e for e in events if e.get("type") == "answer"]
if answer_evts:
    content = answer_evts[0].get("block", {}).get("content", {})
    test("Answer has text", "text" in content)
    text = content.get("text", "")
    test("Answer text is real (not fallback)", "magical circuits" not in text, text[:100])
    test("Answer text > 50 chars", len(text) > 50, f"len={len(text)}")
    print(f"    Answer preview: {text[:120]}...")

# Validate SmartBlock format (iOS Codable compat)
sb_evts = [e for e in events if e.get("type") == "smart_blocks"]
if sb_evts:
    blocks = sb_evts[0].get("blocks", [])
    test("SmartBlocks array non-empty", len(blocks) > 0)
    for i, block in enumerate(blocks):
        test(f"Block[{i}] has id", "id" in block)
        test(f"Block[{i}] has schema_version", "schema_version" in block)
        test(f"Block[{i}] has type", "type" in block)
        test(f"Block[{i}] has content dict", isinstance(block.get("content"), dict))
        btype = block.get("type", "")
        test(f"Block[{i}] type is valid SmartBlockType",
             btype in ["text","code","quiz","flashcard","data_viz","media","progress","interactive","mastery_map"])
        if btype == "text":
            test(f"Block[{i}] content.text exists", "text" in block.get("content", {}))

# Validate actions
action_evts = [e for e in events if e.get("type") == "actions"]
if action_evts:
    action_blocks = action_evts[0].get("blocks", [])
    test("Actions has blocks", len(action_blocks) > 0)
    if action_blocks:
        actions = action_blocks[0].get("content", {}).get("actions", [])
        test("Actions has suggestions", len(actions) > 0, str(action_blocks[0]))
        print(f"    Actions: {actions}")

print(f"\n  Results: {passed}/{passed+failed} passed")
if failed > 0:
    print(f"  ⚠️ {failed} test(s) FAILED")
    sys.exit(1)
else:
    print("  🎉 All tests PASSED!")
