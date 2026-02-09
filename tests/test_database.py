"""Test script for database models."""

import sys
from datetime import datetime, timedelta
from pathlib import Path

# Add parent directory to path so we can import browserfriend
sys.path.insert(0, str(Path(__file__).parent.parent))

from browserfriend.database import (  # noqa: E402
    BrowsingSession,
    PageVisit,
    create_new_session,
    end_session,
    get_current_session,
    get_session_factory,
    init_database,
)


def test_database():
    """Test database models and functionality."""
    print("=" * 60)
    print("Testing BrowserFriend Database Models")
    print("=" * 60)

    # Initialize database
    print("\n1. Initializing database...")
    try:
        init_database()
        print("[OK] Database initialized successfully")
    except Exception as e:
        print(f"[ERROR] Error initializing database: {e}")
        return False

    # Test creating a session
    print("\n2. Creating a new browsing session...")
    test_email = "test@example.com"
    try:
        session = create_new_session(test_email)
        print(f"[OK] Created session: {session.session_id}")
        print(f"  - User email: {session.user_email}")
        print(f"  - Start time: {session.start_time}")
        print(f"  - End time: {session.end_time}")
    except Exception as e:
        print(f"[ERROR] Error creating session: {e}")
        return False

    # Test creating page visits
    print("\n3. Creating page visits...")
    SessionLocal = get_session_factory()
    db_session = SessionLocal()
    try:
        # Create a few page visits
        visit1 = PageVisit(
            session_id=session.session_id,
            user_email=test_email,
            url="https://www.google.com",
            domain="google.com",
            title="Google",
            start_time=datetime.utcnow() - timedelta(minutes=10),
            end_time=datetime.utcnow() - timedelta(minutes=9),
        )
        visit1.calculate_duration()

        visit2 = PageVisit(
            session_id=session.session_id,
            user_email=test_email,
            url="https://www.github.com",
            domain="github.com",
            title="GitHub",
            start_time=datetime.utcnow() - timedelta(minutes=9),
            end_time=datetime.utcnow() - timedelta(minutes=7),
        )
        visit2.calculate_duration()

        visit3 = PageVisit(
            session_id=session.session_id,
            user_email=test_email,
            url="https://www.stackoverflow.com",
            domain="stackoverflow.com",
            title="Stack Overflow",
            start_time=datetime.utcnow() - timedelta(minutes=7),
            end_time=None,  # Still active
        )

        db_session.add(visit1)
        db_session.add(visit2)
        db_session.add(visit3)
        db_session.commit()

        print(f"[OK] Created {3} page visits")
        print(f"  - Visit 1: {visit1.domain} ({visit1.duration_seconds}s)")
        print(f"  - Visit 2: {visit2.domain} ({visit2.duration_seconds}s)")
        print(f"  - Visit 3: {visit3.domain} (active)")
    except Exception as e:
        print(f"[ERROR] Error creating page visits: {e}")
        db_session.rollback()
        return False
    finally:
        db_session.close()

    # Test querying sessions
    print("\n4. Querying sessions...")
    try:
        db_session = SessionLocal()
        sessions = (
            db_session.query(BrowsingSession).filter(BrowsingSession.user_email == test_email).all()
        )
        print(f"[OK] Found {len(sessions)} session(s) for {test_email}")
        for s in sessions:
            print(f"  - Session {s.session_id}: {s.start_time}")
    except Exception as e:
        print(f"[ERROR] Error querying sessions: {e}")
        return False
    finally:
        db_session.close()

    # Test querying page visits
    print("\n5. Querying page visits...")
    try:
        db_session = SessionLocal()
        visits = (
            db_session.query(PageVisit).filter(PageVisit.session_id == session.session_id).all()
        )
        print(f"[OK] Found {len(visits)} page visit(s) for session {session.session_id}")
        for v in visits:
            print(f"  - {v.domain}: {v.url} ({v.duration_seconds}s if ended)")
    except Exception as e:
        print(f"[ERROR] Error querying page visits: {e}")
        return False
    finally:
        db_session.close()

    # Test relationships
    print("\n6. Testing relationships...")
    try:
        db_session = SessionLocal()
        session_with_visits = (
            db_session.query(BrowsingSession)
            .filter(BrowsingSession.session_id == session.session_id)
            .first()
        )
        print(f"[OK] Session has {len(session_with_visits.page_visits)} page visit(s)")
        for visit in session_with_visits.page_visits:
            print(f"  - {visit.domain} belongs to session {visit.session.session_id}")
    except Exception as e:
        print(f"[ERROR] Error testing relationships: {e}")
        return False
    finally:
        db_session.close()

    # Test getting current session
    print("\n7. Testing get_current_session...")
    try:
        current = get_current_session(test_email)
        if current:
            print(f"[OK] Found current session: {current.session_id}")
        else:
            print("[ERROR] No current session found (session should be active)")
    except Exception as e:
        print(f"[ERROR] Error getting current session: {e}")
        return False

    # Test ending session
    print("\n8. Ending session...")
    try:
        ended_session = end_session(session.session_id)
        if ended_session:
            print("[OK] Session ended successfully")
            print(f"  - Duration: {ended_session.duration} seconds")
            print(f"  - End time: {ended_session.end_time}")
        else:
            print("[ERROR] Failed to end session")
    except Exception as e:
        print(f"[ERROR] Error ending session: {e}")
        return False

    # Test querying by user_email
    print("\n9. Testing user_email filtering...")
    try:
        db_session = SessionLocal()
        visits_by_user = (
            db_session.query(PageVisit).filter(PageVisit.user_email == test_email).all()
        )
        print(f"[OK] Found {len(visits_by_user)} page visit(s) for user {test_email}")

        domains = (
            db_session.query(PageVisit.domain)
            .filter(PageVisit.user_email == test_email)
            .distinct()
            .all()
        )
        print(f"[OK] User visited {len(domains)} unique domain(s)")
        for domain_tuple in domains:
            print(f"  - {domain_tuple[0]}")
    except Exception as e:
        print(f"[ERROR] Error querying by user_email: {e}")
        return False
    finally:
        db_session.close()

    # Verify database file exists
    print("\n10. Verifying database file exists...")
    try:
        import os

        from browserfriend.config import get_config

        config = get_config()
        db_path = config.database_path
        if os.path.exists(db_path):
            size = os.path.getsize(db_path)
            print(f"[OK] Database file exists: {db_path}")
            print(f"  - File size: {size} bytes")
        else:
            print(f"[ERROR] Database file not found at: {db_path}")
            return False
    except Exception as e:
        print(f"[ERROR] Error verifying database file: {e}")
        return False

    print("\n" + "=" * 60)
    print("[OK] All database tests passed!")
    print("=" * 60)
    return True


if __name__ == "__main__":
    import sys

    success = test_database()
    sys.exit(0 if success else 1)
