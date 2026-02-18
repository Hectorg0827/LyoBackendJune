
import sys
import os

sys.path.append(os.getcwd())

print(f"Current Path: {sys.path}")
print(f"CWD: {os.getcwd()}")

try:
    print("Attempting to import lyo_app.a2ui.a2ui_producer...")
    from lyo_app.a2ui.a2ui_producer import a2ui_producer
    print("✅ success")
except Exception as e:
    print(f"❌ failed: {e}")

try:
    print("Attempting to import lyo_app.chat.routes...")
    from lyo_app.chat import routes
    print("✅ success")
except Exception as e:
    print(f"❌ failed: {e}")
