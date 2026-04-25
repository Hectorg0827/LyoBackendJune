"""
Diagnostic: Test the full course lifecycle with session_id=1001
Connects to WS, gets welcome scene, then sends Continue 3 times
to verify lesson progression.
"""
import asyncio
import json
import websockets

WS_URL = "ws://localhost:8000/api/v1/classroom/ws/connect"
SESSION_ID = "1001"  # This is the courseId

async def test():
    params = f"?session_id={SESSION_ID}&api_key=test_key"
    url = WS_URL + params

    print(f"Connecting to {url}...")
    async with websockets.connect(url) as ws:
        # Collect welcome scene
        scene_count = 0
        msgs = []

        # Read initial messages (welcome scene)
        for _ in range(10):
            try:
                raw = await asyncio.wait_for(ws.recv(), timeout=15)
                data = json.loads(raw)
                event = data.get("event_type") or data.get("data", {}).get("event_type", "?")
                msgs.append(data)

                if event in ("scene_start", "SCENE_START"):
                    scene_count += 1
                    scene_data = data.get("data", {}).get("scene", data.get("scene", {}))
                    scene_type = scene_data.get("scene_type", "?")
                    components = scene_data.get("components", [])
                    print(f"\n{'='*60}")
                    print(f"SCENE #{scene_count} (type={scene_type})")
                    for c in components:
                        ctype = c.get("type", "?")
                        text = c.get("text", c.get("content", c.get("label", c.get("question", ""))))
                        text_preview = (text[:120] + "...") if len(str(text)) > 120 else text
                        print(f"  [{ctype}] {text_preview}")

                if event in ("scene_complete", "SCENE_COMPLETE"):
                    break

            except asyncio.TimeoutError:
                print("(timeout waiting for message)")
                break

        # Now send 3 CONTINUE actions and observe progression
        for action_num in range(1, 4):
            print(f"\n{'='*60}")
            print(f">>> Sending CONTINUE #{action_num}...")
            action = {
                "event_type": "user_action",
                "action_intent": "continue",
                "session_id": SESSION_ID,
                "component_id": "cta_continue"
            }
            await ws.send(json.dumps(action))

            # Read response scene
            for _ in range(10):
                try:
                    raw = await asyncio.wait_for(ws.recv(), timeout=15)
                    data = json.loads(raw)
                    event = data.get("event_type") or data.get("data", {}).get("event_type", "?")

                    if event in ("scene_start", "SCENE_START"):
                        scene_count += 1
                        scene_data = data.get("data", {}).get("scene", data.get("scene", {}))
                        scene_type = scene_data.get("scene_type", "?")
                        components = scene_data.get("components", [])
                        print(f"\nSCENE #{scene_count} (type={scene_type})")
                        for c in components:
                            ctype = c.get("type", "?")
                            text = c.get("text", c.get("content", c.get("label", c.get("question", ""))))
                            text_preview = (text[:150] + "...") if len(str(text)) > 150 else text
                            print(f"  [{ctype}] {text_preview}")

                    if event in ("scene_complete", "SCENE_COMPLETE"):
                        break

                except asyncio.TimeoutError:
                    print("(timeout)")
                    break

    print(f"\n{'='*60}")
    print(f"Total scenes received: {scene_count}")

asyncio.run(test())
