#!/usr/bin/env python3
"""
Phase 1: LyoBackend with Core Database Functionality
Adding back database support and basic security
"""

import os
import logging
from contextlib import asynccontextmanager
from typing import AsyncGenerator

from fastapi import FastAPI, HTTPException, Depends
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy import create_engine, text
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker
from sqlalchemy.orm import declarative_base, sessionmaker
import uvicorn

# Set environment variables
os.environ.setdefault("ENVIRONMENT", "production")
os.environ.setdefault("PORT", "8080")
os.environ.setdefault("DATABASE_URL", "sqlite+aiosqlite:///./lyo_app_dev.db")

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Database setup
DATABASE_URL = os.getenv("DATABASE_URL", "sqlite+aiosqlite:///./lyo_app_dev.db")
engine = create_async_engine(DATABASE_URL, echo=False)
async_session_maker = async_sessionmaker(engine, expire_on_commit=False)
Base = declarative_base()

# Database dependency
async def get_db():
    async with async_session_maker() as session:
        try:
            yield session
        finally:
            await session.close()

@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """Lifespan with database initialization."""
    logger.info("🚀 Starting LyoBackend Phase 1 on Cloud Run...")
    
    try:
        # Test database connection
        async with async_session_maker() as session:
            await session.execute(text("SELECT 1"))
            logger.info("✅ Database connection established")
        
        logger.info("✅ Backend initialized successfully")
        
    except Exception as e:
        logger.error(f"❌ Failed to start: {e}")
        raise
    
    yield
    
    # Cleanup
    logger.info("🔄 Shutting down...")
    await engine.dispose()

# Create FastAPI app
app = FastAPI(
    title="LyoBackend Phase 1",
    description="Enhanced learning backend with database support",
    version="2.1.0",
    lifespan=lifespan
)

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.get("/")
async def root():
    """Root endpoint."""
    return {
        "name": "LyoBackend Phase 1",
        "version": "2.1.0",
        "status": "operational",
        "features": [
            "Database Support",
            "Async SQLAlchemy",
            "Enhanced Security Foundation"
        ],
        "database": "connected",
        "endpoints": {
            "health": "/health",
            "database": "/database/status",
            "docs": "/docs"
        }
    }

@app.get("/health")
async def health_check(db: AsyncSession = Depends(get_db)):
    """Health check with database test."""
    try:
        # Test database
        result = await db.execute(text("SELECT 1 as test"))
        db_status = "healthy" if result.scalar() == 1 else "error"
        
        return {
            "status": "healthy",
            "service": "lyo-backend-phase1",
            "version": "2.1.0",
            "database": db_status,
            "environment": os.getenv("ENVIRONMENT", "unknown"),
            "port": os.getenv("PORT", "8080")
        }
    except Exception as e:
        logger.error(f"Health check failed: {e}")
        return {
            "status": "degraded",
            "service": "lyo-backend-phase1",
            "version": "2.1.0",
            "database": "error",
            "error": str(e)
        }

@app.get("/database/status")
async def database_status(db: AsyncSession = Depends(get_db)):
    """Database status endpoint."""
    try:
        result = await db.execute(text("SELECT sqlite_version() as version"))
        version = result.scalar()
        
        return {
            "status": "connected",
            "database": "SQLite",
            "version": version,
            "url": "sqlite+aiosqlite:///./lyo_app_dev.db"
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Database error: {str(e)}")

@app.get("/api/v1")
async def api_info():
    """API information."""
    return {
        "version": "1.0.0",
        "status": "operational",
        "message": "LyoBackend Phase 1 API is running successfully",
        "features": ["database", "async", "security-foundation"]
    }

# Error handler
@app.exception_handler(Exception)
async def general_exception_handler(request, exc: Exception):
    """Handle all exceptions."""
    logger.error(f"Unhandled exception: {exc}")
    return JSONResponse(
        status_code=500,
        content={"error": "Internal server error", "phase": "1"}
    )

# For Cloud Run
if __name__ == "__main__":
    port = int(os.getenv("PORT", 8080))
    logger.info(f"🚀 Starting Phase 1 on port {port}")
    
    uvicorn.run(
        "cloud_main_phase1:app",
        host="0.0.0.0",
        port=port,
        log_level="info"
    )
