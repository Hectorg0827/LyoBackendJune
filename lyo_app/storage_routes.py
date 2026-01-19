"""
Storage Routes Module

Re-exports the enhanced storage router and provides alias routes for iOS compatibility.
"""

from fastapi import APIRouter

# Import the main storage router
from lyo_app.storage.enhanced_routes import router as storage_router

# Create the main router that will be exported
router = APIRouter()

# Include the enhanced storage router (which is at /api/v1/storage)
router.include_router(storage_router)

# Create an alias router for iOS compatibility
# iOS CloudStorageService expects: /api/v1/uploads/presigned-url
uploads_router = APIRouter(prefix="/api/v1/uploads", tags=["Uploads (iOS Compat)"])

# Re-export the presigned-url endpoint under /api/v1/uploads for iOS compatibility
from lyo_app.storage.enhanced_routes import get_presigned_url, PresignedURLRequest, PresignedURLResponse
from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession
from lyo_app.core.database import get_db
from lyo_app.auth.dependencies import get_current_user
from lyo_app.models.enhanced import User

@uploads_router.post("/presigned-url", response_model=PresignedURLResponse)
async def uploads_presigned_url(
    request: PresignedURLRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    iOS-compatible endpoint for presigned URL generation.
    
    This is an alias for /api/v1/storage/presigned-url to support the iOS
    CloudStorageService which expects /api/v1/uploads/presigned-url.
    """
    return await get_presigned_url(request, db, current_user)

# Include the uploads router
router.include_router(uploads_router)
