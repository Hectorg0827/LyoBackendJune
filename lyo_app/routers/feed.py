from fastapi import APIRouter
router = APIRouter(tags=["feed"])
@router.get("/feed/following")
async def following(): return [{"post":{"id":"p1","text":"hello"},"rankScore":0.1,"reason":["follow"]}]
@router.get("/feed/for-you")
async def for_you():   return [{"post":{"id":"p2","text":"welcome"},"rankScore":0.9,"reason":["topic:math","velocity"]}]
