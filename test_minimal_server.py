#!/usr/bin/env python3
"""
Simple test server to verify basic functionality
"""
import asyncio
import os
import logging
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
import uvicorn
import google.generativeai as genai

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Set API key
os.environ["GEMINI_API_KEY"] = "AIzaSyAXqRkBk_PUuiy8WKCQ66v447NmTE_tCK0"

app = FastAPI(
    title="LyoBackend Test",
    description="Test server for basic functionality",
    version="1.0.0"
)

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Global AI model
gemini_model = None

@app.on_event("startup")
async def startup_event():
    """Initialize AI model on startup."""
    global gemini_model
    try:
        genai.configure(api_key=os.environ.get("GEMINI_API_KEY"))
        gemini_model = genai.GenerativeModel('models/gemini-1.5-flash')
        logger.info("✅ Gemini AI initialized successfully")
    except Exception as e:
        logger.error(f"❌ Failed to initialize Gemini AI: {e}")

@app.get("/")
async def root():
    return {"message": "LyoBackend Test Server - Fully Functional", "status": "online"}

@app.get("/health")
async def health_check():
    """Health check endpoint."""
    health_status = {
        "status": "healthy",
        "message": "Server is running",
        "ai_available": gemini_model is not None
    }
    
    # Test AI if available
    if gemini_model:
        try:
            response = gemini_model.generate_content("Say 'AI is working' in one sentence.")
            health_status["ai_test"] = response.text.strip()
            health_status["ai_status"] = "working"
        except Exception as e:
            health_status["ai_status"] = f"error: {str(e)}"
            health_status["status"] = "degraded"
    
    return health_status

@app.post("/api/v1/ai/test-real")
async def test_real_ai(request: dict):
    """Test real AI functionality."""
    if not gemini_model:
        raise HTTPException(status_code=503, detail="AI service not available")
    
    try:
        prompt = request.get("prompt", "Hello, please respond with a friendly greeting.")
        response = gemini_model.generate_content(prompt)
        return {
            "success": True,
            "response": response.text,
            "model": "gemini-1.5-flash",
            "mock": False
        }
    except Exception as e:
        logger.error(f"AI generation error: {e}")
        raise HTTPException(status_code=500, detail=f"AI generation failed: {str(e)}")

@app.post("/api/v1/ai/study-session")
async def ai_study_session(request: dict):
    """Socratic tutoring session with real AI."""
    if not gemini_model:
        raise HTTPException(status_code=503, detail="AI service not available")
    
    try:
        user_input = request.get("userInput", "")
        resource_id = request.get("resourceId", "general")
        
        # Socratic tutoring prompt
        prompt = f"""
        You are an expert Socratic tutor. A student is learning about {resource_id}.
        Student says: "{user_input}"
        
        Respond with:
        1. A thoughtful question that guides them to deeper understanding
        2. Brief encouragement 
        3. A hint if they seem stuck
        
        Keep it conversational and encouraging. Don't give direct answers - guide discovery.
        """
        
        response = gemini_model.generate_content(prompt)
        return {
            "success": True,
            "response": response.text,
            "session_type": "socratic_tutoring",
            "mock": False
        }
    except Exception as e:
        logger.error(f"Study session error: {e}")
        raise HTTPException(status_code=500, detail=f"Study session failed: {str(e)}")

if __name__ == "__main__":
    logger.info("🚀 Starting LyoBackend Test Server")
    uvicorn.run(
        app,
        host="0.0.0.0",
        port=8081,
        log_level="info"
    )
