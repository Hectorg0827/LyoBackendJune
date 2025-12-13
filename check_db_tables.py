import asyncio
import logging
import sys
from sqlalchemy import text, inspect
from lyo_app.core.database import engine, Base
from lyo_app.stack.models import StackItem

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

async def check_tables():
    logger.info("Checking database tables...")
    
    async with engine.connect() as conn:
        # Check if stack_items table exists
        result = await conn.execute(text("SELECT to_regclass('public.stack_items');"))
        table_exists = result.scalar()
        
        if table_exists:
            logger.info("Table 'stack_items' EXISTS.")
            
            # Get columns
            # Note: reflection with async engine is a bit tricky, so we'll just query information_schema
            query = text("""
                SELECT column_name, data_type 
                FROM information_schema.columns 
                WHERE table_name = 'stack_items';
            """)
            result = await conn.execute(query)
            columns = result.fetchall()
            logger.info(f"Columns in 'stack_items': {columns}")
            
        else:
            logger.info("Table 'stack_items' DOES NOT EXIST.")
            
            # Try to create it
            logger.info("Attempting to create tables...")
            await conn.run_sync(Base.metadata.create_all)
            logger.info("create_all executed.")
            
            # Check again
            result = await conn.execute(text("SELECT to_regclass('public.stack_items');"))
            if result.scalar():
                logger.info("Table 'stack_items' created successfully.")
            else:
                logger.error("Failed to create table 'stack_items'.")

if __name__ == "__main__":
    try:
        asyncio.run(check_tables())
    except Exception as e:
        logger.error(f"Error checking tables: {e}")
        sys.exit(1)
