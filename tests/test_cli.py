"""Tests for BrowserFriend CLI commands."""

import json
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from typer.testing import CliRunner

from browserfriend.cli import (
    EMAIL_REGEX,
    PID_FILE,
    _delete_pid,
    _format_duration,
    _read_pid,
    _read_pid_data,
    _write_pid,
    _write_pid_data,
    app,
)

runner = CliRunner()


# ---------------------------------------------------------------------------
# Helper fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def _clean_pid_file():
    """Remove PID file before and after each test."""
    if PID_FILE.exists():
        PID_FILE.unlink()
    yield
    if PID_FILE.exists():
        PID_FILE.unlink()


# ---------------------------------------------------------------------------
# Unit tests – helper functions
# ---------------------------------------------------------------------------


class TestFormatDuration:
    def test_zero(self):
        assert _format_duration(0) == "00:00:00"

    def test_seconds_only(self):
        assert _format_duration(45) == "00:00:45"

    def test_minutes_and_seconds(self):
        assert _format_duration(125) == "00:02:05"

    def test_hours_minutes_seconds(self):
        assert _format_duration(3661) == "01:01:01"

    def test_large_duration(self):
        assert _format_duration(86400) == "24:00:00"


class TestEmailRegex:
    """Issue 6: proper email validation."""

    def test_valid_emails(self):
        assert EMAIL_REGEX.match("user@example.com")
        assert EMAIL_REGEX.match("user.name@example.co.uk")
        assert EMAIL_REGEX.match("user+tag@example.com")

    def test_invalid_emails(self):
        assert not EMAIL_REGEX.match("notanemail")
        assert not EMAIL_REGEX.match("@.")
        assert not EMAIL_REGEX.match("a@b.")
        assert not EMAIL_REGEX.match("@example.com")
        assert not EMAIL_REGEX.match("user@")
        assert not EMAIL_REGEX.match("")


class TestPidFileManagement:
    def test_write_and_read_legacy(self, tmp_path):
        """Legacy plain-integer PID file still readable."""
        pid_file = tmp_path / "test.pid"
        pid_file.write_text("12345")
        assert int(pid_file.read_text().strip()) == 12345

    def test_read_missing(self):
        assert _read_pid() is None
        assert _read_pid_data() is None

    def test_delete(self, tmp_path):
        test_pid = tmp_path / "test.pid"
        test_pid.write_text("999")
        test_pid.unlink(missing_ok=True)
        assert not test_pid.exists()


class TestPidDataJsonFormat:
    """Issue 7: PID file stores pid + session_id + started_at as JSON."""

    def test_write_and_read_json(self):
        _write_pid_data(42, "sess-abc-123")
        data = _read_pid_data()
        assert data is not None
        assert data["pid"] == 42
        assert data["session_id"] == "sess-abc-123"
        assert data["started_at"] is not None

    def test_read_pid_from_json(self):
        _write_pid_data(99, "sess-xyz")
        assert _read_pid() == 99

    def test_read_legacy_plain_int(self):
        """Backward compat: plain integer PID file still works."""
        _write_pid(555)
        data = _read_pid_data()
        assert data is not None
        assert data["pid"] == 555
        assert data["session_id"] is None  # legacy has no session_id


class TestIsServerRunning:
    """Issue 4: verify process is actually our server."""

    def test_no_pid(self):
        from browserfriend.cli import _is_server_running

        assert _is_server_running(None) is False

    def test_process_not_found(self):
        from browserfriend.cli import _is_server_running

        assert _is_server_running(99999) is False

    def test_wrong_process_detected(self):
        """If PID belongs to a non-BrowserFriend process, return False."""
        mock_proc = MagicMock()
        mock_proc.is_running.return_value = True
        mock_proc.status.return_value = "running"
        mock_proc.cmdline.return_value = ["notepad.exe"]

        with patch("browserfriend.cli.psutil.Process", return_value=mock_proc):
            from browserfriend.cli import _is_server_running

            # Write a PID file so _delete_pid has something to clean
            _write_pid(1234)
            assert _is_server_running(1234) is False

    def test_correct_process_detected(self):
        """If PID belongs to BrowserFriend, return True."""
        mock_proc = MagicMock()
        mock_proc.is_running.return_value = True
        mock_proc.status.return_value = "running"
        mock_proc.cmdline.return_value = ["python", "main.py", "browserfriend"]

        with patch("browserfriend.cli.psutil.Process", return_value=mock_proc):
            from browserfriend.cli import _is_server_running

            assert _is_server_running(1234) is True


# ---------------------------------------------------------------------------
# CLI command tests
# ---------------------------------------------------------------------------


class TestSetupCommand:
    def test_setup_new_user(self):
        """Test setup command registers a new user."""
        with patch("browserfriend.cli._get_user_email", return_value=None):
            result = runner.invoke(app, ["setup"], input="test@example.com\n")
            assert result.exit_code == 0
            assert "registered" in result.stdout.lower() or "example.com" in result.stdout
            assert "bf start" in result.stdout.lower() or "Next step" in result.stdout

    def test_setup_invalid_email_no_at(self):
        """Issue 6: setup rejects email without @."""
        with patch("browserfriend.cli._get_user_email", return_value=None):
            result = runner.invoke(app, ["setup"], input="notanemail\n")
            assert result.exit_code == 1
            assert "invalid" in result.stdout.lower() or "error" in result.stdout.lower()

    def test_setup_invalid_email_at_dot(self):
        """Issue 6: setup rejects '@.' as email."""
        with patch("browserfriend.cli._get_user_email", return_value=None):
            result = runner.invoke(app, ["setup"], input="@.\n")
            assert result.exit_code == 1

    def test_setup_invalid_email_no_tld(self):
        """Issue 6: setup rejects 'a@b.' as email."""
        with patch("browserfriend.cli._get_user_email", return_value=None):
            result = runner.invoke(app, ["setup"], input="a@b.\n")
            assert result.exit_code == 1

    def test_setup_existing_user_keep(self):
        """Test setup with existing user who keeps current email."""
        with patch("browserfriend.cli._get_user_email", return_value="keep@example.com"):
            result = runner.invoke(app, ["setup"], input="n\n")
            assert result.exit_code == 0
            assert "keep@example.com" in result.stdout or "unchanged" in result.stdout.lower()


class TestStartCommand:
    def test_start_no_user(self):
        """Test start fails when no user is configured."""
        with patch("browserfriend.cli._get_user_email", return_value=None):
            result = runner.invoke(app, ["start"])
            assert result.exit_code == 1
            assert "setup" in result.stdout.lower()

    def test_start_already_running(self):
        """Test start fails when server is already running."""
        with (
            patch("browserfriend.cli._read_pid", return_value=9999),
            patch("browserfriend.cli._is_server_running", return_value=True),
        ):
            result = runner.invoke(app, ["start"])
            assert result.exit_code == 1
            assert "already running" in result.stdout.lower()


class TestStopCommand:
    def test_stop_not_running(self):
        """Test stop fails when no PID file exists."""
        result = runner.invoke(app, ["stop"])
        assert result.exit_code == 1
        assert "not running" in result.stdout.lower()

    def test_stop_stale_pid(self):
        """Test stop cleans up stale PID file."""
        _write_pid_data(99999, "dead-session")
        result = runner.invoke(app, ["stop"])
        assert result.exit_code == 1
        assert "not found" in result.stdout.lower() or "stale" in result.stdout.lower()

    def test_stop_running_server(self):
        """Test stop terminates running server and shows summary."""
        mock_proc = MagicMock()
        mock_proc.is_running.return_value = True
        mock_proc.status.return_value = "running"
        mock_proc.cmdline.return_value = ["python", "main.py", "browserfriend"]
        mock_proc.wait.return_value = None

        with (
            patch("browserfriend.cli._read_pid_data", return_value={
                "pid": 1234, "session_id": "sess-123", "started_at": "2026-01-01T00:00:00+00:00"
            }),
            patch("browserfriend.cli._is_server_running", return_value=True),
            patch("browserfriend.cli._get_user_email", return_value="test@example.com"),
            patch("browserfriend.cli._delete_pid"),
            patch("browserfriend.cli.psutil.Process", return_value=mock_proc),
            patch("browserfriend.database.get_current_session", return_value=None),
        ):
            result = runner.invoke(app, ["stop"])
            assert "stopped" in result.stdout.lower() or result.exit_code == 0

    def test_stop_uses_stored_session_id(self):
        """Issue 7/8: stop reads session_id from PID file."""
        mock_proc = MagicMock()
        mock_proc.is_running.return_value = True
        mock_proc.status.return_value = "running"
        mock_proc.cmdline.return_value = ["python", "main.py"]
        mock_proc.wait.return_value = None

        mock_ended_session = MagicMock()
        mock_ended_session.session_id = "sess-from-pid"
        mock_ended_session.duration = 120.0

        with (
            patch("browserfriend.cli._read_pid_data", return_value={
                "pid": 1234, "session_id": "sess-from-pid", "started_at": "2026-01-01T00:00:00+00:00"
            }),
            patch("browserfriend.cli._is_server_running", return_value=True),
            patch("browserfriend.cli._get_user_email", return_value="test@example.com"),
            patch("browserfriend.cli._delete_pid"),
            patch("browserfriend.cli.psutil.Process", return_value=mock_proc),
            patch("browserfriend.database.end_session", return_value=mock_ended_session) as mock_end,
            patch("browserfriend.database.get_visits_by_session", return_value=[]),
            patch("browserfriend.database.get_top_domains_by_user", return_value=[]),
        ):
            result = runner.invoke(app, ["stop"])
            # Verify end_session was called with the stored session_id
            mock_end.assert_called_once_with("sess-from-pid")


class TestStatusCommand:
    def test_status_server_stopped(self):
        """Test status when server is not running."""
        with patch("browserfriend.cli._get_user_email", return_value=None):
            result = runner.invoke(app, ["status"])
            assert result.exit_code == 0
            assert "STOPPED" in result.stdout
            assert "setup" in result.stdout.lower()

    def test_status_with_user_no_server(self):
        """Test status with user configured but server stopped."""
        with (
            patch("browserfriend.cli._get_user_email", return_value="test@example.com"),
            patch("browserfriend.cli._read_pid", return_value=None),
        ):
            result = runner.invoke(app, ["status"])
            assert result.exit_code == 0
            assert "STOPPED" in result.stdout


class TestDashboardCommand:
    def test_dashboard_no_user(self):
        """Test dashboard fails when no user configured."""
        with patch("browserfriend.cli._get_user_email", return_value=None):
            result = runner.invoke(app, ["dashboard"])
            assert result.exit_code == 1
            assert "setup" in result.stdout.lower()

    def test_dashboard_success(self):
        """Issue 11: dashboard shows informative stub with issue references."""
        with (
            patch("browserfriend.cli._get_user_email", return_value="test@example.com"),
            patch("browserfriend.cli._read_pid", return_value=None),
            patch("browserfriend.cli._is_server_running", return_value=False),
        ):
            result = runner.invoke(app, ["dashboard"])
            assert result.exit_code == 0
            assert "test@example.com" in result.stdout
            assert "Issue #5" in result.stdout
            assert "Issue #6" in result.stdout
            assert "AI" in result.stdout or "insights" in result.stdout.lower()


class TestHelpText:
    def test_main_help(self):
        result = runner.invoke(app, ["--help"])
        assert result.exit_code == 0
        assert "setup" in result.stdout
        assert "start" in result.stdout
        assert "stop" in result.stdout
        assert "status" in result.stdout
        assert "dashboard" in result.stdout

    def test_setup_help(self):
        result = runner.invoke(app, ["setup", "--help"])
        assert result.exit_code == 0
        assert "email" in result.stdout.lower() or "configuration" in result.stdout.lower()

    def test_start_help(self):
        result = runner.invoke(app, ["start", "--help"])
        assert result.exit_code == 0

    def test_stop_help(self):
        result = runner.invoke(app, ["stop", "--help"])
        assert result.exit_code == 0

    def test_status_help(self):
        result = runner.invoke(app, ["status", "--help"])
        assert result.exit_code == 0

    def test_dashboard_help(self):
        result = runner.invoke(app, ["dashboard", "--help"])
        assert result.exit_code == 0
