#!/usr/bin/env python3
"""Test the live backend to verify A2UI blocks are sent."""
import requests
import json
import sys

BASE_URL = "https://lyo-backend-production-5oq7jszolq-uc.a.run.app"

# Test 1: Health check
print("=== TEST 1: Health Check ===")
r = requests.get(f"{BASE_URL}/health", timeout=30)
print(f"Status: {r.status_code}")
if r.status_code != 200:
    print("❌ Backend not healthy!")
    sys.exit(1)
print("✅ Backend healthy\n")

# Test 2: Chat endpoint (fast path)
print("=== TEST 2: Fast-path chat (POST /api/v1/chat) ===")
chat_payload = {
    "message": "Create a course about Peyton",
    "conversation_id": None
}
headers = {
    "Content-Type": "application/json",
    "X-API-Key": "test-key",
    "X-Tenant-Id": "test-tenant"
}
try:
    r = requests.post(f"{BASE_URL}/api/v1/chat", json=chat_payload, headers=headers, timeout=60)
    print(f"Status: {r.status_code}")
    if r.status_code == 200:
        data = r.json()
        print(f"Keys in response: {list(data.keys())}")
        if "ui_component" in data:
            ui = data["ui_component"]
            if ui:
                print(f"✅ ui_component present! type={ui.get('type')}")
                print(f"   Has children: {bool(ui.get('children'))}")
                print(f"   Has id: {bool(ui.get('id'))}")
                # Check for snake_case
                def find_keys(obj, depth=0):
                    keys = set()
                    if isinstance(obj, dict):
                        keys.update(obj.keys())
                        for v in obj.values():
                            keys.update(find_keys(v, depth+1))
                    elif isinstance(obj, list):
                        for v in obj:
                            keys.update(find_keys(v, depth+1))
                    return keys
                all_keys = find_keys(ui)
                style_keys = [k for k in all_keys if k in ('foreground_color', 'font_size', 'font_weight', 'background_color', 'foregroundColor', 'fontSize', 'fontWeight')]
                print(f"   Style keys found: {style_keys}")
                print(f"   First 300 chars: {json.dumps(ui)[:300]}")
            else:
                print("⚠️ ui_component is None/null")
        else:
            print("⚠️ No ui_component key in response")
        
        if "response" in data:
            print(f"   response (first 100): {data['response'][:100]}...")
        
        # Check mode
        if "mode_used" in data:
            print(f"   mode_used: {data['mode_used']}")
    else:
        print(f"Response: {r.text[:500]}")
except Exception as e:
    print(f"Error: {e}")

# Test 3: SSE streaming (deep path)
print("\n=== TEST 3: SSE stream (POST /api/v1/lyo2/chat/stream) ===")
stream_payload = {
    "message": "Create a course about Peyton",
    "text": "Create a course about Peyton",
    "session_id": "test-session-123",
    "user_id": "test-user-123"
}
try:
    r = requests.post(
        f"{BASE_URL}/api/v1/lyo2/chat/stream",
        json=stream_payload,
        headers={**headers, "Accept": "text/event-stream"},
        stream=True,
        timeout=90
    )
    print(f"Status: {r.status_code}")
    if r.status_code != 200:
        print(f"Error body: {r.text}")
    
    event_types = []
    a2ui_events = []
    open_classroom_events = []
    
    for line in r.iter_lines(decode_unicode=True):
        if line and line.startswith("data: "):
            data_str = line[6:]
            if data_str == "[DONE]":
                event_types.append("[DONE]")
                break
            try:
                event = json.loads(data_str)
                etype = event.get("type", "unknown")
                event_types.append(etype)
                if etype == "a2ui":
                    a2ui_events.append(event)
                    print(f"A2UI Event: {json.dumps(event, indent=2)}")
                elif etype == "open_classroom":
                    open_classroom_events.append(event)
            except json.JSONDecodeError:
                event_types.append(f"parse_error: {data_str[:50]}")
    
    print(f"Event types received: {event_types}")
    
    if a2ui_events:
        print(f"\n✅ Got {len(a2ui_events)} A2UI events!")
        for i, evt in enumerate(a2ui_events):
            block = evt.get("block", {})
            content = block.get("content", {})
            comp = content.get("component", {})
            print(f"  A2UI #{i}: block_type={block.get('type')}, comp_type={comp.get('type')}, has_id={bool(comp.get('id'))}")
    else:
        print("❌ No A2UI events in stream!")
    
    if open_classroom_events:
        print(f"\n✅ Got {len(open_classroom_events)} open_classroom events!")
        for evt in open_classroom_events:
            block = evt.get("block", {})
            content = block.get("content", {})
            print(f"  type={content.get('type')}, has_course={bool(content.get('course'))}")
    else:
        print("⚠️ No open_classroom events (may be expected for non-course queries)")

except Exception as e:
    print(f"Error: {e}")

print("\n=== TESTS COMPLETE ===")
