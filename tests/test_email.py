"""Tests for the email delivery module (Issue #6 / Issue #10).

Tests cover:
- Email utility functions (format_duration, calculate_percentage, get_category_color)
- Email template rendering (Jinja2)
- Email sender (Resend API - mocked)
- Dashboard database storage
- CLI dashboard command integration
"""

import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import MagicMock, patch

sys.path.insert(0, str(Path(__file__).parent.parent))


# ============================================================================
# 1. Utils tests
# ============================================================================


def test_format_duration_seconds():
    """Test format_duration with values under 60 seconds."""
    from browserfriend.email.utils import format_duration

    assert format_duration(0) == "0s"
    assert format_duration(30) == "30s"
    assert format_duration(59) == "59s"
    print("[OK] format_duration - seconds")


def test_format_duration_minutes():
    """Test format_duration with values in minutes."""
    from browserfriend.email.utils import format_duration

    assert format_duration(60) == "1m"
    assert format_duration(90) == "1m"  # 1m 30s -> shows as 1m since 30 remaining
    assert format_duration(3540) == "59m"
    print("[OK] format_duration - minutes")


def test_format_duration_hours():
    """Test format_duration with values in hours."""
    from browserfriend.email.utils import format_duration

    assert format_duration(3600) == "1h 0m"
    assert format_duration(8100) == "2h 15m"
    assert format_duration(7200) == "2h 0m"
    print("[OK] format_duration - hours")


def test_calculate_percentage():
    """Test calculate_percentage."""
    from browserfriend.email.utils import calculate_percentage

    assert calculate_percentage(50, 100) == 50.0
    assert calculate_percentage(1, 3) == 33.3
    assert calculate_percentage(0, 100) == 0.0
    assert calculate_percentage(100, 0) == 0.0  # division by zero guard
    print("[OK] calculate_percentage")


def test_get_category_color():
    """Test get_category_color returns correct hex codes."""
    from browserfriend.email.utils import get_category_color

    assert get_category_color("development") == "#2196F3"
    assert get_category_color("social") == "#FF9800"
    assert get_category_color("entertainment") == "#E91E63"
    assert get_category_color("unknown_category") == "#9E9E9E"
    assert get_category_color("DEVELOPMENT") == "#2196F3"  # case-insensitive
    print("[OK] get_category_color")


# ============================================================================
# 2. Renderer tests
# ============================================================================


def _make_sample_insights():
    """Create sample insights dict for testing."""
    return {
        "session_id": "test-session-123",
        "stats": {
            "total_time": 3600,
            "total_visits": 25,
            "unique_domains": 8,
            "session_duration": 4200,
            "top_domains": [
                {
                    "domain": "github.com",
                    "visits": 10,
                    "total_time": 1800,
                    "avg_time": 180,
                    "percentage": 50.0,
                },
                {
                    "domain": "stackoverflow.com",
                    "visits": 5,
                    "total_time": 900,
                    "avg_time": 180,
                    "percentage": 25.0,
                },
                {
                    "domain": "youtube.com",
                    "visits": 3,
                    "total_time": 600,
                    "avg_time": 200,
                    "percentage": 16.7,
                },
            ],
            "time_distribution": {
                "morning": 1200,
                "afternoon": 1800,
                "evening": 600,
                "night": 0,
            },
        },
        "categories": {
            "github.com": "development",
            "stackoverflow.com": "development",
            "youtube.com": "entertainment",
        },
        "summary": "You spent most of your time on development-related sites.",
        "patterns": [
            "Most active during afternoon",
            "Heavy GitHub usage",
        ],
        "productivity_score": 75,
        "productivity_breakdown": {
            "productive_time": 60,
            "neutral_time": 25,
            "distracting_time": 15,
        },
        "recommendations": [
            "Try taking short breaks between coding sessions",
            "Limit YouTube usage during work hours",
        ],
        "time_insights": {
            "most_active_period": "afternoon",
            "focus_hours": ["2pm-4pm"],
            "distraction_hours": ["8pm-10pm"],
        },
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "used_fallback": False,
    }


def test_render_dashboard_email():
    """Test that the template renders without errors and contains key sections."""
    from browserfriend.email.renderer import render_dashboard_email

    insights = _make_sample_insights()
    stats = insights["stats"]
    user_email = "test@example.com"

    html = render_dashboard_email(insights, stats, user_email)

    # Check it's valid HTML
    assert "<html" in html
    assert "</html>" in html

    # Check key content sections
    assert "BrowserFriend" in html
    assert user_email in html
    assert "github.com" in html
    assert "stackoverflow.com" in html
    assert "youtube.com" in html
    assert "75" in html  # productivity score
    assert "development" in html
    assert "entertainment" in html
    assert "Recommendations" in html
    assert "AI Insights" in html
    assert "Productivity Breakdown" in html

    print(f"[OK] render_dashboard_email - rendered {len(html)} chars")


def test_render_dashboard_email_empty_data():
    """Test rendering with minimal/empty data doesn't crash."""
    from browserfriend.email.renderer import render_dashboard_email

    insights = {
        "session_id": "empty-session",
        "stats": {
            "total_time": 0,
            "total_visits": 0,
            "unique_domains": 0,
            "session_duration": 0,
            "top_domains": [],
            "time_distribution": {
                "morning": 0,
                "afternoon": 0,
                "evening": 0,
                "night": 0,
            },
        },
        "categories": {},
        "summary": "",
        "patterns": [],
        "productivity_score": 0,
        "productivity_breakdown": {
            "productive_time": 0,
            "neutral_time": 0,
            "distracting_time": 0,
        },
        "recommendations": [],
        "time_insights": {},
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "used_fallback": True,
    }

    html = render_dashboard_email(insights, insights["stats"], "test@example.com")
    assert "<html" in html
    assert "BrowserFriend" in html
    print("[OK] render_dashboard_email - empty data renders safely")


# ============================================================================
# 3. Sender tests (mocked)
# ============================================================================


def test_send_via_smtp_success():
    """Test successful email sending via SMTP (mocked)."""
    from browserfriend.email.sender import send_dashboard_email

    with patch("browserfriend.email.sender.get_config") as mock_config:
        mock_config.return_value.email_provider = "smtp"
        mock_config.return_value.smtp_username = "user@gmail.com"
        mock_config.return_value.smtp_password = "app_password"
        mock_config.return_value.smtp_host = "smtp.gmail.com"
        mock_config.return_value.smtp_port = 587

        with patch("browserfriend.email.sender.smtplib.SMTP") as mock_smtp:
            mock_server = MagicMock()
            mock_smtp.return_value.__enter__ = MagicMock(return_value=mock_server)
            mock_smtp.return_value.__exit__ = MagicMock(return_value=False)

            result = send_dashboard_email("test@example.com", "<html>test</html>")

            assert result is True
            mock_server.starttls.assert_called_once()
            mock_server.login.assert_called_once_with("user@gmail.com", "app_password")
            mock_server.sendmail.assert_called_once()

    print("[OK] send_dashboard_email (SMTP) - success")


def test_send_via_smtp_missing_credentials():
    """Test that missing SMTP credentials returns False."""
    from browserfriend.email.sender import send_dashboard_email

    with patch("browserfriend.email.sender.get_config") as mock_config:
        mock_config.return_value.email_provider = "smtp"
        mock_config.return_value.smtp_username = None
        mock_config.return_value.smtp_password = None
        mock_config.return_value.smtp_host = "smtp.gmail.com"
        mock_config.return_value.smtp_port = 587

        result = send_dashboard_email("test@example.com", "<html>test</html>")
        assert result is False

    print("[OK] send_dashboard_email (SMTP) - missing credentials")


def test_send_via_smtp_error():
    """Test that SMTP errors are handled gracefully."""
    from browserfriend.email.sender import send_dashboard_email

    with patch("browserfriend.email.sender.get_config") as mock_config:
        mock_config.return_value.email_provider = "smtp"
        mock_config.return_value.smtp_username = "user@gmail.com"
        mock_config.return_value.smtp_password = "app_password"
        mock_config.return_value.smtp_host = "smtp.gmail.com"
        mock_config.return_value.smtp_port = 587

        with patch("browserfriend.email.sender.smtplib.SMTP") as mock_smtp:
            mock_smtp.return_value.__enter__ = MagicMock(
                side_effect=Exception("Connection refused")
            )
            mock_smtp.return_value.__exit__ = MagicMock(return_value=False)

            result = send_dashboard_email("test@example.com", "<html>test</html>")
            assert result is False

    print("[OK] send_dashboard_email (SMTP) - error handled")


def test_send_via_resend_success():
    """Test successful email sending via Resend API (mocked)."""
    from browserfriend.email.sender import send_dashboard_email

    with patch("browserfriend.email.sender.get_config") as mock_config:
        mock_config.return_value.email_provider = "resend"
        mock_config.return_value.resend_api_key = "re_test_key_123"

        with patch("resend.Emails") as mock_emails:
            mock_emails.send.return_value = {"id": "email-123"}

            result = send_dashboard_email("test@example.com", "<html>test</html>")

            assert result is True
            mock_emails.send.assert_called_once()
            call_args = mock_emails.send.call_args[0][0]
            assert call_args["to"] == "test@example.com"

    print("[OK] send_dashboard_email (Resend) - success")


def test_send_via_resend_missing_key():
    """Test that missing Resend API key returns False."""
    import os

    from browserfriend.email.sender import send_dashboard_email

    old_val = os.environ.pop("RESEND_API_KEY", None)
    try:
        with patch("browserfriend.email.sender.get_config") as mock_config:
            mock_config.return_value.email_provider = "resend"
            mock_config.return_value.resend_api_key = None

            result = send_dashboard_email("test@example.com", "<html>test</html>")
            assert result is False
    finally:
        if old_val is not None:
            os.environ["RESEND_API_KEY"] = old_val

    print("[OK] send_dashboard_email (Resend) - missing key")


# ============================================================================
# 4. Dashboard database storage tests
# ============================================================================


def test_dashboard_model_and_save():
    """Test Dashboard model creation and save_dashboard function."""
    from browserfriend.database import (
        Dashboard,
        User,
        create_new_session,
        drop_tables,
        get_session_factory,
        init_database,
        save_dashboard,
    )

    # Reset database
    drop_tables()
    init_database()

    SessionLocal = get_session_factory()
    db = SessionLocal()

    try:
        # Create a user and session
        user = User(email="dashboard-test@example.com")
        db.add(user)
        db.commit()
    finally:
        db.close()

    session = create_new_session("dashboard-test@example.com")

    # Save a dashboard
    insights = _make_sample_insights()
    html = "<html><body>Test Dashboard</body></html>"

    dashboard = save_dashboard(
        session_id=session.session_id,
        user_email="dashboard-test@example.com",
        insights=insights,
        html_content=html,
    )

    assert dashboard is not None
    assert dashboard.id is not None
    assert dashboard.session_id == session.session_id
    assert dashboard.user_email == "dashboard-test@example.com"
    assert dashboard.html_content == html
    assert dashboard.email_sent is True
    assert dashboard.sent_at is not None

    # Verify insights JSON is valid
    stored_insights = json.loads(dashboard.insights_json)
    assert stored_insights["session_id"] == "test-session-123"
    assert stored_insights["productivity_score"] == 75

    # Verify we can query it back
    db = SessionLocal()
    try:
        queried = db.query(Dashboard).filter(Dashboard.id == dashboard.id).first()
        assert queried is not None
        assert queried.user_email == "dashboard-test@example.com"
        print(f"[OK] Dashboard saved and queried: id={queried.id}")
    finally:
        db.close()

    print("[OK] Dashboard model and save_dashboard")


# ============================================================================
# Run all tests
# ============================================================================


def run_all_tests():
    """Run all email module tests."""
    print("=" * 70)
    print("EMAIL MODULE TESTS (Issue #6 / Issue #10)")
    print("=" * 70)

    tests = [
        # Utils
        test_format_duration_seconds,
        test_format_duration_minutes,
        test_format_duration_hours,
        test_calculate_percentage,
        test_get_category_color,
        # Renderer
        test_render_dashboard_email,
        test_render_dashboard_email_empty_data,
        # Sender - SMTP (mocked)
        test_send_via_smtp_success,
        test_send_via_smtp_missing_credentials,
        test_send_via_smtp_error,
        # Sender - Resend (mocked)
        test_send_via_resend_success,
        test_send_via_resend_missing_key,
        # Database
        test_dashboard_model_and_save,
    ]

    passed = 0
    failed = 0

    for test_fn in tests:
        try:
            test_fn()
            passed += 1
        except Exception as exc:
            failed += 1
            print(f"[FAIL] {test_fn.__name__}: {exc}")
            import traceback

            traceback.print_exc()

    print("")
    print("=" * 70)
    print(f"RESULTS: {passed} passed, {failed} failed, {passed + failed} total")
    print("=" * 70)

    return failed == 0


if __name__ == "__main__":
    success = run_all_tests()
    sys.exit(0 if success else 1)
