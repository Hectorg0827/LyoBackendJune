import os
import sys
import time

# INTERMEDIATE BOOTSTRAP
pid = os.getpid()
print(f">>> [PID {pid}] BOOTING INTERMEDIATE MAIN...", flush=True)

print(f">>> [PID {pid}] ATTEMPTING FASTAPI IMPORT...", flush=True)
from fastapi import FastAPI
print(f">>> [PID {pid}] FASTAPI IMPORTED SUCCESSFULLY", flush=True)

print(f">>> [PID {pid}] ATTEMPTING CONFIG IMPORT...", flush=True)
try:
    from lyo_app.core.enhanced_config import settings
    print(f">>> [PID {pid}] CONFIG IMPORTED (ENHANCED)", flush=True)
except ImportError:
    from lyo_app.core.config import settings
    print(f">>> [PID {pid}] CONFIG IMPORTED (LEGACY)", flush=True)

print(f">>> [PID {pid}] ATTEMPTING DATABASE IMPORT...", flush=True)
from lyo_app.core.database import init_db
print(f">>> [PID {pid}] DATABASE IMPORTED SUCCESSFULLY", flush=True)

app = FastAPI()

@app.get("/")
async def root():
    return {
        "status": "ok", 
        "message": "Intermediate LyoBackend is responsive", 
        "pid": os.getpid(),
        "env": settings.ENVIRONMENT
    }

@app.get("/health")
async def health():
    return {"status": "healthy"}
