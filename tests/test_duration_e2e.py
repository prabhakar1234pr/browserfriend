"""End-to-end tests for the --duration flag feature (Issue #12).

Tests the complete workflow:
  1. Duration parsing (valid & invalid)
  2. bf start --duration sets up auto-stop metadata
  3. bf status shows auto-stop remaining time
  4. bf stop cancels the duration monitor
  5. PID file stores duration info and is backward compatible
"""

import json
from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock, patch

import psutil
import pytest
from typer.testing import CliRunner

from browserfriend.cli import (
    MONITOR_PID_FILE,
    PID_DIR,
    PID_FILE,
    _format_duration_human,
    _read_pid_data,
    _write_pid_data,
    app,
    parse_duration,
)

runner = CliRunner()


@pytest.fixture(autouse=True)
def _clean_pid_files():
    """Remove PID + monitor PID files before and after each test."""
    for f in (PID_FILE, MONITOR_PID_FILE):
        if f.exists():
            f.unlink()
    yield
    for f in (PID_FILE, MONITOR_PID_FILE):
        if f.exists():
            f.unlink()


# ========================================================================
# STEP 1: Duration Parsing E2E
# ========================================================================


class TestDurationParsingE2E:
    """E2E: verify all accepted and rejected duration formats."""

    @pytest.mark.parametrize(
        "input_str,expected_seconds",
        [
            ("1m", 60),
            ("5m", 300),
            ("30m", 1800),
            ("1h", 3600),
            ("2h", 7200),
            ("8h", 28800),
            ("1d", 86400),
            ("7d", 604800),
            # case-insensitive
            ("5M", 300),
            ("2H", 7200),
            ("1D", 86400),
        ],
    )
    def test_valid_formats(self, input_str, expected_seconds):
        assert parse_duration(input_str) == expected_seconds

    @pytest.mark.parametrize(
        "bad_input",
        [
            "5x",
            "2hours",
            "-5m",
            "",
            "100",
            "m",
            "abc",
            "5 m",  # space between value and unit
            "1.5h",  # decimal
        ],
    )
    def test_invalid_formats_rejected(self, bad_input):
        with pytest.raises(ValueError, match="Invalid duration format"):
            parse_duration(bad_input)

    def test_human_format_round_trip(self):
        """parse_duration -> _format_duration_human produces readable output."""
        secs = parse_duration("2h")
        human = _format_duration_human(secs)
        assert "2 hours" in human


# ========================================================================
# STEP 2: bf start --duration E2E
# ========================================================================


class TestStartWithDurationE2E:
    """E2E: bf start --duration correctly sets up server + auto-stop."""

    def test_start_with_5m_duration(self):
        """Full start flow with --duration 5m."""
        mock_proc = MagicMock()
        mock_proc.pid = 7777

        mock_session = MagicMock()
        mock_session.session_id = "e2e-dur-sess-001"

        with (
            patch("browserfriend.cli._read_pid", return_value=None),
            patch("browserfriend.cli._is_server_running", return_value=True),
            patch("browserfriend.cli._get_user_email", return_value="e2e@example.com"),
            patch("browserfriend.database.init_database"),
            patch("browserfriend.database.create_new_session", return_value=mock_session),
            patch("browserfriend.cli.subprocess.Popen", return_value=mock_proc),
            patch("browserfriend.cli.time.sleep"),
            patch("browserfriend.cli._start_duration_monitor") as mock_monitor,
        ):
            result = runner.invoke(app, ["start", "--duration", "5m"])

            assert result.exit_code == 0
            # Should show auto-stop scheduled message
            assert "5 minutes" in result.stdout
            assert "auto-stop" in result.stdout.lower()
            # Should show session ID
            assert "e2e-dur-sess-001" in result.stdout

            # Monitor should have been started
            mock_monitor.assert_called_once_with("e2e-dur-sess-001", "e2e@example.com", 300)

        # PID file should contain duration info
        data = _read_pid_data()
        assert data is not None
        assert data["pid"] == 7777
        assert data["duration_seconds"] == 300
        assert data["auto_stop_at"] is not None

    def test_start_without_duration(self):
        """Start without --duration should not set auto-stop."""
        mock_proc = MagicMock()
        mock_proc.pid = 8888

        mock_session = MagicMock()
        mock_session.session_id = "e2e-nodur-sess"

        with (
            patch("browserfriend.cli._read_pid", return_value=None),
            patch("browserfriend.cli._is_server_running", return_value=True),
            patch("browserfriend.cli._get_user_email", return_value="e2e@example.com"),
            patch("browserfriend.database.init_database"),
            patch("browserfriend.database.create_new_session", return_value=mock_session),
            patch("browserfriend.cli.subprocess.Popen", return_value=mock_proc),
            patch("browserfriend.cli.time.sleep"),
        ):
            result = runner.invoke(app, ["start"])

            assert result.exit_code == 0
            assert "runs until you stop it" in result.stdout.lower()

        data = _read_pid_data()
        assert data is not None
        assert data["duration_seconds"] is None
        assert data["auto_stop_at"] is None

    def test_start_invalid_duration_rejected(self):
        """Invalid duration should be rejected before any server logic runs."""
        with patch("browserfriend.cli._get_user_email", return_value="e2e@example.com"):
            result = runner.invoke(app, ["start", "--duration", "5x"])
            assert result.exit_code == 1
            assert "invalid" in result.stdout.lower()

    def test_start_short_flag_d(self):
        """Short flag -d should work the same as --duration."""
        mock_proc = MagicMock()
        mock_proc.pid = 6666

        mock_session = MagicMock()
        mock_session.session_id = "e2e-short-flag"

        with (
            patch("browserfriend.cli._read_pid", return_value=None),
            patch("browserfriend.cli._is_server_running", return_value=True),
            patch("browserfriend.cli._get_user_email", return_value="e2e@example.com"),
            patch("browserfriend.database.init_database"),
            patch("browserfriend.database.create_new_session", return_value=mock_session),
            patch("browserfriend.cli.subprocess.Popen", return_value=mock_proc),
            patch("browserfriend.cli.time.sleep"),
            patch("browserfriend.cli._start_duration_monitor"),
        ):
            result = runner.invoke(app, ["start", "-d", "2h"])
            assert result.exit_code == 0
            assert "2 hours" in result.stdout


# ========================================================================
# STEP 3: bf status with auto-stop E2E
# ========================================================================


class TestStatusAutoStopE2E:
    """E2E: bf status shows auto-stop remaining time."""

    def test_status_shows_remaining_time(self):
        """When auto-stop is scheduled, status should show time remaining."""
        future = (datetime.now(timezone.utc) + timedelta(hours=2)).isoformat()

        with (
            patch("browserfriend.cli._read_pid", return_value=1234),
            patch("browserfriend.cli._is_server_running", return_value=True),
            patch(
                "browserfriend.cli._read_pid_data",
                return_value={
                    "pid": 1234,
                    "session_id": "e2e-status-sess",
                    "started_at": datetime.now(timezone.utc).isoformat(),
                    "duration_seconds": 7200,
                    "auto_stop_at": future,
                },
            ),
            patch("browserfriend.cli._get_user_email", return_value="e2e@example.com"),
            patch("browserfriend.database.get_current_session", return_value=None),
            patch("browserfriend.database.get_visits_by_user", return_value=[]),
        ):
            result = runner.invoke(app, ["status"])
            assert result.exit_code == 0
            assert "RUNNING" in result.stdout
            assert "auto-stop" in result.stdout.lower()

    def test_status_no_autostop_when_no_duration(self):
        """Status should NOT show auto-stop when running without duration."""
        with (
            patch("browserfriend.cli._read_pid", return_value=1234),
            patch("browserfriend.cli._is_server_running", return_value=True),
            patch(
                "browserfriend.cli._read_pid_data",
                return_value={
                    "pid": 1234,
                    "session_id": "e2e-no-dur",
                    "started_at": datetime.now(timezone.utc).isoformat(),
                    "duration_seconds": None,
                    "auto_stop_at": None,
                },
            ),
            patch("browserfriend.cli._get_user_email", return_value="e2e@example.com"),
            patch("browserfriend.database.get_current_session", return_value=None),
            patch("browserfriend.database.get_visits_by_user", return_value=[]),
        ):
            result = runner.invoke(app, ["status"])
            assert result.exit_code == 0
            assert "auto-stop" not in result.stdout.lower()


# ========================================================================
# STEP 4: bf stop cancels monitor E2E
# ========================================================================


class TestStopCancelsMonitorE2E:
    """E2E: bf stop kills the duration monitor when user stops early."""

    def test_early_stop_cancels_monitor(self):
        """Stopping early should terminate the monitor process and clean up."""
        mock_server = MagicMock()
        mock_server.is_running.return_value = True
        mock_server.status.return_value = "running"
        mock_server.cmdline.return_value = ["python", "main.py", "browserfriend"]
        mock_server.wait.return_value = None

        mock_monitor = MagicMock()
        mock_monitor.terminate.return_value = None

        # Simulate monitor PID file exists
        PID_DIR.mkdir(parents=True, exist_ok=True)
        MONITOR_PID_FILE.write_text("4444")

        def mock_psutil_process(pid):
            if pid == 1234:
                return mock_server
            if pid == 4444:
                return mock_monitor
            raise psutil.NoSuchProcess(pid)

        with (
            patch(
                "browserfriend.cli._read_pid_data",
                return_value={
                    "pid": 1234,
                    "session_id": "e2e-stop-sess",
                    "started_at": datetime.now(timezone.utc).isoformat(),
                    "duration_seconds": 3600,
                    "auto_stop_at": (datetime.now(timezone.utc) + timedelta(hours=1)).isoformat(),
                },
            ),
            patch("browserfriend.cli._is_server_running", return_value=True),
            patch("browserfriend.cli._get_user_email", return_value="e2e@example.com"),
            patch("browserfriend.cli._delete_pid"),
            patch("browserfriend.cli.psutil.Process", side_effect=mock_psutil_process),
            patch("browserfriend.database.end_session", return_value=None),
        ):
            result = runner.invoke(app, ["stop"])

            assert "stopped" in result.stdout.lower()
            assert "cancelled auto-stop" in result.stdout.lower()
            mock_monitor.terminate.assert_called_once()

    def test_stop_works_without_monitor(self):
        """Stopping when no monitor is running should work normally."""
        mock_server = MagicMock()
        mock_server.is_running.return_value = True
        mock_server.status.return_value = "running"
        mock_server.cmdline.return_value = ["python", "main.py"]
        mock_server.wait.return_value = None

        MONITOR_PID_FILE.unlink(missing_ok=True)

        with (
            patch(
                "browserfriend.cli._read_pid_data",
                return_value={
                    "pid": 1234,
                    "session_id": "e2e-stop-no-mon",
                    "started_at": datetime.now(timezone.utc).isoformat(),
                },
            ),
            patch("browserfriend.cli._is_server_running", return_value=True),
            patch("browserfriend.cli._get_user_email", return_value="e2e@example.com"),
            patch("browserfriend.cli._delete_pid"),
            patch("browserfriend.cli.psutil.Process", return_value=mock_server),
            patch("browserfriend.database.end_session", return_value=None),
        ):
            result = runner.invoke(app, ["stop"])
            assert "stopped" in result.stdout.lower()
            assert "cancelled" not in result.stdout.lower()


# ========================================================================
# STEP 5: PID file backward compatibility E2E
# ========================================================================


class TestPidFileCompatE2E:
    """E2E: PID file stores duration info and is backward compatible."""

    def test_new_format_with_duration(self):
        """New PID file format includes duration fields."""
        _write_pid_data(
            1234,
            "compat-sess",
            duration_seconds=600,
            auto_stop_at="2026-02-09T22:00:00+00:00",
        )
        raw = json.loads(PID_FILE.read_text())
        assert raw["pid"] == 1234
        assert raw["session_id"] == "compat-sess"
        assert raw["duration_seconds"] == 600
        assert raw["auto_stop_at"] == "2026-02-09T22:00:00+00:00"
        assert "started_at" in raw

    def test_new_format_without_duration(self):
        """PID file without duration stores null values."""
        _write_pid_data(1234, "no-dur-sess")
        raw = json.loads(PID_FILE.read_text())
        assert raw["duration_seconds"] is None
        assert raw["auto_stop_at"] is None

    def test_legacy_format_still_readable(self):
        """Plain integer PID files from older versions are still readable."""
        PID_DIR.mkdir(parents=True, exist_ok=True)
        PID_FILE.write_text("9876")
        data = _read_pid_data()
        assert data is not None
        assert data["pid"] == 9876
        assert data.get("session_id") is None
        assert data.get("duration_seconds") is None


# ========================================================================
# FULL WORKFLOW E2E
# ========================================================================


class TestFullDurationWorkflowE2E:
    """E2E: Complete workflow - start with duration -> status -> early stop."""

    def test_complete_workflow(self):
        """Simulate: start --duration 1h -> check status -> stop early."""
        mock_proc = MagicMock()
        mock_proc.pid = 3333

        mock_session = MagicMock()
        mock_session.session_id = "e2e-full-workflow"

        # --- STEP A: Start with duration ---
        with (
            patch("browserfriend.cli._read_pid", return_value=None),
            patch("browserfriend.cli._is_server_running", return_value=True),
            patch("browserfriend.cli._get_user_email", return_value="workflow@example.com"),
            patch("browserfriend.database.init_database"),
            patch("browserfriend.database.create_new_session", return_value=mock_session),
            patch("browserfriend.cli.subprocess.Popen", return_value=mock_proc),
            patch("browserfriend.cli.time.sleep"),
            patch("browserfriend.cli._start_duration_monitor") as mock_monitor_start,
        ):
            start_result = runner.invoke(app, ["start", "--duration", "1h"])
            assert start_result.exit_code == 0
            assert "1 hour" in start_result.stdout
            assert "auto-stop" in start_result.stdout.lower()
            mock_monitor_start.assert_called_once_with(
                "e2e-full-workflow", "workflow@example.com", 3600
            )

        # Verify PID file has duration info
        pid_data = _read_pid_data()
        assert pid_data["duration_seconds"] == 3600
        assert pid_data["auto_stop_at"] is not None

        # --- STEP B: Check status ---
        with (
            patch("browserfriend.cli._read_pid", return_value=3333),
            patch("browserfriend.cli._is_server_running", return_value=True),
            patch("browserfriend.cli._get_user_email", return_value="workflow@example.com"),
            patch("browserfriend.database.get_current_session", return_value=None),
            patch("browserfriend.database.get_visits_by_user", return_value=[]),
        ):
            status_result = runner.invoke(app, ["status"])
            assert status_result.exit_code == 0
            assert "RUNNING" in status_result.stdout
            assert "auto-stop" in status_result.stdout.lower()

        # --- STEP C: Stop early ---
        mock_server = MagicMock()
        mock_server.is_running.return_value = True
        mock_server.status.return_value = "running"
        mock_server.cmdline.return_value = ["python", "main.py"]
        mock_server.wait.return_value = None

        mock_monitor_proc = MagicMock()

        # Write a monitor PID file
        MONITOR_PID_FILE.write_text("5555")

        def psutil_factory(pid):
            if pid == 3333:
                return mock_server
            if pid == 5555:
                return mock_monitor_proc
            raise psutil.NoSuchProcess(pid)

        with (
            patch("browserfriend.cli._is_server_running", return_value=True),
            patch("browserfriend.cli._get_user_email", return_value="workflow@example.com"),
            patch("browserfriend.cli._delete_pid"),
            patch("browserfriend.cli.psutil.Process", side_effect=psutil_factory),
            patch("browserfriend.database.end_session", return_value=None),
        ):
            stop_result = runner.invoke(app, ["stop"])
            assert "stopped" in stop_result.stdout.lower()
            assert "cancelled auto-stop" in stop_result.stdout.lower()
            mock_monitor_proc.terminate.assert_called_once()
