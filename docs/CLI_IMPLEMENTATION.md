# CLI Implementation Documentation

## Overview

BrowserFriend CLI (`bf`) is a Typer-based command-line interface that provides user-friendly commands for setup, server management, session tracking, and dashboard generation.

**Entry Point**: `bf` (installed via `[project.scripts]` in `pyproject.toml`)  
**Module**: `browserfriend/cli.py`  
**Issue**: [#4 - Implement CLI Commands](https://github.com/prabhakar1234pr/browserfriend/issues/4)

---

## Commands

### `bf setup`

**Purpose**: Initial user configuration and email registration.

**Behavior**:
1. Checks if a user already exists in the database
2. If exists, shows current email and asks for update confirmation
3. Prompts for email address
4. Validates email using regex (`^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$`)
5. Stores user directly in database (no server dependency)
6. Displays success message and next steps

**Error Handling**:
- Invalid email format rejected with clear message
- Database errors caught and reported
- Duplicate email handled gracefully (shows "already registered")

---

### `bf start`

**Purpose**: Start the FastAPI server as a background daemon process.

**Behavior**:
1. Checks if server is already running (PID file + process verification)
2. Cleans up stale PID files if process is dead
3. Verifies user is configured (else directs to `bf setup`)
4. Initializes database tables
5. **Creates browsing session BEFORE starting server** (prevents race condition)
6. Starts server via `subprocess.Popen` (detached, cross-platform)
7. Writes JSON PID file with `{pid, session_id, started_at}`
8. Waits 2 seconds and verifies server is alive
9. Cleans up session if server fails to start

**Cross-Platform Support**:
- Windows: `CREATE_NEW_PROCESS_GROUP` flag
- Unix/Mac: `start_new_session=True`

**PID File Format** (JSON):
```json
{
  "pid": 12345,
  "session_id": "uuid-string",
  "started_at": "2026-02-09T10:00:00+00:00"
}
```

---

### `bf stop`

**Purpose**: Gracefully stop the server and display session summary.

**Behavior**:
1. Reads JSON PID file (pid + session_id)
2. Verifies process exists AND is actually BrowserFriend (cmdline check)
3. Ends the browsing session using stored `session_id` from PID file
4. Queries session statistics (duration, visit count, top domains)
5. Sends SIGTERM (Unix) or `terminate()` (Windows)
6. Waits up to 5 seconds for graceful shutdown; force kills if needed
7. Deletes PID file
8. Displays formatted session summary

**Session Summary Output**:
```
Server stopped.

--- Session Summary ---
  Session ID : abc-123-def
  Duration   : 01:23:45
  Visits     : 42
  Top Domains:
    - github.com (15 visits)
    - stackoverflow.com (12 visits)
    - docs.python.org (8 visits)
-----------------------
```

**Process Verification**:
- Checks cmdline contains `browserfriend`, `main.py`, or `uvicorn`
- Prevents killing wrong process if OS reused the PID
- Cleans up PID file if process belongs to something else

---

### `bf status`

**Purpose**: Display current server and session status.

**Behavior**:
1. Checks server status via PID file + process verification
2. Falls back to HTTP ping (`/api/status`) if PID check fails
3. Shows server running/stopped state
4. Shows database path
5. If user exists, queries and displays:
   - Active session ID, start time, visit count
   - Stale session warning (>30 min inactive)
   - Total all-time visit count

**Stale Session Detection**:
- Queries last `PageVisit.end_time` for the active session
- If >30 minutes ago, displays warning to the user

---

### `bf dashboard`

**Purpose**: Generate dashboard and send via email (stub).

**Behavior**:
1. Verifies user is configured
2. Warns if server is still running
3. Shows informative placeholder with references to Issues #5 and #6
4. Describes what the feature will do when implemented

---

## Architecture

### Module Structure

```
browserfriend/
├── cli.py              # CLI entry point with Typer app (this file)
├── config.py           # Configuration management (Pydantic)
├── database.py         # SQLAlchemy models + query functions
├── server/
│   └── app.py          # FastAPI application
├── dashboard.py        # Dashboard generation (stub)
└── email_service.py    # Email sending (stub)
```

### Dependencies

| Package | Purpose |
|---------|---------|
| `typer` | CLI framework |
| `psutil` | Cross-platform process management |
| `subprocess` | Background server execution |
| `json` | PID file serialization |
| `re` | Email validation regex |
| `pathlib` | Cross-platform path handling |

### PID File Location

`~/.browserfriend/server.pid`

### Database Integration

The CLI uses these functions from `database.py`:
- `init_database()` — Create tables
- `create_new_session(email)` — Create browsing session
- `get_current_session(email)` — Get active session
- `end_session(session_id)` — End and calculate duration
- `get_visits_by_session(id)` — Get visits for summary
- `get_top_domains_by_user(email, limit)` — Top domains
- `get_visits_by_user(email)` — All-time visit count

### Logging

All CLI operations log at DEBUG level to both:
- **stderr** (console output)
- **`~/.browserfriend/cli.log`** (file)

Log format: `TIMESTAMP - MODULE - LEVEL - [FILE:LINE] - MESSAGE`

Every function entry, exit, decision branch, database query, and error is logged.

---

## Issues Fixed

### Critical

| # | Issue | Fix |
|---|-------|-----|
| 3 | Server started before session created (race condition) | Create session BEFORE starting server; clean up session on failure |
| 4 | `_is_server_running()` didn't verify process identity | Check cmdline for `browserfriend`/`main.py`/`uvicorn`; clean stale PID on mismatch |
| 5 | `stop()` didn't verify process before killing | Verify cmdline before terminate; refuse to kill wrong process |

### High Priority

| # | Issue | Fix |
|---|-------|-----|
| 6 | Email validation too simple (`@` and `.` check) | Proper regex: `^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$` |
| 7 | PID file only stored PID, not session_id | JSON format: `{pid, session_id, started_at}` with legacy backward compat |
| 8 | `stop()` queried DB for session instead of using known ID | Use `session_id` from PID file; fall back to DB query only if missing |

### Medium Priority

| # | Issue | Fix |
|---|-------|-----|
| 9 | `setup()` had no error handling for server-not-running | Direct database insert (no server dependency) |
| 10 | `status()` showed stale session as "active" | Check last PageVisit.end_time; warn if >30 min inactive |
| 11 | Dashboard stub was uninformative | Added Issue #5/#6 references and feature description |

---

## Testing

### Test File: `tests/test_cli.py`

**47 total tests** (38 CLI + 9 existing):

| Test Class | Count | What it covers |
|------------|-------|---------------|
| `TestFormatDuration` | 5 | Duration formatting (0s, seconds, minutes, hours, 24h) |
| `TestEmailRegex` | 2 | Valid and invalid email patterns (Issue 6) |
| `TestPidFileManagement` | 3 | Read, write, delete PID files |
| `TestPidDataJsonFormat` | 3 | JSON PID file read/write + legacy backward compat (Issue 7) |
| `TestIsServerRunning` | 4 | No PID, dead process, wrong process, correct process (Issue 4) |
| `TestSetupCommand` | 5 | New user, invalid emails (3 cases), existing user keep (Issue 6) |
| `TestStartCommand` | 2 | No user configured, server already running |
| `TestStopCommand` | 4 | Not running, stale PID, running server, stored session_id (Issues 7/8) |
| `TestStatusCommand` | 2 | Server stopped, user with no server |
| `TestDashboardCommand` | 2 | No user, success stub with issue references (Issue 11) |
| `TestHelpText` | 6 | All command help texts render correctly |

### Running Tests

```bash
uv run pytest tests/ -v
```

---

## User Flow

```
1. bf setup          → Enter email → Stored in DB
2. bf start          → Session created → Server started → PID file written
3. (browse the web)  → Extension sends data → Server tracks visits
4. bf status         → See server state, active session, visit count
5. bf stop           → Session ended → Server stopped → Summary displayed
6. bf dashboard      → (stub) Generate insights and email
```

---

**Document Version**: 1.0  
**Created**: 2026-02-09  
**Status**: Implementation Complete – All Issues Resolved
