from fastapi import APIRouter
router = APIRouter(tags=["resources"])
@router.get("/resources")
async def resources(): 
    return {"videos":[{"id":"yt1","title":"Intro to Variables"}],
            "articles":[{"id":"art1","title":"Linear Equations 101"}]}
