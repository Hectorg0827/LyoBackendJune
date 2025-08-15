from fastapi import APIRouter
router = APIRouter(tags=["tutor"])
@router.post("/tutor/turn")
async def turn(): return [{"type":"Hint","text":"Try isolating x."},{"type":"Explanation","text":"Use inverse operations."}]
@router.get("/tutor/state/{learner_id}")
async def load(learner_id:str): return {"learnerId":learner_id,"state":"demo"}
@router.put("/tutor/state/{learner_id}")
async def save(learner_id:str): return {"ok":True}
