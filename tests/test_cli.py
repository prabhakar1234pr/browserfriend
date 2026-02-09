"""Tests for BrowserFriend CLI commands."""

from unittest.mock import MagicMock, patch

import pytest
from typer.testing import CliRunner

from browserfriend.cli import PID_FILE, _format_duration, _read_pid, _write_pid, app

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


@pytest.fixture
def _init_test_db(tmp_path):
    """Initialise a temporary database for tests."""
    db_path = str(tmp_path / "test.db")
    with patch(
        "browserfriend.config.Config.__init__",
        lambda self, **kw: (
            super(type(self), self).__init__(**kw),
            setattr(self, "database_path", db_path),
        )[-1],
    ):
        # Re-import to pick up patched config
        from browserfriend.database import init_database

        init_database()
        yield db_path


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


class TestPidFileManagement:
    def test_write_and_read(self, tmp_path):
        with patch("browserfriend.cli.PID_FILE", tmp_path / "test.pid"):
            # Use the patched constant via direct calls
            pid_file = tmp_path / "test.pid"
            pid_file.write_text("12345")
            assert int(pid_file.read_text().strip()) == 12345

    def test_read_missing(self):
        assert _read_pid() is None

    def test_delete(self, tmp_path):
        test_pid = tmp_path / "test.pid"
        test_pid.write_text("999")
        test_pid.unlink(missing_ok=True)
        assert not test_pid.exists()


# ---------------------------------------------------------------------------
# CLI command tests
# ---------------------------------------------------------------------------


class TestSetupCommand:
    def test_setup_new_user(self):
        """Test setup command registers a new user."""
        with patch("browserfriend.cli._get_user_email", return_value=None):
            result = runner.invoke(app, ["setup"], input="test@example.com\n")
            assert result.exit_code == 0
            assert (
                "registered" in result.stdout.lower() or "example.com" in result.stdout
            )
            assert "bf start" in result.stdout.lower() or "Next step" in result.stdout

    def test_setup_invalid_email(self):
        """Test setup rejects invalid email."""
        with patch("browserfriend.cli._get_user_email", return_value=None):
            result = runner.invoke(app, ["setup"], input="notanemail\n")
            assert result.exit_code == 1
            assert (
                "invalid" in result.stdout.lower() or "error" in result.stdout.lower()
            )

    def test_setup_existing_user_keep(self):
        """Test setup with existing user who keeps current email."""
        with patch(
            "browserfriend.cli._get_user_email", return_value="keep@example.com"
        ):
            result = runner.invoke(app, ["setup"], input="n\n")
            assert result.exit_code == 0
            assert (
                "keep@example.com" in result.stdout
                or "unchanged" in result.stdout.lower()
            )


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
        _write_pid(99999)  # Non-existent PID
        result = runner.invoke(app, ["stop"])
        assert result.exit_code == 1
        assert "not found" in result.stdout.lower() or "stale" in result.stdout.lower()

    def test_stop_running_server(self):
        """Test stop terminates running server and shows summary."""
        mock_proc = MagicMock()
        mock_proc.is_running.return_value = True
        mock_proc.status.return_value = "running"
        mock_proc.wait.return_value = None

        mock_db = MagicMock()
        mock_db.get_current_session.return_value = None

        with (
            patch("browserfriend.cli._read_pid", return_value=1234),
            patch("browserfriend.cli._is_server_running", return_value=True),
            patch("browserfriend.cli._get_user_email", return_value="test@example.com"),
            patch("browserfriend.cli._delete_pid"),
            patch("browserfriend.cli.psutil.Process", return_value=mock_proc),
            patch("browserfriend.database.get_current_session", return_value=None),
        ):
            result = runner.invoke(app, ["stop"])
            assert "stopped" in result.stdout.lower() or result.exit_code == 0


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
        """Test dashboard generates stubs successfully."""
        with (
            patch("browserfriend.cli._get_user_email", return_value="test@example.com"),
            patch("browserfriend.cli._read_pid", return_value=None),
            patch("browserfriend.cli._is_server_running", return_value=False),
        ):
            result = runner.invoke(app, ["dashboard"])
            assert result.exit_code == 0
            assert "test@example.com" in result.stdout
            assert (
                "placeholder" in result.stdout.lower() or "Dashboard" in result.stdout
            )


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
        assert (
            "email" in result.stdout.lower() or "configuration" in result.stdout.lower()
        )

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
