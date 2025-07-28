#!/usr/bin/env python3
"""
Simple test to check if the server can start
"""

try:
    print("Testing configuration loading...")
    from lyo_app.core.config import settings
    print(f"✅ Config loaded - Database: {settings.database_url}")
    
    print("Testing app creation...")
    from lyo_app.main import app
    print("✅ App created successfully")
    
    print("Testing server startup...")
    import uvicorn
    print("🚀 Starting server on http://localhost:8000")
    uvicorn.run(app, host="0.0.0.0", port=8000, reload=True)
    
except Exception as e:
    print(f"❌ Error: {e}")
    import traceback
    traceback.print_exc()
