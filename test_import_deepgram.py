
import sys
import os
sys.path.append(os.getcwd())

print("Starting import test...", flush=True)
try:
    print("Importing deepgram...", flush=True)
    import deepgram
    print("Imported deepgram successfully", flush=True)
    from deepgram import AsyncDeepgramClient
    print("Imported AsyncDeepgramClient successfully", flush=True)
except Exception as e:
    print(f"Import failed: {e}", flush=True)
    import traceback
    traceback.print_exc()
