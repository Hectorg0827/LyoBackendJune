#!/usr/bin/env python3
"""
Unified Start Script for LyoBackend
----------------------------------
This script starts the LyoBackend application using the new unified architecture
with improved configuration, database handling, error management, and API consistency.
"""

import os
import argparse
import sys
import logging
import uvicorn


def main():
    """Start the LyoBackend application."""
    # Parse command line arguments
    parser = argparse.ArgumentParser(description="Start LyoBackend server")
    parser.add_argument(
        "--port", type=int, default=int(os.getenv("PORT", 8000)),
        help="Port to run the server on (default: 8000 or PORT env var)"
    )
    parser.add_argument(
        "--host", type=str, default=os.getenv("HOST", "0.0.0.0"),
        help="Host to bind the server to (default: 0.0.0.0 or HOST env var)"
    )
    parser.add_argument(
        "--workers", type=int, default=int(os.getenv("WORKERS", "1")),
        help="Number of worker processes (default: 1 or WORKERS env var)"
    )
    parser.add_argument(
        "--env", type=str, default=os.getenv("ENVIRONMENT", "development"),
        choices=["development", "staging", "production"],
        help="Environment to run in (default: development or ENVIRONMENT env var)"
    )
    parser.add_argument(
        "--log-level", type=str, default=os.getenv("LOG_LEVEL", "info").lower(),
        choices=["debug", "info", "warning", "error", "critical"],
        help="Logging level (default: info or LOG_LEVEL env var)"
    )
    parser.add_argument(
        "--reload", action="store_true",
        help="Enable auto-reload (development only)"
    )
    args = parser.parse_args()
    
    # Set environment variables
    os.environ["ENVIRONMENT"] = args.env
    os.environ["LOG_LEVEL"] = args.log_level.upper()
    
    # Configure logging
    logging.basicConfig(
        level=getattr(logging, args.log_level.upper()),
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )
    logger = logging.getLogger("start_unified")
    
    # Print startup information
    logger.info("🚀 Starting LyoBackend with unified architecture...")
    logger.info(f"📊 Environment: {args.env}")
    logger.info(f"🌐 URL: http://{args.host}:{args.port}")
    
    # In development mode, show documentation URL
    if args.env != "production":
        logger.info(f"📖 API Docs: http://{args.host}:{args.port}/docs")
    
    # Don't allow reload in production
    if args.reload and args.env == "production":
        logger.warning("⚠️ Auto-reload is not recommended in production. Disabling.")
        args.reload = False
    
    # Check if we're using PostgreSQL in production
    if args.env == "production":
        database_url = os.getenv("DATABASE_URL", "")
        if "sqlite" in database_url.lower():
            logger.error("❌ SQLite is not supported in production! Set DATABASE_URL to a PostgreSQL connection.")
            sys.exit(1)
    
    # Display warning if not using PostgreSQL in staging
    if args.env == "staging" and "sqlite" in os.getenv("DATABASE_URL", "").lower():
        logger.warning("⚠️ Using SQLite in staging environment. Consider using PostgreSQL for better performance.")
    
    print("=" * 50)
    
    # Start the server
    uvicorn.run(
        "lyo_app.unified_main:app",
        host=args.host,
        port=args.port,
        reload=args.reload and args.env == "development",
        workers=args.workers,
        log_level=args.log_level,
    )


if __name__ == "__main__":
    main()
