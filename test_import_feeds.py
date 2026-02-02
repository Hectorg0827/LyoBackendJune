
import sys
import os
# Add current directory to path
sys.path.append(os.getcwd())

print("Starting import test...", flush=True)
try:
    from lyo_app.feeds import models
    print("Imported models successfully", flush=True)
except Exception as e:
    print(f"Import failed: {e}", flush=True)
    import traceback
    traceback.print_exc()

try:
    from lyo_app.feeds import schemas
    print("Imported schemas successfully", flush=True)
except Exception as e:
    print(f"Import schemas failed: {e}", flush=True)
    import traceback
    traceback.print_exc()
