import sys
import os
import asyncio
sys.path.append(os.getcwd())

# Mock settings if needed, but try real first
from lyo_app.core.ai_resilience import ai_resilience_manager

async def test_streaming():
    print(">>> Initializing AI Manager...")
    # Initialize explicitly
    await ai_resilience_manager.initialize()
    
    # Ensure we use Gemini
    print(">>> Force referencing Gemini model")
    # messages
    messages = [{"role": "user", "content": "Count from 1 to 10 slowly."}]
    
    print(">>> Starting Stream Test...")
    start_time = asyncio.get_event_loop().time()
    first_chunk_time = None
    chunk_count = 0
    
    try:
        # Use a specific provider order to force internal _stream_gemini
        async for chunk in ai_resilience_manager.stream_chat_completion(
            messages, 
            provider_order=["gemini-2.0-flash"]
        ):
            chunk_count += 1
            if not first_chunk_time:
                first_chunk_time = asyncio.get_event_loop().time()
                latency = first_chunk_time - start_time
                print(f"\n>>> FIRST CHUNK RECEIVED in {latency:.4f}s")
                print(f">>> First Chunk Content: {chunk!r}")
            print(chunk, end="|", flush=True)
            
        print("\n\n>>> Stream finished.")
        print(f">>> Total Chunks: {chunk_count}")
        
        if chunk_count > 1 and first_chunk_time:
            print(">>> SUCCESS: Streaming appears to be working (multiple chunks received).")
        else:
            print(">>> FAILURE: Streamed as single chunk or empty.")

    except Exception as e:
        print(f"\n>>> ERROR: {e}")
        import traceback
        traceback.print_exc()
    finally:
        await ai_resilience_manager.close()

if __name__ == "__main__":
    asyncio.run(test_streaming())
