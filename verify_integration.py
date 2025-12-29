import asyncio
import httpx
import sys
import uuid

BASE_URL = "http://localhost:8000"

async def main():
    async with httpx.AsyncClient(base_url=BASE_URL, timeout=10.0) as client:
        print(f"Checking {BASE_URL}...")
        
        # 1. Health/Root Check (with retry)
        for i in range(12):  # 12 * 5s = 60s
            try:
                print(f"Attempt {i+1}: Checking root...")
                resp = await client.get("/")
                print(f"Root: {resp.status_code}")
                break
            except (httpx.ConnectError, httpx.ReadTimeout):
                print("Server not ready, waiting 5s...")
                await asyncio.sleep(5)
        else:
            print("Server failed to start in 60s!")
            sys.exit(1)

        # 2. Register
        username = f"user_{uuid.uuid4().hex[:8]}"
        email = f"{username}@example.com"
        password = "Password123!"
        
        print(f"Registering {username}...")
        resp = await client.post("/auth/register", json={
            "email": email,
            "username": username,
            "password": password,
            "confirm_password": password,
            "first_name": "Integration",
            "last_name": "Test"
        })
        
        if resp.status_code != 201:
            print(f"Registration Failed: {resp.status_code} {resp.text}")
            sys.exit(1)
        
        user_data = resp.json()
        print(f"Registered user ID: {user_data.get('id')}")
        
        # 3. Login
        print("Logging in...")
        resp = await client.post("/auth/login", json={
            "email": email,
            "password": password
        })
        
        if resp.status_code != 200:
            print(f"Login Failed: {resp.status_code} {resp.text}")
            sys.exit(1)
            
        token_data = resp.json()
        access_token = token_data["access_token"]
        print("Login success, token received.")
        
        # 4. Get Me
        print("Fetching /auth/me...")
        resp = await client.get("/auth/me", headers={
            "Authorization": f"Bearer {access_token}"
        })
        
        if resp.status_code != 200:
            print(f"Get Me Failed: {resp.status_code} {resp.text}")
            sys.exit(1)
            
        me_data = resp.json()
        print(f"Authenticated as: {me_data.get('email')} (ID: {me_data.get('id')})")
        
        print("\n✅ Integration Verified: Auth Flow Works!")

if __name__ == "__main__":
    asyncio.run(main())
