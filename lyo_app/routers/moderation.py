from fastapi import APIRouter
router = APIRouter(tags=["moderation"])
@router.post("/moderation/report")
async def report(): return {"ok":True,"status":"queued"}
