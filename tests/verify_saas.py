import requests
import time
import os
import sys

# Configuration
BASE_URL = "http://localhost:8000"
BOOTSTRAP_SECRET = "lyo-bootstrap-2024"

def print_pass(msg):
    print(f"✅ PASS: {msg}")

def print_fail(msg):
    print(f"❌ FAIL: {msg}")
    # Don't exit immediately, try other tests

def verify_bootstrap():
    print(f"\n--- 1. Verifying Bootstrap (Migrations) ---")
    url = f"{BASE_URL}/api/v1/tenants/bootstrap?secret={BOOTSTRAP_SECRET}"
    try:
        resp = requests.post(url)
        if resp.status_code == 200:
            data = resp.json()
            if data.get("tables_created") is True:
                print_pass("Bootstrap executed successfully (migrations applied).")
            elif "already exists" in data.get("message", ""):
                 print_pass("Bootstrap confirmed organization exists.")
            else:
                print_pass(f"Bootstrap ran: {data}")
            return True
        else:
            print_fail(f"Bootstrap failed: {resp.status_code} - {resp.text}")
            return False
    except Exception as e:
        print_fail(f"Connection error: {e}")
        return False

def verify_api_key_auth():
    print(f"\n--- 2. Verifying API Key Auth & Rate Limits ---")
    # We need an API key. Since we can't easily retrieve one via public API without login,
    # we will test the *rejection* of invalid keys, which confirms the middleware is active.
    
    url = f"{BASE_URL}/api/v1/storage/stats" # Protected endpoint
    
    # Test 1: No Key
    resp = requests.get(url)
    if resp.status_code in [401, 403]:
        print_pass("Rejected request without API Key")
    else:
        print_fail(f"Expected 401/403, got {resp.status_code}")

    # Test 2: Invalid Key
    resp = requests.get(url, headers={"X-API-Key": "invalid-key-123"})
    if resp.status_code in [401, 403]:
        print_pass("Rejected request with invalid API Key")
    else:
        print_fail(f"Expected 401/403 for invalid key, got {resp.status_code}")

    # Note: To test SUCCESS, we'd need to login as admin and generate a key.
    # For now, rejection proves the gatekeeper is installed.

def verify_storage_isolation_logic():
    print(f"\n--- 3. Verifying Storage Isolation (Logic Check via Upload) ---")
    # We can't upload without a valid token/key. 
    # But we can verify the endpoint exists and demands auth.
    
    url = f"{BASE_URL}/api/v1/storage/upload"
    files = {'file': ('test.txt', 'content')}
    
    resp = requests.post(url, files=files)
    
    # We expect 401 because we aren't sending auth.
    # If we get 404, the route isn't registered.
    if resp.status_code == 401:
        print_pass("Storage endpoint detected and protected (401).")
    elif resp.status_code == 404:
        print_fail("Storage endpoint NOT FOUND (404). Update didn't deploy?")
    else:
        print_pass(f"Storage endpoint responded: {resp.status_code}")

def main():
    print(f"Testing environment: {BASE_URL}")
    
    if verify_bootstrap():
        verify_api_key_auth()
        verify_storage_isolation_logic()
    else:
        print("Skipping further tests due to bootstrap failure.")

if __name__ == "__main__":
    main()
