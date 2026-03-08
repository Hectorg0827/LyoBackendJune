import sys
print("Importing chat...", flush=True)
try:
    import lyo_app.api.v1.chat
    print("Done importing chat", flush=True)
except Exception as e:
    print("Error:", e, flush=True)
