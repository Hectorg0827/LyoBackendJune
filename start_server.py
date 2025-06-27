#!/usr/bin/env python3
"""
Start the LyoApp API server.
"""

import uvicorn

if __name__ == "__main__":
    print("🚀 Starting LyoApp API Server...")
    print("📊 Environment: Development")
    print("🗄️ Database: SQLite (./lyo_app_dev.db)")
    print("🌐 URL: http://localhost:8000")
    print("📖 Docs: http://localhost:8000/docs")
    print("=" * 50)
    
    uvicorn.run(
        "lyo_app.main:app",
        host="0.0.0.0",
        port=8000,
        reload=True,
        log_level="info"
    )
