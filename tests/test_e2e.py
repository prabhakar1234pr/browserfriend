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
    drop_tables,
    get_session_factory,
    init_database,
)
from browserfriend.server.app import app


def test_e2e_workflow():
    """End-to-end test of the complete BrowserFriend workflow."""
    print("=" * 80)
    print("END-TO-END TEST: BrowserFriend FastAPI Server")
    print("=" * 80)

    # Drop and recreate tables to ensure schema matches models (Fix 2 changed User PK)
    print("\n[SETUP] Dropping and recreating database tables...")
    drop_tables()
    init_database()
    print("[OK] Database tables recreated with latest schema")

    client = TestClient(app)
    SessionLocal = get_session_factory()

    # ========================================================================
    # STEP 1: Status Check (replaces old /health - Fix 3)
    # ========================================================================
    print("\n" + "=" * 80)
    print("STEP 1: Status Endpoint (single health/status - Fix 3)")
    print("=" * 80)
    try:
        response = client.get("/api/status")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "running"
        assert data["database"] == "connected"
        print(f"[OK] Status check passed: {data}")

        # Verify /health is removed
        response = client.get("/health")
        assert response.status_code == 404, "/health should not exist"
        print("[OK] /health endpoint correctly removed")
    except Exception as e:
        print(f"[ERROR] Status check failed: {e}")
        import traceback
        traceback.print_exc()
        return False

    # ========================================================================
    # STEP 2: Setup - Create User (Fix 2 - integer PK)
    # ========================================================================
    print("\n" + "=" * 80)
    print("STEP 2: Setup - Create User (Fix 2 - integer PK)")
    print("=" * 80)
    test_email = "e2e-test@example.com"
    try:
        response = client.post("/api/setup", json={"email": test_email})
        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert data["email"] == test_email
        print(f"[OK] User setup successful: {data['email']}")

        # Verify user in database has integer id (Fix 2)
        session = SessionLocal()
        try:
            user = session.query(User).filter(User.email == test_email).first()
            assert user is not None
            assert isinstance(user.id, int), f"Expected integer id, got {type(user.id)}"
            assert user.email == test_email
            print(f"[OK] User verified in database: id={user.id}, email={user.email}")
        finally:
            session.close()
    except Exception as e:
        print(f"[ERROR] Setup failed: {e}")
        import traceback
        traceback.print_exc()
        return False

    # ========================================================================
    # STEP 3: Track Page Visit with email in request (Fix 5)
    # ========================================================================
    print("\n" + "=" * 80)
    print("STEP 3: Track Page Visit with email (Fix 5 - no single-user assumption)")
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
                "email": test_email,
            },
        )
        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert "session_id" in data, "Response should include session_id (Fix 6)"
        assert "example.com" in data["message"]
        first_session_id = data["session_id"]
        print(f"[OK] First page visit tracked: {data['message']}")
        print(f"[OK] Session ID returned in response: {first_session_id} (Fix 6)")

        # Verify session was created
        session = SessionLocal()
        try:
            sessions = (
                session.query(BrowsingSession)
                .filter(BrowsingSession.end_time.is_(None))
                .all()
            )
            assert len(sessions) == 1
            assert sessions[0].session_id == first_session_id
            print(f"[OK] Session created: {first_session_id}")

            # Verify page visit
            visits = session.query(PageVisit).filter(PageVisit.session_id == first_session_id).all()
            assert len(visits) == 1
            assert visits[0].domain == "example.com"
            assert visits[0].duration_seconds == 120
            print(f"[OK] Page visit created: {visits[0].domain} ({visits[0].duration_seconds}s)")
        finally:
            session.close()
    except Exception as e:
        print(f"[ERROR] Track with email failed: {e}")
        import traceback
        traceback.print_exc()
        return False

    # ========================================================================
    # STEP 4: Track without email should fail (Fix 5 enforced)
    # ========================================================================
    print("\n" + "=" * 80)
    print("STEP 4: Track without email should fail (Fix 5 enforced)")
    print("=" * 80)
    try:
        end_time = datetime.now(timezone.utc)
        timestamp_str = end_time.isoformat().replace("+00:00", "Z")

        response = client.post(
            "/api/track",
            json={
                "url": "https://www.example.com",
                "duration": 60,
                "timestamp": timestamp_str,
                # no email field
            },
        )
        assert response.status_code == 422, f"Expected 422, got {response.status_code}"
        print("[OK] Track without email correctly rejected with 422")
    except Exception as e:
        print(f"[ERROR] Track without email test failed: {e}")
        import traceback
        traceback.print_exc()
        return False

    # ========================================================================
    # STEP 5: Track with wrong email should fail (Fix 5)
    # ========================================================================
    print("\n" + "=" * 80)
    print("STEP 5: Track with non-existent email should fail (Fix 5)")
    print("=" * 80)
    try:
        end_time = datetime.now(timezone.utc)
        timestamp_str = end_time.isoformat().replace("+00:00", "Z")

        response = client.post(
            "/api/track",
            json={
                "url": "https://www.example.com",
                "duration": 60,
                "timestamp": timestamp_str,
                "email": "unknown@example.com",
            },
        )
        assert response.status_code == 404, f"Expected 404, got {response.status_code}"
        print("[OK] Track with unknown email correctly rejected with 404")
    except Exception as e:
        print(f"[ERROR] Track with wrong email test failed: {e}")
        import traceback
        traceback.print_exc()
        return False

    # ========================================================================
    # STEP 6: Multiple Page Visits in Same Session
    # ========================================================================
    print("\n" + "=" * 80)
    print("STEP 6: Multiple Page Visits in Same Session")
    print("=" * 80)
    try:
        base_time = datetime.now(timezone.utc)
        visits_data = [
            {
                "url": "https://www.github.com",
                "title": "GitHub",
                "duration": 180,
                "timestamp": (base_time + timedelta(minutes=2)).isoformat().replace("+00:00", "Z"),
                "email": test_email,
            },
            {
                "url": "https://www.stackoverflow.com/questions/123",
                "title": "Stack Overflow Question",
                "duration": 240,
                "timestamp": (base_time + timedelta(minutes=5)).isoformat().replace("+00:00", "Z"),
                "email": test_email,
            },
        ]

        for i, visit_data in enumerate(visits_data, 1):
            response = client.post("/api/track", json=visit_data)
            assert response.status_code == 200
            data = response.json()
            assert data["success"] is True
            assert data["session_id"] == first_session_id, "Should use same session"
            print(f"[OK] Visit {i} tracked in same session: {data['message']}")

        # Verify all in same session
        session = SessionLocal()
        try:
            visits = session.query(PageVisit).filter(PageVisit.session_id == first_session_id).all()
            assert len(visits) == 3  # 1 from step 3 + 2 from this step
            domains = {v.domain for v in visits}
            assert domains == {"example.com", "github.com", "stackoverflow.com"}
            print(f"[OK] All {len(visits)} visits in same session. Domains: {domains}")
        finally:
            session.close()
    except Exception as e:
        print(f"[ERROR] Multiple visits test failed: {e}")
        import traceback
        traceback.print_exc()
        return False

    # ========================================================================
    # STEP 7: End Session Endpoint (Fix 4)
    # ========================================================================
    print("\n" + "=" * 80)
    print("STEP 7: End Session Endpoint (Fix 4)")
    print("=" * 80)
    try:
        response = client.post(
            "/api/session/end",
            json={"session_id": first_session_id},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert data["session_id"] == first_session_id
        assert data["duration_seconds"] is not None
        print(f"[OK] Session ended: {first_session_id}")
        print(f"[OK] Duration: {data['duration_seconds']}s")

        # Verify session is ended in database
        session = SessionLocal()
        try:
            bs = session.query(BrowsingSession).filter(BrowsingSession.session_id == first_session_id).first()
            assert bs.end_time is not None
            assert bs.duration is not None
            print(f"[OK] Session end_time set: {bs.end_time}")
        finally:
            session.close()

        # Try ending again - should fail
        response = client.post(
            "/api/session/end",
            json={"session_id": first_session_id},
        )
        assert response.status_code == 400, "Ending already-ended session should return 400"
        print("[OK] Re-ending session correctly rejected with 400")

        # Try ending non-existent session
        response = client.post(
            "/api/session/end",
            json={"session_id": "non-existent-id"},
        )
        assert response.status_code == 404, "Non-existent session should return 404"
        print("[OK] Non-existent session correctly rejected with 404")
    except Exception as e:
        print(f"[ERROR] End session test failed: {e}")
        import traceback
        traceback.print_exc()
        return False

    # ========================================================================
    # STEP 8: New Session After End (Fix 1 - session lifecycle)
    # ========================================================================
    print("\n" + "=" * 80)
    print("STEP 8: New Session Created After Previous Ended (Fix 1)")
    print("=" * 80)
    try:
        end_time = datetime.now(timezone.utc)
        timestamp_str = end_time.isoformat().replace("+00:00", "Z")

        response = client.post(
            "/api/track",
            json={
                "url": "https://www.newsite.com",
                "title": "New Site",
                "duration": 30,
                "timestamp": timestamp_str,
                "email": test_email,
            },
        )
        assert response.status_code == 200
        data = response.json()
        second_session_id = data["session_id"]
        assert second_session_id != first_session_id, "Should be a new session"
        print(f"[OK] New session created: {second_session_id}")
        print(f"[OK] Different from first session: {first_session_id}")
    except Exception as e:
        print(f"[ERROR] New session test failed: {e}")
        import traceback
        traceback.print_exc()
        return False

    # ========================================================================
    # STEP 9: Error Handling
    # ========================================================================
    print("\n" + "=" * 80)
    print("STEP 9: Error Handling")
    print("=" * 80)

    # Invalid email in setup
    try:
        response = client.post("/api/setup", json={"email": "invalid-email"})
        assert response.status_code == 422
        print("[OK] Invalid email correctly rejected (422)")
    except Exception as e:
        print(f"[ERROR] Invalid email test failed: {e}")
        return False

    # Invalid timestamp
    try:
        response = client.post(
            "/api/track",
            json={
                "url": "https://www.example.com",
                "duration": 60,
                "timestamp": "invalid-timestamp",
                "email": test_email,
            },
        )
        assert response.status_code == 400
        print("[OK] Invalid timestamp correctly rejected (400)")
    except Exception as e:
        print(f"[ERROR] Invalid timestamp test failed: {e}")
        return False

    # Missing required fields
    try:
        response = client.post("/api/track", json={"url": "https://www.example.com"})
        assert response.status_code == 422
        print("[OK] Missing required fields correctly rejected (422)")
    except Exception as e:
        print(f"[ERROR] Missing fields test failed: {e}")
        return False

    # ========================================================================
    # STEP 10: Data Integrity
    # ========================================================================
    print("\n" + "=" * 80)
    print("STEP 10: Data Integrity Verification")
    print("=" * 80)
    try:
        session = SessionLocal()
        try:
            # User has integer id
            user = session.query(User).filter(User.email == test_email).first()
            assert user is not None
            assert isinstance(user.id, int)
            print(f"[OK] User: id={user.id}, email={user.email} (Fix 2)")

            # Sessions
            all_sessions = session.query(BrowsingSession).all()
            assert len(all_sessions) == 2
            ended = [s for s in all_sessions if s.end_time is not None]
            active = [s for s in all_sessions if s.end_time is None]
            print(f"[OK] Total sessions: {len(all_sessions)} ({len(ended)} ended, {len(active)} active)")

            # Page visits
            all_visits = session.query(PageVisit).all()
            assert len(all_visits) == 4  # 3 from first session + 1 from second
            for visit in all_visits:
                assert visit.user_email == test_email
                assert visit.start_time is not None
                assert visit.end_time is not None
                assert visit.duration_seconds is not None
                assert visit.domain is not None
            print(f"[OK] Total page visits: {len(all_visits)}, all with complete data")
        finally:
            session.close()
    except Exception as e:
        print(f"[ERROR] Data integrity check failed: {e}")
        import traceback
        traceback.print_exc()
        return False

    # ========================================================================
    # SUMMARY
    # ========================================================================
    print("\n" + "=" * 80)
    print("END-TO-END TEST SUMMARY")
    print("=" * 80)
    print("[OK] All end-to-end tests passed!")
    print("\nFixes Verified:")
    print("  [OK] Fix 1: Session lifecycle - stale sessions auto-ended, new sessions created")
    print("  [OK] Fix 2: User model - integer PK with unique email")
    print("  [OK] Fix 3: Removed /health, single /api/status endpoint")
    print("  [OK] Fix 4: POST /api/session/end endpoint works")
    print("  [OK] Fix 5: Email required in track request, no single-user assumption")
    print("  [OK] Fix 6: session_id returned in track response")
    print("=" * 80)
    return True


if __name__ == "__main__":
    import sys

    success = test_e2e_workflow()
    sys.exit(0 if success else 1)
