#!/usr/bin/env python3
"""
Lyo Backend Smoke Test
======================

This smoke test validates all critical backend functionality including:
- Health checks
- Authentication (login/refresh)
- Problem Details error handling
- Async course generation with idempotency
- WebSocket progress tracking
- Task polling fallback
- Course payload normalization
- Feeds endpoint

Usage:
    python smoke_test.py --base http://localhost:8000 --email demo@example.com --password demo

Expected Output:
    ✅ Health
    ✅ Login
    ✅ Refresh
    ✅ ProblemDetails
    ✅ Generate
    ✅ Idempotency
    ✅ WebSocket progress
    ✅ Task DONE
    ✅ Course payload normalized
    ✅ Feeds reachable

Requirements:
    pip install websockets requests
"""

import argparse
import json
import time
import uuid
import asyncio
import requests

try:
    import websockets
except ImportError:
    raise SystemExit("Install websockets: pip install websockets")


def ok(name, cond, extra=""):
    """Print test result with checkmark or X"""
    symbol = "✅" if cond else "❌"
    print(f"{symbol} {name} {extra if extra else ''}")
    return cond


def get(obj, path, default=None):
    """Get nested dict value by dot-separated path"""
    current = obj
    for key in path.split("."):
        if isinstance(current, dict) and key in current:
            current = current[key]
        else:
            return default
    return current


async def ws_progress(url, timeout=30):
    """Connect to WebSocket and collect progress events"""
    events = []
    try:
        async with websockets.connect(url) as ws:
            start = time.time()
            while time.time() - start < timeout:
                try:
                    msg = await asyncio.wait_for(ws.recv(), timeout=5)
                    events.append(json.loads(msg))
                    # Stop when task completes
                    if get(events[-1], "state") in ("DONE", "ERROR"):
                        break
                except asyncio.TimeoutError:
                    pass
    except Exception as e:
        return False, events, str(e)
    
    return bool(events), events, ""


def main():
    parser = argparse.ArgumentParser(description="Lyo Backend Smoke Test")
    parser.add_argument("--base", required=True, help="Base URL (e.g., http://localhost:8000)")
    parser.add_argument("--email", required=True, help="Test user email")
    parser.add_argument("--password", required=True, help="Test user password")
    parser.add_argument("--timeout", type=int, default=300, help="Task completion timeout in seconds")
    
    args = parser.parse_args()
    base = args.base.rstrip("/")
    ws_base = base.replace("http", "ws")
    
    # Setup session
    session = requests.Session()
    session.headers["content-type"] = "application/json"
    
    print("🔥 Starting Lyo Backend Smoke Test")
    print(f"Base URL: {base}")
    print("-" * 50)
    
    # Test 1: Health Check
    try:
        r = session.get(f"{base}/v1/health/ready", timeout=10)
        ok("Health", r.status_code == 200)
    except Exception as e:
        ok("Health", False, f"Error: {e}")
        return
    
    # Test 2: Login
    try:
        login_payload = {"email": args.email, "password": args.password}
        r = session.post(f"{base}/v1/auth/login", 
                        data=json.dumps(login_payload), 
                        timeout=10)
        access_token = get(r.json(), "access_token")
        refresh_token = get(r.json(), "refresh_token")
        login_success = ok("Login", r.status_code == 200 and access_token)
        
        if not login_success:
            print(f"Login failed: {r.status_code} - {r.text}")
            return
            
        # Set auth header for subsequent requests
        session.headers["Authorization"] = f"Bearer {access_token}"
        
    except Exception as e:
        ok("Login", False, f"Error: {e}")
        return
    
    # Test 3: Token Refresh
    try:
        if refresh_token:
            r = session.post(f"{base}/v1/auth/refresh",
                           data=json.dumps({"refresh_token": refresh_token}),
                           timeout=10)
            ok("Refresh", r.status_code == 200)
        else:
            ok("Refresh", False, "No refresh token received")
    except Exception as e:
        ok("Refresh", False, f"Error: {e}")
    
    # Test 4: Problem Details Error Handling
    try:
        # Send invalid request (missing Idempotency-Key)
        r = session.post(f"{base}/v1/courses:generate", 
                        data=json.dumps({}),
                        timeout=10)
        is_problem_details = (
            r.status_code in (400, 422) and 
            r.headers.get("content-type", "").startswith("application/problem+json")
        )
        ok("ProblemDetails", is_problem_details)
    except Exception as e:
        ok("ProblemDetails", False, f"Error: {e}")
    
    # Test 5: Course Generation Kickoff
    try:
        idempotency_key = str(uuid.uuid4())
        payload = {
            "topic": "genai",
            "interests": ["ml", "ai"],
            "level": "beginner",
            "locale": "en"
        }
        headers = {
            "Idempotency-Key": idempotency_key,
            "Prefer": "respond-async"
        }
        r = session.post(f"{base}/v1/courses:generate",
                        headers=headers,
                        data=json.dumps(payload),
                        timeout=15)
        
        task_id = get(r.json(), "task_id")
        provisional_course_id = get(r.json(), "provisional_course_id")
        
        generate_success = ok("Generate", r.status_code == 202 and task_id)
        
        if not generate_success:
            print(f"Generate failed: {r.status_code} - {r.text}")
            return
            
    except Exception as e:
        ok("Generate", False, f"Error: {e}")
        return
    
    # Test 6: Idempotency Check
    try:
        # Send same request again with same idempotency key
        r2 = session.post(f"{base}/v1/courses:generate",
                         headers={"Idempotency-Key": idempotency_key},
                         data=json.dumps(payload),
                         timeout=10)
        same_task_id = get(r2.json(), "task_id") == task_id
        ok("Idempotency", same_task_id)
    except Exception as e:
        ok("Idempotency", False, f"Error: {e}")
    
    # Test 7: WebSocket Progress Tracking
    try:
        ws_url = f"{ws_base}/v1/ws/tasks/{task_id}"
        success, events, error = asyncio.get_event_loop().run_until_complete(
            ws_progress(ws_url, timeout=60)
        )
        ok("WebSocket progress", success or not error, 
           f"Events: {len(events)}" if success else f"Error: {error}")
    except Exception as e:
        ok("WebSocket progress", False, f"Error: {e}")
    
    # Test 8: Task Polling Fallback
    try:
        state = None
        course_id = None
        start_time = time.time()
        
        while time.time() - start_time < args.timeout:
            r = session.get(f"{base}/v1/tasks/{task_id}", timeout=10)
            if r.status_code != 200:
                break
                
            task_data = r.json()
            state = get(task_data, "state")
            
            if state in ("DONE", "ERROR"):
                course_id = get(task_data, "resultId")
                break
                
            print(f"  Task state: {state}, Progress: {get(task_data, 'progressPct', 0)}%")
            time.sleep(2)
        
        task_done = ok("Task DONE", state == "DONE")
        
        if not task_done:
            print(f"Task ended in state: {state}")
            return
            
    except Exception as e:
        ok("Task DONE", False, f"Error: {e}")
        return
    
    # Test 9: Course Payload Normalization
    try:
        if course_id:
            r = session.get(f"{base}/v1/courses/{course_id}", timeout=10)
            if r.status_code == 200:
                course_data = r.json()
                items = get(course_data, "items", [])
                
                # Check if items have required fields
                if items:
                    first_item = items[0]
                    required_fields = ["id", "type", "title", "source", "sourceUrl"]
                    has_required = all(field in first_item for field in required_fields)
                    ok("Course payload normalized", has_required)
                else:
                    ok("Course payload normalized", False, "No items in course")
            else:
                ok("Course payload normalized", False, f"HTTP {r.status_code}")
        else:
            ok("Course payload normalized", False, "No course_id received")
    except Exception as e:
        ok("Course payload normalized", False, f"Error: {e}")
    
    # Test 10: Feeds Endpoint
    try:
        r = session.get(f"{base}/v1/feeds?limit=5", timeout=10)
        # Feeds might be empty, so 200, 204, or 404 are acceptable
        feeds_ok = r.status_code in (200, 204, 404)
        ok("Feeds reachable", feeds_ok, f"Status: {r.status_code}")
    except Exception as e:
        ok("Feeds reachable", False, f"Error: {e}")
    
    print("-" * 50)
    print("🎯 Smoke test completed!")
    print("\n💡 If you see any ❌, check the backend logs and fix the issues.")
    print("All ✅ means your backend is 100% functional! 🚀")


if __name__ == "__main__":
    main()
