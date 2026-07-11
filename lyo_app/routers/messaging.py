"""
Messaging Router — Direct messages between users.

Uses ORM models from lyo_app.models.social (Conversation, ConversationParticipant,
Message, MessageReadReceipt) which map to tables created by migration
20250728_add_social_and_messenger_models.
"""

from __future__ import annotations

import logging
from datetime import datetime
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import func, select, and_, desc, case
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from lyo_app.auth.jwt_auth import get_current_user
from lyo_app.auth.models import User
from lyo_app.core.database import get_db
from lyo_app.models.social import (
    Conversation,
    ConversationParticipant,
    Message,
    MessageReadReceipt,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/messages", tags=["Messages"])

# ── Pydantic schemas ────────────────────────────────────────────────────────


class ParticipantOut(BaseModel):
    id: int
    username: str
    display_name: str
    avatar_url: Optional[str] = None


class MessageOut(BaseModel):
    id: int
    conversation_id: int
    sender_id: int
    content: Optional[str] = None
    message_type: Optional[str] = "text"
    media_url: Optional[str] = None
    is_edited: bool = False
    is_deleted: bool = False
    created_at: str
    updated_at: Optional[str] = None


class ConversationOut(BaseModel):
    id: int
    type: Optional[str] = "direct"
    name: Optional[str] = None
    participants: List[ParticipantOut]
    last_message: Optional[MessageOut] = None
    unread_count: int = 0
    updated_at: str


class ConversationsListResponse(BaseModel):
    conversations: List[ConversationOut]


class MessagesListResponse(BaseModel):
    messages: List[MessageOut]
    total: int
    page: int
    per_page: int


class CreateConversationRequest(BaseModel):
    participant_ids: List[int] = Field(..., min_length=1)


class SendMessageRequest(BaseModel):
    content: str = Field(..., min_length=1)
    message_type: str = "text"


# ── Helpers ─────────────────────────────────────────────────────────────────


def _user_to_participant(u: User) -> ParticipantOut:
    first = u.first_name or ""
    last = u.last_name or ""
    display = f"{first} {last}".strip() or u.username
    return ParticipantOut(
        id=u.id,
        username=u.username,
        display_name=display,
        avatar_url=u.avatar_url,
    )


def _message_to_out(m: Message) -> MessageOut:
    return MessageOut(
        id=m.id,
        conversation_id=m.conversation_id,
        sender_id=m.sender_id,
        content=m.content if not m.is_deleted else None,
        message_type=m.message_type or "text",
        media_url=m.media_url if not m.is_deleted else None,
        is_edited=m.is_edited or False,
        is_deleted=m.is_deleted or False,
        created_at=m.created_at.isoformat() if m.created_at else "",
        updated_at=m.updated_at.isoformat() if m.updated_at else None,
    )


# ── Endpoints ───────────────────────────────────────────────────────────────


@router.get("/conversations", response_model=ConversationsListResponse)
async def list_conversations(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """List all conversations for the current user with last message, unread count, and other participants."""

    # Step 1: Get conversation IDs where user is a participant
    my_parts_q = (
        select(ConversationParticipant)
        .where(ConversationParticipant.user_id == current_user.id)
    )
    my_parts_result = await db.execute(my_parts_q)
    my_parts = my_parts_result.scalars().all()

    if not my_parts:
        return ConversationsListResponse(conversations=[])

    conv_id_to_last_read: dict[int, Optional[datetime]] = {
        p.conversation_id: p.last_read_at for p in my_parts
    }
    conv_ids = list(conv_id_to_last_read.keys())

    # Step 2: Load conversations with participants -> users
    convs_q = (
        select(Conversation)
        .where(Conversation.id.in_(conv_ids))
        .options(
            selectinload(Conversation.participants).selectinload(ConversationParticipant.user)
        )
        .order_by(desc(Conversation.updated_at))
    )
    convs_result = await db.execute(convs_q)
    convs = convs_result.scalars().unique().all()

    # Step 3: For each conversation get last message and unread count
    out: list[ConversationOut] = []
    for conv in convs:
        # Last message
        last_msg_q = (
            select(Message)
            .where(Message.conversation_id == conv.id)
            .order_by(desc(Message.created_at))
            .limit(1)
        )
        last_msg_result = await db.execute(last_msg_q)
        last_msg = last_msg_result.scalar_one_or_none()

        # Unread count: messages after user's last_read_at that aren't from user
        last_read = conv_id_to_last_read.get(conv.id)
        unread_count = 0
        if last_read is not None:
            unread_q = (
                select(func.count(Message.id))
                .where(
                    and_(
                        Message.conversation_id == conv.id,
                        Message.sender_id != current_user.id,
                        Message.created_at > last_read,
                        Message.is_deleted == False,  # noqa: E712
                    )
                )
            )
        else:
            # Never read — all messages from others are unread
            unread_q = (
                select(func.count(Message.id))
                .where(
                    and_(
                        Message.conversation_id == conv.id,
                        Message.sender_id != current_user.id,
                        Message.is_deleted == False,  # noqa: E712
                    )
                )
            )
        unread_result = await db.execute(unread_q)
        unread_count = unread_result.scalar() or 0

        # Other participants (everyone except current user)
        participants = [
            _user_to_participant(p.user)
            for p in conv.participants
            if p.user_id != current_user.id and p.user is not None
        ]

        out.append(
            ConversationOut(
                id=conv.id,
                type=conv.type or "direct",
                name=conv.name,
                participants=participants,
                last_message=_message_to_out(last_msg) if last_msg else None,
                unread_count=unread_count,
                updated_at=conv.updated_at.isoformat() if conv.updated_at else "",
            )
        )

    return ConversationsListResponse(conversations=out)


@router.get("/conversations/{conversation_id}", response_model=MessagesListResponse)
async def get_conversation_messages(
    conversation_id: int,
    page: int = Query(1, ge=1),
    per_page: int = Query(50, ge=1, le=100),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Get paginated messages in a conversation."""

    # Verify membership
    membership_q = select(ConversationParticipant).where(
        and_(
            ConversationParticipant.conversation_id == conversation_id,
            ConversationParticipant.user_id == current_user.id,
        )
    )
    membership_result = await db.execute(membership_q)
    if not membership_result.scalar_one_or_none():
        raise HTTPException(status_code=403, detail="Not a member of this conversation")

    # Total count (soft-deleted messages don't consume pagination slots,
    # matching the unread-count logic)
    total_q = select(func.count(Message.id)).where(
        Message.conversation_id == conversation_id,
        Message.is_deleted == False,  # noqa: E712
    )
    total_result = await db.execute(total_q)
    total = total_result.scalar() or 0

    # Paginated messages: page 1 is the most recent window (what a chat UI
    # opens to); messages within a page stay chronological for display.
    offset = (page - 1) * per_page
    msgs_q = (
        select(Message)
        .where(
            Message.conversation_id == conversation_id,
            Message.is_deleted == False,  # noqa: E712
        )
        .order_by(Message.created_at.desc())
        .offset(offset)
        .limit(per_page)
    )
    msgs_result = await db.execute(msgs_q)
    msgs = list(reversed(msgs_result.scalars().all()))

    return MessagesListResponse(
        messages=[_message_to_out(m) for m in msgs],
        total=total,
        page=page,
        per_page=per_page,
    )


@router.post("/conversations", response_model=ConversationOut, status_code=201)
async def create_conversation(
    body: CreateConversationRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Create a new conversation. For 1-on-1 DMs, reuse existing conversation if one exists."""

    participant_ids = list(set(body.participant_ids))
    # Remove current user if included (they're added automatically)
    if current_user.id in participant_ids:
        participant_ids.remove(current_user.id)

    if not participant_ids:
        raise HTTPException(status_code=400, detail="Must include at least one other participant")

    # Validate that all participant users exist
    users_q = select(User).where(User.id.in_(participant_ids))
    users_result = await db.execute(users_q)
    found_users = users_result.scalars().all()
    found_ids = {u.id for u in found_users}
    missing = set(participant_ids) - found_ids
    if missing:
        raise HTTPException(status_code=404, detail=f"Users not found: {list(missing)}")

    all_ids = sorted([current_user.id] + participant_ids)
    conv_type = "direct" if len(all_ids) == 2 else "group"

    # For direct messages, check if a *direct* conversation already exists
    # between these two users (a two-person group thread must not be reused).
    if conv_type == "direct":
        existing_q = (
            select(ConversationParticipant.conversation_id)
            .join(
                Conversation,
                Conversation.id == ConversationParticipant.conversation_id,
            )
            .where(
                ConversationParticipant.user_id.in_(all_ids),
                Conversation.type == "direct",
            )
            .group_by(ConversationParticipant.conversation_id)
            .having(func.count(ConversationParticipant.user_id) == len(all_ids))
        )
        existing_result = await db.execute(existing_q)
        candidate_conv_ids = [row[0] for row in existing_result.all()]

        # Verify exact match (no extra participants)
        for cid in candidate_conv_ids:
            count_q = select(func.count(ConversationParticipant.id)).where(
                ConversationParticipant.conversation_id == cid
            )
            count_result = await db.execute(count_q)
            if count_result.scalar() == len(all_ids):
                # Reuse existing conversation — load and return it
                conv_q = (
                    select(Conversation)
                    .where(Conversation.id == cid)
                    .options(
                        selectinload(Conversation.participants).selectinload(
                            ConversationParticipant.user
                        )
                    )
                )
                conv_result = await db.execute(conv_q)
                existing_conv = conv_result.scalar_one()
                participants_out = [
                    _user_to_participant(p.user)
                    for p in existing_conv.participants
                    if p.user_id != current_user.id and p.user is not None
                ]

                # Real last-message / unread state, same as list_conversations,
                # so reopening an existing DM shows its preview and badge.
                last_msg_q = (
                    select(Message)
                    .where(Message.conversation_id == existing_conv.id)
                    .order_by(desc(Message.created_at))
                    .limit(1)
                )
                last_msg = (await db.execute(last_msg_q)).scalar_one_or_none()

                my_last_read = next(
                    (
                        p.last_read_at
                        for p in existing_conv.participants
                        if p.user_id == current_user.id
                    ),
                    None,
                )
                unread_filters = [
                    Message.conversation_id == existing_conv.id,
                    Message.sender_id != current_user.id,
                    Message.is_deleted == False,  # noqa: E712
                ]
                if my_last_read is not None:
                    unread_filters.append(Message.created_at > my_last_read)
                unread_count = (
                    await db.execute(
                        select(func.count(Message.id)).where(and_(*unread_filters))
                    )
                ).scalar() or 0

                return ConversationOut(
                    id=existing_conv.id,
                    type=existing_conv.type or "direct",
                    name=existing_conv.name,
                    participants=participants_out,
                    last_message=_message_to_out(last_msg) if last_msg else None,
                    unread_count=unread_count,
                    updated_at=existing_conv.updated_at.isoformat() if existing_conv.updated_at else "",
                )

    # Create new conversation
    conv = Conversation(type=conv_type, name=None)
    db.add(conv)
    await db.flush()

    # Add participants
    for uid in all_ids:
        cp = ConversationParticipant(
            conversation_id=conv.id,
            user_id=uid,
            is_admin=(uid == current_user.id),
        )
        db.add(cp)

    await db.commit()

    # Re-load with participants
    conv_q = (
        select(Conversation)
        .where(Conversation.id == conv.id)
        .options(
            selectinload(Conversation.participants).selectinload(
                ConversationParticipant.user
            )
        )
    )
    conv_result = await db.execute(conv_q)
    conv = conv_result.scalar_one()

    participants_out = [
        _user_to_participant(p.user)
        for p in conv.participants
        if p.user_id != current_user.id and p.user is not None
    ]

    return ConversationOut(
        id=conv.id,
        type=conv.type or "direct",
        name=conv.name,
        participants=participants_out,
        last_message=None,
        unread_count=0,
        updated_at=conv.updated_at.isoformat() if conv.updated_at else "",
    )


@router.post("/conversations/{conversation_id}/messages", response_model=MessageOut, status_code=201)
async def send_message(
    conversation_id: int,
    body: SendMessageRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Send a message in a conversation."""

    # Verify membership
    membership_q = select(ConversationParticipant).where(
        and_(
            ConversationParticipant.conversation_id == conversation_id,
            ConversationParticipant.user_id == current_user.id,
        )
    )
    membership_result = await db.execute(membership_q)
    if not membership_result.scalar_one_or_none():
        raise HTTPException(status_code=403, detail="Not a member of this conversation")

    msg = Message(
        conversation_id=conversation_id,
        sender_id=current_user.id,
        content=body.content,
        message_type=body.message_type,
    )
    db.add(msg)

    # Update conversation updated_at
    conv_q = select(Conversation).where(Conversation.id == conversation_id)
    conv_result = await db.execute(conv_q)
    conv = conv_result.scalar_one_or_none()
    if conv:
        conv.updated_at = datetime.utcnow()

    await db.commit()
    await db.refresh(msg)

    return _message_to_out(msg)


@router.post("/conversations/{conversation_id}/read")
async def mark_conversation_read(
    conversation_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Mark a conversation as read (update last_read_at for the current user)."""

    membership_q = select(ConversationParticipant).where(
        and_(
            ConversationParticipant.conversation_id == conversation_id,
            ConversationParticipant.user_id == current_user.id,
        )
    )
    membership_result = await db.execute(membership_q)
    participant = membership_result.scalar_one_or_none()
    if not participant:
        raise HTTPException(status_code=403, detail="Not a member of this conversation")

    participant.last_read_at = datetime.utcnow()
    await db.commit()

    return {"status": "ok"}


@router.delete("/{message_id}")
async def delete_message(
    message_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Soft-delete a message (only the sender can delete their own messages)."""

    msg_q = select(Message).where(Message.id == message_id)
    msg_result = await db.execute(msg_q)
    msg = msg_result.scalar_one_or_none()

    if not msg:
        raise HTTPException(status_code=404, detail="Message not found")

    if msg.sender_id != current_user.id:
        raise HTTPException(status_code=403, detail="Can only delete your own messages")

    if msg.is_deleted:
        raise HTTPException(status_code=400, detail="Message already deleted")

    msg.is_deleted = True
    msg.updated_at = datetime.utcnow()
    await db.commit()

    return {"status": "deleted", "message_id": message_id}
