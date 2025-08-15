from fastapi import APIRouter
router = APIRouter(tags=["messaging"])
@router.post("/chats")
async def create_chat(): return {"chatId":"c1"}
@router.get("/chats")
async def list_chats(): return [{"chatId":"c1","last":"hi"}]
@router.get("/chats/{chat_id}/history")
async def history(chat_id:str): return [{"id":"m1","text":"hello"}]
@router.post("/push/register")
async def register_push(): return {"ok":True}
