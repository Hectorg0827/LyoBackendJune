from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from lyo_app.core.database import get_db
from lyo_app.models.notebook import NotebookNote
from pydantic import BaseModel
from typing import List, Optional
import datetime
from sqlalchemy import select

router = APIRouter()

class NoteCreate(BaseModel):
    user_id: str
    title: Optional[str] = None
    text: str
    source_context: Optional[str] = None
    tags: Optional[List[str]] = []
    color: Optional[str] = "#FBBF24"

class NoteResponse(BaseModel):
    id: str
    user_id: str
    title: Optional[str]
    text: str
    source_context: Optional[str]
    tags: Optional[List[str]]
    color: Optional[str]
    created_at: datetime.datetime
    updated_at: datetime.datetime

    class Config:
        from_attributes = True

@router.post("/", response_model=NoteResponse)
async def create_note(note: NoteCreate, db: AsyncSession = Depends(get_db)):
    db_note = NotebookNote(**note.model_dump())
    db.add(db_note)
    await db.commit()
    await db.refresh(db_note)
    return db_note

@router.get("/{user_id}", response_model=List[NoteResponse])
async def get_notes(user_id: str, db: AsyncSession = Depends(get_db)):
    stmt = select(NotebookNote).filter(NotebookNote.user_id == user_id).order_by(NotebookNote.created_at.desc())
    result = await db.execute(stmt)
    notes = result.scalars().all()
    return notes

@router.delete("/{note_id}")
async def delete_note(note_id: str, db: AsyncSession = Depends(get_db)):
    stmt = select(NotebookNote).filter(NotebookNote.id == note_id)
    result = await db.execute(stmt)
    note = result.scalar_one_or_none()
    if not note:
        raise HTTPException(status_code=404, detail="Note not found")
    await db.delete(note)
    await db.commit()
    return {"status": "success"}
