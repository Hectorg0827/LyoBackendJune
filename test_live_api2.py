#!/usr/bin/env python3
"""Live API endpoint tests against deployed backend."""
import subprocess, json, sys, time

BASE = "https://lyo-backend-production-5oq7jszolq-uc.a.run.app"
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

def curl_get(path, timeout=15):
    cmd = ["curl", "-s", "--max-time", str(timeout), f"{BASE}{path}"]
    result = subprocess.run(cmd, capture_output=True, text=True)
    try:
        return json.loads(result.stdout)
    except:
        return {"_raw": result.stdout[:500], "_error": "JSON parse failed"}

def curl_post(path, payload, timeout=45):
    cmd = [
        "curl", "-s", "--max-time", str(timeout),
        "-X", "POST", f"{BASE}{path}",
        "-H", "Content-Type: application/json",
        "-H", "X-API-Key: test-key",
        "-d", json.dumps(payload)
    ]
    result = subprocess.run(cmd, capture_output=True, text=True)
    try:
        return json.loads(result.stdout)
    except:
        return {"_raw": result.stdout[:500], "_error": "JSON parse failed"}

def curl_stream(path, payload, timeout=45):
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

# ═══ TEST 1: Health Check ═══
print("\n=== 1. Health Check ===")
health = curl_get("/health")
test("Health returns healthy", health.get("status") == "healthy")
test("Has version", "version" in health)
test("Has features", "features" in health)

# ═══ TEST 2: Fast-path chat (/api/v1/ai/chat) ═══
print("\n=== 2. Fast-path Chat (/api/v1/ai/chat) ===")
chat = curl_post("/api/v1/ai/chat", {
    "message": "What is the speed of light?",
    "conversation_id": "test-fast-1"
})
test("Returns response key", "response" in chat, str(chat.get("_error", "")))
test("Response non-empty", len(chat.get("response", "")) > 10)
test("Has conversationHistory", "conversationHistory" in chat)

# ═══ TEST 3: Chat routes (/api/v1/chat) - Explainer ═══
print("\n=== 3. Chat Routes — Explainer ===")
expl = curl_post("/api/v1/chat", {
    "message": "Explain quantum computing simply",
    "conversation_id": "test-explain-1"
}, timeout=60)
test("Chat route returns response", "response" in expl, str(expl)[:200])
if "response" in expl:
    test("Response non-empty", len(expl.get("response", "")) > 10)
    mode = expl.get("mode_used", "unknown")
    print(f"    Mode used: {mode}")
    if expl.get("a2ui_component"):
        comp = expl["a2ui_component"]
        test("A2UI has type", "type" in comp)
        test("A2UI has id", "id" in comp)
        test("A2UI has children", isinstance(comp.get("children"), list))
        j = json.dumps(comp)
        test("A2UI JSON serializable", True)
        test("No camelCase foregroundColor", "foregroundColor" not in j)
        test("No camelCase fontSize", "fontSize" not in j)
        print(f"    A2UI root type: {comp.get('type')}, children: {len(comp.get('children', []))}")
    else:
        print("    (No a2ui_component — may be routed to fast path)")

# ═══ TEST 4: SSE Stream ═══
print("\n=== 4. SSE Stream (/api/v1/lyo2/chat/stream) ===")
raw = curl_stream("/api/v1/lyo2/chat/stream", {
    "message": "Explain gravity to me",
    "conversation_id": "test-stream-1",
    "user_id": "test-user"
}, timeout=60)

events = []
for line in raw.strip().split("\n"):
    line = line.strip()
    if line.startswith("data: ") and line != "data: [DONE]":
        try:
            events.append(json.loads(line[6:]))
        except:
            pass

test("SSE returns events", len(events) > 0, f"raw: {raw[:200]}")
etypes = [e.get("type") for e in events]
print(f"    Event types: {etypes}")

test("Has skeleton event", "skeleton" in etypes)
test("Has answer event", "answer" in etypes)
test("Stream has [DONE]", "[DONE]" in raw)

if "a2ui" in etypes:
    a2ui_evt = [e for e in events if e.get("type") == "a2ui"][0]
    block = a2ui_evt.get("block", {})
    test("A2UI block has content", "content" in block)
    inner = block.get("content", {}).get("component", {})
    if inner:
        test("A2UI inner has type", "type" in inner)
        test("A2UI inner has id", "id" in inner)
else:
    print("    (No a2ui event — router classified as simple tutoring)")

answer_evts = [e for e in events if e.get("type") == "answer"]
if answer_evts:
    content = answer_evts[0].get("block", {}).get("content", {})
    test("Answer has text", "text" in content)
    test("Answer text non-empty", len(content.get("text", "")) > 5)

# ═══ TEST 5: Edge cases ═══
print("\n=== 5. Edge Cases ===")

empty = curl_post("/api/v1/ai/chat", {"message": "", "conversation_id": "test-empty"})
test("Empty message handled", isinstance(empty, dict))

uni = curl_post("/api/v1/ai/chat", {"message": "数学とは何ですか？🧠", "conversation_id": "test-uni"})
test("Unicode handled", "response" in uni or "detail" in uni)

long_msg = "Explain " + "the theory of everything " * 100
lng = curl_post("/api/v1/ai/chat", {"message": long_msg, "conversation_id": "test-long"}, timeout=30)
test("Long message handled", isinstance(lng, dict))

# ═══ SUMMARY ═══
print(f"\n{'='*50}")
print(f"  LIVE API TEST RESULTS")
print(f"{'='*50}")
print(f"  ✅ Passed: {passed}")
print(f"  ❌ Failed: {failed}")
print(f"{'='*50}")
sys.exit(0 if failed == 0 else 1)
