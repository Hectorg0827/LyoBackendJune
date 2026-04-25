"""Check courses and lessons using raw SQL."""
import asyncio
from sqlalchemy import text
from lyo_app.core.database import AsyncSessionLocal
# Import all models to register them with SQLAlchemy
import lyo_app.auth.models
import lyo_app.learning.models

async def check():
    async with AsyncSessionLocal() as db:
        r = await db.execute(text("SELECT count(*) FROM courses"))
        print(f"Courses: {r.scalar()}")
        r = await db.execute(text("SELECT id, title, topic FROM courses ORDER BY id LIMIT 5"))
        for row in r.all():
            print(f"  Course {row[0]}: {row[1]} (topic: {row[2]})")
            lr = await db.execute(text(f"SELECT count(*) FROM lessons WHERE course_id = {row[0]}"))
            l_count = lr.scalar()
            print(f"    Lessons: {l_count}")
            if l_count > 0:
                lr2 = await db.execute(text(
                    f"SELECT order_index, title, content_type FROM lessons WHERE course_id = {row[0]} ORDER BY order_index LIMIT 5"
                ))
                for l in lr2.all():
                    print(f"      L{l[0]}: {l[1]} ({l[2]})")

asyncio.run(check())
