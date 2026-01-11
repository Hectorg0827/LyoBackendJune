
import sys
import os

sys.path.append(os.getcwd())

print("Testing imports for lyo_app/ai_classroom/__init__.py dependencies...")

# Skip __init__.py execution by importing submodules directly
# This mimics what __init__.py does but one by one

try:
    print("Importing .models...")
    from lyo_app.ai_classroom import models
    print("✅ .models OK")
except Exception as e: print(f"❌ .models FAILED: {e}")

try:
    print("Importing .schemas...")
    from lyo_app.ai_classroom import schemas
    print("✅ .schemas OK")
except Exception as e: print(f"❌ .schemas FAILED: {e}")

try:
    print("Importing .graph_service...")
    from lyo_app.ai_classroom import graph_service
    print("✅ .graph_service OK")
except Exception as e: print(f"❌ .graph_service FAILED: {e}")

try:
    print("Importing .interaction_service...")
    from lyo_app.ai_classroom import interaction_service
    print("✅ .interaction_service OK")
except Exception as e: print(f"❌ .interaction_service FAILED: {e}")

try:
    print("Importing .remediation_service...")
    from lyo_app.ai_classroom import remediation_service
    print("✅ .remediation_service OK")
except Exception as e: print(f"❌ .remediation_service FAILED: {e}")

try:
    print("Importing .spaced_repetition_service...")
    from lyo_app.ai_classroom import spaced_repetition_service
    print("✅ .spaced_repetition_service OK")
except Exception as e: print(f"❌ .spaced_repetition_service FAILED: {e}")

try:
    print("Importing .asset_service...")
    from lyo_app.ai_classroom import asset_service
    print("✅ .asset_service OK")
except Exception as e: print(f"❌ .asset_service FAILED: {e}")

try:
    print("Importing .ad_service...")
    from lyo_app.ai_classroom import ad_service
    print("✅ .ad_service OK")
except Exception as e: print(f"❌ .ad_service FAILED: {e}")

try:
    print("Importing .graph_generator...")
    from lyo_app.ai_classroom import graph_generator
    print("✅ .graph_generator OK")
except Exception as e: print(f"❌ .graph_generator FAILED: {e}")

try:
    print("Importing .playback_routes...")
    from lyo_app.ai_classroom import playback_routes
    print("✅ .playback_routes OK")
except Exception as e: print(f"❌ .playback_routes FAILED: {e}")

print("Classroom imports check complete.")
