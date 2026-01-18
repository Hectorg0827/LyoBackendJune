import asyncio
import aiosqlite

async def test_connection():
    try:
        print("Opening database connection...")
        async with aiosqlite.connect("./lyo_app_dev.db") as db:
            print("Executing PRAGMA... ")
            async with db.execute("PRAGMA user_version") as cursor:
                result = await cursor.fetchone()
                print(f"User version: {result}")
        print("Connection test successful!")
    except Exception as e:
        print(f"Connection test failed: {e}")

if __name__ == "__main__":
    asyncio.run(test_connection())
