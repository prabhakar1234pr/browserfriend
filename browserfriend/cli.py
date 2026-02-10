"""CLI implementation for BrowserFriend using Typer.

Provides commands: setup, start, stop, status, dashboard.
"""

import json
import logging
import os
import re
import signal
import subprocess
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Optional

import psutil
import typer

from browserfriend.config import get_config

# ---------------------------------------------------------------------------
# Logging setup
# ---------------------------------------------------------------------------

LOG_FORMAT = "%(asctime)s - %(name)s - %(levelname)s - [%(filename)s:%(lineno)d] - %(message)s"
DATE_FORMAT = "%Y-%m-%d %H:%M:%S"


def _setup_cli_logging() -> logging.Logger:
    """Configure CLI logging with maximum verbosity."""
    config = get_config()

    # Ensure config dir exists for log file
    config_dir = Path.home() / ".browserfriend"
    config_dir.mkdir(exist_ok=True)

    log_file = config.log_file or str(config_dir / "cli.log")

    handlers: list[logging.Handler] = [
        logging.StreamHandler(sys.stderr),
        logging.FileHandler(log_file),
    ]

    logging.basicConfig(
        level=logging.DEBUG,
        format=LOG_FORMAT,
        datefmt=DATE_FORMAT,
        handlers=handlers,
        force=True,
    )

    # Set all browserfriend loggers to DEBUG
    logging.getLogger("browserfriend").setLevel(logging.DEBUG)

    logger = logging.getLogger("browserfriend.cli")
    logger.setLevel(logging.DEBUG)
    logger.info("CLI logging initialised  (level=DEBUG, log_file=%s)", log_file)
    return logger


logger = _setup_cli_logging()

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

EMAIL_REGEX = re.compile(r"^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$")

# ---------------------------------------------------------------------------
# Typer app
# ---------------------------------------------------------------------------

app = typer.Typer(
    name="bf",
    help="BrowserFriend – track, analyse and understand your browsing habits.",
    add_completion=False,
)

# ---------------------------------------------------------------------------
# Helpers – PID file management (JSON: pid, session_id, started_at)
# ---------------------------------------------------------------------------

PID_DIR = Path.home() / ".browserfriend"
PID_FILE = PID_DIR / "server.pid"


def _read_pid_data() -> Optional[dict]:
    """Read PID data (pid, session_id, started_at) from JSON PID file.

    Also handles legacy plain-integer PID files for backward compat.
    Returns None if file missing or invalid.
    """
    logger.debug("Attempting to read PID file: %s", PID_FILE)
    if not PID_FILE.exists():
        logger.debug("PID file does not exist")
        return None
    try:
        raw = PID_FILE.read_text().strip()
        # Try JSON dict first
        try:
            data = json.loads(raw)
            if isinstance(data, dict):
                logger.debug("Read PID data from JSON: %s", data)
                return data
            # json.loads("555") returns int – treat as legacy
            raise json.JSONDecodeError("not a dict", raw, 0)
        except json.JSONDecodeError:
            # Legacy plain-integer format
            pid = int(raw)
            logger.debug("Read legacy PID %d from file (no session_id)", pid)
            return {"pid": pid, "session_id": None, "started_at": None}
    except (ValueError, OSError) as exc:
        logger.warning("Failed to read PID file: %s", exc)
        return None


def _read_pid() -> Optional[int]:
    """Read PID from the PID file. Returns None if file missing or invalid."""
    data = _read_pid_data()
    if data is None:
        return None
    return data.get("pid")


def _write_pid_data(
    pid: int,
    session_id: str,
    duration_seconds: Optional[int] = None,
    auto_stop_at: Optional[str] = None,
) -> None:
    """Write PID + session_id + started_at + duration info to the PID file as JSON."""
    data = {
        "pid": pid,
        "session_id": session_id,
        "started_at": datetime.now(timezone.utc).isoformat(),
        "duration_seconds": duration_seconds,
        "auto_stop_at": auto_stop_at,
    }
    logger.debug("Writing PID data to %s: %s", PID_FILE, data)
    PID_DIR.mkdir(exist_ok=True)
    PID_FILE.write_text(json.dumps(data))
    logger.info("PID data written to %s (pid=%d, session=%s)", PID_FILE, pid, session_id)


def _write_pid(pid: int) -> None:
    """Write PID to the PID file (legacy helper, prefer _write_pid_data)."""
    logger.debug("Writing PID %d to %s", pid, PID_FILE)
    PID_DIR.mkdir(exist_ok=True)
    PID_FILE.write_text(str(pid))
    logger.info("PID %d written to %s", pid, PID_FILE)


def _delete_pid() -> None:
    """Delete the PID file."""
    logger.debug("Deleting PID file: %s", PID_FILE)
    try:
        PID_FILE.unlink(missing_ok=True)
        logger.info("PID file deleted")
    except OSError as exc:
        logger.warning("Failed to delete PID file: %s", exc)


def _is_server_running(pid: Optional[int] = None) -> bool:
    """Check if the BrowserFriend server process is running.

    Verifies both that the process exists AND that it is actually our
    server (by inspecting the command line) to avoid false positives
    from PID reuse.  (Issue 4 fix)
    """
    if pid is None:
        pid = _read_pid()
    if pid is None:
        logger.debug("No PID available – server not running")
        return False

    try:
        proc = psutil.Process(pid)

        # Basic liveness check
        if not proc.is_running() or proc.status() == psutil.STATUS_ZOMBIE:
            logger.debug("Process %d not alive (status=%s)", pid, proc.status())
            return False

        # Verify the process is actually our server (Issue 4)
        try:
            cmdline = " ".join(proc.cmdline()).lower()
            logger.debug("Process %d cmdline: %s", pid, cmdline)
            is_ours = "browserfriend" in cmdline or "main.py" in cmdline or "uvicorn" in cmdline
            if not is_ours:
                logger.warning(
                    "Process %d exists but is NOT BrowserFriend server (cmdline: %s). "
                    "Cleaning up stale PID file.",
                    pid,
                    cmdline,
                )
                _delete_pid()
                return False
            logger.debug("Process %d verified as BrowserFriend server", pid)
            return True
        except (psutil.AccessDenied, psutil.ZombieProcess) as exc:
            # Cannot read cmdline – fall back to assuming it's ours
            logger.debug(
                "Cannot read cmdline for PID %d (%s), assuming it is our server",
                pid,
                exc,
            )
            return True

    except (psutil.NoSuchProcess, psutil.AccessDenied) as exc:
        logger.debug("Process %d not accessible: %s", pid, exc)
        return False


def _get_user_email() -> Optional[str]:
    """Retrieve the first user email from the database."""
    logger.debug("Querying database for user email")
    try:
        from browserfriend.database import User, get_session_factory

        SessionLocal = get_session_factory()
        session = SessionLocal()
        try:
            user = session.query(User).order_by(User.id.desc()).first()
            if user:
                logger.debug("Found user email: %s", user.email)
                return user.email
            logger.debug("No user found in database")
            return None
        finally:
            session.close()
    except Exception as exc:
        logger.error("Failed to query user email: %s", exc, exc_info=True)
        return None


def _format_duration(seconds: float) -> str:
    """Format seconds into HH:MM:SS string."""
    hours = int(seconds // 3600)
    minutes = int((seconds % 3600) // 60)
    secs = int(seconds % 60)
    return f"{hours:02d}:{minutes:02d}:{secs:02d}"


def parse_duration(duration_str: str) -> int:
    """Parse duration string to seconds.

    Supported formats:
        5m, 30m    -> minutes
        2h, 8h     -> hours
        1d, 7d     -> days

    Args:
        duration_str: Duration string (e.g., "5m", "2h", "1d")

    Returns:
        Duration in seconds

    Raises:
        ValueError: If format is invalid
    """
    match = re.match(r"^(\d+)([mhd])$", duration_str.strip().lower())
    if not match:
        raise ValueError(
            f"Invalid duration format: '{duration_str}'. "
            "Use format like: 5m (minutes), 2h (hours), 1d (days)"
        )

    value = int(match.group(1))
    unit = match.group(2)

    if value <= 0:
        raise ValueError("Duration value must be positive.")

    multipliers = {"m": 60, "h": 3600, "d": 86400}
    seconds = value * multipliers[unit]

    logger.debug("Parsed duration '%s' -> %d seconds", duration_str, seconds)
    return seconds


def _format_duration_human(seconds: int) -> str:
    """Format seconds into a human-friendly string.

    Examples:
        300  -> "5 minutes"
        7200 -> "2 hours"
        90   -> "1 minute 30 seconds"
    """
    if seconds >= 86400:
        days = seconds // 86400
        return f"{days} day{'s' if days != 1 else ''}"
    if seconds >= 3600:
        hours = seconds // 3600
        remaining_min = (seconds % 3600) // 60
        parts = [f"{hours} hour{'s' if hours != 1 else ''}"]
        if remaining_min:
            parts.append(f"{remaining_min} minute{'s' if remaining_min != 1 else ''}")
        return " ".join(parts)
    if seconds >= 60:
        minutes = seconds // 60
        remaining_sec = seconds % 60
        parts = [f"{minutes} minute{'s' if minutes != 1 else ''}"]
        if remaining_sec:
            parts.append(f"{remaining_sec} second{'s' if remaining_sec != 1 else ''}")
        return " ".join(parts)
    return f"{seconds} second{'s' if seconds != 1 else ''}"


# ---------------------------------------------------------------------------
# Command: setup
# ---------------------------------------------------------------------------


@app.command()
def setup() -> None:
    """Initial user configuration and email registration."""
    logger.info("=" * 60)
    logger.info("CLI command: setup")
    logger.info("=" * 60)

    # Ensure tables exist before querying (first-run fix)
    try:
        from browserfriend.database import init_database

        init_database()
    except Exception as exc:
        logger.debug("Could not init database in setup preamble: %s", exc)

    existing_email = _get_user_email()
    if existing_email:
        logger.info("Existing user found: %s", existing_email)
        typer.echo(f"Current email: {existing_email}")
        update = typer.confirm("Do you want to update your email?", default=False)
        if not update:
            logger.info("User chose not to update email")
            typer.echo("Setup unchanged. Current email kept.")
            return
        logger.info("User chose to update email")

    email = typer.prompt("Enter your email address")
    logger.info("User entered email: %s", email)

    # Validate email format with proper regex (Issue 6 fix)
    if not EMAIL_REGEX.match(email):
        logger.error("Invalid email format: %s", email)
        typer.echo("Error: Invalid email format. Please provide a valid email.")
        raise typer.Exit(code=1)

    logger.debug("Email validation passed (regex)")

    # Store in database directly (Issue 9 fix – no dependency on running server)
    try:
        from browserfriend.database import User, get_session_factory, init_database

        logger.debug("Initialising database")
        init_database()

        SessionLocal = get_session_factory()
        session = SessionLocal()
        try:
            logger.debug("Querying for existing user with email: %s", email)
            user = session.query(User).filter(User.email == email).first()
            if user:
                logger.info(
                    "User already exists in database: id=%d, email=%s",
                    user.id,
                    user.email,
                )
                typer.echo(f"User already registered: {user.email}")
            else:
                logger.info("Creating new user with email: %s", email)
                user = User(email=email)
                session.add(user)
                session.commit()
                session.refresh(user)
                logger.info(
                    "User created: id=%d, email=%s, created_at=%s",
                    user.id,
                    user.email,
                    user.created_at,
                )
                typer.echo(f"User registered successfully: {user.email}")
        finally:
            session.close()
            logger.debug("Database session closed")

    except Exception as exc:
        logger.error("Setup failed: %s", exc, exc_info=True)
        typer.echo(f"Error during setup: {exc}")
        raise typer.Exit(code=1)

    typer.echo("\nNext step: Run `bf start` to begin tracking.")
    logger.info("Setup command completed successfully")


# ---------------------------------------------------------------------------
# Command: start
# ---------------------------------------------------------------------------


@app.command()
def start(
    duration: Optional[str] = typer.Option(
        None,
        "--duration",
        "-d",
        help="Auto-stop after duration (e.g., 5m, 2h, 1d). If not set, runs until manually stopped.",
    ),
) -> None:
    """Start the BrowserFriend server as a background process."""
    logger.info("=" * 60)
    logger.info("CLI command: start")
    logger.info("=" * 60)

    config = get_config()
    logger.debug(
        "Config loaded: host=%s, port=%d, db=%s",
        config.server_host,
        config.server_port,
        config.database_path,
    )

    # Check if server is already running
    pid = _read_pid()
    if pid and _is_server_running(pid):
        logger.warning("Server already running with PID %d", pid)
        typer.echo(f"Error: Server is already running (PID {pid}).")
        typer.echo("Run `bf stop` first to stop the current server.")
        raise typer.Exit(code=1)

    # Clean up stale PID file if process is dead
    if pid:
        logger.info("Stale PID file found (PID %d not running), cleaning up", pid)
        _delete_pid()

    # Parse duration if provided
    duration_seconds = None
    auto_stop_time = None

    if duration:
        try:
            duration_seconds = parse_duration(duration)
            auto_stop_time = datetime.now(timezone.utc) + timedelta(seconds=duration_seconds)
            typer.echo(f"Auto-stop scheduled in {_format_duration_human(duration_seconds)}")
            typer.echo(f"Will stop at: {auto_stop_time.strftime('%I:%M %p')}")
        except ValueError as e:
            logger.error("Invalid duration: %s", e)
            typer.echo(f"Error: {e}")
            raise typer.Exit(code=1)

    # Ensure user is configured
    user_email = _get_user_email()
    if not user_email:
        logger.error("No user configured – setup required")
        typer.echo("Error: No user configured. Run `bf setup` first.")
        raise typer.Exit(code=1)
    logger.info("User email for session: %s", user_email)

    # Initialise database tables
    try:
        from browserfriend.database import init_database

        logger.debug("Ensuring database tables exist")
        init_database()
        logger.info("Database tables ready")
    except Exception as exc:
        logger.error("Database initialisation failed: %s", exc, exc_info=True)
        typer.echo(f"Error: Failed to initialise database: {exc}")
        raise typer.Exit(code=1)

    # ── Issue 3 fix: create session BEFORE starting server ──
    # This prevents the race where the extension hits the server before a
    # session exists, causing get_or_create_active_session to spawn a
    # duplicate session.
    try:
        from browserfriend.database import create_new_session

        logger.info("Creating browsing session before server start")
        browsing_session = create_new_session(user_email)
        session_id = browsing_session.session_id
        logger.info("Browsing session created: session_id=%s, user=%s", session_id, user_email)
    except Exception as exc:
        logger.error("Failed to create browsing session: %s", exc, exc_info=True)
        typer.echo(f"Error: Failed to create session: {exc}")
        raise typer.Exit(code=1)

    # Start server as background process
    logger.info("Starting FastAPI server in background")
    try:
        python_exe = sys.executable
        logger.debug("Python executable: %s", python_exe)

        # Use CREATE_NEW_PROCESS_GROUP on Windows, start_new_session on Unix
        kwargs: dict = {}
        if sys.platform == "win32":
            logger.debug("Windows platform detected – using CREATE_NEW_PROCESS_GROUP")
            kwargs["creationflags"] = subprocess.CREATE_NEW_PROCESS_GROUP
        else:
            logger.debug("Unix platform detected – using start_new_session=True")
            kwargs["start_new_session"] = True

        # Use main.py as the entry point for the server
        main_py = Path(__file__).parent.parent / "main.py"
        logger.debug("Server entry point: %s", main_py)

        proc = subprocess.Popen(
            [python_exe, str(main_py)],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            cwd=str(main_py.parent),
            **kwargs,
        )
        logger.info("Server process started with PID %d", proc.pid)

        # Issue 7 fix: store pid + session_id + duration info in PID file
        _write_pid_data(
            proc.pid,
            session_id,
            duration_seconds=duration_seconds,
            auto_stop_at=auto_stop_time.isoformat() if auto_stop_time else None,
        )

    except Exception as exc:
        logger.error("Failed to start server process: %s", exc, exc_info=True)
        # Issue 3 fix: clean up the session we just created
        logger.info("Cleaning up session %s after server start failure", session_id)
        try:
            from browserfriend.database import end_session

            end_session(session_id)
            logger.info("Cleaned up session %s", session_id)
        except Exception as cleanup_exc:
            logger.warning("Failed to clean up session: %s", cleanup_exc)
        typer.echo(f"Error: Failed to start server: {exc}")
        raise typer.Exit(code=1)

    # Wait briefly and verify server started
    logger.debug("Waiting 2 seconds for server to start")
    time.sleep(2)
    if not _is_server_running(proc.pid):
        logger.error("Server process died shortly after starting (PID %d)", proc.pid)
        _delete_pid()
        # Issue 3 fix: clean up session on failure
        try:
            from browserfriend.database import end_session

            end_session(session_id)
        except Exception:
            pass
        typer.echo("Error: Server failed to start. Check logs for details.")
        raise typer.Exit(code=1)
    logger.info("Server process verified running (PID %d)", proc.pid)

    # If duration provided, start monitor process
    if duration_seconds:
        _start_duration_monitor(session_id, user_email, duration_seconds)
        typer.echo(
            f"Server started — {_format_duration_human(duration_seconds)} countdown begins "
            "when the extension starts tracking"
        )
    else:
        typer.echo("Server started (runs until you stop it)")

    typer.echo(f"URL: http://{config.server_host}:{config.server_port}")
    typer.echo(f"Session ID: {session_id}")
    logger.info("Start command completed successfully")


# ---------------------------------------------------------------------------
# Duration monitor
# ---------------------------------------------------------------------------

MONITOR_PID_FILE = PID_DIR / "monitor.pid"


def _start_duration_monitor(session_id: str, user_email: str, duration_seconds: int) -> None:
    """Start a background process that auto-stops the server after *duration_seconds*.

    The monitor sleeps in a loop (checking every 60 s) until the absolute stop
    time is reached, then triggers the stop -> dashboard -> email workflow.

    Args:
        session_id: Current browsing session ID.
        user_email: User email for dashboard generation.
        duration_seconds: How long to wait before auto-stop.
    """
    project_root = Path(__file__).parent.parent

    monitor_script = f"""
import time, sys, os, json
from pathlib import Path
from datetime import datetime, timezone

project_root = Path(r"{project_root}")
sys.path.insert(0, str(project_root))

from dotenv import load_dotenv
load_dotenv(project_root / ".env")

# --- Phase 1: Wait for the extension to start tracking ---
# The countdown should not begin until actual browsing activity is recorded.
print("Waiting for extension to start tracking ...")

WAIT_TIMEOUT = 300  # give up after 5 minutes of no activity
wait_start = datetime.now(timezone.utc).timestamp()
tracking_started = False

from browserfriend.database import get_session_factory, init_database
from browserfriend.database import PageVisit
init_database()

while datetime.now(timezone.utc).timestamp() - wait_start < WAIT_TIMEOUT:
    try:
        SessionLocal = get_session_factory()
        db = SessionLocal()
        try:
            visit = db.query(PageVisit).filter(PageVisit.session_id == "{session_id}").first()
            if visit:
                tracking_started = True
                print("Extension connected — first activity detected!")
                break
        finally:
            db.close()
    except Exception:
        pass
    time.sleep(3)

if not tracking_started:
    print("No tracking activity detected within 5 minutes — starting countdown anyway")

# --- Phase 2: Actual countdown starts NOW ---
auto_stop_at = datetime.now(timezone.utc).timestamp() + {duration_seconds}
stop_time_iso = datetime.fromtimestamp(auto_stop_at, tz=timezone.utc).isoformat()

# Update the PID file so bf status shows accurate remaining time
pid_file = Path.home() / ".browserfriend" / "server.pid"
if pid_file.exists():
    try:
        data = json.loads(pid_file.read_text())
        data["auto_stop_at"] = stop_time_iso
        pid_file.write_text(json.dumps(data))
    except Exception:
        pass

print(f"Countdown started — waiting {duration_seconds} seconds ...")

while datetime.now(timezone.utc).timestamp() < auto_stop_at:
    time.sleep(min(60, max(1, auto_stop_at - datetime.now(timezone.utc).timestamp())))

print("Duration reached! Auto-stopping server ...")

# --- Stop the server process ---
pid_file = Path.home() / ".browserfriend" / "server.pid"
stopped = False
if pid_file.exists():
    try:
        import psutil
        data = json.loads(pid_file.read_text())
        pid = data.get("pid")
        if pid:
            try:
                proc = psutil.Process(pid)
                proc.terminate()
                proc.wait(timeout=5)
                stopped = True
                print(f"Server process {{pid}} terminated")
            except Exception as e:
                print(f"Could not terminate server: {{e}}")
        pid_file.unlink(missing_ok=True)
    except Exception as e:
        print(f"Error reading PID file: {{e}}")
else:
    print("No PID file found – server may already be stopped")
    stopped = True

# --- End the browsing session in the database ---
print("Ending browsing session ...")
try:
    from browserfriend.database import end_session
    ended = end_session("{session_id}")
    if ended:
        print(f"Session ended (duration: {{ended.duration:.0f}}s)")
    else:
        print("Session was already ended or not found")
except Exception as e:
    print(f"Warning: could not end session: {{e}}")

# --- Generate dashboard and send email ---
print("Generating dashboard ...")
try:
    from browserfriend.llm.analyzer import generate_insights
    insights = generate_insights("{session_id}")

    from browserfriend.email.renderer import render_dashboard_email
    html_content = render_dashboard_email(insights, insights["stats"], "{user_email}")

    from browserfriend.email.sender import send_dashboard_email
    if send_dashboard_email("{user_email}", html_content):
        print(f"Dashboard sent to {user_email}")
        from browserfriend.database import save_dashboard
        save_dashboard("{session_id}", "{user_email}", insights, html_content)
        print("Dashboard saved to database")
    else:
        print("Failed to send email – check RESEND_API_KEY")
except Exception as e:
    print(f"Error generating dashboard: {{e}}")
    import traceback
    traceback.print_exc()

# Clean up own PID file
monitor_pid = Path.home() / ".browserfriend" / "monitor.pid"
monitor_pid.unlink(missing_ok=True)

print("Auto-stop sequence complete!")
"""

    kwargs: dict = {}
    if sys.platform == "win32":
        kwargs["creationflags"] = subprocess.CREATE_NEW_PROCESS_GROUP
    else:
        kwargs["start_new_session"] = True

    monitor_process = subprocess.Popen(
        [sys.executable, "-c", monitor_script],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        **kwargs,
    )

    logger.info(
        "Started duration monitor (PID: %d) for %d seconds",
        monitor_process.pid,
        duration_seconds,
    )

    PID_DIR.mkdir(exist_ok=True)
    MONITOR_PID_FILE.write_text(str(monitor_process.pid))


# ---------------------------------------------------------------------------
# Command: stop
# ---------------------------------------------------------------------------


@app.command()
def stop() -> None:
    """Stop the BrowserFriend server and display session summary."""
    logger.info("=" * 60)
    logger.info("CLI command: stop")
    logger.info("=" * 60)

    # Issue 7 fix: read full PID data (pid + session_id)
    pid_data = _read_pid_data()
    if pid_data is None:
        logger.warning("No PID file found – server not running")
        typer.echo("Error: Server is not running (no PID file found).")
        raise typer.Exit(code=1)

    pid = pid_data.get("pid")
    stored_session_id = pid_data.get("session_id")
    logger.info(
        "PID data from file: pid=%s, session_id=%s, started_at=%s",
        pid,
        stored_session_id,
        pid_data.get("started_at"),
    )

    if pid is None:
        logger.warning("PID file exists but has no pid value")
        _delete_pid()
        typer.echo("Error: Corrupt PID file. Cleaned up.")
        raise typer.Exit(code=1)

    if not _is_server_running(pid):
        logger.warning("Process %d is not running – cleaning up stale PID", pid)
        _delete_pid()
        typer.echo("Error: Server process not found. Cleaned up stale PID file.")
        raise typer.Exit(code=1)

    # End the active browsing session
    # Issue 8 fix: use stored session_id from PID file when available
    user_email = _get_user_email()
    session_summary = None
    if user_email:
        logger.info("Ending active session for user: %s", user_email)
        try:
            from browserfriend.database import (
                end_session,
                get_current_session,
                get_top_domains_by_user,
                get_visits_by_session,
            )

            # Prefer stored session_id (Issue 8), fall back to DB query
            target_session_id = stored_session_id
            if target_session_id:
                logger.info("Using stored session_id from PID file: %s", target_session_id)
            else:
                logger.info("No session_id in PID file, querying DB for active session")
                current_session = get_current_session(user_email)
                target_session_id = current_session.session_id if current_session else None

            if target_session_id:
                logger.info("Ending session: %s", target_session_id)
                ended = end_session(target_session_id)
                if ended:
                    visits = get_visits_by_session(ended.session_id)
                    top_domains = get_top_domains_by_user(user_email, limit=3)
                    duration = ended.duration or 0.0
                    session_summary = {
                        "session_id": ended.session_id,
                        "duration": duration,
                        "visit_count": len(visits),
                        "top_domains": top_domains,
                    }
                    logger.info(
                        "Session ended: id=%s, duration=%.1fs, visits=%d, top_domains=%s",
                        ended.session_id,
                        duration,
                        len(visits),
                        top_domains,
                    )
                else:
                    logger.warning(
                        "end_session returned None for session %s (may already be ended)",
                        target_session_id,
                    )
            else:
                logger.info("No active session found for user %s", user_email)
        except Exception as exc:
            logger.error("Failed to end session: %s", exc, exc_info=True)
            typer.echo(f"Warning: Could not end session cleanly: {exc}")

    # Issue 5 fix: verify process identity before terminating
    logger.info("Terminating server process PID %d", pid)
    try:
        proc = psutil.Process(pid)

        # Verify it's our server before killing (Issue 5)
        try:
            cmdline = " ".join(proc.cmdline()).lower()
            if (
                "browserfriend" not in cmdline
                and "main.py" not in cmdline
                and "uvicorn" not in cmdline
            ):
                logger.warning(
                    "Process %d is NOT BrowserFriend server (cmdline: %s). "
                    "Will not terminate. Cleaning up PID file.",
                    pid,
                    cmdline,
                )
                _delete_pid()
                typer.echo(
                    f"Warning: Process {pid} is not BrowserFriend server. PID file cleaned up."
                )
                return
        except (psutil.AccessDenied, psutil.ZombieProcess):
            logger.debug("Cannot verify cmdline for PID %d, proceeding with termination", pid)

        if sys.platform == "win32":
            logger.debug("Windows: calling proc.terminate()")
            proc.terminate()
        else:
            logger.debug("Unix: sending SIGTERM")
            os.kill(pid, signal.SIGTERM)

        logger.debug("Waiting up to 5 seconds for process to exit")
        proc.wait(timeout=5)
        logger.info("Server process %d terminated gracefully", pid)
    except psutil.TimeoutExpired:
        logger.warning("Process %d did not exit in time – force killing", pid)
        proc.kill()
        logger.info("Process %d force killed", pid)
    except (psutil.NoSuchProcess, psutil.AccessDenied) as exc:
        logger.warning("Could not terminate process %d: %s", pid, exc)

    _delete_pid()

    # Kill duration monitor if running
    if MONITOR_PID_FILE.exists():
        try:
            monitor_pid = int(MONITOR_PID_FILE.read_text().strip())
            monitor_proc = psutil.Process(monitor_pid)
            monitor_proc.terminate()
            MONITOR_PID_FILE.unlink(missing_ok=True)
            typer.echo("Cancelled auto-stop timer")
            logger.info("Cancelled duration monitor (PID %d)", monitor_pid)
        except (psutil.NoSuchProcess, ValueError):
            MONITOR_PID_FILE.unlink(missing_ok=True)
            logger.debug("Monitor process already gone, cleaned up PID file")
        except psutil.AccessDenied:
            logger.warning("Cannot terminate monitor process – access denied")

    # Display summary
    typer.echo("Server stopped.")
    if session_summary:
        typer.echo("")
        typer.echo("--- Session Summary ---")
        typer.echo(f"  Session ID : {session_summary['session_id']}")
        typer.echo(f"  Duration   : {_format_duration(session_summary['duration'])}")
        typer.echo(f"  Visits     : {session_summary['visit_count']}")
        if session_summary["top_domains"]:
            typer.echo("  Top Domains:")
            for domain, count in session_summary["top_domains"]:
                typer.echo(f"    - {domain} ({count} visits)")
        typer.echo("-----------------------")

    logger.info("Stop command completed successfully")


# ---------------------------------------------------------------------------
# Command: status
# ---------------------------------------------------------------------------


@app.command()
def status() -> None:
    """Display current server and session status."""
    logger.info("=" * 60)
    logger.info("CLI command: status")
    logger.info("=" * 60)

    config = get_config()

    pid = _read_pid()
    server_running = _is_server_running(pid) if pid else False

    # Fallback: try pinging the status endpoint
    if not server_running:
        logger.debug("PID check says not running, trying HTTP ping fallback")
        try:
            import urllib.request

            url = f"http://{config.server_host}:{config.server_port}/api/status"
            logger.debug("Pinging %s", url)
            req = urllib.request.Request(url, method="GET")
            with urllib.request.urlopen(req, timeout=2) as resp:
                if resp.status == 200:
                    server_running = True
                    logger.info("HTTP ping succeeded – server is running")
        except Exception as exc:
            logger.debug("HTTP ping failed: %s", exc)

    typer.echo("=== BrowserFriend Status ===")
    typer.echo("")

    if server_running:
        typer.echo(f"  Server     : RUNNING (PID {pid})")
        typer.echo(f"  URL        : http://{config.server_host}:{config.server_port}")

        # Show auto-stop info if scheduled
        try:
            pid_data = _read_pid_data()
            if pid_data and pid_data.get("auto_stop_at"):
                auto_stop = datetime.fromisoformat(pid_data["auto_stop_at"])
                now = datetime.now(timezone.utc)
                remaining = (auto_stop - now).total_seconds()

                if remaining > 0:
                    typer.echo(f"  Auto-stop  : in {_format_duration_human(int(remaining))}")
                    typer.echo(f"  Stops at   : {auto_stop.strftime('%I:%M %p')}")
                else:
                    typer.echo("  Auto-stop  : imminent (time reached)")
        except (json.JSONDecodeError, KeyError, ValueError) as exc:
            logger.debug("Could not read auto-stop info: %s", exc)
    else:
        typer.echo("  Server     : STOPPED")

    typer.echo(f"  Database   : {config.database_path}")

    # Session and visit info
    user_email = _get_user_email()
    if user_email:
        logger.debug("Querying session info for user: %s", user_email)
        try:
            from browserfriend.database import (
                PageVisit,
                get_current_session,
                get_session_factory,
                get_visits_by_session,
                get_visits_by_user,
            )

            active_session = get_current_session(user_email)
            if active_session:
                visits_in_session = get_visits_by_session(active_session.session_id)
                typer.echo("")
                typer.echo("  --- Active Session ---")
                typer.echo(f"  Session ID : {active_session.session_id}")
                typer.echo(f"  Started    : {active_session.start_time}")
                typer.echo(f"  Visits     : {len(visits_in_session)}")

                # Issue 10 fix: warn if session may be stale (>30 min inactive)
                if visits_in_session:
                    SessionLocal = get_session_factory()
                    db_session = SessionLocal()
                    try:
                        last_visit = (
                            db_session.query(PageVisit)
                            .filter(PageVisit.session_id == active_session.session_id)
                            .order_by(PageVisit.end_time.desc())
                            .first()
                        )
                        if last_visit and last_visit.end_time:
                            last_end = last_visit.end_time
                            if last_end.tzinfo is None:
                                last_end = last_end.replace(tzinfo=timezone.utc)
                            time_since = datetime.now(timezone.utc) - last_end
                            if time_since > timedelta(minutes=30):
                                typer.echo(
                                    f"  WARNING: Session may be stale (>30 min inactive, "
                                    f"last activity {_format_duration(time_since.total_seconds())} ago)"
                                )
                                logger.warning(
                                    "Active session %s may be stale (last activity %s ago)",
                                    active_session.session_id,
                                    time_since,
                                )
                    finally:
                        db_session.close()

                logger.info(
                    "Active session: id=%s, start=%s, visits=%d",
                    active_session.session_id,
                    active_session.start_time,
                    len(visits_in_session),
                )
            else:
                typer.echo("")
                typer.echo("  No active session.")
                logger.info("No active session for user %s", user_email)

            all_visits = get_visits_by_user(user_email)
            typer.echo(f"  Total visits (all time): {len(all_visits)}")
            logger.info("Total all-time visits: %d", len(all_visits))
        except Exception as exc:
            logger.error("Failed to query session/visit info: %s", exc, exc_info=True)
            typer.echo(f"  (Could not query session info: {exc})")
    else:
        typer.echo("")
        typer.echo("  No user configured. Run `bf setup` first.")
        logger.info("No user configured")

    typer.echo("")
    typer.echo("============================")
    logger.info("Status command completed successfully")


# ---------------------------------------------------------------------------
# Command: dashboard
# ---------------------------------------------------------------------------


@app.command()
def dashboard(
    session_id: Optional[str] = typer.Option(None, help="Specific session ID (default: latest)"),
) -> None:
    """Generate AI-powered dashboard with browsing insights and send via email."""
    logger.info("=" * 60)
    logger.info("CLI command: dashboard")
    logger.info("=" * 60)

    user_email = _get_user_email()
    if not user_email:
        logger.error("No user configured")
        typer.echo("Error: No user configured. Run `bf setup` first.")
        raise typer.Exit(code=1)
    logger.info("User email: %s", user_email)

    # Check if server is running
    pid = _read_pid()
    if pid and _is_server_running(pid):
        logger.warning("Server is still running – warning user")
        typer.echo(
            "Warning: Server is currently running. Consider stopping it first with `bf stop`."
        )

    # Get session for this user
    try:
        from browserfriend.database import BrowsingSession, get_session_factory

        SessionLocal = get_session_factory()
        db_session = SessionLocal()
        try:
            if session_id:
                session = (
                    db_session.query(BrowsingSession)
                    .filter(BrowsingSession.session_id == session_id)
                    .first()
                )
            else:
                session = (
                    db_session.query(BrowsingSession)
                    .filter(BrowsingSession.user_email == user_email)
                    .order_by(BrowsingSession.start_time.desc())
                    .first()
                )
            if not session:
                logger.error("No browsing sessions found for user: %s", user_email)
                typer.echo(
                    "Error: No browsing sessions found. Start tracking first with `bf start`."
                )
                raise typer.Exit(code=1)

            target_session_id = session.session_id
            logger.info("Using session: %s", target_session_id)
        finally:
            db_session.close()
    except typer.Exit:
        raise
    except Exception as exc:
        logger.error("Failed to query sessions: %s", exc, exc_info=True)
        typer.echo(f"Error: Failed to query sessions: {exc}")
        raise typer.Exit(code=1)

    # Generate insights
    try:
        from browserfriend.llm import InsufficientDataError, LLMError
        from browserfriend.llm.analyzer import generate_insights

        insights = generate_insights(target_session_id)

    except InsufficientDataError as exc:
        logger.error("Insufficient data: %s", exc)
        typer.echo(f"Error: {exc}")
        raise typer.Exit(code=1)
    except LLMError as exc:
        logger.error("LLM error: %s", exc)
        typer.echo(f"Error: {exc}")
        raise typer.Exit(code=1)
    except Exception as exc:
        logger.error("Dashboard generation failed: %s", exc, exc_info=True)
        typer.echo(f"Error: Failed to generate dashboard: {exc}")
        raise typer.Exit(code=1)

    # Render HTML email
    try:
        from browserfriend.email.renderer import render_dashboard_email

        html_content = render_dashboard_email(insights, insights["stats"], user_email)
        logger.info("Email template rendered (%d chars)", len(html_content))
    except Exception as exc:
        logger.error("Email rendering failed: %s", exc, exc_info=True)
        typer.echo(f"Error: Failed to render email template: {exc}")
        raise typer.Exit(code=1)

    # Send email
    try:
        from browserfriend.email.sender import send_dashboard_email

        if send_dashboard_email(user_email, html_content):
            typer.echo(f"Check your email! Dashboard sent to {user_email}")
            logger.info("Dashboard email sent to %s", user_email)
        else:
            typer.echo("Failed to send email. Check your SMTP settings in .env")
            logger.error("send_dashboard_email returned False")
    except Exception as exc:
        logger.error("Email sending failed: %s", exc, exc_info=True)
        typer.echo(f"Error: Failed to send email: {exc}")

    # Save dashboard to database
    try:
        from browserfriend.database import save_dashboard

        save_dashboard(target_session_id, user_email, insights, html_content)
        logger.info("Dashboard saved to database")
    except Exception as exc:
        logger.warning("Failed to save dashboard to database: %s", exc)

    logger.info("Dashboard command completed successfully")


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------


def cli_main() -> None:
    """Entry point for the CLI."""
    logger.debug("CLI entry point invoked with args: %s", sys.argv)
    app()


if __name__ == "__main__":
    cli_main()
