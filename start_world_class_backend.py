"""
Simple World-Class Backend Startup Script
"""

import uvicorn
import structlog

logger = structlog.get_logger(__name__)

if __name__ == "__main__":
    logger.info("🚀 Starting LyoApp World-Class Backend...")
    
    try:
        uvicorn.run(
            "lyo_app.enterprise_main:app",
            host="0.0.0.0",
            port=8000,
            reload=True,
            log_level="info",
            access_log=True
        )
    except Exception as e:
        logger.error(f"Failed to start server: {e}")
        print(f"❌ Server startup failed: {e}")
        
        print("\n🔄 Falling back to simple main...")
        try:
            uvicorn.run(
                "lyo_app.main:app",
                host="0.0.0.0", 
                port=8000,
                reload=True,
                log_level="info"
            )
        except Exception as e2:
            print(f"❌ Fallback also failed: {e2}")
            print("Please check your dependencies and configuration")
