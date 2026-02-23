import os
import json
import requests
import uuid
from dotenv import load_dotenv

load_dotenv()
load_dotenv(".env.production")

RUNWARE_API_KEY = os.getenv("RUNWARE_API_KEY")

def test_runware_sync():
    if not RUNWARE_API_KEY:
        print("API Key not found!")
        return

    print("Testing Runware Integration via REST (Sync)...")

    # Simplest possible payload to test if the API responds
    payload = [
        {
            "taskType": "imageInference",
            "taskUUID": str(uuid.uuid4()), # Must be a valid UUIDv4
            "positivePrompt": "A futuristic city skyline at sunset, cyberpunk style, highly detailed 8k resolution",
            "model": "runware:100@1", # Runware default fast model
            "width": 512,
            "height": 512,
            "numberResults": 1,
            "outputType": "URL",
            "outputFormat": "WEBP",
        }
    ]

    headers = {
        "Authorization": f"Bearer {RUNWARE_API_KEY}",
        "Content-Type": "application/json"
    }

    try:
        response = requests.post(
            "https://api.runware.ai/v1",
            headers=headers,
            json=payload,
            timeout=30 # Increased timeout
        )
        
        print(f"Status: {response.status_code}")
        
        if response.status_code == 200:
            data = response.json()
            print("\nSuccess! Response:")
            print(json.dumps(data, indent=2))
        else:
            print(f"Error: {response.text}")

    except Exception as e:
        print(f"Exception occurred: {e}")

if __name__ == "__main__":
    test_runware_sync()
