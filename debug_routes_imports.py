
import sys
import os

sys.path.append(os.getcwd())

print("Testing imports for lyo_app/ai_classroom/routes.py...")

try:
    print("Importing intent_detector...")
    from lyo_app.ai_classroom import intent_detector
    print("✅ intent_detector OK")
except Exception as e: print(f"❌ intent_detector FAILED: {e}")

try:
    print("Importing conversation_flow...")
    from lyo_app.ai_classroom import conversation_flow
    print("✅ conversation_flow OK")
except Exception as e: print(f"❌ conversation_flow FAILED: {e}")

try:
    print("Importing streaming...")
    from lyo_app import streaming
    print("✅ streaming OK")
except Exception as e: print(f"❌ streaming FAILED: {e}")

try:
    print("Importing auth.dependencies...")
    from lyo_app.auth import dependencies
    print("✅ auth.dependencies OK")
except Exception as e: print(f"❌ auth.dependencies FAILED: {e}")

try:
    print("Importing models.enhanced...")
    from lyo_app.models import enhanced
    print("✅ models.enhanced OK")
except Exception as e: print(f"❌ models.enhanced FAILED: {e}")

try:
    print("Importing core.database...")
    from lyo_app.core import database
    print("✅ core.database OK")
except Exception as e: print(f"❌ core.database FAILED: {e}")

try:
    print("Importing ai_classroom.models...")
    from lyo_app.ai_classroom import models
    print("✅ ai_classroom.models OK")
except Exception as e: print(f"❌ ai_classroom.models FAILED: {e}")

try:
    print("Importing core.context_engine...")
    from lyo_app.core import context_engine
    print("✅ core.context_engine OK")
except Exception as e: print(f"❌ core.context_engine FAILED: {e}")

try:
    print("Importing personalization.soft_skills...")
    from lyo_app.personalization import soft_skills
    print("✅ personalization.soft_skills OK")
except Exception as e: print(f"❌ personalization.soft_skills FAILED: {e}")

try:
    print("Importing auth.routes...")
    from lyo_app.auth import routes
    print("✅ auth.routes OK")
except Exception as e: print(f"❌ auth.routes FAILED: {e}")

print("Import checks complete.")
