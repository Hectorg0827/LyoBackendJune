import os
import sys
import time

# ADVANCED BOOTSTRAP
pid = os.getpid()
print(f">>> [PID {pid}] BOOTING ADVANCED MAIN...", flush=True)

print(f">>> [PID {pid}] ATTEMPTING FASTAPI IMPORT...", flush=True)
from fastapi import FastAPI
print(f">>> [PID {pid}] FASTAPI IMPORTED SUCCESSFULLY", flush=True)

print(f">>> [PID {pid}] ATTEMPTING OBSERVABILITY IMPORT...", flush=True)
try:
    from lyo_app.core.observability import instrument_app
    print(f">>> [PID {pid}] OBSERVABILITY IMPORTED", flush=True)
except Exception as e:
    print(f">>> [PID {pid}] OBSERVABILITY IMPORT FAILED: {e}", flush=True)

print(f">>> [PID {pid}] ATTEMPTING LOGGING SETUP...", flush=True)
from lyo_app.core.logging import setup_logging, logger
setup_logging()
print(f">>> [PID {pid}] LOGGING INITIALIZED", flush=True)

print(f">>> [PID {pid}] ATTEMPTING ERROR HANDLER SETUP...", flush=True)
from lyo_app.core.exceptions import setup_error_handlers
print(f">>> [PID {pid}] ERROR HANDLERS IMPORTED", flush=True)

app = FastAPI()

@app.get("/")
async def root():
    return {
        "status": "ok", 
        "message": "Advanced LyoBackend is responsive", 
        "pid": os.getpid()
    }

@app.get("/health")
async def health():
    return {"status": "healthy"}
