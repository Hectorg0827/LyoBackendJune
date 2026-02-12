"""
Thorough smoke test for all booking & review endpoints.
Requires: uvicorn running on localhost:8000
"""

import asyncio
import httpx
import sys
import traceback

BASE = "http://localhost:8000"
passed = 0
failed = 0


def ok(label, detail=""):
    global passed
    passed += 1
    extra = f" — {detail}" if detail else ""
    print(f"  ✅ {label}{extra}")


def fail(label, detail=""):
    global failed
    failed += 1
    print(f"  ❌ {label} — {detail}")


async def main():
    global passed, failed
    timeout = httpx.Timeout(30.0, connect=10.0)
    async with httpx.AsyncClient(base_url=BASE, timeout=timeout) as c:

        # ── 0. Health check ───────────────────────────────────────
        print("\n🧪 0. Server reachability")
        try:
            r = await c.get("/docs")
            if r.status_code == 200:
                ok("GET /docs", f"HTTP {r.status_code}")
            else:
                fail("GET /docs", f"HTTP {r.status_code}")
        except Exception as e:
            fail("Server unreachable", str(e))
            print("\n⛔ Cannot continue — server is down.")
            return

        # ── 1. Register + get token ──────────────────────────────
        print("\n🧪 1. Auth — register & get token")
        token = None

        # Try register
        r = await c.post("/api/v1/auth/register", json={
            "email": "smoke_booking@lyo.app",
            "password": "TestPass123!",
            "name": "BookingTester"
        })
        if r.status_code in (200, 201):
            data = r.json()
            token = data.get("access_token")
            ok("Register", f"HTTP {r.status_code}")
        elif r.status_code == 409 or r.status_code == 400:
            ok("Register (already exists)", f"HTTP {r.status_code}")
        else:
            fail("Register", f"HTTP {r.status_code}: {r.text[:200]}")

        # Get token via /token
        if not token:
            r = await c.post("/api/v1/auth/token", data={
                "username": "smoke_booking@lyo.app",
                "password": "TestPass123!"
            })
            if r.status_code == 200:
                token = r.json().get("access_token")
                ok("Token", f"HTTP {r.status_code}")
            else:
                fail("Token", f"HTTP {r.status_code}: {r.text[:200]}")

        if not token:
            # Try alternate login endpoints
            for path in ["/api/v1/auth/login", "/auth/login"]:
                r = await c.post(path, json={
                    "email": "smoke_booking@lyo.app",
                    "password": "TestPass123!"
                })
                if r.status_code == 200:
                    token = r.json().get("access_token")
                    ok(f"Login via {path}")
                    break

        if not token:
            fail("Could not obtain auth token", "Trying endpoints without auth")
            # We'll still try the endpoints to see what errors we get
            headers = {}
        else:
            ok(f"Token obtained", f"{token[:20]}...")
            headers = {"Authorization": f"Bearer {token}"}

        # ── 2. Create a private lesson ───────────────────────────
        print("\n🧪 2. POST /api/v1/community/lessons — Create lesson")
        lesson_id = None
        r = await c.post("/api/v1/community/lessons", headers=headers, json={
            "title": "Intro to Calculus",
            "subject": "Math",
            "price_per_hour": 30.0,
            "currency": "USD",
            "duration_minutes": 60,
            "description": "Learn derivatives and integrals",
            "location": "Library Room 101",
            "latitude": 25.7617,
            "longitude": -80.1918
        })
        print(f"    Response: HTTP {r.status_code}")
        print(f"    Body: {r.text[:300]}")
        if r.status_code in (200, 201):
            data = r.json()
            lesson_id = data.get("id")
            ok("Created lesson", f"id={lesson_id}")
        else:
            fail("Create lesson", f"HTTP {r.status_code}")

        # ── 3. Get lesson ────────────────────────────────────────
        print("\n🧪 3. GET /api/v1/community/lessons/{id}")
        if lesson_id:
            r = await c.get(f"/api/v1/community/lessons/{lesson_id}", headers=headers)
            print(f"    Response: HTTP {r.status_code}")
            print(f"    Body: {r.text[:300]}")
            if r.status_code == 200:
                ok("Get lesson")
            else:
                fail("Get lesson", f"HTTP {r.status_code}")
        else:
            fail("Get lesson", "No lesson_id from previous step")

        # ── 4. Get available slots ───────────────────────────────
        print("\n🧪 4. GET /api/v1/community/lessons/{id}/slots?date=2025-02-15")
        if lesson_id:
            r = await c.get(
                f"/api/v1/community/lessons/{lesson_id}/slots",
                params={"date": "2025-02-15"},
                headers=headers
            )
            print(f"    Response: HTTP {r.status_code}")
            print(f"    Body: {r.text[:500]}")
            if r.status_code == 200:
                slots = r.json()
                available = [s for s in slots if s.get("is_available")]
                ok("Get slots", f"{len(slots)} total, {len(available)} available")
            else:
                fail("Get slots", f"HTTP {r.status_code}")
        else:
            fail("Get slots", "No lesson_id")

        # ── 5. Create a booking ──────────────────────────────────
        print("\n🧪 5. POST /api/v1/community/bookings — Book a slot")
        if lesson_id:
            slot_id = f"{lesson_id}-20250215-1000"
            r = await c.post("/api/v1/community/bookings", headers=headers, json={
                "lesson_id": lesson_id,
                "slot_id": slot_id,
                "notes": "Looking forward to it!"
            })
            print(f"    Response: HTTP {r.status_code}")
            print(f"    Body: {r.text[:300]}")
            if r.status_code in (200, 201):
                ok("Created booking")
            else:
                fail("Create booking", f"HTTP {r.status_code}")
        else:
            fail("Create booking", "No lesson_id")

        # ── 6. Double-booking conflict ───────────────────────────
        print("\n🧪 6. POST /api/v1/community/bookings — Conflict check")
        if lesson_id:
            r = await c.post("/api/v1/community/bookings", headers=headers, json={
                "lesson_id": lesson_id,
                "slot_id": f"{lesson_id}-20250215-1000",
                "notes": "Should fail"
            })
            print(f"    Response: HTTP {r.status_code}")
            if r.status_code == 400:
                ok("Double-booking rejected", r.json().get("detail", ""))
            else:
                fail("Double-booking should return 400", f"Got {r.status_code}")
        else:
            fail("Conflict check", "No lesson_id")

        # ── 7. Get my bookings ───────────────────────────────────
        print("\n🧪 7. GET /api/v1/community/bookings/my")
        r = await c.get("/api/v1/community/bookings/my", headers=headers)
        print(f"    Response: HTTP {r.status_code}")
        print(f"    Body: {r.text[:300]}")
        if r.status_code == 200:
            bookings = r.json()
            ok("Get my bookings", f"{len(bookings)} bookings")
        else:
            fail("Get my bookings", f"HTTP {r.status_code}")

        # ── 8. Submit a review ───────────────────────────────────
        print("\n🧪 8. POST /api/v1/community/reviews — Submit review")
        if lesson_id:
            r = await c.post("/api/v1/community/reviews", headers=headers, json={
                "target_type": "lesson",
                "target_id": str(lesson_id),
                "rating": 5,
                "text": "Excellent instructor!"
            })
            print(f"    Response: HTTP {r.status_code}")
            print(f"    Body: {r.text[:300]}")
            if r.status_code in (200, 201):
                ok("Submit review")
            else:
                fail("Submit review", f"HTTP {r.status_code}")
        else:
            fail("Submit review", "No lesson_id")

        # ── 9. Duplicate review ──────────────────────────────────
        print("\n🧪 9. POST /api/v1/community/reviews — Duplicate check")
        if lesson_id:
            r = await c.post("/api/v1/community/reviews", headers=headers, json={
                "target_type": "lesson",
                "target_id": str(lesson_id),
                "rating": 4,
                "text": "Should fail"
            })
            if r.status_code == 400:
                ok("Duplicate review rejected")
            else:
                fail("Duplicate review should return 400", f"Got {r.status_code}")
        else:
            fail("Duplicate check", "No lesson_id")

        # ── 10. Get reviews ──────────────────────────────────────
        print("\n🧪 10. GET /api/v1/community/reviews/lesson/{id}")
        if lesson_id:
            r = await c.get(f"/api/v1/community/reviews/lesson/{lesson_id}", headers=headers)
            print(f"    Response: HTTP {r.status_code}")
            print(f"    Body: {r.text[:300]}")
            if r.status_code == 200:
                reviews = r.json()
                ok("Get reviews", f"{len(reviews)} reviews")
            else:
                fail("Get reviews", f"HTTP {r.status_code}")
        else:
            fail("Get reviews", "No lesson_id")

        # ── 11. Get review stats ─────────────────────────────────
        print("\n🧪 11. GET /api/v1/community/reviews/lesson/{id}/stats")
        if lesson_id:
            r = await c.get(f"/api/v1/community/reviews/lesson/{lesson_id}/stats", headers=headers)
            print(f"    Response: HTTP {r.status_code}")
            print(f"    Body: {r.text[:300]}")
            if r.status_code == 200:
                stats = r.json()
                ok("Get review stats", f"avg={stats.get('average_rating')}, count={stats.get('review_count')}")
            else:
                fail("Get review stats", f"HTTP {r.status_code}")
        else:
            fail("Get review stats", "No lesson_id")

        # ── 12. Cancel booking ───────────────────────────────────
        print("\n🧪 12. DELETE /api/v1/community/bookings/{id}")
        if lesson_id:
            # Get booking ID first
            r = await c.get("/api/v1/community/bookings/my", headers=headers)
            if r.status_code == 200:
                bookings = r.json()
                if bookings:
                    booking_id = bookings[0]["id"]
                    r = await c.delete(f"/api/v1/community/bookings/{booking_id}", headers=headers)
                    if r.status_code == 204:
                        ok("Cancel booking", f"id={booking_id}")
                    else:
                        fail("Cancel booking", f"HTTP {r.status_code}: {r.text[:200]}")
                else:
                    fail("Cancel booking", "No bookings found")
            else:
                fail("Cancel booking", "Could not list bookings")
        else:
            fail("Cancel booking", "No lesson_id")

        # ── 13. Verify slot is available again ───────────────────
        print("\n🧪 13. Verify slot availability after cancel")
        if lesson_id:
            r = await c.get(
                f"/api/v1/community/lessons/{lesson_id}/slots",
                params={"date": "2025-02-15"},
                headers=headers
            )
            if r.status_code == 200:
                slots = r.json()
                ten_am = next((s for s in slots if "1000" in s.get("id", "")), None)
                if ten_am and ten_am.get("is_available"):
                    ok("10:00 slot available again after cancel")
                elif ten_am:
                    fail("10:00 slot should be available after cancel", f"is_available={ten_am.get('is_available')}")
                else:
                    fail("10:00 slot not found in response")
            else:
                fail("Verify slots", f"HTTP {r.status_code}")

    # ── Final report ──────────────────────────────────────────────
    print("\n" + "=" * 60)
    print(f"  SMOKE TEST RESULTS: {passed} passed, {failed} failed")
    print("=" * 60)
    if failed > 0:
        sys.exit(1)
    else:
        print("\n🎉 All smoke tests passed!")

if __name__ == "__main__":
    asyncio.run(main())
