"""
Stack Routes for learning stack items API.
"""

from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.ext.asyncio import AsyncSession
from pydantic import BaseModel, Field
from datetime import datetime

from lyo_app.core.database import get_db
from lyo_app.auth.routes import get_current_user
from lyo_app.models.enhanced import User
from lyo_app.stack import crud
from lyo_app.stack.models import StackItemType, StackItemStatus


router = APIRouter(tags=["Stack"])


# Pydantic Schemas
class StackItemCreate(BaseModel):
    """Schema for creating a stack item."""
    title: str = Field(..., min_length=1, max_length=255)
    description: Optional[str] = None
    item_type: str = Field(default="topic")
    content_id: Optional[str] = None
    content_type: Optional[str] = None
    priority: int = Field(default=0, ge=0, le=100)
    extra_data: Optional[dict] = None


class StackItemUpdate(BaseModel):
    """Schema for updating a stack item."""
    title: Optional[str] = Field(None, min_length=1, max_length=255)
    description: Optional[str] = None
    status: Optional[str] = None
    progress: Optional[float] = Field(None, ge=0.0, le=1.0)
    priority: Optional[int] = Field(None, ge=0, le=100)


class StackItemResponse(BaseModel):
    """Schema for stack item response."""
    id: int
    user_id: int
    title: str
    description: Optional[str] = None
    item_type: str
    status: str
    progress: float
    priority: int
    content_id: Optional[str] = None
    content_type: Optional[str] = None
    extra_data: Optional[dict] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

    class Config:
        from_attributes = True


class StackItemListResponse(BaseModel):
    """Schema for stack items list response."""
    items: List[StackItemResponse]
    total: int
    limit: int
    offset: int


@router.get("/items", response_model=StackItemListResponse)
async def get_stack_items(
    status: Optional[str] = Query(None, description="Filter by status"),
    item_type: Optional[str] = Query(None, description="Filter by item type"),
    limit: int = Query(50, ge=1, le=100),
    offset: int = Query(0, ge=0),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Get all stack items for the current user."""
    # Convert string to enum if provided
    status_enum = None
    type_enum = None
    
    if status:
        try:
            status_enum = StackItemStatus(status)
        except ValueError:
            pass
    
    if item_type:
        try:
            type_enum = StackItemType(item_type)
        except ValueError:
            pass
    
    items = await crud.get_user_stack_items(
        db=db,
        user_id=current_user.id,
        status=status_enum,
        item_type=type_enum,
        limit=limit,
        offset=offset
    )
    
    return StackItemListResponse(
        items=[StackItemResponse.model_validate(item) for item in items],
        total=len(items),
        limit=limit,
        offset=offset
    )


@router.post("/items", response_model=StackItemResponse, status_code=status.HTTP_201_CREATED)
async def create_stack_item(
    item: StackItemCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Create a new stack item for the current user."""
    # Convert string to enum
    try:
        item_type_enum = StackItemType(item.item_type)
    except ValueError:
        item_type_enum = StackItemType.TOPIC
    
    new_item = await crud.create_stack_item(
        db=db,
        user_id=current_user.id,
        title=item.title,
        item_type=item_type_enum,
        description=item.description,
        content_id=item.content_id,
        content_type=item.content_type,
        priority=item.priority,
        extra_data=item.extra_data
    )
    
    return StackItemResponse.model_validate(new_item)


@router.get("/items/{item_id}", response_model=StackItemResponse)
async def get_stack_item(
    item_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Get a specific stack item by ID."""
    item = await crud.get_stack_item(db=db, item_id=item_id)
    
    if not item:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Stack item not found"
        )
    
    if item.user_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Not authorized to access this item"
        )
    
    return StackItemResponse.model_validate(item)


@router.put("/items/{item_id}", response_model=StackItemResponse)
async def update_stack_item(
    item_id: int,
    item_update: StackItemUpdate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Update a stack item."""
    item = await crud.get_stack_item(db=db, item_id=item_id)
    
    if not item:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Stack item not found"
        )
    
    if item.user_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Not authorized to update this item"
        )
    
    # Update status if provided
    if item_update.status:
        try:
            status_enum = StackItemStatus(item_update.status)
            await crud.update_stack_item_status(db=db, item_id=item_id, status=status_enum)
        except ValueError:
            pass
    
    # Update progress if provided
    if item_update.progress is not None:
        await crud.update_stack_item_progress(db=db, item_id=item_id, progress=item_update.progress)
    
    # Refresh and return
    updated_item = await crud.get_stack_item(db=db, item_id=item_id)
    return StackItemResponse.model_validate(updated_item)


@router.delete("/items/{item_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_stack_item(
    item_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Delete a stack item."""
    item = await crud.get_stack_item(db=db, item_id=item_id)
    
    if not item:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Stack item not found"
        )
    
    if item.user_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Not authorized to delete this item"
        )
    
    await crud.delete_stack_item(db=db, item_id=item_id)
    return None
