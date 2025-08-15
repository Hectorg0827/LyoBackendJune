from fastapi import APIRouter
router = APIRouter(tags=["admin"])
@router.get("/admin/moderation/queue")
async def queue(): return [{"id":"rep1","target":"p1"}]
@router.post("/admin/moderation/{report_id}/action")
async def action(report_id:str): return {"ok":True}
@router.get("/admin/ranker/inspect")
async def inspect(userId:str="u1"): return {"userId":userId,"items":[{"id":"p2","features":{"recency":0.8}}]}
@router.post("/admin/reindex-embeddings")
async def reindex(scope:str="posts"): return {"ok":True,"scope":scope}
