"""Test script for API setup endpoint."""

import sys
from pathlib import Path

# Add parent directory to path so we can import browserfriend
sys.path.insert(0, str(Path(__file__).parent.parent))

from fastapi.testclient import TestClient

from browserfriend.database import User, get_session_factory, init_database
from browserfriend.server.app import app


def test_setup_endpoint():
    """Test POST /api/setup endpoint."""
    print("=" * 60)
    print("Testing POST /api/setup Endpoint")
    print("=" * 60)

    # Initialize database
    init_database()

    client = TestClient(app)

    # Clean up any existing test users
    SessionLocal = get_session_factory()
    session = SessionLocal()
    try:
        session.query(User).filter(User.email == "test@example.com").delete()
        session.query(User).filter(User.email == "newuser@example.com").delete()
        session.commit()
    finally:
        session.close()

    print("\n1. Testing POST /api/setup with new email...")
    try:
        response = client.post(
            "/api/setup",
            json={"email": "newuser@example.com"},
        )
        print(f"[OK] Status code: {response.status_code}")
        print(f"[OK] Response: {response.json()}")

        if response.status_code != 200:
            print(f"[ERROR] Expected status 200, got {response.status_code}")
            return False

        data = response.json()
        if data["success"] is not True:
            print(f"[ERROR] Expected success=True, got {data['success']}")
            return False

        if data["email"] != "newuser@example.com":
            print(f"[ERROR] Expected email=newuser@example.com, got {data['email']}")
            return False

        # Verify user was created in database
        session = SessionLocal()
        try:
            user = session.query(User).filter(User.email == "newuser@example.com").first()
            if not user:
                print("[ERROR] User was not created in database")
                return False
            print("[OK] User created in database successfully")
        finally:
            session.close()

    except Exception as e:
        print(f"[ERROR] Failed to call /api/setup: {e}")
        import traceback

        traceback.print_exc()
        return False

    print("\n2. Testing POST /api/setup with existing email (idempotent)...")
    try:
        response = client.post(
            "/api/setup",
            json={"email": "newuser@example.com"},
        )
        print(f"[OK] Status code: {response.status_code}")
        print(f"[OK] Response: {response.json()}")

        if response.status_code != 200:
            print(f"[ERROR] Expected status 200, got {response.status_code}")
            return False

        data = response.json()
        if data["success"] is not True:
            print(f"[ERROR] Expected success=True, got {data['success']}")
            return False

        if data["email"] != "newuser@example.com":
            print(f"[ERROR] Expected email=newuser@example.com, got {data['email']}")
            return False

        # Verify only one user exists (idempotent)
        session = SessionLocal()
        try:
            users = session.query(User).filter(User.email == "newuser@example.com").all()
            if len(users) != 1:
                print(f"[ERROR] Expected 1 user, found {len(users)}")
                return False
            print("[OK] Endpoint is idempotent - no duplicate users created")
        finally:
            session.close()

    except Exception as e:
        print(f"[ERROR] Failed to call /api/setup with existing email: {e}")
        import traceback

        traceback.print_exc()
        return False

    print("\n3. Testing POST /api/setup with invalid email...")
    try:
        response = client.post(
            "/api/setup",
            json={"email": "invalid-email"},
        )
        print(f"[OK] Status code: {response.status_code}")

        if response.status_code != 422:
            print(f"[ERROR] Expected status 422 (validation error), got {response.status_code}")
            print(f"[ERROR] Response: {response.json()}")
            return False

        print("[OK] Invalid email correctly rejected with 422 status")
    except Exception as e:
        print(f"[ERROR] Failed to test invalid email: {e}")
        return False

    print("\n4. Testing POST /api/setup with missing email field...")
    try:
        response = client.post(
            "/api/setup",
            json={},
        )
        print(f"[OK] Status code: {response.status_code}")

        if response.status_code != 422:
            print(f"[ERROR] Expected status 422 (validation error), got {response.status_code}")
            return False

        print("[OK] Missing email field correctly rejected with 422 status")
    except Exception as e:
        print(f"[ERROR] Failed to test missing email: {e}")
        return False

    print("\n5. Testing POST /api/setup with different valid email formats...")
    test_emails = [
        "user@example.com",
        "user.name@example.com",
        "user+tag@example.co.uk",
        "user123@subdomain.example.com",
    ]

    for test_email in test_emails:
        try:
            # Clean up first
            session = SessionLocal()
            try:
                session.query(User).filter(User.email == test_email).delete()
                session.commit()
            finally:
                session.close()

            response = client.post(
                "/api/setup",
                json={"email": test_email},
            )

            if response.status_code != 200:
                print(
                    f"[ERROR] Valid email {test_email} rejected with status {response.status_code}"
                )
                return False

            data = response.json()
            if data["email"] != test_email:
                print(f"[ERROR] Email mismatch for {test_email}")
                return False

            print(f"[OK] Email format '{test_email}' accepted")
        except Exception as e:
            print(f"[ERROR] Failed to test email {test_email}: {e}")
            return False

    print("\n" + "=" * 60)
    print("[OK] All setup endpoint tests passed!")
    print("=" * 60)
    return True


if __name__ == "__main__":
    import sys

    success = test_setup_endpoint()

    sys.exit(0 if success else 1)
