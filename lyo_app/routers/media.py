from fastapi import APIRouter
router = APIRouter(tags=["media"])
@router.post("/media/presign")
async def presign(): return {"uploadUrl":"https://gcs.demo/upload","assetUrl":"gs://bucket/key","mime":"image/jpeg"}
@router.post("/media/commit")
async def commit(): return {"mediaId":"m_demo","status":"pending"}
