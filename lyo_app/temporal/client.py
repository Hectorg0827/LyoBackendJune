"""
Temporal Client - Singleton connection to Temporal server

Usage:
    from lyo_app.temporal import get_temporal_client
    
    client = await get_temporal_client()
    await client.start_workflow(...)
"""

import os
import logging
from typing import Optional
from temporalio.client import Client

logger = logging.getLogger(__name__)

_temporal_client: Optional[Client] = None


async def get_temporal_client() -> Client:
    """
    Get or create the Temporal client singleton.
    
    Environment variables:
        TEMPORAL_HOST: Temporal server address (default: localhost:7233)
        TEMPORAL_NAMESPACE: Temporal namespace (default: default)
    """
    global _temporal_client
    
    if _temporal_client is None:
        host = os.getenv("TEMPORAL_HOST", "localhost:7233")
        namespace = os.getenv("TEMPORAL_NAMESPACE", "default")
        
        logger.info(f"Connecting to Temporal at {host}, namespace: {namespace}")
        
        try:
            _temporal_client = await Client.connect(
                host,
                namespace=namespace,
            )
            logger.info("✅ Connected to Temporal server")
        except Exception as e:
            logger.error(f"❌ Failed to connect to Temporal: {e}")
            raise
    
    return _temporal_client


async def close_temporal_client():
    """Close the Temporal client connection."""
    global _temporal_client
    if _temporal_client is not None:
        # Note: Temporal Python SDK doesn't have explicit close, but we clear the ref
        _temporal_client = None
        logger.info("Temporal client connection cleared")


def is_temporal_available() -> bool:
    """Check if Temporal is configured and available."""
    return _temporal_client is not None
