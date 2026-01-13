"""
Google A2A Protocol Implementation for Lyo Backend
https://google.github.io/A2A/
"""

from fastapi import APIRouter, FastAPI
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from typing import Optional, List, Dict, Any
from enum import Enum
import uuid
import asyncio
import json

# Main A2A Router
router = APIRouter(prefix="/a2a", tags=["A2A Protocol"])

# Discovery Router (often separate for standardized paths)
discovery_router = APIRouter(tags=["A2A Discovery"])

def include_a2a_routes(app: FastAPI):
    """Helper to include all A2A routes in the main app"""
    app.include_router(router)
    app.include_router(discovery_router)

# ============ A2A Models ============

class TaskState(str, Enum):
    SUBMITTED = "submitted"
    WORKING = "working"
    INPUT_REQUIRED = "input-required"
    COMPLETED = "completed"
    CANCELED = "canceled"
    FAILED = "failed"

class Part(BaseModel):
    type: str  # "text", "file", "data"
    text: Optional[str] = None
    file: Optional[Dict[str, Any]] = None
    data: Optional[Dict[str, Any]] = None

class Message(BaseModel):
    role: str  # "user" or "agent"
    parts: List[Part]

class Artifact(BaseModel):
    name: str
    description: Optional[str] = None
    parts: List[Part]
    index: Optional[int] = None
    append: Optional[bool] = None
    lastChunk: Optional[bool] = None

class TaskRequest(BaseModel):
    id: Optional[str] = None
    sessionId: Optional[str] = None
    message: Message
    acceptedOutputModes: Optional[List[str]] = None
    pushNotification: Optional[Dict[str, Any]] = None

class TaskResponse(BaseModel):
    id: str
    sessionId: Optional[str] = None
    state: TaskState
    message: Optional[Message] = None
    artifacts: Optional[List[Artifact]] = None

# ============ Agent Card ============

AGENT_CARD = {
    "name": "Lyo Learning Agent",
    "description": "AI-powered personal learning mentor",
    "url": "https://lyo-backend-830162750094.us-central1.run.app",
    "version": "1.0.0",
    "capabilities": {
        "streaming": True,
        "pushNotifications": True,
        "stateTransitionHistory": True
    },
    "authentication": {
        "schemes": ["bearer", "api_key"]
    },
    "defaultInputModes": ["text", "application/json"],
    "defaultOutputModes": ["text", "application/json"],
    "skills": [
        {
            "id": "course_generation",
            "name": "Course Generation",
            "description": "Generate personalized learning courses",
            "inputModes": ["text"],
            "outputModes": ["application/json"]
        },
        {
            "id": "quiz_generation",
            "name": "Quiz Generation",
            "description": "Generate quizzes and assessments",
            "inputModes": ["text"],
            "outputModes": ["application/json"]
        },
        {
            "id": "tutoring",
            "name": "AI Tutoring",
            "description": "Socratic-style tutoring",
            "inputModes": ["text"],
            "outputModes": ["text"]
        }
    ]
}

@discovery_router.get("/.well-known/agent.json")
async def get_agent_card():
    """Discover agent capabilities"""
    return AGENT_CARD

@router.post("/tasks/send")
async def send_task(request: TaskRequest):
    """Sync task execution (for short tasks)"""
    # Mock implementation for verification
    task_id = request.id or str(uuid.uuid4())
    
    return TaskResponse(
        id=task_id,
        sessionId=request.sessionId,
        state=TaskState.SUBMITTED,
        message=Message(role="agent", parts=[Part(type="text", text="Task received")])
    )

@router.post("/tasks/sendSubscribe")
async def stream_task(request: TaskRequest):
    """Async task streaming via SSE"""
    task_id = request.id or str(uuid.uuid4())
    
    async def event_generator():
        # 1. Ack
        yield f"data: {json.dumps({'type': 'task', 'task': {'state': 'submitted', 'message': {'role': 'agent', 'parts': [{'type': 'text', 'text': 'Processing...'}]}}})}\n\n"
        await asyncio.sleep(0.5)
        
        # 2. Working
        yield f"data: {json.dumps({'type': 'task', 'task': {'state': 'working'}})}\n\n"
        await asyncio.sleep(1.0)
        
        # 3. Artifact (Course)
        # Check skill request
        # Simplified: Just return a dummy course for verification
        course_data = {
            "courseId": "a2a_generated",
            "title": "A2A Generated Course"
        }
        artifact_payload = {
            "type": "artifact",
            "artifact": {
                "name": "course",
                "parts": [
                    {
                        "type": "text",
                        "text": json.dumps(course_data)
                    }
                ]
            }
        }
        yield f"data: {json.dumps(artifact_payload)}\n\n"
        
        # 4. Complete
        yield f"data: {json.dumps({'type': 'task', 'task': {'state': 'completed'}})}\n\n"
    
    return StreamingResponse(event_generator(), media_type="text/event-stream")
