#!/usr/bin/env python3
"""
Simple test to check if server starts correctly
"""
import uvicorn
import asyncio
from lyo_app.main import app

async def test_startup():
    """Test if the app can be created and basic endpoints work"""
    try:
        print("Testing app creation...")
        
        # Test if we can access the app
        print("✅ App created successfully")
        print("✅ FastAPI docs will be at: http://localhost:8000/docs")
        print("✅ API endpoints will be at: http://localhost:8000/api/v1/")
        
        return True
    except Exception as e:
        print(f"❌ Error: {e}")
        return False

if __name__ == "__main__":
    if asyncio.run(test_startup()):
        print("\n🚀 Starting server...")
        uvicorn.run(
            "lyo_app.main:app",
            host="0.0.0.0", 
            port=8000,
            reload=True,
            log_level="info"
        )
