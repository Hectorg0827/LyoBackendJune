"""
Full course lifecycle test - 5 CONTINUE actions to trigger quiz rotation.
"""
import asyncio
import json
import websockets

WS_URL = "ws://localhost:8000/api/v1/classroom/ws/connect"
SESSION_ID = "1001"

async def test():
    params = f"?session_id={SESSION_ID}&api_key=test_key"
    url = WS_URL + params

    print(f"Connecting to {url}...")
    async with websockets.connect(url) as ws:
        scene_count = 0

        # Collect all messages for 15 seconds (welcome + initial scene)
        print("\n--- WAITING FOR WELCOME SCENE ---")
        welcome_done = False
        for _ in range(15):
            try:
                raw = await asyncio.wait_for(ws.recv(), timeout=20)
                data = json.loads(raw)
                event = data.get("event_type") or data.get("data", {}).get("event_type", "?")

                if "scene_start" in str(event).lower():
                    scene_count += 1
                    scene_data = data.get("data", {}).get("scene", data.get("scene", {}))
                    scene_type = scene_data.get("scene_type", "?")
                    components = scene_data.get("components", [])
                    print(f"\n  WELCOME SCENE #{scene_count} (type={scene_type})")
                    for c in components:
                        ctype = c.get("type", "?")
                        text = c.get("text", c.get("content", c.get("label", c.get("question", ""))))
                        text_preview = (str(text)[:100] + "...") if len(str(text)) > 100 else text
                        print(f"    [{ctype}] {text_preview}")

                if "scene_complete" in str(event).lower():
                    welcome_done = True
                    break

                if "system_state" in str(event).lower():
                    print(f"  [system_state received]")

            except asyncio.TimeoutError:
                print("  (timeout)")
                break

        # Send 5 CONTINUE actions
        for i in range(1, 6):
            print(f"\n{'='*60}")
            print(f">>> CONTINUE #{i}")
            action = {
                "event_type": "user_action",
                "action_intent": "continue",
                "session_id": SESSION_ID,
                "component_id": "cta_continue"
            }
            await ws.send(json.dumps(action))

            for _ in range(10):
                try:
                    raw = await asyncio.wait_for(ws.recv(), timeout=20)
                    data = json.loads(raw)
                    event = data.get("event_type") or data.get("data", {}).get("event_type", "?")

                    if "scene_start" in str(event).lower():
                        scene_count += 1
                        scene_data = data.get("data", {}).get("scene", data.get("scene", {}))
                        scene_type = scene_data.get("scene_type", "?")
                        components = scene_data.get("components", [])
                        print(f"\n  SCENE #{scene_count} (type={scene_type})")
                        for c in components:
                            ctype = c.get("type", "?")
                            text = c.get("text", c.get("content", c.get("label", c.get("question", ""))))
                            text_preview = (str(text)[:120] + "...") if len(str(text)) > 120 else text
                            print(f"    [{ctype}] {text_preview}")

                    if "scene_complete" in str(event).lower():
                        break

                except asyncio.TimeoutError:
                    print("  (timeout)")
                    break

    print(f"\n{'='*60}")
    print(f"TOTAL SCENES: {scene_count}")

asyncio.run(test())
