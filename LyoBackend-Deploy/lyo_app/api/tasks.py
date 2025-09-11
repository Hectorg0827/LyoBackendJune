"""Task progress API endpoints with WebSocket support."""

import uuid
from datetime import datetime
from typing import Optional
from fastapi import APIRouter, Depends, WebSocket, WebSocketDisconnect, Query
from sqlalchemy.orm import Session

from lyo_app.core.database import get_db
from lyo_app.core.problems import ResourceNotFoundProblem, ValidationProblem
from lyo_app.models.enhanced import User, Task
from lyo_app.schemas import TaskProgress
from lyo_app.auth.jwt_auth import require_active_user
from lyo_app.services.websocket_manager import websocket_manager

import logging

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/tasks", tags=["tasks"])


@router.get("/{task_id}", response_model=TaskProgress)
async def get_task_status(
    task_id: str,
    current_user: User = Depends(require_active_user),
    db: Session = Depends(get_db)
):
    """
    Get task progress status (polling fallback for WebSocket).
    
    This endpoint provides task progress information for clients that
    cannot use WebSocket connections or as a fallback mechanism.
    
    Args:
        task_id: UUID of the task
        
    Returns:
        TaskProgress with current status and progress information
        
    Raises:
        ResourceNotFoundProblem: Task not found
        AuthorizationProblem: Task belongs to different user
    """
    try:
        task_uuid = uuid.UUID(task_id)
    except ValueError:
        raise ValidationProblem("Invalid task ID format")
    
    task = db.query(Task).filter(Task.id == task_uuid).first()
    
    if not task:
        raise ResourceNotFoundProblem("task", task_id)
    
    # Ensure user can only access their own tasks
    if task.user_id != current_user.id:
        from lyo_app.core.problems import AuthorizationProblem
        raise AuthorizationProblem("You can only access your own tasks")
    
    return TaskProgress(
        task_id=str(task.id),
        state=task.state,
        progress_pct=task.progress_pct,
        message=task.message,
        result_id=str(task.result_course_id) if task.result_course_id else None,
        created_at=task.created_at,
        started_at=task.started_at,
        completed_at=task.completed_at,
        error_details=task.error_details
    )


@router.websocket("/ws/{task_id}")
async def task_progress_websocket(
    websocket: WebSocket,
    task_id: str,
    token: Optional[str] = Query(None, description="JWT access token for authentication")
):
    """
    WebSocket endpoint for real-time task progress updates.
    
    This endpoint provides real-time progress updates for long-running tasks
    like course generation. Client connects with a task_id and receives
    progress events as they occur.
    
    Protocol:
        - Client connects with task_id and optional token query parameter
        - Server authenticates user and validates task ownership
        - Server sends progress events as JSON messages
        - Connection closes when task completes or on error
    
    Message Format:
        {
            "task_id": "uuid",
            "state": "RUNNING|DONE|ERROR",
            "progress_pct": 42,
            "message": "Processing...",
            "result_id": "uuid|null",
            "timestamp": "2025-01-01T12:00:00Z"
        }
        
    Args:
        task_id: UUID of the task to monitor
        token: JWT access token (query parameter for WebSocket compatibility)
    """
    await websocket.accept()
    
    try:
        # Validate task ID format
        try:
            task_uuid = uuid.UUID(task_id)
        except ValueError:
            await websocket.send_json({
                "error": "Invalid task ID format",
                "type": "validation_error"
            })
            await websocket.close(code=1000)
            return
        
        # Authenticate user (WebSocket doesn't support standard headers)
        user = None
        if token:
            try:
                from lyo_app.auth.jwt_auth import verify_token
                from lyo_app.core.database import get_db
                
                token_data = verify_token(token, "access")
                db = next(get_db())
                user = db.query(User).filter(User.id == token_data.user_id).first()
                
                if not user or not user.is_active:
                    raise Exception("User not found or inactive")
                    
            except Exception as e:
                logger.warning(f"WebSocket authentication failed: {e}")
                await websocket.send_json({
                    "error": "Authentication failed",
                    "type": "auth_error"
                })
                await websocket.close(code=1000)
                return
        else:
            # For development, allow unauthenticated access
            # In production, always require authentication
            logger.warning("WebSocket connection without authentication")
        
        # Validate task exists and user has access
        db = next(get_db())
        task = db.query(Task).filter(Task.id == task_uuid).first()
        
        if not task:
            await websocket.send_json({
                "error": f"Task {task_id} not found",
                "type": "not_found_error"
            })
            await websocket.close(code=1000)
            return
        
        if user and task.user_id != user.id:
            await websocket.send_json({
                "error": "Access denied to this task",
                "type": "access_denied_error"
            })
            await websocket.close(code=1000)
            return
        
        # Send current task status immediately
        current_status = {
            "task_id": task_id,
            "state": task.state.value,
            "progress_pct": task.progress_pct,
            "message": task.message,
            "result_id": str(task.result_course_id) if task.result_course_id else None,
            "timestamp": datetime.utcnow().isoformat()
        }
        
        await websocket.send_json(current_status)
        
        # If task is already complete, close connection
        if task.state in ["DONE", "ERROR"]:
            await websocket.close(code=1000)
            return
        
        # Subscribe to task progress updates
        await websocket_manager.subscribe_to_task(websocket, task_id)
        
        # Keep connection alive and handle client messages
        while True:
            # Wait for client message (ping/pong for keepalive)
            try:
                message = await websocket.receive_json()
                
                # Handle client ping
                if message.get("type") == "ping":
                    await websocket.send_json({
                        "type": "pong",
                        "timestamp": datetime.utcnow().isoformat()
                    })
                
                # Handle status request
                elif message.get("type") == "status_request":
                    # Refresh task status from database
                    db.refresh(task)
                    current_status = {
                        "task_id": task_id,
                        "state": task.state.value,
                        "progress_pct": task.progress_pct,
                        "message": task.message,
                        "result_id": str(task.result_course_id) if task.result_course_id else None,
                        "timestamp": datetime.utcnow().isoformat()
                    }
                    await websocket.send_json(current_status)
                
            except Exception as e:
                logger.debug(f"WebSocket receive error: {e}")
                break
                
    except WebSocketDisconnect:
        logger.debug(f"WebSocket disconnected for task {task_id}")
    except Exception as e:
        logger.error(f"WebSocket error for task {task_id}: {e}")
        try:
            await websocket.send_json({
                "error": str(e),
                "type": "server_error"
            })
        except:
            pass
    finally:
        # Clean up subscription
        try:
            websocket_manager.unsubscribe_from_task(websocket, task_id)
        except:
            pass


@router.get("", response_model=list[TaskProgress])
async def list_user_tasks(
    current_user: User = Depends(require_active_user),
    db: Session = Depends(get_db),
    state: Optional[str] = Query(None, description="Filter by task state"),
    task_type: Optional[str] = Query(None, description="Filter by task type"),
    limit: int = Query(20, ge=1, le=100, description="Number of tasks to return"),
    offset: int = Query(0, ge=0, description="Number of tasks to skip")
):
    """
    List user's tasks with filtering and pagination.
    
    Returns:
        List of TaskProgress objects for the user's tasks
    """
    query = db.query(Task).filter(Task.user_id == current_user.id)
    
    if state:
        query = query.filter(Task.state == state)
    
    if task_type:
        query = query.filter(Task.task_type == task_type)
    
    # Order by creation date (newest first)
    query = query.order_by(Task.created_at.desc())
    
    # Apply pagination
    tasks = query.offset(offset).limit(limit).all()
    
    return [
        TaskProgress(
            task_id=str(task.id),
            state=task.state,
            progress_pct=task.progress_pct,
            message=task.message,
            result_id=str(task.result_course_id) if task.result_course_id else None,
            created_at=task.created_at,
            started_at=task.started_at,
            completed_at=task.completed_at,
            error_details=task.error_details
        )
        for task in tasks
    ]


@router.delete("/{task_id}", status_code=204)
async def cancel_task(
    task_id: str,
    current_user: User = Depends(require_active_user),
    db: Session = Depends(get_db)
):
    """
    Cancel a running task.
    
    Note: This sets the task state to ERROR but does not guarantee
    that the Celery worker will stop immediately. The worker should
    check task status periodically and handle cancellation gracefully.
    
    Args:
        task_id: UUID of the task to cancel
        
    Raises:
        ResourceNotFoundProblem: Task not found
        AuthorizationProblem: Task belongs to different user
        ValidationProblem: Task cannot be cancelled (already complete)
    """
    try:
        task_uuid = uuid.UUID(task_id)
    except ValueError:
        raise ValidationProblem("Invalid task ID format")
    
    task = db.query(Task).filter(Task.id == task_uuid).first()
    
    if not task:
        raise ResourceNotFoundProblem("task", task_id)
    
    if task.user_id != current_user.id:
        from lyo_app.core.problems import AuthorizationProblem
        raise AuthorizationProblem("You can only cancel your own tasks")
    
    if task.state in ["DONE", "ERROR"]:
        raise ValidationProblem("Cannot cancel completed task")
    
    # Update task state
    task.state = "ERROR"
    task.message = "Task cancelled by user"
    task.completed_at = datetime.utcnow()
    task.updated_at = datetime.utcnow()
    task.error_details = {
        "cancelled_by_user": True,
        "cancelled_at": datetime.utcnow().isoformat()
    }
    
    db.commit()
    
    # Notify WebSocket subscribers
    websocket_manager.publish_task_progress(task_id, {
        "task_id": task_id,
        "state": "ERROR",
        "progress_pct": task.progress_pct,
        "message": "Task cancelled by user",
        "result_id": None,
        "timestamp": datetime.utcnow().isoformat()
    })
    
    # TODO: Send cancellation signal to Celery worker
    # from lyo_app.workers.celery_app import celery_app
    # celery_app.control.revoke(task_id, terminate=True)
    
    return None
