from fastapi import APIRouter
router = APIRouter(tags=["planner"])
@router.post("/planner/draft")
async def draft(): return {"id":"plan1","modules":[{"id":"m1","lessons":[{"id":"l1","title":"Variables"}]}]}
@router.post("/planner/attach-content")
async def attach(): return {"ok":True}
