
import sys
import os

# Add current directory to path
sys.path.append(os.getcwd())

try:
    from lyo_app.core.config_v2 import HttpUrl, settings
    print(f"HttpUrl is defined: {HttpUrl}")
    print(f"Settings loaded: {settings.APP_NAME}")
    print("SUCCESS")
except Exception as e:
    print(f"FAILURE: {e}")
    import traceback
    traceback.print_exc()
