"""
API endpoints for stories and messenger (chat) features.
"""
from fastapi import APIRouter, Depends, HTTPException, WebSocket, WebSocketDisconnect, status
from sqlalchemy.orm import Session
from typing import List, Optional
from datetime import datetime, timedelta
from lyo_app.models.social import Story, StoryView, Conversation, ConversationParticipant, Message, MessageReadReceipt
from lyo_app.core.database import get_db
from lyo_app.auth.routes import get_current_user
from lyo_app.auth.models import User
from lyo_app.monetization.engine import get_ad_for_placement

router = APIRouter(prefix="/social", tags=["Stories & Messenger"])

# --- Story Endpoints ---
@router.post("/stories/", response_model=dict)
async def create_story(
    content_type: str,
    media_url: Optional[str] = None,
    text_content: Optional[str] = None,
    metadata: Optional[dict] = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    expires_at = datetime.utcnow() + timedelta(hours=24)
    story = Story(
        user_id=current_user.id,
        content_type=content_type,
        media_url=media_url,
        text_content=text_content,
        metadata=metadata,
        expires_at=expires_at
    )
    db.add(story)
    db.commit()
    db.refresh(story)
    return {"id": story.id, "expires_at": story.expires_at}

@router.get("/stories/", response_model=List[dict])
async def get_active_stories(db: Session = Depends(get_db)):
    now = datetime.utcnow()
    stories = db.query(Story).filter(Story.expires_at > now).all()
    payload = [{"type": "story", "id": s.id, "user_id": s.user_id, "media_url": s.media_url, "text_content": s.text_content, "created_at": s.created_at} for s in stories]
    ad = get_ad_for_placement("story")
    if ad:
        payload.append({"type": "ad", "ad": ad.model_dump()})
    return payload

@router.post("/stories/{story_id}/view", response_model=dict)
async def view_story(story_id: int, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    story = db.query(Story).filter(Story.id == story_id).first()
    if not story:
        raise HTTPException(status_code=404, detail="Story not found")
    view = StoryView(story_id=story_id, viewer_id=current_user.id)
    story.view_count += 1
    db.add(view)
    db.commit()
    return {"viewed": True}

@router.delete("/stories/{story_id}", response_model=dict)
async def delete_story(story_id: int, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    story = db.query(Story).filter(Story.id == story_id, Story.user_id == current_user.id).first()
    if not story:
        raise HTTPException(status_code=404, detail="Story not found or not owned by user")
    db.delete(story)
    db.commit()
    return {"deleted": True}

# --- Messenger Endpoints ---
@router.post("/messenger/conversations", response_model=dict)
async def create_conversation(
    participant_ids: List[int],
    name: Optional[str] = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    conversation = Conversation(type="group" if len(participant_ids) > 1 else "direct", name=name)
    db.add(conversation)
    db.commit()
    db.refresh(conversation)
    # Add participants
    for uid in set(participant_ids + [current_user.id]):
        participant = ConversationParticipant(conversation_id=conversation.id, user_id=uid, is_admin=(uid == current_user.id))
        db.add(participant)
    db.commit()
    return {"id": conversation.id}

@router.get("/messenger/conversations", response_model=List[dict])
async def list_conversations(db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    cps = db.query(ConversationParticipant).filter(ConversationParticipant.user_id == current_user.id).all()
    return [{"id": cp.conversation_id, "is_admin": cp.is_admin} for cp in cps]

@router.get("/messenger/conversations/{conv_id}/messages", response_model=List[dict])
async def get_messages(conv_id: int, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    cp = db.query(ConversationParticipant).filter(ConversationParticipant.conversation_id == conv_id, ConversationParticipant.user_id == current_user.id).first()
    if not cp:
        raise HTTPException(status_code=403, detail="Not a participant")
    msgs = db.query(Message).filter(Message.conversation_id == conv_id).order_by(Message.created_at).all()
    return [{"id": m.id, "sender_id": m.sender_id, "content": m.content, "created_at": m.created_at} for m in msgs]

@router.post("/messenger/conversations/{conv_id}/messages", response_model=dict)
async def send_message(conv_id: int, content: str, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    cp = db.query(ConversationParticipant).filter(ConversationParticipant.conversation_id == conv_id, ConversationParticipant.user_id == current_user.id).first()
    if not cp:
        raise HTTPException(status_code=403, detail="Not a participant")
    msg = Message(conversation_id=conv_id, sender_id=current_user.id, content=content, created_at=datetime.utcnow())
    db.add(msg)
    db.commit()
    db.refresh(msg)
    return {"id": msg.id, "created_at": msg.created_at}

# --- WebSocket for Real-time Chat (scaffold) ---
active_connections = {}

@router.websocket("/messenger/ws/{user_id}")
async def chat_ws(websocket: WebSocket, user_id: int, db: Session = Depends(get_db)):
    await websocket.accept()
    active_connections[user_id] = websocket
    try:
        while True:
            data = await websocket.receive_text()
            # Here you would parse data, route to conversation, broadcast, etc.
            await websocket.send_text(f"Echo: {data}")
    except WebSocketDisconnect:
        del active_connections[user_id]
