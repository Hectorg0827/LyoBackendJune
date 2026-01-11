
import time
import sys
import os

# Measure import time
start_import = time.time()
print(f"[{time.time()}] Importing AIPerformanceOptimizer...", flush=True)
from lyo_app.ai_agents.optimization.performance_optimizer import ai_performance_optimizer
end_import = time.time()
print(f"[{time.time()}] Import took {end_import - start_import:.3f}s")

# Check if thread is running (it SHOULD NOT be)
import threading
threads = [t.name for t in threading.enumerate()]
print(f"Active threads: {threads}")

is_monitoring_active = ai_performance_optimizer.resource_optimizer._monitoring_active
print(f"Monitoring active check: {is_monitoring_active}")

if is_monitoring_active:
    print("FAIL: Monitoring started automatically!", file=sys.stderr)
else:
    print("PASS: Monitoring NOT started automatically.")

# Now simulate initialize
import asyncio

async def test_init():
    print(f"[{time.time()}] creating loop...", flush=True)
    print(f"[{time.time()}] Calling initialize()...", flush=True)
    await ai_performance_optimizer.initialize()
    print(f"[{time.time()}] Initialize done.", flush=True)
    
    is_active_after = ai_performance_optimizer.resource_optimizer._monitoring_active
    print(f"Monitoring active after init: {is_active_after}")
    
    threads_after = [t.name for t in threading.enumerate()]
    print(f"Active threads after init: {threads_after}")
    
    if is_active_after:
        print("PASS: Monitoring started after initialize().")
    else:
        print("FAIL: Monitoring DID NOT start after initialize().", file=sys.stderr)

asyncio.run(test_init())
