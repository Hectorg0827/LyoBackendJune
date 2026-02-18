
import sys
import os
import signal

# Add project root to path
sys.path.append(os.getcwd())

def handler(signum, frame):
    raise TimeoutError("Import timed out!")

signal.signal(signal.SIGALRM, handler)

modules_to_test = [
    "lyo_app.core.database",
    "lyo_app.auth.jwt_auth",
    "lyo_app.models.enhanced",
    "lyo_app.chat.models",
    "lyo_app.chat.schemas",
    "lyo_app.core.lyo_protocol",
    "lyo_app.chat.router",
    "lyo_app.chat.agents",
    "lyo_app.chat.assembler",
    "lyo_app.chat.stores",
    "lyo_app.streaming",
    "lyo_app.personalization.service",
    "lyo_app.core.ai_resilience",
    "lyo_app.core.context_engine",
    "lyo_app.core.personality",
    "lyo_app.chat.a2ui_integration",
    "lyo_app.a2ui.a2ui_producer",
    "lyo_app.ai_agents.a2a",  # The suspect
]

print("🔍 Debugging Import Cycle...")

for module in modules_to_test:
    print(f"Testing import: {module}...", end="", flush=True)
    signal.alarm(3)  # 3 seconds timeout
    try:
        __import__(module)
        signal.alarm(0)
        print(" ✅ OK")
    except TimeoutError:
        print(" ❌ TIMEOUT (Cycle likely here)")
        break
    except Exception as e:
        signal.alarm(0)
        print(f" ❌ ERROR: {e}")
        break
