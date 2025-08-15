from fastapi import APIRouter
router = APIRouter(tags=["stories"])
@router.post("/stories")
async def create(): return {"storyId":"s1"}
@router.get("/stories/reel")
async def reel(): return [{"user":{"id":"u1"},"items":[{"id":"s1"}]}]
@router.post("/stories/{story_id}/view")
async def view(story_id:str): return {"ok":True}
