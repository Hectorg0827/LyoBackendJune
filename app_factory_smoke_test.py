#!/usr/bin/env python3
import json, sys, traceback

try:
    from fastapi.testclient import TestClient
    print("Imported TestClient", flush=True)
except Exception as e:
    print("Failed to import TestClient:", e, flush=True)
    traceback.print_exc()
    sys.exit(1)

try:
    from lyo_app.app_factory import create_app
    print("Imported create_app", flush=True)
except Exception as e:
    print("Failed to import create_app:", e, flush=True)
    traceback.print_exc()
    sys.exit(1)

try:
    app = create_app()
    print("App created", flush=True)
except Exception as e:
    print("Failed to create app:", e, flush=True)
    traceback.print_exc()
    sys.exit(1)

try:
    client = TestClient(app)
    print("TestClient created", flush=True)
except Exception as e:
    print("Failed to create TestClient:", e, flush=True)
    traceback.print_exc()
    sys.exit(1)

def show_response(name, resp):
    print(f"{name} status: {resp.status_code}", flush=True)
    try:
        data = resp.json()
        print(f"{name} json keys: {sorted(list(data.keys()))[:6]}", flush=True)
    except Exception as e:
        print(f"{name} parse error: {e}", flush=True)

try:
    h = client.get("/healthz")
    show_response("/healthz", h)
except Exception as e:
    print("/healthz request failed:", e, flush=True)
    traceback.print_exc()

try:
    m = client.get("/market-status")
    show_response("/market-status", m)
except Exception as e:
    print("/market-status request failed:", e, flush=True)
    traceback.print_exc()

print("Total routes:", len(app.routes), flush=True)
