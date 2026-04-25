#!/usr/bin/env python3
"""Diagnose: dump full JSON of scene_start and component_render."""
import asyncio, websockets, json

async def test():
    uri = 'ws://localhost:8000/api/v1/classroom/ws/connect?session_id=diag_full&token=guest'
    async with websockets.connect(uri, open_timeout=10) as ws:
        print('CONNECTED', flush=True)
        for i in range(5):
            try:
                msg = await asyncio.wait_for(ws.recv(), timeout=25)
                d = json.loads(msg)
                evt = d.get('event_type', d.get('type', 'unknown'))
                print(f'\n=== MSG{i}: {evt} ===', flush=True)
                print(json.dumps(d, indent=2, default=str)[:800], flush=True)
            except asyncio.TimeoutError:
                print(f'MSG{i}: TIMEOUT', flush=True)
                break

asyncio.run(test())
