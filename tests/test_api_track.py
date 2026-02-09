"""Test script for API track endpoint."""

import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

# Add parent directory to path so we can import browserfriend
sys.path.insert(0, str(Path(__file__).parent.parent))

from fastapi.testclient import TestClient

from browserfriend.database import (
    BrowsingSession,
    PageVisit,
    User,
    get_session_factory,
    init_database,
)
from browserfriend.server.app import app


def test_track_endpoint():
    """Test POST /api/track endpoint."""
    print("=" * 60)
    print("Testing POST /api/track Endpoint")
    print("=" * 60)

    # Initialize database
    init_database()

    client = TestClient(app)

    # Setup: Create a test user
    SessionLocal = get_session_factory()
    session = SessionLocal()
    try:
        # Clean up test data
        session.query(PageVisit).delete()
        session.query(BrowsingSession).delete()
        session.query(User).filter(User.email == "tracktest@example.com").delete()

        # Create test user
        test_user = User(email="tracktest@example.com")
        session.add(test_user)
        session.commit()
        print("[OK] Created test user: tracktest@example.com")
    finally:
        session.close()

    print("\n1. Testing POST /api/track with valid data...")
    try:
        # Create ISO timestamp
        end_time = datetime.now(timezone.utc)
        timestamp_str = end_time.isoformat().replace("+00:00", "Z")
        duration = 120  # 2 minutes

        response = client.post(
            "/api/track",
            json={
                "url": "https://www.example.com",
                "title": "Example Page",
                "duration": duration,
                "timestamp": timestamp_str,
            },
        )
        print(f"[OK] Status code: {response.status_code}")
        print(f"[OK] Response: {response.json()}")

        if response.status_code != 200:
            print(f"[ERROR] Expected status 200, got {response.status_code}")
            print(f"[ERROR] Response: {response.json()}")
            return False

        data = response.json()
        if data["success"] is not True:
            print(f"[ERROR] Expected success=True, got {data['success']}")
            return False

        # Verify page visit was created in database
        session = SessionLocal()
        try:
            page_visits = session.query(PageVisit).filter(PageVisit.url == "https://www.example.com").all()
            if len(page_visits) != 1:
                print(f"[ERROR] Expected 1 page visit, found {len(page_visits)}")
                return False

            visit = page_visits[0]
            if visit.domain != "example.com":
                print(f"[ERROR] Expected domain=example.com, got {visit.domain}")
                return False

            if visit.duration_seconds != duration:
                print(f"[ERROR] Expected duration={duration}, got {visit.duration_seconds}")
                return False

            if visit.title != "Example Page":
                print(f"[ERROR] Expected title='Example Page', got {visit.title}")
                return False

            print("[OK] Page visit created in database successfully")
            print(f"[OK] Domain extracted correctly: {visit.domain}")
            print(f"[OK] Duration stored correctly: {visit.duration_seconds}s")
        finally:
            session.close()

    except Exception as e:
        print(f"[ERROR] Failed to call /api/track: {e}")
        import traceback

        traceback.print_exc()
        return False

    print("\n2. Testing POST /api/track creates session if none exists...")
    try:
        # End any existing sessions
        session = SessionLocal()
        try:
            session.query(BrowsingSession).update({"end_time": datetime.now(timezone.utc)})
            session.commit()
        finally:
            session.close()

        # Track another visit - should create new session
        end_time = datetime.now(timezone.utc)
        timestamp_str = end_time.isoformat().replace("+00:00", "Z")

        response = client.post(
            "/api/track",
            json={
                "url": "https://www.github.com",
                "title": "GitHub",
                "duration": 60,
                "timestamp": timestamp_str,
            },
        )

        if response.status_code != 200:
            print(f"[ERROR] Expected status 200, got {response.status_code}")
            return False

        # Verify new session was created
        session = SessionLocal()
        try:
            active_sessions = (
                session.query(BrowsingSession)
                .filter(BrowsingSession.end_time.is_(None))
                .all()
            )
            if len(active_sessions) != 1:
                print(f"[ERROR] Expected 1 active session, found {len(active_sessions)}")
                return False
            print("[OK] New session created automatically")
        finally:
            session.close()

    except Exception as e:
        print(f"[ERROR] Failed to test session creation: {e}")
        import traceback

        traceback.print_exc()
        return False

    print("\n3. Testing POST /api/track with multiple visits in same session...")
    try:
        end_time = datetime.now(timezone.utc)
        timestamp_str = end_time.isoformat().replace("+00:00", "Z")

        # Track multiple visits
        for i, url in enumerate(["https://www.google.com", "https://www.stackoverflow.com"]):
            visit_time = end_time + timedelta(seconds=i * 60)
            visit_timestamp = visit_time.isoformat().replace("+00:00", "Z")

            response = client.post(
                "/api/track",
                json={
                    "url": url,
                    "title": f"Page {i+1}",
                    "duration": 45,
                    "timestamp": visit_timestamp,
                },
            )

            if response.status_code != 200:
                print(f"[ERROR] Visit {i+1} failed with status {response.status_code}")
                return False

        # Verify all visits are in the same session
        session = SessionLocal()
        try:
            active_sessions = (
                session.query(BrowsingSession)
                .filter(BrowsingSession.end_time.is_(None))
                .all()
            )
            if len(active_sessions) != 1:
                print(f"[ERROR] Expected 1 active session, found {len(active_sessions)}")
                return False

            session_id = active_sessions[0].session_id
            visits = session.query(PageVisit).filter(PageVisit.session_id == session_id).all()
            if len(visits) < 3:  # At least 3 visits (example.com, github.com, google.com, stackoverflow.com)
                print(f"[ERROR] Expected at least 3 visits in session, found {len(visits)}")
                return False

            print(f"[OK] Multiple visits tracked in same session: {len(visits)} visits")
        finally:
            session.close()

    except Exception as e:
        print(f"[ERROR] Failed to test multiple visits: {e}")
        import traceback

        traceback.print_exc()
        return False

    print("\n4. Testing POST /api/track with invalid timestamp...")
    try:
        response = client.post(
            "/api/track",
            json={
                "url": "https://www.example.com",
                "title": "Test",
                "duration": 60,
                "timestamp": "invalid-timestamp",
            },
        )

        if response.status_code != 400:
            print(f"[ERROR] Expected status 400, got {response.status_code}")
            return False

        print("[OK] Invalid timestamp correctly rejected with 400 status")
    except Exception as e:
        print(f"[ERROR] Failed to test invalid timestamp: {e}")
        return False

    print("\n5. Testing POST /api/track with missing user (no setup)...")
    try:
        # Delete all users
        session = SessionLocal()
        try:
            session.query(User).delete()
            session.commit()
        finally:
            session.close()

        end_time = datetime.now(timezone.utc)
        timestamp_str = end_time.isoformat().replace("+00:00", "Z")

        response = client.post(
            "/api/track",
            json={
                "url": "https://www.example.com",
                "title": "Test",
                "duration": 60,
                "timestamp": timestamp_str,
            },
        )

        if response.status_code != 404:
            print(f"[ERROR] Expected status 404 (no user), got {response.status_code}")
            print(f"[ERROR] Response: {response.json()}")
            return False

        print("[OK] Missing user correctly rejected with 404 status")

        # Restore test user for remaining tests
        session = SessionLocal()
        try:
            test_user = User(email="tracktest@example.com")
            session.add(test_user)
            session.commit()
        finally:
            session.close()

    except Exception as e:
        print(f"[ERROR] Failed to test missing user: {e}")
        return False

    print("\n6. Testing POST /api/track calculates start_time correctly...")
    try:
        # Create a specific timestamp
        end_time = datetime(2024, 1, 1, 12, 2, 0, tzinfo=timezone.utc)
        timestamp_str = end_time.isoformat().replace("+00:00", "Z")
        duration = 120  # 2 minutes

        response = client.post(
            "/api/track",
            json={
                "url": "https://www.test.com",
                "title": "Test Page",
                "duration": duration,
                "timestamp": timestamp_str,
            },
        )

        if response.status_code != 200:
            print(f"[ERROR] Expected status 200, got {response.status_code}")
            return False

        # Verify start_time calculation
        session = SessionLocal()
        try:
            visit = (
                session.query(PageVisit)
                .filter(PageVisit.url == "https://www.test.com")
                .first()
            )
            if not visit:
                print("[ERROR] Page visit not found")
                return False

            expected_start = end_time - timedelta(seconds=duration)
            # Ensure both datetimes are timezone-aware for comparison
            visit_start = visit.start_time
            visit_end = visit.end_time
            if visit_start.tzinfo is None:
                visit_start = visit_start.replace(tzinfo=timezone.utc)
            if visit_end.tzinfo is None:
                visit_end = visit_end.replace(tzinfo=timezone.utc)

            if abs((visit_start - expected_start).total_seconds()) > 1:
                print(
                    f"[ERROR] Start time calculation incorrect. "
                    f"Expected: {expected_start}, Got: {visit_start}"
                )
                return False

            if abs((visit_end - end_time).total_seconds()) > 1:
                print(
                    f"[ERROR] End time incorrect. "
                    f"Expected: {end_time}, Got: {visit_end}"
                )
                return False

            print("[OK] Start time and end time calculated correctly")
            print(f"[OK] Start: {visit.start_time}, End: {visit.end_time}, Duration: {visit.duration_seconds}s")
        finally:
            session.close()

    except Exception as e:
        print(f"[ERROR] Failed to test time calculation: {e}")
        import traceback

        traceback.print_exc()
        return False

    print("\n" + "=" * 60)
    print("[OK] All track endpoint tests passed!")
    print("=" * 60)
    return True


if __name__ == "__main__":
    import sys

    success = test_track_endpoint()

    sys.exit(0 if success else 1)
