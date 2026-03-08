import sys

file_path = "/Users/hectorgarcia/Desktop/LyoBackendJune/lyo_app/enhanced_main.py"
with open(file_path, "r") as f:
    text = f.read()

injection = """
    try:
        from lyo_app.api.progressive_course import router as progressive_router
        app.include_router(progressive_router)
        logger.info("✅ Progressive Course Generation routes integrated (iOS Phase A Compatibility)")
    except ImportError as e:
        logger.warning(f"⚠️ Progressive Course routes not loaded: {e}")
"""

if "progressive_course" not in text:
    # Insert it right before "app.include_router(auth_router"
    target = "    app.include_router(auth_router, prefix=\"/auth\", tags=[\"auth\"])"
    text = text.replace(target, injection + "\n" + target)
    with open(file_path, "w") as f:
        f.write(text)
    print("Patched enhanced_main.py successfully.")
else:
    print("Already patched.")

