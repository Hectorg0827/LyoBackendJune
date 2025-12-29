import os
import sys

# MINIMAL BOOTSTRAP
pid = os.getpid()
print(f">>> [PID {pid}] BOOTING MINIMAL MAIN...", flush=True)
print(f">>> [PID {pid}] SYS.PATH: {sys.path}", flush=True)

print(f">>> [PID {pid}] ATTEMPTING FASTAPI IMPORT...", flush=True)
from fastapi import FastAPI
print(f">>> [PID {pid}] FASTAPI IMPORTED SUCCESSFULLY", flush=True)

app = FastAPI()

@app.get("/")
async def root():
    return {"status": "ok", "message": "Minimal LyoBackend is responsive", "pid": os.getpid()}

@app.get("/health")
async def health():
    return {"status": "healthy"}
