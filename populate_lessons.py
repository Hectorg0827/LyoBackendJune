"""Populate lessons for course 1001 (Async Python 101)."""
import asyncio
from sqlalchemy import text
from lyo_app.core.database import AsyncSessionLocal

LESSONS = [
    {
        "title": "What is Asynchronous Programming?",
        "description": "Introduction to async concepts, why blocking I/O is a problem, and how async solves it.",
        "content": (
            "Asynchronous programming allows your code to start a long-running operation "
            "and continue doing other work while waiting for it to complete. In traditional "
            "(synchronous) code, when you make a network request or read a file, your program "
            "blocks — it just waits, doing nothing. With async, you can handle thousands of "
            "I/O operations concurrently without threads.\n\n"
            "Key concepts: blocking vs non-blocking, concurrency vs parallelism, the event loop."
        ),
        "content_type": "text",
        "order_index": 0,
    },
    {
        "title": "Python's asyncio Module and the Event Loop",
        "description": "Understanding asyncio, the event loop, and how Python manages async tasks.",
        "content": (
            "Python's asyncio module provides the foundation for writing async code. At its "
            "core is the event loop — a mechanism that continuously checks for completed I/O "
            "operations and runs the appropriate callbacks.\n\n"
            "import asyncio\n\n"
            "async def main():\n"
            "    print('Hello')\n"
            "    await asyncio.sleep(1)\n"
            "    print('World')\n\n"
            "asyncio.run(main())\n\n"
            "The event loop runs your coroutines, switching between them at await points."
        ),
        "content_type": "text",
        "order_index": 1,
    },
    {
        "title": "async and await Keywords",
        "description": "Deep dive into async def, await, and how coroutines work under the hood.",
        "content": (
            "The 'async def' keyword creates a coroutine function. When called, it returns "
            "a coroutine object that must be awaited. The 'await' keyword pauses the coroutine "
            "and yields control back to the event loop.\n\n"
            "Rules:\n"
            "1. You can only use 'await' inside an 'async def' function\n"
            "2. You can only await 'awaitable' objects (coroutines, Tasks, Futures)\n"
            "3. A coroutine does NOT run until it is awaited or scheduled\n\n"
            "Common mistake: calling an async function without await — this creates the "
            "coroutine but never executes it!"
        ),
        "content_type": "text",
        "order_index": 2,
    },
    {
        "title": "Concurrent Tasks with asyncio.gather()",
        "description": "Running multiple async operations concurrently for maximum performance.",
        "content": (
            "asyncio.gather() lets you run multiple coroutines concurrently. This is where "
            "async really shines — instead of waiting for each operation sequentially, you "
            "launch them all at once.\n\n"
            "async def fetch_all():\n"
            "    results = await asyncio.gather(\n"
            "        fetch_user(1),\n"
            "        fetch_user(2),\n"
            "        fetch_user(3),\n"
            "    )\n"
            "    return results  # All three fetched concurrently!\n\n"
            "Also useful: asyncio.create_task() for fire-and-forget tasks, "
            "and asyncio.wait() for more control over completion."
        ),
        "content_type": "text",
        "order_index": 3,
    },
    {
        "title": "Error Handling in Async Code",
        "description": "try/except with async, handling multiple task failures, and timeout patterns.",
        "content": (
            "Error handling in async code works similarly to sync code, but with nuances:\n\n"
            "1. Use try/except around await calls\n"
            "2. asyncio.gather(return_exceptions=True) collects errors without crashing\n"
            "3. asyncio.wait_for() adds timeouts:\n\n"
            "async def fetch_with_timeout():\n"
            "    try:\n"
            "        result = await asyncio.wait_for(slow_operation(), timeout=5.0)\n"
            "    except asyncio.TimeoutError:\n"
            "        print('Operation timed out!')\n\n"
            "4. asyncio.shield() protects a coroutine from cancellation\n"
            "5. TaskGroups (Python 3.11+) provide structured concurrency with proper cleanup."
        ),
        "content_type": "text",
        "order_index": 4,
    },
    {
        "title": "Real-World Async: HTTP Clients and Servers",
        "description": "Building async web applications with aiohttp and FastAPI.",
        "content": (
            "The most common use case for async Python is web I/O. Libraries like aiohttp "
            "and httpx let you make hundreds of HTTP requests concurrently.\n\n"
            "import httpx\n\n"
            "async def fetch_apis():\n"
            "    async with httpx.AsyncClient() as client:\n"
            "        tasks = [client.get(url) for url in urls]\n"
            "        responses = await asyncio.gather(*tasks)\n\n"
            "On the server side, FastAPI is built on async Python:\n\n"
            "@app.get('/users/{user_id}')\n"
            "async def get_user(user_id: int):\n"
            "    user = await db.fetch_user(user_id)\n"
            "    return user\n\n"
            "This handles thousands of concurrent requests with minimal resources."
        ),
        "content_type": "text",
        "order_index": 5,
    },
]

async def populate():
    async with AsyncSessionLocal() as db:
        # Check if lessons already exist
        r = await db.execute(text("SELECT count(*) FROM lessons WHERE course_id = 1001"))
        if r.scalar() > 0:
            print("Lessons already exist for course 1001")
            return

        for lesson in LESSONS:
            await db.execute(text(
                "INSERT INTO lessons (title, description, content, content_type, order_index, course_id, organization_id, is_published, is_preview, created_at, updated_at) "
                "VALUES (:title, :description, :content, :content_type, :order_index, 1001, 1, 1, 0, datetime('now'), datetime('now'))"
            ), lesson)
        await db.commit()
        print(f"Inserted {len(LESSONS)} lessons for course 1001")

        # Verify
        r = await db.execute(text("SELECT order_index, title FROM lessons WHERE course_id = 1001 ORDER BY order_index"))
        for row in r.all():
            print(f"  L{row[0]}: {row[1]}")

asyncio.run(populate())
