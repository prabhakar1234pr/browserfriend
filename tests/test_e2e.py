"""End-to-end test for BrowserFriend FastAPI server."""

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


def test_e2e_workflow():
    """End-to-end test of the complete BrowserFriend workflow."""
    print("=" * 80)
    print("END-TO-END TEST: BrowserFriend FastAPI Server")
    print("=" * 80)

    # Initialize database
    print("\n[SETUP] Initializing database...")
    init_database()
    print("[OK] Database initialized")

    client = TestClient(app)

    # Clean up any existing test data
    SessionLocal = get_session_factory()
    session = SessionLocal()
    try:
        session.query(PageVisit).delete()
        session.query(BrowsingSession).delete()
        session.query(User).delete()
        session.commit()
        print("[OK] Cleaned up existing test data")
    finally:
        session.close()

    # ========================================================================
    # STEP 1: Health Check
    # ========================================================================
    print("\n" + "=" * 80)
    print("STEP 1: Health Check")
    print("=" * 80)
    try:
        response = client.get("/health")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "healthy"
        assert data["service"] == "BrowserFriend"
        print("[OK] Health check passed")
    except Exception as e:
        print(f"[ERROR] Health check failed: {e}")
        return False

    # ========================================================================
    # STEP 2: Status Check
    # ========================================================================
    print("\n" + "=" * 80)
    print("STEP 2: Status Endpoint")
    print("=" * 80)
    try:
        response = client.get("/api/status")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "running"
        assert "database" in data
        print(f"[OK] Status check passed: {data}")
    except Exception as e:
        print(f"[ERROR] Status check failed: {e}")
        return False

    # ========================================================================
    # STEP 3: Setup - Create User
    # ========================================================================
    print("\n" + "=" * 80)
    print("STEP 3: Setup - Create User")
    print("=" * 80)
    test_email = "e2e-test@example.com"
    try:
        response = client.post("/api/setup", json={"email": test_email})
        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert data["email"] == test_email
        print(f"[OK] User setup successful: {data['email']}")

        # Verify user in database
        session = SessionLocal()
        try:
            user = session.query(User).filter(User.email == test_email).first()
            assert user is not None
            assert user.email == test_email
            print(f"[OK] User verified in database: {user.email}")
        finally:
            session.close()
    except Exception as e:
        print(f"[ERROR] Setup failed: {e}")
        import traceback

        traceback.print_exc()
        return False

    # ========================================================================
    # STEP 4: Track First Page Visit (Creates Session)
    # ========================================================================
    print("\n" + "=" * 80)
    print("STEP 4: Track First Page Visit (Creates Session)")
    print("=" * 80)
    try:
        end_time = datetime.now(timezone.utc)
        timestamp_str = end_time.isoformat().replace("+00:00", "Z")

        response = client.post(
            "/api/track",
            json={
                "url": "https://www.example.com/page1",
                "title": "Example Page 1",
                "duration": 120,
                "timestamp": timestamp_str,
            },
        )
        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert "example.com" in data["message"]
        print(f"[OK] First page visit tracked: {data['message']}")

        # Verify session was created
        session = SessionLocal()
        try:
            sessions = (
                session.query(BrowsingSession)
                .filter(BrowsingSession.end_time.is_(None))
                .all()
            )
            assert len(sessions) == 1
            session_id = sessions[0].session_id
            print(f"[OK] Session created: {session_id}")

            # Verify page visit was created
            visits = session.query(PageVisit).filter(PageVisit.session_id == session_id).all()
            assert len(visits) == 1
            visit = visits[0]
            assert visit.url == "https://www.example.com/page1"
            assert visit.domain == "example.com"
            assert visit.duration_seconds == 120
            print(f"[OK] Page visit created: {visit.domain} ({visit.duration_seconds}s)")
        finally:
            session.close()
    except Exception as e:
        print(f"[ERROR] First page visit tracking failed: {e}")
        import traceback

        traceback.print_exc()
        return False

    # ========================================================================
    # STEP 5: Track Multiple Page Visits (Same Session)
    # ========================================================================
    print("\n" + "=" * 80)
    print("STEP 5: Track Multiple Page Visits (Same Session)")
    print("=" * 80)
    try:
        base_time = datetime.now(timezone.utc)
        visits_data = [
            {
                "url": "https://www.github.com",
                "title": "GitHub",
                "duration": 180,
                "timestamp": (base_time + timedelta(minutes=2)).isoformat().replace("+00:00", "Z"),
            },
            {
                "url": "https://www.stackoverflow.com/questions/123",
                "title": "Stack Overflow Question",
                "duration": 240,
                "timestamp": (base_time + timedelta(minutes=5)).isoformat().replace("+00:00", "Z"),
            },
            {
                "url": "https://www.google.com/search?q=test",
                "title": "Google Search",
                "duration": 60,
                "timestamp": (base_time + timedelta(minutes=9)).isoformat().replace("+00:00", "Z"),
            },
        ]

        for i, visit_data in enumerate(visits_data, 1):
            response = client.post("/api/track", json=visit_data)
            assert response.status_code == 200
            data = response.json()
            assert data["success"] is True
            print(f"[OK] Visit {i} tracked: {data['message']}")

        # Verify all visits are in the same session
        session = SessionLocal()
        try:
            active_sessions = (
                session.query(BrowsingSession)
                .filter(BrowsingSession.end_time.is_(None))
                .all()
            )
            assert len(active_sessions) == 1
            session_id = active_sessions[0].session_id

            visits = session.query(PageVisit).filter(PageVisit.session_id == session_id).all()
            assert len(visits) == 4  # 1 from step 4 + 3 from this step
            print(f"[OK] All {len(visits)} visits are in the same session: {session_id}")

            # Verify domains
            domains = [visit.domain for visit in visits]
            assert "example.com" in domains
            assert "github.com" in domains
            assert "stackoverflow.com" in domains
            assert "google.com" in domains
            print(f"[OK] All domains tracked correctly: {set(domains)}")
        finally:
            session.close()
    except Exception as e:
        print(f"[ERROR] Multiple page visits tracking failed: {e}")
        import traceback

        traceback.print_exc()
        return False

    # ========================================================================
    # STEP 6: Verify Data Integrity
    # ========================================================================
    print("\n" + "=" * 80)
    print("STEP 6: Verify Data Integrity")
    print("=" * 80)
    try:
        session = SessionLocal()
        try:
            # Check user
            user = session.query(User).filter(User.email == test_email).first()
            assert user is not None
            print(f"[OK] User exists: {user.email}")

            # Check sessions
            all_sessions = session.query(BrowsingSession).all()
            assert len(all_sessions) == 1
            print(f"[OK] Total sessions: {len(all_sessions)}")

            # Check page visits
            all_visits = session.query(PageVisit).all()
            assert len(all_visits) == 4
            print(f"[OK] Total page visits: {len(all_visits)}")

            # Verify relationships
            for visit in all_visits:
                assert visit.user_email == test_email
                assert visit.session_id == all_sessions[0].session_id
                assert visit.start_time is not None
                assert visit.end_time is not None
                assert visit.duration_seconds is not None
                assert visit.domain is not None

            print("[OK] All data integrity checks passed")
            print(f"[OK] User: {user.email}")
            print(f"[OK] Session: {all_sessions[0].session_id}")
            print(f"[OK] Visits: {len(all_visits)} visits across {len(set(v.domain for v in all_visits))} domains")
        finally:
            session.close()
    except Exception as e:
        print(f"[ERROR] Data integrity check failed: {e}")
        import traceback

        traceback.print_exc()
        return False

    # ========================================================================
    # STEP 7: Error Handling Tests
    # ========================================================================
    print("\n" + "=" * 80)
    print("STEP 7: Error Handling")
    print("=" * 80)

    # Test invalid email
    try:
        response = client.post("/api/setup", json={"email": "invalid-email"})
        assert response.status_code == 422
        print("[OK] Invalid email correctly rejected")
    except Exception as e:
        print(f"[ERROR] Invalid email test failed: {e}")
        return False

    # Test invalid timestamp
    try:
        response = client.post(
            "/api/track",
            json={
                "url": "https://www.example.com",
                "duration": 60,
                "timestamp": "invalid-timestamp",
            },
        )
        assert response.status_code == 400
        print("[OK] Invalid timestamp correctly rejected")
    except Exception as e:
        print(f"[ERROR] Invalid timestamp test failed: {e}")
        return False

    # Test missing required fields
    try:
        response = client.post("/api/track", json={"url": "https://www.example.com"})
        assert response.status_code == 422
        print("[OK] Missing required fields correctly rejected")
    except Exception as e:
        print(f"[ERROR] Missing fields test failed: {e}")
        return False

    # ========================================================================
    # SUMMARY
    # ========================================================================
    print("\n" + "=" * 80)
    print("END-TO-END TEST SUMMARY")
    print("=" * 80)
    print("[OK] All end-to-end tests passed!")
    print("\nTested Features:")
    print("  [OK] Health check endpoint")
    print("  [OK] Status endpoint with database check")
    print("  [OK] User setup with email validation")
    print("  [OK] Page visit tracking")
    print("  [OK] Session management (auto-creation)")
    print("  [OK] Multiple visits in same session")
    print("  [OK] Data integrity and relationships")
    print("  [OK] Error handling (invalid inputs)")
    print("=" * 80)
    return True


if __name__ == "__main__":
    import sys

    success = test_e2e_workflow()
    sys.exit(0 if success else 1)
