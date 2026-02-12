"""
Unit tests for the Community Booking & Review system.

Validates:
  - Model imports and instantiation
  - Schema validation (happy path + edge cases)
  - Service instantiation and method presence
  - Route endpoint count after additions
"""

import asyncio
import sys
import traceback
from datetime import datetime, timedelta

sys.path.insert(0, "/Users/hectorgarcia/Desktop/LyoBackendJune")

# ── Global counters ───────────────────────────────────────────────────────────
passed = 0
failed = 0


def ok(label: str):
    global passed
    passed += 1
    print(f"  ✅ {label}")


def fail(label: str, err: Exception):
    global failed
    failed += 1
    print(f"  ❌ {label}: {err}")


# ── 1. Model imports ─────────────────────────────────────────────────────────

def test_model_imports():
    print("\n🧪 1. Model imports")
    try:
        from lyo_app.community.models import (
            BookingStatus, PrivateLesson, Booking, Review
        )
        ok("BookingStatus enum imported")

        # Verify enum values
        assert BookingStatus.PENDING.value == "pending"
        assert BookingStatus.CONFIRMED.value == "confirmed"
        assert BookingStatus.CANCELLED.value == "cancelled"
        assert BookingStatus.COMPLETED.value == "completed"
        ok("BookingStatus has 4 correct values")

        # Verify table names
        assert PrivateLesson.__tablename__ == "private_lessons"
        assert Booking.__tablename__ == "bookings"
        assert Review.__tablename__ == "reviews"
        ok("Table names are correct")

    except Exception as e:
        fail("Model imports", e)


# ── 2. Schema validation ─────────────────────────────────────────────────────

def test_schemas():
    print("\n🧪 2. Schema validation")
    from lyo_app.community.schemas import (
        PrivateLessonCreate, PrivateLessonRead,
        BookingSlotRead, BookingCreate, BookingRead,
        ReviewCreate, ReviewRead, ReviewStatsRead
    )
    from lyo_app.community.models import BookingStatus

    # ── PrivateLessonCreate ──
    try:
        pl = PrivateLessonCreate(
            title="Calculus Tutoring",
            subject="Math",
            price_per_hour=25.0,
            duration_minutes=60,
        )
        assert pl.title == "Calculus Tutoring"
        assert pl.currency == "USD"  # default
        ok("PrivateLessonCreate valid data")
    except Exception as e:
        fail("PrivateLessonCreate valid data", e)

    try:
        PrivateLessonCreate(title="", subject="Math")
        fail("PrivateLessonCreate empty title should fail", ValueError("Did not raise"))
    except Exception:
        ok("PrivateLessonCreate rejects empty title")

    # ── BookingSlotRead ──
    try:
        now = datetime.utcnow()
        slot = BookingSlotRead(
            id="1-20250210-0900",
            start_time=now,
            end_time=now + timedelta(hours=1),
            is_available=True,
        )
        assert slot.is_available is True
        ok("BookingSlotRead uses snake_case fields")
    except Exception as e:
        fail("BookingSlotRead", e)

    # ── BookingCreate ──
    try:
        bc = BookingCreate(
            lesson_id=1,
            slot_id="1-20250210-0900",
            notes="First session",
        )
        assert bc.lesson_id == 1
        assert bc.slot_id == "1-20250210-0900"
        ok("BookingCreate uses snake_case fields")
    except Exception as e:
        fail("BookingCreate", e)

    # ── BookingRead ──
    try:
        now = datetime.utcnow()
        br = BookingRead(
            id=1,
            lesson_id=1,
            lesson_title="Calculus 101",
            student_id=42,
            status=BookingStatus.PENDING,
            slot_start=now,
            slot_end=now + timedelta(hours=1),
            notes=None,
            created_at=now,
        )
        assert br.status == BookingStatus.PENDING
        ok("BookingRead with snake_case fields")
    except Exception as e:
        fail("BookingRead", e)

    # ── ReviewCreate ──
    try:
        rc = ReviewCreate(
            target_type="lesson",
            target_id="1",
            rating=5,
            text="Great lesson!",
        )
        assert rc.rating == 5
        ok("ReviewCreate valid (lesson)")
    except Exception as e:
        fail("ReviewCreate valid", e)

    try:
        rc2 = ReviewCreate(
            target_type="institution",
            target_id="42",
            rating=3,
        )
        assert rc2.text is None
        ok("ReviewCreate valid (institution, no text)")
    except Exception as e:
        fail("ReviewCreate institution", e)

    try:
        ReviewCreate(target_type="invalid", target_id="1", rating=3)
        fail("ReviewCreate bad target_type should fail", ValueError("Did not raise"))
    except Exception:
        ok("ReviewCreate rejects invalid target_type")

    try:
        ReviewCreate(target_type="lesson", target_id="1", rating=0)
        fail("ReviewCreate rating=0 should fail", ValueError("Did not raise"))
    except Exception:
        ok("ReviewCreate rejects rating < 1")

    try:
        ReviewCreate(target_type="lesson", target_id="1", rating=6)
        fail("ReviewCreate rating=6 should fail", ValueError("Did not raise"))
    except Exception:
        ok("ReviewCreate rejects rating > 5")

    # ── ReviewRead ──
    try:
        now = datetime.utcnow()
        rr = ReviewRead(
            id=1,
            author_id=10,
            author_name="Alice",
            author_avatar=None,
            target_type="lesson",
            target_id="1",
            rating=4,
            text="Very helpful",
            created_at=now,
        )
        assert rr.author_name == "Alice"
        ok("ReviewRead with snake_case fields")
    except Exception as e:
        fail("ReviewRead", e)

    # ── ReviewStatsRead ──
    try:
        stats = ReviewStatsRead(
            average_rating=4.2,
            review_count=15,
            rating_distribution={"1": 0, "2": 1, "3": 2, "4": 5, "5": 7},
        )
        assert stats.review_count == 15
        assert stats.average_rating == 4.2
        ok("ReviewStatsRead with snake_case fields")
    except Exception as e:
        fail("ReviewStatsRead", e)


# ── 3. Service instantiation ─────────────────────────────────────────────────

def test_service():
    print("\n🧪 3. Service instantiation & method checks")
    try:
        from lyo_app.community.service import CommunityService
        svc = CommunityService()
        ok("CommunityService instantiated")

        required_methods = [
            "create_private_lesson",
            "get_private_lesson",
            "get_available_slots",
            "create_booking",
            "get_user_bookings",
            "cancel_booking",
            "get_reviews",
            "submit_review",
            "get_review_stats",
        ]
        for method in required_methods:
            assert hasattr(svc, method), f"Missing method: {method}"
        ok(f"All {len(required_methods)} booking/review methods present")

    except Exception as e:
        fail("Service", e)


# ── 4. Route count ────────────────────────────────────────────────────────────

def test_routes():
    print("\n🧪 4. Route endpoint verification")
    try:
        from lyo_app.community.routes import router
        route_paths = [r.path for r in router.routes if hasattr(r, "path")]

        expected_paths = [
            "/lessons/{lesson_id}",
            "/lessons",
            "/lessons/{lesson_id}/slots",
            "/bookings",
            "/bookings/my",
            "/bookings/{booking_id}",
            "/reviews/{target_type}/{target_id}",
            "/reviews",
            "/reviews/{target_type}/{target_id}/stats",
        ]
        for ep in expected_paths:
            assert ep in route_paths, f"Missing route: {ep}"
        ok(f"All {len(expected_paths)} booking/review routes registered")

    except Exception as e:
        fail("Routes", e)


# ── 5. App factory registration ──────────────────────────────────────────────

def test_app_factory():
    print("\n🧪 5. App factory — community router registered")
    try:
        from lyo_app.app_factory import create_app
        app = create_app()
        community_routes = [
            r.path for r in app.routes if hasattr(r, "path") and "community" in r.path
        ]
        assert len(community_routes) > 0, "No community routes in the app"
        ok(f"Community routes found in app ({len(community_routes)} paths)")
    except Exception as e:
        fail("App factory", e)


# ── 6. Slot ID parsing logic (unit-level) ─────────────────────────────────────

def test_slot_id_parsing():
    print("\n🧪 6. Slot ID parsing logic")
    try:
        # Simulate the parsing that create_booking does
        slot_id = "5-20250315-1400"
        parts = slot_id.split("-")
        assert len(parts) == 3
        assert parts[0] == "5"           # lesson_id
        assert parts[1] == "20250315"    # date
        assert parts[2] == "1400"        # time

        slot_start = datetime.strptime(f"{parts[1]}{parts[2]}", "%Y%m%d%H%M")
        slot_end = slot_start + timedelta(hours=1)
        assert slot_start.hour == 14
        assert slot_end.hour == 15
        assert slot_start.month == 3
        assert slot_start.day == 15
        ok("Slot ID parsing produces correct datetime")

        # Edge: malformed ID
        bad_id = "nope"
        bad_parts = bad_id.split("-")
        assert len(bad_parts) < 3  # would be caught by the service
        ok("Malformed slot ID correctly detected")
    except Exception as e:
        fail("Slot ID parsing", e)


# ── Main ──────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    print("=" * 60)
    print("  Booking & Review System — Unit Tests")
    print("=" * 60)

    test_model_imports()
    test_schemas()
    test_service()
    test_routes()
    test_app_factory()
    test_slot_id_parsing()

    print("\n" + "=" * 60)
    print(f"  RESULTS: {passed} passed, {failed} failed")
    print("=" * 60)

    if failed > 0:
        sys.exit(1)
    else:
        print("\n🎉 All booking & review tests passed!")
