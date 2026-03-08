import asyncio
import json
from lyo_app.ai.nexus.agent import LyoNexusAgent
from lyo_app.ai.nexus.factory import LyoNexusFactory
from lyo_app.ai.nexus.media_worker import LyoNexusMediaWorker

async def run_test():
    print("Starting Nexus Test...")
    
    # Mock LLM output
    test_text = "Here is an explanation of the engine.\n\n<media_req: four_stroke_diagram>\n\nThe first stroke is intake."
    
    async def mock_stream():
        chunk_size = 5
        for i in range(0, len(test_text), chunk_size):
            yield test_text[i:i+chunk_size]
            await asyncio.sleep(0.01)
            
    async def dispatch_update(update_brick):
        print(f"ASYNC UPDATE RECEIVED: {json.dumps(update_brick, indent=2)}")

    nexus_factory = LyoNexusFactory()
    nexus_media = LyoNexusMediaWorker(dispatch_update_callback=dispatch_update)
    nexus_agent = LyoNexusAgent(factory=nexus_factory, media_worker=nexus_media)
    
    print("Piping stream into Nexus...")
    async for brick in nexus_agent.process_stream(mock_stream(), ["a2ui_v1"]):
        print(f"YIELDED BRICK: {json.dumps(brick, indent=2)}")
        
    print("Waiting for async media generation...")
    await asyncio.sleep(3) # Wait for media worker
    print("Done")

if __name__ == "__main__":
    asyncio.run(run_test())
