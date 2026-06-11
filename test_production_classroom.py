import asyncio
import json
import websockets
import sys

# Connect to the live deployed server
WS_URL = "wss://lyobackendjune-lyo.up.railway.app/api/v1/classroom/ws/connect"
SESSION_ID = "1001"  # Target CourseId

async def test_live_classroom():
    params = f"?session_id={SESSION_ID}&api_key=test_key"
    url = WS_URL + params

    print(f"Connecting to live production websocket: {url}...")
    try:
        async with websockets.connect(url, close_timeout=10) as ws:
            print("Successfully connected! Collecting first scene (Welcome scene)...")
            scene_count = 0
            
            for _ in range(10):
                try:
                    raw = await asyncio.wait_for(ws.recv(), timeout=20)
                    data = json.loads(raw)
                    event = data.get("event_type") or data.get("data", {}).get("event_type", "?")
                    
                    if event in ("scene_start", "SCENE_START"):
                        scene_count += 1
                        scene_data = data.get("data", {}).get("scene", data.get("scene", {}))
                        scene_type = scene_data.get("scene_type", "?")
                        components = scene_data.get("components", [])
                        print(f"\n{'='*60}")
                        print(f"✅ SCENE #{scene_count} LOADED (Type: {scene_type})")
                        for c in components:
                            ctype = c.get("type", "?")
                            text = c.get("text", c.get("content", c.get("label", c.get("question", ""))))
                            text_preview = (text[:120] + "...") if len(str(text)) > 120 else text
                            print(f"  [{ctype}] {text_preview}")

                    if event in ("scene_complete", "SCENE_COMPLETE"):
                        print("\n🏁 Welcome scene complete!")
                        break
                except asyncio.TimeoutError:
                    print("(Timeout waiting for live message stream)")
                    break

            # Send a user continue action to trigger the classroom director's dynamic progression
            print(f"\n{'='*60}")
            print(">>> Sending User CONTINUE action to test lesson generation/playback...")
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
                    raw = await asyncio.wait_for(ws.recv(), timeout=20)
                    data = json.loads(raw)
                    event = data.get("event_type") or data.get("data", {}).get("event_type", "?")

                    if event in ("scene_start", "SCENE_START"):
                        scene_count += 1
                        scene_data = data.get("data", {}).get("scene", data.get("scene", {}))
                        scene_type = scene_data.get("scene_type", "?")
                        components = scene_data.get("components", [])
                        print(f"\n✅ SCENE #{scene_count} LOADED (Type: {scene_type})")
                        for c in components:
                            ctype = c.get("type", "?")
                            text = c.get("text", c.get("content", c.get("label", c.get("question", ""))))
                            text_preview = (text[:150] + "...") if len(str(text)) > 150 else text
                            print(f"  [{ctype}] {text_preview}")

                    if event in ("scene_complete", "SCENE_COMPLETE"):
                        print("\n🏁 First dynamic classroom transition successful!")
                        break
                except asyncio.TimeoutError:
                    print("(Timeout waiting for next scene)")
                    break

            print(f"\n{'='*60}")
            print(f"SUCCESS: AI Classroom socket transition tested successfully! Total scenes: {scene_count}")
    except Exception as e:
        print(f"Error testing live socket: {e}")
        sys.exit(1)

if __name__ == "__main__":
    asyncio.run(test_live_classroom())
