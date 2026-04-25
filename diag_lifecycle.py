#!/usr/bin/env python3
"""Full lifecycle test: connect, get scene, tap Continue, check for next scene."""
import asyncio, websockets, json

async def test():
    uri = 'ws://localhost:8000/api/v1/classroom/ws/connect?session_id=lifecycle_test&token=guest'
    async with websockets.connect(uri, open_timeout=10) as ws:
        print('CONNECTED', flush=True)
        scenes_received = 0
        cta_component_id = None
        
        for i in range(10):
            try:
                msg = await asyncio.wait_for(ws.recv(), timeout=30)
                d = json.loads(msg)
                evt = d.get('event_type', d.get('type', 'unknown'))
                
                if evt == 'scene_start':
                    scenes_received += 1
                    s = d.get('scene', {})
                    comps = s.get('components', [])
                    print(f'\nSCENE #{scenes_received}: type={s.get("scene_type")} components={len(comps)}', flush=True)
                    for c in comps:
                        ct = c.get('type', '?')
                        text = c.get('text', c.get('label', c.get('content', '')))
                        print(f'  {ct}: {str(text)[:120]}', flush=True)
                        if ct == 'CTAButton':
                            cta_component_id = c.get('component_id')
                
                elif evt == 'scene_complete':
                    print(f'SCENE_COMPLETE (scene #{scenes_received})', flush=True)
                    # After first scene completes, send Continue action
                    if scenes_received == 1 and cta_component_id:
                        print(f'\n>>> SENDING CONTINUE ACTION (component={cta_component_id})', flush=True)
                        action = {
                            "event_type": "user_action",
                            "session_id": "lifecycle_test",
                            "action_intent": "continue",
                            "component_id": cta_component_id,
                            "timestamp": "2026-04-07T00:00:00Z"
                        }
                        await ws.send(json.dumps(action))
                        print('>>> ACTION SENT, waiting for next scene...', flush=True)
                
                elif evt == 'component_render':
                    c = d.get('component', {})
                    ct = c.get('type', '?')
                    text = c.get('text', c.get('label', c.get('content', '')))
                    print(f'  RENDER {ct}: {str(text)[:120]}', flush=True)
                
                elif evt == 'system_state':
                    print(f'system_state (connected)', flush=True)
                
                elif evt == 'error':
                    print(f'ERROR: {json.dumps(d)[:300]}', flush=True)
                    
                else:
                    print(f'{evt}: {json.dumps(d)[:200]}', flush=True)
                    
            except asyncio.TimeoutError:
                print(f'\nTIMEOUT after {i} messages. Scenes received: {scenes_received}', flush=True)
                break
        
        print(f'\nDONE. Total scenes: {scenes_received}', flush=True)

asyncio.run(test())
