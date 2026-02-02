import requests
import json
import time

BASE_URL = "http://localhost:8000"
API_KEY = "lyo_sk_live_S5ALtW3WDjhF-TAgn767ORCCga4Nx52xBlAkMHg2-TQ"

def headers():
    return {"Content-Type": "application/json", "X-API-Key": API_KEY}

def test_cinematic_hook():
    print("Testing Cinematic Hook...")
    try:
        # 1. Register a temp user (needed for chat usually)
        email = f"cinematic_{int(time.time())}@example.com"
        r_reg = requests.post(f"{BASE_URL}/auth/register", headers=headers(), json={
            "email": email,
            "password": "TestPass123!",
            "confirm_password": "TestPass123!",
            "first_name": "Cine",
            "last_name": "Tezt",
            "username": f"cinetest_{int(time.time())}"
        })
        access_token = r_reg.json().get("access_token")
        if not access_token:
            print("❌ Failed to register temp user")
            print(r_reg.text)
            return

        h = headers()
        h["Authorization"] = f"Bearer {access_token}"

        # 2. Send Cinematic Request
        # Use /api/v1/chat as per existing tests
        url = f"{BASE_URL}/api/v1/chat"
        print(f"POST {url}")
        
        r = requests.post(url, headers=h, json={
            "message": "Give me a cinematic trailer for Time Travel",
            "include_chips": True,
            "include_ctas": True
        })
        
        if r.status_code != 200:
             print(f"❌ Chat failed: {r.status_code}")
             print(r.text)
             return

        data = r.json()
        print("Response received.")
        
        # 3. Verify Lyo Blocks
        lyo_blocks = data.get("lyoBlocks") or data.get("lyo_blocks", [])
        if not lyo_blocks:
             print("❌ No lyo_blocks found in response")
             # Print a snippet of response
             print(str(data)[:500])
             return

        # 4. Find Cinematic Block
        cinematic_block = None
        for block in lyo_blocks:
            # Check presentation_hint
            # Note: The pydantic model might serialize enum to value or name
            hint = block.get("presentation_hint")
            role = block.get("role")
            
            print(f"Block found: role={role}, hint={hint}")
            
            if hint == "cinematic" or hint == "CINEMATIC":
                cinematic_block = block
                break
        
        if cinematic_block:
            print("✅ Found Cinematic Block!")
            print(json.dumps(cinematic_block, indent=2))
        else:
            print("❌ No block with presentation_hint='cinematic' found")
            print("Blocks received:")
            print(json.dumps(lyo_blocks, indent=2))

    except Exception as e:
        print(f"❌ Exception: {e}")

if __name__ == "__main__":
    test_cinematic_hook()
