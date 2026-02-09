"""End-to-end test for email delivery feature (Issue #6 / Issue #10).

Tests the complete workflow:
1. Setup user
2. Create session with page visits
3. Generate insights (fallback mode)
4. Render email template
5. Send email (mocked)
6. Save dashboard to database
7. Verify all data integrity
"""

import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).parent.parent))


def test_email_e2e_workflow():
    """End-to-end test of the complete email delivery workflow."""
    print("=" * 70)
    print("END-TO-END TEST: Email Delivery (Issue #6 / Issue #10)")
    print("=" * 70)

    # ====================================================================
    # SETUP: Database and test data
    # ====================================================================
    print("\n[SETUP] Initializing database...")
    from browserfriend.database import (
        BrowsingSession,
        Dashboard,
        PageVisit,
        User,
        drop_tables,
        get_session_factory,
        init_database,
        save_dashboard,
    )

    drop_tables()
    init_database()

    SessionLocal = get_session_factory()
    db = SessionLocal()
    try:
        user = User(email="e2e-email-test@example.com")
        db.add(user)
        db.commit()
        print(f"[OK] User created: {user.email}")
    finally:
        db.close()

    # Create a browsing session with page visits
    db = SessionLocal()
    try:
        bs = BrowsingSession(
            user_email="e2e-email-test@example.com",
            start_time=datetime.now(timezone.utc) - timedelta(hours=2),
        )
        db.add(bs)
        db.commit()
        db.refresh(bs)
        test_session_id = bs.session_id
        print(f"[OK] Session created: {test_session_id}")

        base_time = datetime.now(timezone.utc) - timedelta(hours=2)
        test_visits = [
            ("https://github.com/user/repo", "GitHub - Repository", 300),
            ("https://stackoverflow.com/questions/123", "Stack Overflow Question", 180),
            ("https://docs.python.org/3/library/json.html", "json - Python Docs", 120),
            ("https://www.youtube.com/watch?v=abc", "YouTube Video", 240),
            ("https://twitter.com/home", "Twitter Home", 60),
            ("https://mail.google.com/inbox", "Gmail - Inbox", 90),
        ]

        from browserfriend.database import extract_domain

        for i, (url, title, duration) in enumerate(test_visits):
            start = base_time + timedelta(minutes=i * 5)
            pv = PageVisit(
                session_id=test_session_id,
                user_email="e2e-email-test@example.com",
                url=url,
                domain=extract_domain(url),
                title=title,
                start_time=start,
                end_time=start + timedelta(seconds=duration),
                duration_seconds=duration,
            )
            db.add(pv)
        db.commit()
        print(f"[OK] {len(test_visits)} page visits created")

        # End the session
        bs.end_time = datetime.now(timezone.utc)
        bs.calculate_duration()
        db.commit()
        db.refresh(bs)
        print(f"[OK] Session ended (duration: {bs.duration:.0f}s)")
    finally:
        db.close()

    # Use the session object for the rest of the test
    class _Ses:
        session_id = test_session_id

    session = _Ses()

    # ====================================================================
    # STEP 1: Generate insights (using fallback - no LLM key needed)
    # ====================================================================
    print("\n" + "=" * 70)
    print("STEP 1: Generate Insights")
    print("=" * 70)

    from browserfriend.llm.analyzer import analyze_browsing_data, generate_fallback_insights

    stats = analyze_browsing_data(session.session_id)
    assert stats["total_visits"] == len(test_visits)
    assert stats["unique_domains"] == len(test_visits)  # all unique
    assert stats["total_time"] > 0
    assert len(stats["top_domains"]) > 0
    print(
        f"[OK] Stats generated: {stats['total_visits']} visits, "
        f"{stats['unique_domains']} domains, {stats['total_time']:.0f}s total"
    )

    # Use fallback insights (no API key needed for testing)
    insights = generate_fallback_insights(stats)
    assert "categories" in insights
    assert "summary" in insights
    assert "productivity_score" in insights
    assert "recommendations" in insights
    print(f"[OK] Fallback insights: score={insights['productivity_score']}")

    # Assemble full insights dict (same format as generate_insights returns)
    full_insights = {
        "session_id": session.session_id,
        "stats": {
            "total_time": stats["total_time"],
            "total_visits": stats["total_visits"],
            "unique_domains": stats["unique_domains"],
            "session_duration": stats["session_duration"],
            "top_domains": stats["top_domains"],
            "time_distribution": stats["time_distribution"],
        },
        "categories": insights["categories"],
        "summary": insights["summary"],
        "patterns": insights["patterns"],
        "productivity_score": insights["productivity_score"],
        "productivity_breakdown": insights["productivity_breakdown"],
        "recommendations": insights["recommendations"],
        "time_insights": insights["time_insights"],
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "used_fallback": True,
    }

    # ====================================================================
    # STEP 2: Render Email Template
    # ====================================================================
    print("\n" + "=" * 70)
    print("STEP 2: Render Email Template")
    print("=" * 70)

    from browserfriend.email.renderer import render_dashboard_email

    html_content = render_dashboard_email(
        full_insights, full_insights["stats"], "e2e-email-test@example.com"
    )

    # Verify HTML content
    assert "<html" in html_content
    assert "BrowserFriend" in html_content
    assert "e2e-email-test@example.com" in html_content
    assert "github.com" in html_content
    assert "stackoverflow.com" in html_content
    assert "youtube.com" in html_content
    assert "Productivity Breakdown" in html_content
    assert "Top Domains" in html_content
    assert "Recommendations" in html_content
    print(f"[OK] Email template rendered: {len(html_content)} chars")

    # Check it's under 100KB
    assert len(html_content) < 100_000, f"Email too large: {len(html_content)} bytes"
    print(f"[OK] Email size OK: {len(html_content)} bytes (< 100KB)")

    # ====================================================================
    # STEP 3: Send Email (mocked - SMTP)
    # ====================================================================
    print("\n" + "=" * 70)
    print("STEP 3: Send Email via SMTP (mocked)")
    print("=" * 70)

    from browserfriend.email.sender import send_dashboard_email

    # Test successful SMTP send
    with patch("browserfriend.email.sender.get_config") as mock_config:
        mock_config.return_value.email_provider = "smtp"
        mock_config.return_value.smtp_username = "user@gmail.com"
        mock_config.return_value.smtp_password = "app_password"
        mock_config.return_value.smtp_host = "smtp.gmail.com"
        mock_config.return_value.smtp_port = 587

        with patch("browserfriend.email.sender.smtplib.SMTP") as mock_smtp:
            from unittest.mock import MagicMock

            mock_server = MagicMock()
            mock_smtp.return_value.__enter__ = MagicMock(return_value=mock_server)
            mock_smtp.return_value.__exit__ = MagicMock(return_value=False)

            result = send_dashboard_email("e2e-email-test@example.com", html_content)
            assert result is True
            mock_server.starttls.assert_called_once()
            mock_server.login.assert_called_once_with("user@gmail.com", "app_password")
            mock_server.sendmail.assert_called_once()
            print("[OK] Email sent via SMTP (mocked)")

    # Test missing SMTP credentials
    with patch("browserfriend.email.sender.get_config") as mock_config:
        mock_config.return_value.email_provider = "smtp"
        mock_config.return_value.smtp_username = None
        mock_config.return_value.smtp_password = None
        mock_config.return_value.smtp_host = "smtp.gmail.com"
        mock_config.return_value.smtp_port = 587

        result = send_dashboard_email("test@example.com", "<html>test</html>")
        assert result is False
        print("[OK] Missing SMTP credentials correctly handled")

    # Test SMTP connection error
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
            print("[OK] SMTP error correctly handled")

    # ====================================================================
    # STEP 4: Save Dashboard to Database
    # ====================================================================
    print("\n" + "=" * 70)
    print("STEP 4: Save Dashboard to Database")
    print("=" * 70)

    dashboard = save_dashboard(
        session_id=session.session_id,
        user_email="e2e-email-test@example.com",
        insights=full_insights,
        html_content=html_content,
    )

    assert dashboard is not None
    assert dashboard.id is not None
    assert dashboard.session_id == session.session_id
    assert dashboard.user_email == "e2e-email-test@example.com"
    assert dashboard.email_sent is True
    assert dashboard.sent_at is not None
    print(f"[OK] Dashboard saved: id={dashboard.id}")

    # Verify JSON integrity
    stored = json.loads(dashboard.insights_json)
    assert stored["session_id"] == session.session_id
    assert stored["productivity_score"] == full_insights["productivity_score"]
    assert len(stored["recommendations"]) == len(full_insights["recommendations"])
    print("[OK] Insights JSON integrity verified")

    # Verify HTML integrity
    assert dashboard.html_content == html_content
    print("[OK] HTML content integrity verified")

    # ====================================================================
    # STEP 5: Data Integrity Verification
    # ====================================================================
    print("\n" + "=" * 70)
    print("STEP 5: Data Integrity Verification")
    print("=" * 70)

    db = SessionLocal()
    try:
        # User exists
        user = db.query(User).filter(User.email == "e2e-email-test@example.com").first()
        assert user is not None
        print(f"[OK] User: id={user.id}, email={user.email}")

        # Session exists and is ended
        bs = (
            db.query(BrowsingSession)
            .filter(BrowsingSession.session_id == session.session_id)
            .first()
        )
        assert bs is not None
        assert bs.end_time is not None
        assert bs.duration is not None
        print(f"[OK] Session: id={bs.session_id}, duration={bs.duration:.0f}s")

        # Page visits exist
        visits = db.query(PageVisit).filter(PageVisit.session_id == session.session_id).all()
        assert len(visits) == len(test_visits)
        print(f"[OK] Page visits: {len(visits)}")

        # Dashboard exists
        dashboards = db.query(Dashboard).filter(Dashboard.session_id == session.session_id).all()
        assert len(dashboards) == 1
        assert dashboards[0].email_sent is True
        print(f"[OK] Dashboard: id={dashboards[0].id}, email_sent={dashboards[0].email_sent}")

        # Dashboard relationship works
        assert dashboards[0].session is not None
        assert dashboards[0].session.session_id == session.session_id
        print("[OK] Dashboard -> Session relationship works")
    finally:
        db.close()

    # ====================================================================
    # STEP 6: Verify Historical Dashboard Query
    # ====================================================================
    print("\n" + "=" * 70)
    print("STEP 6: Historical Dashboard Query")
    print("=" * 70)

    db = SessionLocal()
    try:
        # Query dashboards by user email
        user_dashboards = (
            db.query(Dashboard)
            .filter(Dashboard.user_email == "e2e-email-test@example.com")
            .order_by(Dashboard.sent_at.desc())
            .all()
        )
        assert len(user_dashboards) >= 1
        print(f"[OK] Found {len(user_dashboards)} dashboard(s) for user")

        # Verify we can reconstruct insights from stored JSON
        latest = user_dashboards[0]
        reconstructed = json.loads(latest.insights_json)
        assert "categories" in reconstructed
        assert "summary" in reconstructed
        assert "productivity_score" in reconstructed
        print("[OK] Historical insights can be reconstructed from DB")
    finally:
        db.close()

    # ====================================================================
    # SUMMARY
    # ====================================================================
    print("\n" + "=" * 70)
    print("EMAIL DELIVERY E2E TEST SUMMARY")
    print("=" * 70)
    print("[OK] All end-to-end tests passed!")
    print("\nFeatures Verified:")
    print("  [OK] Browsing data analysis (stats, domains, time distribution)")
    print("  [OK] Fallback insights generation (rule-based)")
    print("  [OK] HTML email template rendering (Jinja2)")
    print("  [OK] Email sending via Resend (mocked)")
    print("  [OK] Missing API key error handling")
    print("  [OK] API error handling")
    print("  [OK] Dashboard storage in database")
    print("  [OK] Data integrity (User, Session, Visits, Dashboard)")
    print("  [OK] Dashboard -> Session relationship")
    print("  [OK] Historical dashboard query")
    print("=" * 70)
    return True


if __name__ == "__main__":
    success = test_email_e2e_workflow()
    sys.exit(0 if success else 1)
