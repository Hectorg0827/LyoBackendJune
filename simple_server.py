"""
Simple production server for LyoBackend.
Direct imports to avoid module conflicts.
"""

import logging
import uvicorn
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

# Direct imports to avoid conflicts
from lyo_app.core.database import init_db
from lyo_app.core.config import settings

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan events."""
    # Startup
    logger.info("Starting LyoBackend production server...")
    
    try:
        # Initialize database
        await init_db()
        logger.info("Database initialized successfully")
        
        logger.info("LyoBackend production server started successfully")
        
    except Exception as e:
        logger.error(f"Failed to start application: {e}")
        raise
    
    yield
    
    # Shutdown
    logger.info("Shutting down LyoBackend production server...")


# Create FastAPI application
app = FastAPI(
    title="LyoBackend Production API",
    description="Production-ready backend for Lyo learning app",
    version="1.0.0",
    lifespan=lifespan
)

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # In production, specify allowed origins
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# Basic health check endpoint
@app.get("/health")
async def health_check():
    """Basic health check endpoint."""
    return {
        "status": "healthy",
        "message": "LyoBackend Production API is running",
        "version": "1.0.0"
    }


@app.get("/")
async def root():
    """Root endpoint."""
    return {
        "name": "LyoBackend Production API",
        "version": "1.0.0",
        "status": "operational",
        "documentation": "/docs",
        "health": "/health",
        "message": "Welcome to LyoBackend Production API!"
    }


# Basic API info endpoint
@app.get("/api/v1")
async def api_info():
    """API information."""
    return {
        "version": "1.0.0",
        "status": "operational",
        "features": [
            "Database connectivity",
            "Health monitoring",
            "CORS enabled",
            "Production ready"
        ],
        "endpoints": {
            "root": "/",
            "health": "/health",
            "docs": "/docs",
            "redoc": "/redoc"
        }
    }


# Test database connection endpoint
@app.get("/api/v1/db-test")
async def test_database():
    """Test database connection."""
    try:
        from lyo_app.core.database import get_db
        from sqlalchemy import text
        
        # Get database session
        async for db in get_db():
            # Test query
            result = await db.execute(text("SELECT 1 as test"))
            test_result = result.fetchone()
            
            if test_result and test_result[0] == 1:
                return {
                    "status": "success",
                    "message": "Database connection successful",
                    "test_query": "SELECT 1",
                    "result": test_result[0]
                }
            else:
                raise HTTPException(status_code=500, detail="Database test failed")
                
    except Exception as e:
        logger.error(f"Database test error: {e}")
        raise HTTPException(status_code=500, detail=f"Database connection failed: {str(e)}")


# Test Redis connection endpoint
@app.get("/api/v1/redis-test")
async def test_redis():
    """Test Redis connection."""
    try:
        import redis
        client = redis.Redis.from_url(settings.redis_url)
        
        # Test ping
        result = client.ping()
        
        if result:
            return {
                "status": "success", 
                "message": "Redis connection successful",
                "test_operation": "ping",
                "result": "PONG"
            }
        else:
            raise HTTPException(status_code=500, detail="Redis test failed")
            
    except Exception as e:
        logger.error(f"Redis test error: {e}")
        raise HTTPException(status_code=500, detail=f"Redis connection failed: {str(e)}")


if __name__ == "__main__":
    logger.info("Starting LyoBackend simple production server...")
    
    uvicorn.run(
        "simple_server:app",
        host="0.0.0.0",
        port=8000,
        reload=False,
        access_log=True,
        log_level="info"
    )
