from sqlalchemy import Column, String, DateTime, Text, JSON
from lyo_app.core.database import Base
import datetime
import uuid

class NotebookNote(Base):
    __tablename__ = "notebook_notes"
    
    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id = Column(String, nullable=False, index=True)
    title = Column(String, nullable=True)
    text = Column(Text, nullable=False)
    source_context = Column(Text, nullable=True)
    tags = Column(JSON, nullable=True, default=list)
    color = Column(String, default="#FBBF24")
    created_at = Column(DateTime, default=datetime.datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.datetime.utcnow, onupdate=datetime.datetime.utcnow)
