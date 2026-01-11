
import sys
import os

# Add current directory to path
sys.path.append(os.getcwd())

print("Attempting to import lyo_app.ai_classroom.routes...")
try:
    from lyo_app.ai_classroom import routes
    print("✅ Successfully imported lyo_app.ai_classroom.routes")
except ImportError as e:
    print(f"❌ Failed to import lyo_app.ai_classroom.routes: {e}")
    sys.exit(1)
except Exception as e:
    print(f"❌ Crash during import of lyo_app.ai_classroom.routes: {e}")
    sys.exit(1)

print("Attempting to import lyo_app.enhanced_main...")
try:
    from lyo_app import enhanced_main
    print("✅ Successfully imported lyo_app.enhanced_main")
except Exception as e:
    print(f"❌ Crash during import of main app: {e}")
    sys.exit(1)

print("✅ Startup checks passed locally.")
