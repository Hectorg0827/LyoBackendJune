#!/usr/bin/env python3
"""
Simple server starter for troubleshooting docs access
"""
import uvicorn
from lyo_app.main import app

if __name__ == "__main__":
    print("Starting FastAPI server on port 8000...")
    print("Docs will be available at: http://localhost:8000/docs")
    print("API will be available at: http://localhost:8000/")
    
    uvicorn.run(
        app,
        host="0.0.0.0",
        port=8000,
        reload=True,
        log_level="info"
    )
