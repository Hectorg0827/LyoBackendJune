import asyncio
from lyo_app.core.database import engine
from lyo_app.community.models import MarketplaceItem

async def main():
    print("Connecting to database...")
    async with engine.begin() as conn:
        print("Creating table marketplace_items...")
        await conn.run_sync(MarketplaceItem.__table__.create, checkfirst=True)
    print("Table created successfully!")

if __name__ == "__main__":
    asyncio.run(main())
