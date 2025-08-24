"""
Database models for educational resources
"""
from sqlalchemy import Column, Integer, String, Text, DateTime, Boolean, JSON, Enum, ForeignKey
from sqlalchemy.orm import relationship
from sqlalchemy.ext.hybrid import hybrid_property
from enum import Enum as PyEnum
from datetime import datetime
from lyo_app.core.database import Base

class ResourceType(PyEnum):
    EBOOK = "ebook"
    VIDEO = "video"
    PODCAST = "podcast"
    COURSE = "course"
    ARTICLE = "article"
    DOCUMENT = "document"

class ResourceProvider(PyEnum):
    YOUTUBE = "youtube"
    KHAN_ACADEMY = "khan_academy"
    MIT_OCW = "mit_ocw"
    COURSERA = "coursera"
    EDX = "edx"
    INTERNET_ARCHIVE = "internet_archive"
    PROJECT_GUTENBERG = "project_gutenberg"
    OPEN_LIBRARY = "open_library"
    GOOGLE_BOOKS = "google_books"
    OPENSTAX = "openstax"
    SPOTIFY = "spotify"
    TED = "ted"
    VIMEO = "vimeo"
    LISTEN_NOTES = "listen_notes"
    CUSTOM = "custom"

class EducationalResource(Base):
    """Model for storing educational resources from various APIs"""
    __tablename__ = "educational_resources"
    
    id = Column(Integer, primary_key=True, index=True)
    
    # Basic Information
    title = Column(String(500), nullable=False, index=True)
    description = Column(Text)
    author = Column(String(200))
    publisher = Column(String(200))
    
    # Resource Classification
    resource_type = Column(Enum(ResourceType), nullable=False, index=True)
    provider = Column(Enum(ResourceProvider), nullable=False, index=True)
    subject_area = Column(String(100), index=True)  # Math, Science, History, etc.
    difficulty_level = Column(String(50))  # Beginner, Intermediate, Advanced
    
    # External Links and IDs
    external_id = Column(String(200), index=True)  # Provider's internal ID
    external_url = Column(String(1000), nullable=False)
    thumbnail_url = Column(String(1000))
    download_url = Column(String(1000))
    
    # Content Metadata
    duration_minutes = Column(Integer)  # For videos/podcasts
    page_count = Column(Integer)  # For books/documents
    language = Column(String(10), default='en')
    isbn = Column(String(20))  # For books
    
    # Quality and Curation
    quality_score = Column(Integer, default=0)  # 0-100 quality rating
    is_curated = Column(Boolean, default=False)
    is_active = Column(Boolean, default=True)
    
    # API Response Storage
    raw_api_data = Column(JSON)  # Store original API response
    
    # Timestamps
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    last_verified = Column(DateTime)  # When link was last checked
    
    # Relationships
    tags = relationship("ResourceTag", back_populates="resource")
    course_resources = relationship("CourseResource", back_populates="resource")
    
    @hybrid_property
    def is_available(self):
        """Check if resource is still available (not broken link)"""
        return self.is_active and self.last_verified
    
    def __repr__(self):
        return f"<EducationalResource(title='{self.title}', type='{self.resource_type}')>"

class ResourceTag(Base):
    """Tags for categorizing resources"""
    __tablename__ = "resource_tags"
    
    id = Column(Integer, primary_key=True)
    resource_id = Column(Integer, ForeignKey("educational_resources.id"))
    tag = Column(String(50), index=True)
    
    resource = relationship("EducationalResource", back_populates="tags")

class CourseResource(Base):
    """Junction table linking courses with educational resources"""
    __tablename__ = "course_resources"
    
    id = Column(Integer, primary_key=True)
    course_id = Column(Integer, ForeignKey("courses.id"))
    resource_id = Column(Integer, ForeignKey("educational_resources.id"))
    resource_order = Column(Integer, default=0)
    is_required = Column(Boolean, default=False)
    notes = Column(Text)  # AI curator notes about why this resource was selected
    
    # Note: Course relationship will be established when courses model is available
    resource = relationship("EducationalResource", back_populates="course_resources")

class ResourceCollection(Base):
    """Curated collections of resources"""
    __tablename__ = "resource_collections"
    
    id = Column(Integer, primary_key=True)
    name = Column(String(200), nullable=False)
    description = Column(Text)
    created_by = Column(String(100))  # AI or user ID
    is_public = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.utcnow)
