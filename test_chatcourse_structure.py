import asyncio
from lyo_app.core.database import AsyncSessionLocal
from lyo_app.chat.models import ChatCourse
from sqlalchemy import select

async def main():
    async with AsyncSessionLocal() as db:
        result = await db.execute(select(ChatCourse.modules).where(ChatCourse.id == '8281d156-714d-4114-8604-7d76e80e5018'))
        row = result.scalar_one_or_none()
        print(row)

asyncio.run(main())
