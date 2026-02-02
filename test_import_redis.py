
import sys
import os
sys.path.append(os.getcwd())

print("Starting Redis test...", flush=True)
try:
    print("Importing redis...", flush=True)
    import redis
    print("Imported redis successfully", flush=True)
    
    # Try connecting
    # Need to mimic rate_limiter.py logic for URL
    redis_url = os.getenv("REDIS_URL")
    if not redis_url:
        host = os.getenv("REDIS_HOST")
        port = os.getenv("REDIS_PORT", "6379")
        if host:
            redis_url = f"redis://{host}:{port}/0"
    
    if not redis_url:
        print("No Redis URL found in env, using default localhost", flush=True)
        redis_url = "redis://localhost:6379/0"
        
    print(f"Connecting to {redis_url}...", flush=True)
    client = redis.from_url(redis_url, decode_responses=True)
    print("Client created, pinging...", flush=True)
    client.ping()
    print("Ping successful!", flush=True)

except Exception as e:
    print(f"Redis test failed: {e}", flush=True)
    import traceback
    traceback.print_exc()
