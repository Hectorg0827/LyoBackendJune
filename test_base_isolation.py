#!/usr/bin/env python3
"""
Test importing just the Base class definition without engine.
"""

import sys
print("Testing isolated Base import...")

try:
    print("Step 1: Importing SQLAlchemy base...")
    from sqlalchemy.ext.declarative import declarative_base
    from sqlalchemy import MetaData
    from sqlalchemy.orm import DeclarativeBase
    print("✓ SQLAlchemy base classes imported")
    
    print("Step 2: Creating Base class manually...")
    class TestBase(DeclarativeBase):
        """Test base class."""
        metadata = MetaData()
    
    print("✓ Base class created manually")
    
    print("Step 3: Testing if config import works...")
    from lyo_app.core.config import settings
    print(f"✓ Config imported, DB URL: {settings.database_url[:20]}...")
    
    print("All tests passed!")
    
except Exception as e:
    print(f"❌ Error: {e}")
    import traceback
    traceback.print_exc()

print("Test complete.")
