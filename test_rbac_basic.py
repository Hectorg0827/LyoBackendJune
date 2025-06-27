#!/usr/bin/env python3
"""Test RBAC setup"""

import asyncio
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

async def test():
    try:
        print("🔄 Testing imports...")
        
        from lyo_app.auth.rbac import Role, Permission
        print("✅ RBAC imports successful")
        
        from lyo_app.core.database import init_db
        print("✅ Database imports successful")
        
        print("🔄 Initializing database...")
        await init_db()
        print("✅ Database initialization successful")
        
        print("🎉 Basic setup test completed!")
        return True
        
    except Exception as e:
        print(f"❌ Error: {e}")
        import traceback
        traceback.print_exc()
        return False

if __name__ == "__main__":
    success = asyncio.run(test())
    sys.exit(0 if success else 1)
