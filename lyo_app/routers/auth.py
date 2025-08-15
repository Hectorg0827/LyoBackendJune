from fastapi import APIRouter
router = APIRouter(tags=["auth"])
@router.post("/auth/login")
async def login(): return {"access":"demo_access","refresh":"demo_refresh"}
@router.post("/auth/refresh")
async def refresh(): return {"access":"demo_access_rotated","refresh":"demo_refresh_rotated"}
@router.get("/auth/jwks.json")
async def jwks(): return {"keys":[{"kty":"RSA","kid":"demo","n":"...","e":"AQAB"}]}
