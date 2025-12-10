"""
Stack CRUD operations for learning stack items.
"""

from typing import Optional, List
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_
from sqlalchemy.orm import selectinload

from lyo_app.stack.models import StackItem, StackItemType, StackItemStatus


async def create_stack_item(
    db: AsyncSession,
    user_id: int,
    title: str,
    item_type: StackItemType = StackItemType.TOPIC,
    description: Optional[str] = None,
    content_id: Optional[str] = None,
    content_type: Optional[str] = None,
    priority: int = 0,
    extra_data: Optional[dict] = None
) -> StackItem:
    """Create a new stack item for a user."""
    item = StackItem(
        user_id=user_id,
        title=title,
        item_type=item_type.value if isinstance(item_type, StackItemType) else item_type,
        description=description,
        content_id=content_id,
        content_type=content_type,
        priority=priority,
        extra_data=extra_data or {}
    )
    db.add(item)
    await db.commit()
    await db.refresh(item)
    return item


async def get_stack_item(db: AsyncSession, item_id: int) -> Optional[StackItem]:
    """Get a stack item by ID."""
    result = await db.execute(
        select(StackItem).where(StackItem.id == item_id)
    )
    return result.scalar_one_or_none()


async def get_user_stack_items(
    db: AsyncSession,
    user_id: int,
    status: Optional[StackItemStatus] = None,
    item_type: Optional[StackItemType] = None,
    limit: int = 50,
    offset: int = 0
) -> List[StackItem]:
    """Get all stack items for a user with optional filters."""
    query = select(StackItem).where(StackItem.user_id == user_id)
    
    if status:
        query = query.where(StackItem.status == status.value)
    if item_type:
        query = query.where(StackItem.item_type == item_type.value)
    
    query = query.order_by(StackItem.priority.desc(), StackItem.created_at.desc())
    query = query.limit(limit).offset(offset)
    
    result = await db.execute(query)
    return result.scalars().all()


async def update_stack_item_status(
    db: AsyncSession,
    item_id: int,
    status: StackItemStatus
) -> Optional[StackItem]:
    """Update the status of a stack item."""
    item = await get_stack_item(db, item_id)
    if item:
        item.status = status.value
        await db.commit()
        await db.refresh(item)
    return item


async def update_stack_item_progress(
    db: AsyncSession,
    item_id: int,
    progress: float
) -> Optional[StackItem]:
    """Update the progress of a stack item."""
    item = await get_stack_item(db, item_id)
    if item:
        item.progress = max(0.0, min(1.0, progress))
        if item.progress >= 1.0:
            item.status = StackItemStatus.COMPLETED.value
        elif item.progress > 0:
            item.status = StackItemStatus.IN_PROGRESS.value
        await db.commit()
        await db.refresh(item)
    return item


async def delete_stack_item(db: AsyncSession, item_id: int) -> bool:
    """Delete a stack item."""
    item = await get_stack_item(db, item_id)
    if item:
        await db.delete(item)
        await db.commit()
        return True
    return False
