import asyncio
from lyo_app.auth.models import User
print("User columns:", [c.name for c in User.__table__.columns])
print("User dict:", dir(User))
