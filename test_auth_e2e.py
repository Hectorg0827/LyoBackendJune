import asyncio
import json
import uuid
import sys
from fastapi.testclient import TestClient

# Try to import the main app
try:
    from lyo_app.main import app
except ImportError:
    try:
        from lyo_app.enterprise_main import app
    except ImportError:
        print("Could not import app")
        sys.exit(1)

client = TestClient(app)

def run_tests():
    print("Testing End-to-End Auth flow...")
    test_email = f"test_{uuid.uuid4().hex[:8]}@example.com"
    test_password = "SecurePassword123!"
    
    # 1. Register
    print(f"\n1. Registering new user: {test_email}")
    reg_response = client.post("/api/v1/auth/register", json={
        "email": test_email,
        "password": test_password,
        "full_name": "Test User",
        "username": test_email.split('@')[0]
    })
    print(f"Register Status: {reg_response.status_code}")
    if reg_response.status_code not in (200, 201):
        print(f"Register Error: {reg_response.text}")
        # if registration fails due to missing route, maybe try /auth/register
        reg_response = client.post("/auth/register", json={
            "email": test_email,
            "password": test_password,
            "full_name": "Test User",
            "username": test_email.split('@')[0]
        })
        print(f"Fallback Register Status (/auth/register): {reg_response.status_code}")

    if reg_response.status_code in (200, 201):
        print(f"Register Response JSON: {json.dumps(reg_response.json(), indent=2)}")

    # 2. Login
    print(f"\n2. Logging in as: {test_email}")
    login_response = client.post("/api/v1/auth/login", json={
        "email": test_email,
        "password": test_password
    })
    print(f"Login Status: {login_response.status_code}")
    if login_response.status_code not in (200, 201):
        login_response = client.post("/auth/login", json={
            "email": test_email,
            "password": test_password
        })
        print(f"Fallback Login Status (/auth/login): {login_response.status_code}")
        
    if login_response.status_code in (200, 201):
        print(f"Login Response JSON: {json.dumps(login_response.json(), indent=2)}")

if __name__ == "__main__":
    run_tests()
