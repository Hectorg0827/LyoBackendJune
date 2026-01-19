#!/usr/bin/env python3
"""Test the presigned URL endpoints on production"""
import requests
import json
import time

BASE_URL = 'https://lyo-backend-830162750094.us-central1.run.app'

def main():
    print(f"Testing against: {BASE_URL}")
    
    unique = str(int(time.time()))
    email = f'cliptest{unique}@test.com'
    username = f'cliptest{unique}'
    
    print(f"\n1. Registering user {email}...")
    r = requests.post(f'{BASE_URL}/auth/register', json={
        'email': email,
        'username': username, 
        'password': 'TestTest123!',
        'confirm_password': 'TestTest123!',
        'first_name': 'Clip',
        'last_name': 'Test'
    }, timeout=30)
    print(f"   Status: {r.status_code}")
    data = r.json()
    token = data.get('access_token')
    
    if not token:
        print(f"   Error: {data}")
        return
        
    print(f"   Token: {token[:50]}...")
    
    headers = {'Authorization': f'Bearer {token}'}
    
    # Test presigned URL endpoint (iOS alias)
    print("\n2. Testing /api/v1/uploads/presigned-url...")
    r = requests.post(f'{BASE_URL}/api/v1/uploads/presigned-url', 
                      json={'filename': 'test.mp4', 'content_type': 'video/mp4', 'folder': 'clips'},
                      headers=headers, timeout=30)
    print(f"   Status: {r.status_code}")
    resp_json = r.json()
    print(f"   Response: {json.dumps(resp_json, indent=2)}")
    
    # Check if we got a presigned URL
    if 'upload_url' in resp_json:
        print("   ✅ SUCCESS: Got presigned upload URL!")
    elif 'error' in resp_json and 'No cloud storage configured' in str(resp_json):
        print("   ⚠️ Cloud storage not configured on production")
    else:
        print("   ❌ Unexpected response")
    
    # Test storage endpoint (main)
    print("\n3. Testing /api/v1/storage/presigned-url...")
    r = requests.post(f'{BASE_URL}/api/v1/storage/presigned-url',
                      json={'filename': 'test2.mp4', 'content_type': 'video/mp4', 'folder': 'clips'},
                      headers=headers, timeout=30)
    print(f"   Status: {r.status_code}")
    resp_json = r.json()
    print(f"   Response: {json.dumps(resp_json, indent=2)}")
    
    if 'upload_url' in resp_json:
        print("   ✅ SUCCESS: Got presigned upload URL!")
    elif 'error' in resp_json and 'No cloud storage configured' in str(resp_json):
        print("   ⚠️ Cloud storage not configured on production")
    else:
        print("   ❌ Unexpected response")

if __name__ == '__main__':
    main()
