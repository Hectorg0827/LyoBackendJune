
import asyncio
import websockets
import json
import numpy as np

async def verify_live_intelligence():
    # Use 127.0.0.1 for reliability
    uri = "ws://127.0.0.1:8000/api/v2/chat/test-live-session/audio"
    
    print(f"🔗 Connecting to {uri}...")
    try:
        async with websockets.connect(uri) as websocket:
            print("✅ Connected to Audio WebSocket")
            
            # 1. Generate 3 seconds of "speech" (white noise / sine wave) 
            # and 2 seconds of silence
            sample_rate = 24000
            duration_speech = 3
            duration_silence = 2
            
            t = np.linspace(0, duration_speech, int(sample_rate * duration_speech), endpoint=False)
            audio_speech = (np.sin(2 * np.pi * 440 * t) * 32767).astype(np.int16)
            audio_silence = np.zeros(int(sample_rate * duration_silence), dtype=np.int16)
            
            # Combine
            full_audio = np.concatenate([audio_speech, audio_silence])
            raw_bytes = full_audio.tobytes()
            
            # 2. Stream in small chunks (20ms frames = 960 bytes)
            chunk_size = 960 
            print(f"📤 Streaming {len(raw_bytes)} bytes in {chunk_size} byte chunks...")
            
            for i in range(0, len(raw_bytes), chunk_size):
                chunk = raw_bytes[i:i+chunk_size]
                await websocket.send(chunk)
                await asyncio.sleep(0.02) # Simulate real-time
                
            print("🏁 Finished streaming audio")
            
            # 3. Wait a bit for interim results if Deepgram is configured
            print("⏳ Waiting for backend processing...")
            await asyncio.sleep(5)
            
    except Exception as e:
        print(f"❌ Verification failed: {e}")

if __name__ == "__main__":
    asyncio.run(verify_live_intelligence())
