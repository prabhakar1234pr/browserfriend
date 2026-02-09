# Vision Document: CLI Implementation for BrowserFriend

## Issue Reference
**GitHub Issue**: [#4 - Implement CLI Commands (setup, start, stop, status, dashboard)](https://github.com/prabhakar1234pr/browserfriend/issues/4)

## Executive Summary
This vision document outlines the implementation plan for a comprehensive command-line interface (CLI) for BrowserFriend using Typer. The CLI will provide user-friendly commands for setup, server management, and dashboard generation, enabling users to interact with BrowserFriend without directly managing the FastAPI server or database.

## Current State

### ✅ Completed Components
- **FastAPI Server**: Fully implemented with REST API endpoints (`/api/status`, `/api/setup`, `/api/track`, `/api/session/end`)
- **Database Models**: Complete SQLAlchemy models for User, BrowsingSession, and PageVisit
- **Session Management**: Automatic session creation and termination with 30-minute inactivity timeout
- **Configuration Management**: Pydantic-based configuration system with environment variable support
- **Database Functions**: Comprehensive database helper functions for queries and operations

### ❌ Missing Components
- **CLI Module**: `browserfriend/cli.py` exists but is empty
- **Background Process Management**: No mechanism to start/stop server as daemon
- **PID File Management**: No process tracking system
- **User Interaction**: No command-line prompts or user-friendly output
- **Session Summary**: No functionality to display session statistics

## Desired End State

### User Experience Flow
1. **Initial Setup**: User runs `bf setup`, enters email, system validates and stores it
2. **Start Tracking**: User runs `bf start`, server starts in background, session begins
3. **Monitor Status**: User can run `bf status` anytime to check server and session state
4. **Stop Tracking**: User runs `bf stop`, server stops gracefully, session summary displayed
5. **Generate Dashboard**: User runs `bf dashboard`, receives email with browsing insights

### Command Specifications

#### 1. `bf setup`
**Purpose**: Initial user configuration and email registration

**Behavior**:
- Prompt user for email address interactively
- Validate email format using Pydantic EmailStr
- If email already configured, show current email and ask for confirmation to update
- Call `/api/setup` endpoint (or direct database insert via `database.py`)
- Display success message with email confirmation
- Provide next steps guidance: "Run `bf start` to begin tracking"

**Implementation Notes**:
- Use Typer's `prompt()` for interactive input
- Leverage existing `/api/setup` endpoint or `database.py` User model
- Allow email update if already configured (with confirmation prompt)
- Handle duplicate email gracefully (user already exists)

#### 2. `bf start`
**Purpose**: Start FastAPI server as background daemon process

**Behavior**:
- Check if server is already running (read PID file)
- If running, show error and exit
- Start FastAPI server using `main.py` in background process
- Generate UUID for session_id
- Create BrowsingSession in database using current user's email
- Save process PID to `~/.browserfriend/server.pid`
- Display:
  - "✅ Server started on http://localhost:8000"
  - "Session ID: {session_id}"
- Server runs detached from terminal (daemon mode)

**Implementation Notes**:
- Use `subprocess.Popen` with `start_new_session=True` for background execution
- Cross-platform PID file management (Windows/Linux/Mac)
- Ensure server starts with proper configuration from `config.py`
- Handle port conflicts gracefully

#### 3. `bf stop`
**Purpose**: Gracefully stop server and display session summary

**Behavior**:
- Read PID from `~/.browserfriend/server.pid`
- Verify process exists and is BrowserFriend server
- Send SIGTERM signal to process
- Wait for graceful shutdown
- Get current active session for user
- End session (set end_time, calculate duration)
- Query session statistics:
  - Duration (formatted as HH:MM:SS)
  - Number of visits tracked
  - Top 3 domains visited
- Display formatted summary
- Delete PID file
- Print "✅ Server stopped"

**Implementation Notes**:
- Use `psutil` for process termination (cross-platform support)
- Query database for session statistics using existing functions
- Format duration and domain list for readability
- Handle case where no active session exists
- Note: Duration flag deferred to post-MVP (start with simple manual stop)

#### 4. `bf status`
**Purpose**: Display current server and session status

**Behavior**:
- Check server status:
  - Read PID file
  - Verify process exists
  - OR ping `/api/status` endpoint as fallback
- Display server status (running/stopped)
- If running:
  - Server URL (from config)
  - Active session ID (from database)
  - Session start time (formatted)
  - Number of visits in current session
- Always show:
  - Database location (from config)
  - Total all-time visits (from database)

**Implementation Notes**:
- Use `psutil` or `os.kill(pid, 0)` to check process existence
- Query database for active session and statistics
- Format timestamps and numbers for readability
- Handle edge cases (no user, no sessions, etc.)

#### 5. `bf dashboard`
**Purpose**: Generate dashboard and send via email

**Behavior**:
- Check if server is running
- If running, stop it first (or show warning)
- Get user email from database (assume single user for now)
- Get latest/current session data
- Call dashboard generation function (stub - Issue #5)
- Call email sending function (stub - Issue #6)
- Print "📧 Dashboard generated and sent to {email}"

**Implementation Notes**:
- Integrate with `dashboard.py` module
- Integrate with `email_service.py` module
- Show informative placeholder messages for stubs, return success
- Handle missing email configuration gracefully
- Provide clear feedback on dashboard generation status

## Technical Architecture

### Module Structure
```
browserfriend/
├── cli.py              # Main CLI entry point with Typer app
├── config.py           # Configuration (already exists)
├── database.py         # Database operations (already exists)
├── server/
│   └── app.py          # FastAPI app (already exists)
├── dashboard.py        # Dashboard generation (exists, may need updates)
└── email_service.py    # Email sending (exists, may need updates)
```

### Key Dependencies
- **Typer**: CLI framework (already in `pyproject.toml`)
- **psutil** (optional): Better process management (may need to add)
- **subprocess/multiprocessing**: Background process execution
- **pathlib**: Cross-platform path handling

### Configuration Integration
- Use `config.py` for:
  - Server host/port
  - Database path
  - User email (if configured)
  - Log file location
- Store PID file in `~/.browserfriend/server.pid`
- Ensure `~/.browserfriend/` directory exists (handled by config)

### Database Integration
- Use existing functions from `database.py`:
  - `get_current_session()` - Get active session
  - `end_session()` - End a session
  - `get_visits_by_session()` - Get visits for session
  - `get_top_domains_by_user()` - Get top domains
  - `get_total_time_by_user()` - Get total browsing time
  - `get_visits_by_user()` - Get all visits
- **Note**: CLI assumes single user per machine (local-first design)

### Error Handling
- **Server already running**: Clear error message, suggest `bf stop`
- **Server not running**: Clear error message for `bf stop`/`bf status`
- **No user configured**: Prompt to run `bf setup` first
- **Database errors**: Graceful error messages with troubleshooting hints
- **Port conflicts**: Detect and report port already in use
- **Permission errors**: Handle file system permission issues

## Implementation Plan

### Phase 1: Core CLI Structure
1. Create Typer app in `cli.py`
2. Set up command structure (setup, start, stop, status, dashboard)
3. Implement basic command stubs with help text
4. Add entry point in `pyproject.toml` (if not exists)

### Phase 2: Setup Command
1. Implement `setup` command with email prompt
2. Add email validation
3. Integrate with `/api/setup` endpoint or direct database
4. Add success/error messaging

### Phase 3: Start Command
1. Implement PID file management utilities
2. Add process existence checking
3. Implement background server startup
4. Create session in database
5. Add success messaging with session ID

### Phase 4: Stop Command
1. Implement PID file reading
2. Add process termination logic
3. Implement session ending
4. Add session statistics querying
5. Format and display summary
6. Clean up PID file

### Phase 5: Status Command
1. Implement server status checking
2. Query active session from database
3. Query session statistics
4. Format and display status information

### Phase 6: Dashboard Command
1. Implement server running check
2. Integrate with dashboard generation (stub)
3. Integrate with email service (stub)
4. Add success messaging

### Phase 7: Testing & Polish
1. Test all commands on Windows/Linux/Mac
2. Test error cases and edge cases
3. Improve error messages and user feedback
4. Add command help text and documentation

## Success Criteria

### Functional Requirements
- ✅ All 5 commands (`setup`, `start`, `stop`, `status`, `dashboard`) implemented
- ✅ Server can start and stop as background process
- ✅ PID file management works correctly
- ✅ Session management integrated with CLI
- ✅ Status command shows accurate information
- ✅ Dashboard command integrates with existing modules

### Quality Requirements
- ✅ Clear, user-friendly error messages
- ✅ Cross-platform compatibility (Windows/Linux/Mac)
- ✅ Proper error handling for all edge cases
- ✅ Helpful command help text
- ✅ Consistent output formatting

### Integration Requirements
- ✅ Works with existing FastAPI server
- ✅ Uses existing database models and functions
- ✅ Respects configuration from `config.py`
- ✅ Integrates with dashboard and email modules (stubs acceptable)

## Decisions Made

### ✅ Process Management Library
**Decision**: Use `psutil` for better cross-platform support
- Provides consistent API across Windows/Linux/Mac
- Better process verification and termination handling
- Needs to be added to `pyproject.toml` dependencies

### ✅ Background Execution
**Decision**: Use `subprocess.Popen` with `start_new_session=True`
- Standard library approach, no additional dependencies
- `start_new_session=True` ensures proper daemon behavior
- Cross-platform compatible

### ✅ PID File Location
**Decision**: `~/.browserfriend/server.pid` confirmed
- Consistent with existing config directory structure
- Handled by `config.py` directory creation

### ✅ Multiple Users
**Decision**: CLI assumes single user per machine (local-first design)
- Simpler implementation for v1
- Aligns with local-first architecture
- Can be extended in future versions if needed

### ✅ Dashboard/Email Stubs
**Decision**: Show informative placeholder messages, return success
- Stubs should provide clear feedback about functionality
- Return success status to allow CLI flow to complete
- Placeholder messages guide users on future functionality

### ⏸️ Duration Flag
**Decision**: Deferred to post-MVP
- Start with simple manual stop command
- Can add duration-based auto-stop in future iteration

### ✅ Setup Behavior
**Decision**: Allow email update if already configured (with confirmation)
- If email exists, show current email and prompt for update confirmation
- Provides flexibility for users to change email if needed
- Confirmation prevents accidental changes

## Next Steps

1. ✅ All decisions made - ready for implementation
2. Add `psutil` to `pyproject.toml` dependencies
3. Create implementation branch: `feature/cli-implementation`
4. Begin Phase 1: Core CLI structure
5. Iterate through phases with testing
6. Create PR when all phases complete
7. Close issue #4 upon merge

---

**Document Version**: 1.1  
**Created**: 2026-02-09  
**Updated**: 2026-02-09  
**Status**: Ready for Implementation - All Decisions Finalized
