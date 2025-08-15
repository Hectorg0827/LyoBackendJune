from fastapi import APIRouter
router = APIRouter(tags=["practice"])
@router.post("/practice/generate")
async def gen(): return [{"id":"q1","type":"mcq","stem":"2x=10?"}]
@router.post("/practice/result")
async def result(): return {"score":1.0,"weak":["fractions"]}
