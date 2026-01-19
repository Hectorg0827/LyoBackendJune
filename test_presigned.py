#!/usr/bin/env python3
"""Test the presigned URL endpoints"""
import requests
import json

import time

BASE_URL = 'http://localhost:8000'

def main():
    # Use a unique email each time
    unique = str(int(time.time()))
    email = f'cliptest{unique}@test.com'
    username = f'cliptest{unique}'
    
    print(f"1. Registering user {email}...")
    r = requests.post(f'{BASE_URL}/auth/register', json={
        'email': email,
        'username': username, 
        'password': 'TestTest123!',
        'confirm_password': 'TestTest123!',
        'first_name': 'Clip',
        'last_name': 'Test'
    })
    data = r.json()
    token = data.get('access_token')
    
    print(f"   Status: {r.status_code}")
    if not token:
        print(f"   Error: {data}")
        return
        
    print(f"   Token: {token[:50]}...")

    # Test presigned URL endpoint (iOS alias)
    print("\n2. Testing /api/v1/uploads/presigned-url endpoint (iOS)...")
    headers = {'Authorization': f'Bearer {token}'}
    r = requests.post(f'{BASE_URL}/api/v1/uploads/presigned-url', 
                      json={'filename': 'test.mp4', 'content_type': 'video/mp4', 'folder': 'clips'},
                      headers=headers)
    print(f"   Status: {r.status_code}")
    print(f"   Response: {json.dumps(r.json(), indent=2)}")

    # Also test the /api/v1/storage/presigned-url endpoint
    print("\n3. Testing /api/v1/storage/presigned-url endpoint...")
    r = requests.post(f'{BASE_URL}/api/v1/storage/presigned-url',
                      json={'filename': 'test2.mp4', 'content_type': 'video/mp4', 'folder': 'clips'},
                      headers=headers)
    print(f"   Status: {r.status_code}")
    print(f"   Response: {json.dumps(r.json(), indent=2)}")

if __name__ == '__main__':
    main()
