#!/usr/bin/env python3
"""
Minimal test to find the import issue.
"""

import sys
print("Starting minimal test...")

try:
    print("Step 1: Importing enum...")
    from enum import Enum
    print("✓ Enum imported")
    
    print("Step 2: Importing datetime...")
    from datetime import datetime
    print("✓ datetime imported")
    
    print("Step 3: Importing SQLAlchemy...")
    from sqlalchemy import Column, Integer, String
    print("✓ SQLAlchemy imported")
    
    print("Step 4: Importing Base...")
    from lyo_app.core.database import Base
    print("✓ Base imported")
    
    print("Step 5: Testing enum definition...")
    class TestEnum(str, Enum):
        TEST = "test"
    print("✓ Enum definition works")
    
    print("All basic imports successful!")
    
except Exception as e:
    print(f"❌ Error at step: {e}")
    import traceback
    traceback.print_exc()

print("Test complete.")
