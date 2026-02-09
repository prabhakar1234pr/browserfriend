"""Test script for API status endpoint."""

import sys
from pathlib import Path

# Add parent directory to path so we can import browserfriend
sys.path.insert(0, str(Path(__file__).parent.parent))

from fastapi.testclient import TestClient

from browserfriend.server.app import app, StatusResponse, TrackingData, SetupData, SuccessResponse


def test_pydantic_models():
    """Test Pydantic models validation."""
    print("=" * 60)
    print("Testing Pydantic Models")
    print("=" * 60)

    # Test TrackingData
    print("\n1. Testing TrackingData model...")
    try:
        tracking = TrackingData(
            url="https://www.example.com",
            title="Example",
            duration=120,
            timestamp="2024-01-01T12:00:00Z",
        )
        print(f"[OK] TrackingData created: {tracking.url}, duration={tracking.duration}s")
    except Exception as e:
        print(f"[ERROR] Failed to create TrackingData: {e}")
        return False

    # Test SetupData with valid email
    print("\n2. Testing SetupData model with valid email...")
    try:
        setup = SetupData(email="test@example.com")
        print(f"[OK] SetupData created: {setup.email}")
    except Exception as e:
        print(f"[ERROR] Failed to create SetupData: {e}")
        return False

    # Test SetupData with invalid email
    print("\n3. Testing SetupData model with invalid email...")
    try:
        setup_invalid = SetupData(email="invalid-email")
        print(f"[ERROR] Should have rejected invalid email")
        return False
    except Exception as e:
        print(f"[OK] Correctly rejected invalid email: {type(e).__name__}")

    # Test SuccessResponse
    print("\n4. Testing SuccessResponse model...")
    try:
        success = SuccessResponse(success=True, message="Operation completed")
        print(f"[OK] SuccessResponse created: {success.message}")
    except Exception as e:
        print(f"[ERROR] Failed to create SuccessResponse: {e}")
        return False

    # Test StatusResponse
    print("\n5. Testing StatusResponse model...")
    try:
        status = StatusResponse(status="running", database="connected")
        print(f"[OK] StatusResponse created: status={status.status}, database={status.database}")
    except Exception as e:
        print(f"[ERROR] Failed to create StatusResponse: {e}")
        return False

    print("\n" + "=" * 60)
    print("[OK] All Pydantic model tests passed!")
    print("=" * 60)
    return True


def test_status_endpoint():
    """Test /api/status endpoint."""
    print("\n" + "=" * 60)
    print("Testing /api/status Endpoint")
    print("=" * 60)

    client = TestClient(app)

    print("\n1. Testing GET /api/status...")
    try:
        response = client.get("/api/status")
        print(f"[OK] Status code: {response.status_code}")
        print(f"[OK] Response: {response.json()}")

        if response.status_code != 200:
            print(f"[ERROR] Expected status 200, got {response.status_code}")
            return False

        data = response.json()
        if "status" not in data or "database" not in data:
            print(f"[ERROR] Missing required fields in response: {data}")
            return False

        print(f"[OK] Status: {data['status']}")
        print(f"[OK] Database: {data['database']}")
    except Exception as e:
        print(f"[ERROR] Failed to call /api/status: {e}")
        return False

    print("\n" + "=" * 60)
    print("[OK] Status endpoint test passed!")
    print("=" * 60)
    return True


if __name__ == "__main__":
    import sys

    success1 = test_pydantic_models()
    success2 = test_status_endpoint()

    sys.exit(0 if (success1 and success2) else 1)
