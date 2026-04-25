#!/usr/bin/env python3
"""Diagnose WebSocket classroom pipeline."""
import asyncio, websockets, json, sys

async def test():
    uri = 'ws://localhost:8000/api/v1/classroom/ws/connect?session_id=diag_test3&token=guest'
    try:
        async with websockets.connect(uri, open_timeout=10) as ws:
            print('CONNECTED', flush=True)
            for i in range(5):
                try:
                    msg = await asyncio.wait_for(ws.recv(), timeout=25)
                    d = json.loads(msg)
                    evt = d.get('event_type', d.get('type', 'unknown'))
                    print(f'MSG{i}: event={evt}', flush=True)
                    if 'scene' in d:
                        s = d['scene']
                        print(f'  scene_type={s.get("scene_type")}', flush=True)
                        comps = s.get('components', [])
                        print(f'  num_components={len(comps)}', flush=True)
                        for j, c in enumerate(comps):
                            ct = c.get('type', '?')
                            content = str(c.get('content', ''))[:100]
                            print(f'  C{j}: type={ct} content={content}', flush=True)
                    if evt == 'error':
                        print(f'  FULL: {json.dumps(d)[:300]}', flush=True)
                except asyncio.TimeoutError:
                    print(f'MSG{i}: TIMEOUT (no more messages)', flush=True)
                    break
    except Exception as e:
        print(f'CONNECT_ERROR: {e}', flush=True)

asyncio.run(test())
