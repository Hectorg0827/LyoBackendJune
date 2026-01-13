
import asyncio
import logging
import sys
from unittest.mock import MagicMock, patch

# Mock modules that might cause side effects or require heavy dependencies
sys.modules['lyo_app.ai.next_gen_algorithm'] = MagicMock()
sys.modules['lyo_app.ai.gemma_local'] = MagicMock()

# Configure logging
logging.basicConfig(level=logging.INFO)

async def test_db_init():
    print("🧪 Testing database initialization in lifespan...")
    
    # Mock init_db to verify it gets called
    with patch('lyo_app.core.database.init_db', new_callable=MagicMock) as mock_init_db:
        # Make it an async mock
        async def async_mock(*args, **kwargs):
            print("✅ init_db() was called!")
            return None
        mock_init_db.side_effect = async_mock
        
        from lyo_app.app_factory import lifespan, app
        
        # Run lifespan
        async with lifespan(app):
            print("✨ Lifespan started")
            await asyncio.sleep(0.1)
            
        print("🏁 Lifespan finished")

if __name__ == "__main__":
    try:
        asyncio.run(test_db_init())
    except Exception as e:
        print(f"❌ Test failed: {e}")
