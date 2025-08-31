#!/usr/bin/env python3
"""
Superior AI Backend Startup Script
Handles graceful startup with dependency checking
"""

import os
import sys
import logging
import traceback
from pathlib import Path

# Add project root to Python path
PROJECT_ROOT = Path(__file__).parent
sys.path.insert(0, str(PROJECT_ROOT))

# Set environment variables for superior AI
os.environ.setdefault('ENABLE_SUPERIOR_AI_MODE', 'true')
os.environ.setdefault('ENABLE_ADAPTIVE_DIFFICULTY', 'true') 
os.environ.setdefault('ENABLE_ADVANCED_SOCRATIC', 'true')
os.environ.setdefault('PYTHONPATH', str(PROJECT_ROOT))
os.environ.setdefault('PORT', '8080')

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)

logger = logging.getLogger(__name__)

def check_superior_ai_components():
    """Check if superior AI components are available"""
    try:
        logger.info("🧪 Checking Superior AI components...")
        
        # Check adaptive engine
        from lyo_app.ai_study.adaptive_engine import AdaptiveDifficultyEngine
        logger.info("✅ Advanced Adaptive Difficulty Engine loaded")
        
        # Check socratic engine  
        from lyo_app.ai_study.advanced_socratic import AdvancedSocraticEngine
        logger.info("✅ Advanced Socratic Questioning Engine loaded")
        
        # Check prompt engine
        from lyo_app.ai_study.superior_prompts import SuperiorPromptEngine
        logger.info("✅ Superior Prompt Engineering System loaded")
        
        # Check enhanced service
        from lyo_app.ai_study.service import StudyModeService
        logger.info("✅ Enhanced Study Service Integration loaded")
        
        logger.info("🌟 All Superior AI components verified!")
        return True
        
    except Exception as e:
        logger.warning(f"⚠️ Superior AI component check failed: {e}")
        logger.warning("Continuing with standard mode...")
        return False

def start_application():
    """Start the FastAPI application with proper error handling"""
    try:
        logger.info("🚀 Starting Superior AI Backend...")
        
        # Check superior AI components
        superior_ai_available = check_superior_ai_components()
        
        if superior_ai_available:
            logger.info("🎯 Superior AI mode enabled!")
        else:
            logger.info("📱 Standard mode enabled")
        
        # Import and start the main application
        logger.info("📦 Loading main application...")
        from lyo_app.unified_main import app
        
        logger.info("✅ Application loaded successfully!")
        
        # Import uvicorn for running the server
        import uvicorn
        
        port = int(os.environ.get('PORT', 8080))
        logger.info(f"🌐 Starting server on port {port}")
        
        # Start the server
        uvicorn.run(
            app,
            host="0.0.0.0",
            port=port,
            workers=1,
            timeout_keep_alive=300,
            access_log=True,
            log_level="info"
        )
        
    except ImportError as e:
        logger.error(f"❌ Import error: {e}")
        logger.error("📋 Traceback:")
        traceback.print_exc()
        sys.exit(1)
        
    except Exception as e:
        logger.error(f"❌ Startup error: {e}")
        logger.error("📋 Traceback:")
        traceback.print_exc()
        sys.exit(1)

if __name__ == "__main__":
    start_application()
