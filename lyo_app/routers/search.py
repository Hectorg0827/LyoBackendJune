from fastapi import APIRouter
router = APIRouter(tags=["search"])
@router.get("/search")
async def search(q:str="", type:str="posts"): 
    return {"query":q,"type":type,"results":[{"id":"p3","why":["keyword","semantic"]}]}
@router.get("/explore/trending")
async def trending(): return [{"id":"p_hot"}]
