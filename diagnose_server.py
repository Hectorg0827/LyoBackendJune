#!/usr/bin/env python3
"""
Test script to diagnose server startup issues
"""
import sys
import traceback

def test_imports():
    try:
        print("Testing basic imports...")
        import fastapi
        print(f"✅ FastAPI version: {fastapi.__version__}")
        
        import uvicorn
        print(f"✅ Uvicorn imported successfully")
        
        print("\nTesting app imports...")
        from lyo_app.main import app
        print("✅ Main app imported successfully")
        
        print("\nTesting app creation...")
        print(f"✅ App type: {type(app)}")
        print(f"✅ App title: {app.title}")
        
        return True
        
    except Exception as e:
        print(f"❌ Error during import test: {e}")
        traceback.print_exc()
        return False

def test_server_start():
    try:
        print("\nTesting server startup...")
        from lyo_app.main import app
        import uvicorn
        
        print("Starting server on port 8000...")
        uvicorn.run(app, host="127.0.0.1", port=8000, log_level="info")
        
    except Exception as e:
        print(f"❌ Error starting server: {e}")
        traceback.print_exc()

if __name__ == "__main__":
    print("=== LyoApp Server Diagnosis ===")
    
    if test_imports():
        print("\n✅ All imports successful!")
        print("\n=== Starting Server ===")
        test_server_start()
    else:
        print("\n❌ Import test failed. Please fix dependencies first.")
        sys.exit(1)
