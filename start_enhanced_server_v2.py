"""Enhanced LyoBackend v2 startup script with comprehensive system initialization."""

import asyncio
import logging
import sys
import os
import signal
from pathlib import Path
from typing import Optional

# Add the project root to Python path
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


class LyoBackendServer:
    """Enhanced LyoBackend v2 server manager."""
    
    def __init__(self):
        self.server_process = None
        self.is_running = False
    
    async def startup_checks(self):
        """Perform startup checks and initialization."""
        logger.info("🔍 Performing startup checks...")
        
        # Check Python version
        if sys.version_info < (3, 9):
            logger.error("❌ Python 3.9+ required")
            sys.exit(1)
        
        logger.info(f"✅ Python {sys.version.split()[0]}")
        
        # Check required environment variables
        required_env_vars = [
            "DATABASE_URL",
            "JWT_SECRET_KEY"
        ]
        
        missing_vars = []
        for var in required_env_vars:
            if not os.getenv(var):
                missing_vars.append(var)
        
        if missing_vars:
            logger.warning(f"⚠️ Missing environment variables: {', '.join(missing_vars)}")
            logger.info("Using default values for development")
        
        # Set default environment variables if not set
        if not os.getenv("DATABASE_URL"):
            os.environ["DATABASE_URL"] = "sqlite+aiosqlite:///lyo_app_dev.db"
            logger.info("🔧 Using SQLite database for development")
        
        if not os.getenv("JWT_SECRET_KEY"):
            os.environ["JWT_SECRET_KEY"] = "development-secret-key-change-in-production"
            logger.warning("🔧 Using default JWT secret (change in production!)")
        
        if not os.getenv("REDIS_URL"):
            os.environ["REDIS_URL"] = "redis://localhost:6379/0"
            logger.info("🔧 Using default Redis URL")
        
        # Check for required directories
        required_dirs = [
            "lyo_app",
            "lyo_app/core",
            "lyo_app/models",
            "lyo_app/api",
            "lyo_app/services"
        ]
        
        for dir_path in required_dirs:
            if not Path(dir_path).exists():
                logger.error(f"❌ Missing required directory: {dir_path}")
                sys.exit(1)
        
        logger.info("✅ Directory structure verified")
        
        # Import and check core modules
        try:
            from lyo_app.core.settings import settings
            logger.info("✅ Settings module loaded")
            
            from lyo_app.enhanced_main_v2 import app
            logger.info("✅ FastAPI application loaded")
            
        except ImportError as e:
            logger.error(f"❌ Failed to import core modules: {e}")
            sys.exit(1)
        
        logger.info("🚀 All startup checks passed!")
    
    def setup_signal_handlers(self):
        """Setup signal handlers for graceful shutdown."""
        def signal_handler(signum, frame):
            logger.info(f"Received signal {signum}, initiating graceful shutdown...")
            self.is_running = False
        
        signal.signal(signal.SIGINT, signal_handler)
        signal.signal(signal.SIGTERM, signal_handler)
    
    async def start_server(
        self,
        host: str = "0.0.0.0",
        port: int = 8000,
        reload: bool = False,
        workers: int = 1
    ):
        """Start the LyoBackend v2 server."""
        try:
            import uvicorn
            
            # Server configuration
            config = uvicorn.Config(
                app="lyo_app.enhanced_main_v2:app",
                host=host,
                port=port,
                reload=reload,
                workers=workers if not reload else 1,  # Workers don't work with reload
                log_level="info",
                access_log=True,
                ws_ping_interval=30,
                ws_ping_timeout=30,
                loop="asyncio",
                http="httptools",
                lifespan="on"
            )
            
            server = uvicorn.Server(config)
            
            logger.info(f"🚀 Starting LyoBackend v2 on {host}:{port}")
            logger.info(f"📝 Reload mode: {'enabled' if reload else 'disabled'}")
            logger.info(f"👥 Workers: {workers if not reload else 1}")
            logger.info(f"🌐 API docs: http://{host}:{port}/v1/docs")
            logger.info(f"📊 Health check: http://{host}:{port}/health")
            
            self.is_running = True
            await server.serve()
            
        except Exception as e:
            logger.error(f"❌ Failed to start server: {e}")
            raise
    
    async def run_validation(self):
        """Run system validation after startup."""
        logger.info("🧪 Running post-startup validation...")
        
        try:
            from comprehensive_validation_v2 import LyoBackendValidator
            
            # Wait a moment for server to be ready
            await asyncio.sleep(3)
            
            validator = LyoBackendValidator("http://localhost:8000")
            results = await validator.run_full_validation()
            
            if results["overall_status"] == "success":
                logger.info("✅ All validation tests passed!")
            else:
                logger.warning("⚠️ Some validation tests failed, but server is running")
                
        except ImportError:
            logger.warning("⚠️ Validation module not available, skipping validation")
        except Exception as e:
            logger.error(f"❌ Validation failed: {e}")


async def main():
    """Main startup function."""
    print("""
╔══════════════════════════════════════════════════════════════╗
║                    LyoBackend v2 Enhanced                   ║
║                  AI-Powered Learning Platform               ║
╠══════════════════════════════════════════════════════════════╣
║ Features:                                                    ║
║ • JWT Authentication with refresh tokens                    ║
║ • Async course generation with Gemma 3                     ║
║ • WebSocket real-time progress updates                     ║
║ • RFC 9457 Problem Details error handling                  ║
║ • Push notifications (APNs/FCM)                            ║
║ • Community features and gamification                      ║
║ • AI-powered content curation                              ║
║ • Comprehensive observability                              ║
╚══════════════════════════════════════════════════════════════╝
    """)
    
    # Parse command line arguments
    import argparse
    
    parser = argparse.ArgumentParser(description="LyoBackend v2 Enhanced Server")
    parser.add_argument("--host", default="0.0.0.0", help="Host to bind to")
    parser.add_argument("--port", type=int, default=8000, help="Port to bind to")
    parser.add_argument("--reload", action="store_true", help="Enable auto-reload")
    parser.add_argument("--workers", type=int, default=1, help="Number of worker processes")
    parser.add_argument("--validate", action="store_true", help="Run validation after startup")
    parser.add_argument("--dev", action="store_true", help="Development mode (reload + validation)")
    
    args = parser.parse_args()
    
    # Development mode shortcuts
    if args.dev:
        args.reload = True
        args.validate = True
    
    # Create server instance
    server = LyoBackendServer()
    
    try:
        # Perform startup checks
        await server.startup_checks()
        
        # Setup signal handlers
        server.setup_signal_handlers()
        
        # Start validation task if requested
        validation_task = None
        if args.validate:
            validation_task = asyncio.create_task(server.run_validation())
        
        # Start the server
        await server.start_server(
            host=args.host,
            port=args.port,
            reload=args.reload,
            workers=args.workers
        )
        
        # Wait for validation to complete if running
        if validation_task and not validation_task.done():
            await validation_task
        
    except KeyboardInterrupt:
        logger.info("👋 Shutdown requested by user")
    except Exception as e:
        logger.error(f"❌ Server startup failed: {e}")
        sys.exit(1)
    finally:
        logger.info("🛑 LyoBackend v2 shutdown complete")


if __name__ == "__main__":
    # Handle Windows event loop policy
    if sys.platform.startswith('win'):
        asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())
    
    # Run the server
    asyncio.run(main())
