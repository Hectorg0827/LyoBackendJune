"""Check what courses and lessons exist in the database."""
import asyncio
from sqlalchemy import select, func
from lyo_app.core.database import AsyncSessionLocal
from lyo_app.learning.models import Course, Lesson

async def check():
    async with AsyncSessionLocal() as db:
        r = await db.execute(select(func.count(Course.id)))
        c_count = r.scalar()
        print(f"Courses: {c_count}")
        r = await db.execute(select(Course.id, Course.title, Course.topic).limit(5))
        for row in r.all():
            print(f"  Course {row.id}: {row.title} (topic: {row.topic})")
            lr = await db.execute(select(func.count(Lesson.id)).where(Lesson.course_id == row.id))
            l_count = lr.scalar()
            print(f"    Lessons: {l_count}")
            if l_count > 0:
                lr2 = await db.execute(
                    select(Lesson.order_index, Lesson.title, Lesson.content_type)
                    .where(Lesson.course_id == row.id)
                    .order_by(Lesson.order_index)
                    .limit(5)
                )
                for l in lr2.all():
                    print(f"      L{l.order_index}: {l.title} ({l.content_type})")

asyncio.run(check())
