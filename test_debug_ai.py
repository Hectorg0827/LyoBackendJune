#!/usr/bin/env python3
"""
Debug test to see the full traceback
"""

import asyncio
import os
import sys
import traceback
from pathlib import Path

os.chdir(Path(__file__).parent)

from dotenv import load_dotenv
load_dotenv(override=False)

print("Importing AIResilienceManager...")
try:
    from lyo_app.core.ai_resilience import AIResilienceManager
    print("✅ Import succeeded\n")
except Exception as e:
    print(f"❌ Import failed: {e}\n")
    traceback.print_exc()
    sys.exit(1)

async def test():
    print("Creating manager instance...")
    manager = AIResilienceManager()
    
    print("Calling initialize()...")
    try:
        await manager.initialize()
        print("✅ Initialize succeeded")
        return True
    except Exception as e:
        print(f"❌ Initialize failed:")
        print(f"\nError type: {type(e).__name__}")
        print(f"Error message: {e}\n")
        print("Full traceback:")
        traceback.print_exc()
        return False

asyncio.run(test())
