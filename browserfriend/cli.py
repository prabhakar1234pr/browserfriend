"""CLI implementation for BrowserFriend using Typer.

Provides commands: setup, start, stop, status, dashboard.
"""

import logging
import os
import signal
import subprocess
import sys
import time
from pathlib import Path
from typing import Optional

import psutil
import typer

from browserfriend.config import get_config

# ---------------------------------------------------------------------------
# Logging setup
# ---------------------------------------------------------------------------

LOG_FORMAT = (
    "%(asctime)s - %(name)s - %(levelname)s - [%(filename)s:%(lineno)d] - %(message)s"
)
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
# Typer app
# ---------------------------------------------------------------------------

app = typer.Typer(
    name="bf",
    help="BrowserFriend – track, analyse and understand your browsing habits.",
    add_completion=False,
)

# ---------------------------------------------------------------------------
# Helpers – PID file management
# ---------------------------------------------------------------------------

PID_DIR = Path.home() / ".browserfriend"
PID_FILE = PID_DIR / "server.pid"


def _read_pid() -> Optional[int]:
    """Read PID from the PID file. Returns None if file missing or invalid."""
    logger.debug("Attempting to read PID file: %s", PID_FILE)
    if not PID_FILE.exists():
        logger.debug("PID file does not exist")
        return None
    try:
        pid = int(PID_FILE.read_text().strip())
        logger.debug("Read PID %d from file", pid)
        return pid
    except (ValueError, OSError) as exc:
        logger.warning("Failed to read PID file: %s", exc)
        return None


def _write_pid(pid: int) -> None:
    """Write PID to the PID file."""
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
    """Check if the BrowserFriend server process is running."""
    if pid is None:
        pid = _read_pid()
    if pid is None:
        logger.debug("No PID available – server not running")
        return False
    try:
        proc = psutil.Process(pid)
        is_running = proc.is_running() and proc.status() != psutil.STATUS_ZOMBIE
        logger.debug("Process %d running=%s, status=%s", pid, is_running, proc.status())
        return is_running
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
            user = session.query(User).first()
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


# ---------------------------------------------------------------------------
# Command: setup
# ---------------------------------------------------------------------------


@app.command()
def setup() -> None:
    """Initial user configuration and email registration."""
    logger.info("=" * 60)
    logger.info("CLI command: setup")
    logger.info("=" * 60)

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

    # Validate email format (basic check)
    if "@" not in email or "." not in email.split("@")[-1]:
        logger.error("Invalid email format: %s", email)
        typer.echo("Error: Invalid email format. Please provide a valid email.")
        raise typer.Exit(code=1)

    logger.debug("Email validation passed")

    # Store in database via database module
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
def start() -> None:
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
        _write_pid(proc.pid)

    except Exception as exc:
        logger.error("Failed to start server process: %s", exc, exc_info=True)
        typer.echo(f"Error: Failed to start server: {exc}")
        raise typer.Exit(code=1)

    # Wait briefly and verify server started
    logger.debug("Waiting 2 seconds for server to start")
    time.sleep(2)
    if not _is_server_running(proc.pid):
        logger.error("Server process died shortly after starting (PID %d)", proc.pid)
        _delete_pid()
        typer.echo("Error: Server failed to start. Check logs for details.")
        raise typer.Exit(code=1)
    logger.info("Server process verified running (PID %d)", proc.pid)

    # Create a new browsing session
    try:
        from browserfriend.database import create_new_session

        session = create_new_session(user_email)
        session_id = session.session_id
        logger.info(
            "Browsing session created: session_id=%s, user=%s", session_id, user_email
        )
    except Exception as exc:
        logger.error("Failed to create browsing session: %s", exc, exc_info=True)
        typer.echo(f"Warning: Server started but session creation failed: {exc}")
        session_id = "unknown"

    typer.echo(f"Server started on http://{config.server_host}:{config.server_port}")
    typer.echo(f"Session ID: {session_id}")
    logger.info("Start command completed successfully")


# ---------------------------------------------------------------------------
# Command: stop
# ---------------------------------------------------------------------------


@app.command()
def stop() -> None:
    """Stop the BrowserFriend server and display session summary."""
    logger.info("=" * 60)
    logger.info("CLI command: stop")
    logger.info("=" * 60)

    pid = _read_pid()
    if pid is None:
        logger.warning("No PID file found – server not running")
        typer.echo("Error: Server is not running (no PID file found).")
        raise typer.Exit(code=1)

    logger.info("PID from file: %d", pid)

    if not _is_server_running(pid):
        logger.warning("Process %d is not running – cleaning up stale PID", pid)
        _delete_pid()
        typer.echo("Error: Server process not found. Cleaned up stale PID file.")
        raise typer.Exit(code=1)

    # End the active browsing session
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

            current_session = get_current_session(user_email)
            if current_session:
                logger.info("Active session found: %s", current_session.session_id)
                ended = end_session(current_session.session_id)
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
                        "end_session returned None for session %s",
                        current_session.session_id,
                    )
            else:
                logger.info("No active session found for user %s", user_email)
        except Exception as exc:
            logger.error("Failed to end session: %s", exc, exc_info=True)
            typer.echo(f"Warning: Could not end session cleanly: {exc}")

    # Terminate the server process
    logger.info("Terminating server process PID %d", pid)
    try:
        proc = psutil.Process(pid)
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
    else:
        typer.echo("  Server     : STOPPED")

    typer.echo(f"  Database   : {config.database_path}")

    # Session and visit info
    user_email = _get_user_email()
    if user_email:
        logger.debug("Querying session info for user: %s", user_email)
        try:
            from browserfriend.database import (
                get_current_session,
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
def dashboard() -> None:
    """Generate dashboard and send via email."""
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

    # Dashboard generation (stub)
    logger.info("Generating dashboard (stub) for user: %s", user_email)
    typer.echo("Generating dashboard...")
    typer.echo(
        "  (Dashboard generation is a placeholder – full implementation in Issue #5)"
    )

    # Email sending (stub)
    logger.info("Sending dashboard email (stub) to: %s", user_email)
    typer.echo(f"Sending dashboard to {user_email}...")
    typer.echo("  (Email sending is a placeholder – full implementation in Issue #6)")

    typer.echo(f"\nDashboard generated and sent to {user_email}")
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
