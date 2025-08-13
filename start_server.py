#!/usr/bin/env python3
"""Unified server start script pointing to enhanced_main (cloud-ready)."""

import os
import uvicorn


def main():
    port = int(os.getenv("PORT", 8000))
    env = os.getenv("ENVIRONMENT", "development")
    print("🚀 Starting LyoApp API Server (enhanced_main)...")
    print(f"📊 Environment: {env}")
    print(f"🌐 URL: http://localhost:{port}")
    if env != "production":
        print(f"📖 Docs: http://localhost:{port}/docs")
    print("=" * 50)
    uvicorn.run(
        "lyo_app.enhanced_main:app",
        host="0.0.0.0",
        port=port,
        reload=env != "production",
        log_level="info",
    )


if __name__ == "__main__":  # pragma: no cover
    main()
