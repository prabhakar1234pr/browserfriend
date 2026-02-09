"""Test script for Steps 1, 2, and 3."""

import sys
from pathlib import Path

# Add parent directory to path so we can import browserfriend
sys.path.insert(0, str(Path(__file__).parent.parent))

from fastapi.testclient import TestClient

from browserfriend.server.app import app


def test_step1_server_package_structure():
    """Test Step 1: Verify server package structure exists."""
    print("=" * 60)
    print("Testing Step 1: Server Package Structure")
    print("=" * 60)

    # Check if server package exists
    server_dir = Path(__file__).parent.parent / "browserfriend" / "server"
    init_file = server_dir / "__init__.py"
    app_file = server_dir / "app.py"

    print("\n1. Checking server package directory...")
    if not server_dir.exists():
        print("[ERROR] browserfriend/server/ directory does not exist")
        return False
    print("[OK] browserfriend/server/ directory exists")

    print("\n2. Checking __init__.py...")
    if not init_file.exists():
        print("[ERROR] browserfriend/server/__init__.py does not exist")
        return False
    print("[OK] browserfriend/server/__init__.py exists")

    # Check if it exports app
    try:
        from browserfriend.server import app as imported_app

        if imported_app is None:
            print("[ERROR] app is not exported from browserfriend.server")
            return False
        print("[OK] app is exported from browserfriend.server")
    except Exception as e:
        print(f"[ERROR] Failed to import app from browserfriend.server: {e}")
        return False

    print("\n3. Checking app.py...")
    if not app_file.exists():
        print("[ERROR] browserfriend/server/app.py does not exist")
        return False
    print("[OK] browserfriend/server/app.py exists")

    print("\n" + "=" * 60)
    print("[OK] Step 1 tests passed!")
    print("=" * 60)
    return True


def test_step2_fastapi_app_moved():
    """Test Step 2: Verify FastAPI app is moved and works."""
    print("\n" + "=" * 60)
    print("Testing Step 2: FastAPI App Moved from main.py")
    print("=" * 60)

    print("\n1. Checking if app can be imported from server.app...")
    try:
        from browserfriend.server.app import app

        print("[OK] app imported successfully from browserfriend.server.app")
    except Exception as e:
        print(f"[ERROR] Failed to import app: {e}")
        return False

    print("\n2. Checking if app is a FastAPI instance...")
    from fastapi import FastAPI

    if not isinstance(app, FastAPI):
        print("[ERROR] app is not a FastAPI instance")
        return False
    print("[OK] app is a FastAPI instance")

    print("\n3. Checking if lifespan is configured...")
    if app.router.lifespan_context is None:
        print("[ERROR] lifespan context manager is not configured")
        return False
    print("[OK] lifespan context manager is configured")

    print("\n4. Testing if server can start (health endpoint)...")
    client = TestClient(app)
    try:
        response = client.get("/health")
        if response.status_code != 200:
            print(f"[ERROR] Health endpoint returned {response.status_code}")
            return False
        print("[OK] Server can start and respond to requests")
        print(f"[OK] Health endpoint response: {response.json()}")
    except Exception as e:
        print(f"[ERROR] Failed to start server: {e}")
        return False

    print("\n" + "=" * 60)
    print("[OK] Step 2 tests passed!")
    print("=" * 60)
    return True


def test_step3_cors_middleware():
    """Test Step 3: Verify CORS middleware is configured."""
    print("\n" + "=" * 60)
    print("Testing Step 3: CORS Middleware Configuration")
    print("=" * 60)

    print("\n1. Checking if CORS middleware is added...")
    # Check if CORSMiddleware is in the middleware stack
    has_cors = False
    for middleware in app.user_middleware:
        if "CORSMiddleware" in str(middleware):
            has_cors = True
            break

    if not has_cors:
        print("[ERROR] CORS middleware is not configured")
        return False
    print("[OK] CORS middleware is configured")

    print("\n2. Testing CORS headers with chrome-extension origin...")
    client = TestClient(app)
    try:
        # Test OPTIONS request (preflight)
        response = client.options(
            "/api/status",
            headers={
                "Origin": "chrome-extension://abcdefghijklmnop",
                "Access-Control-Request-Method": "GET",
            },
        )
        print(f"[OK] OPTIONS request status: {response.status_code}")

        # Check CORS headers in response
        cors_headers = {
            "access-control-allow-origin": response.headers.get("access-control-allow-origin"),
            "access-control-allow-methods": response.headers.get("access-control-allow-methods"),
            "access-control-allow-credentials": response.headers.get(
                "access-control-allow-credentials"
            ),
        }

        print(f"[OK] CORS headers: {cors_headers}")

        # Test GET request with chrome-extension origin
        response = client.get(
            "/api/status",
            headers={"Origin": "chrome-extension://abcdefghijklmnop"},
        )
        if response.status_code != 200:
            print(
                f"[ERROR] GET request with chrome-extension origin failed: {response.status_code}"
            )
            return False
        print("[OK] GET request with chrome-extension origin succeeded")

        # Test GET request with localhost origin
        response = client.get(
            "/api/status",
            headers={"Origin": "http://localhost:3000"},
        )
        if response.status_code != 200:
            print(f"[ERROR] GET request with localhost origin failed: {response.status_code}")
            return False
        print("[OK] GET request with localhost origin succeeded")

    except Exception as e:
        print(f"[ERROR] Failed to test CORS: {e}")
        return False

    print("\n" + "=" * 60)
    print("[OK] Step 3 tests passed!")
    print("=" * 60)
    return True


if __name__ == "__main__":
    import sys

    success1 = test_step1_server_package_structure()
    success2 = test_step2_fastapi_app_moved()
    success3 = test_step3_cors_middleware()

    sys.exit(0 if (success1 and success2 and success3) else 1)
