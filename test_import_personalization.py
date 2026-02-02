
import sys
import os
sys.path.append(os.getcwd())

print("Starting import test...", flush=True)
try:
    from lyo_app.personalization import models
    print("Imported models successfully", flush=True)
except Exception as e:
    print(f"Import failed: {e}", flush=True)
    import traceback
    traceback.print_exc()
