from fastapi import APIRouter
router = APIRouter(tags=["notifications"])
@router.get("/notifications")
async def list_notifs(): return [{"id":"n1","type":"comment","postId":"p1"}]
