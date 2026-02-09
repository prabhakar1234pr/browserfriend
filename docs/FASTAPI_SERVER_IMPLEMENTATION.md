# FastAPI Server Endpoints Implementation

## Overview

This document describes the implementation of the FastAPI server endpoints for BrowserFriend, which receives browsing data from a Chrome extension and stores it in a SQLite database. The server provides RESTful API endpoints for setup, tracking, session management, and status monitoring.

## Table of Contents

1. [Architecture](#architecture)
2. [API Endpoints](#api-endpoints)
3. [Database Models](#database-models)
4. [Session Management](#session-management)
5. [Error Handling](#error-handling)
6. [Logging](#logging)
7. [Testing](#testing)
8. [Configuration](#configuration)
9. [Usage Examples](#usage-examples)
10. [Chrome Extension Integration](#chrome-extension-integration)
11. [Issues Fixed](#issues-fixed)

## Architecture

### Server Structure

```
browserfriend/
  server/
    __init__.py      # Package initialization, exports app
    app.py           # FastAPI application with all endpoints
  database.py        # Database models and helpers
  config.py          # Configuration management
main.py              # Entry point for running the server
```

### Key Design Decisions

1. **Package Structure**: `browserfriend/server/` package for better organization
2. **Session Lifecycle**: Server auto-ends stale sessions (>30 min inactivity) and creates new ones
3. **User Identification**: Email is required in every tracking request (no single-user assumption)
4. **CORS Configuration**: Allows Chrome extension origins and localhost for development
5. **Single Status Endpoint**: `/api/status` serves as both health check and status endpoint
6. **Default Port**: 8000 (standard FastAPI port)

## API Endpoints

### GET /api/status

Single status/health endpoint. Checks server state and database connectivity.

**Response** (200):
```json
{
  "status": "running",
  "database": "connected"
}
```

### POST /api/setup

Save user email during setup. Creates a User record if it doesn't exist.

**Request Body**:
```json
{
  "email": "user@example.com"
}
```

**Response** (200):
```json
{
  "success": true,
  "email": "user@example.com"
}
```

**Error Responses**:
- `422`: Invalid email format
- `500`: Database error

### POST /api/track

Receive completed page visit from Chrome extension.
Requires `email` to identify the user.
Returns `session_id` of the session used.
Stale sessions (>30 min inactivity) are auto-ended and a new session is created.

**Request Body**:
```json
{
  "url": "https://www.example.com",
  "title": "Example Page",
  "duration": 120,
  "timestamp": "2024-01-01T12:02:00Z",
  "email": "user@example.com"
}
```

**Response** (200):
```json
{
  "success": true,
  "message": "Page visit tracked: example.com",
  "session_id": "abc-123-def"
}
```

**Error Responses**:
- `400`: Invalid timestamp format
- `404`: No user found with given email (setup required)
- `422`: Validation error (missing fields)
- `500`: Database error

### POST /api/session/end

End a browsing session by setting its end_time.

**Request Body**:
```json
{
  "session_id": "abc-123-def"
}
```

**Response** (200):
```json
{
  "success": true,
  "message": "Session ended successfully",
  "session_id": "abc-123-def",
  "duration_seconds": 1234.5
}
```

**Error Responses**:
- `400`: Session is already ended
- `404`: Session not found
- `500`: Database error

## Database Models

### User

```python
class User(Base):
    __tablename__ = "users"
    id = Column(Integer, primary_key=True, autoincrement=True)
    email = Column(String(255), unique=True, nullable=False, index=True)
    created_at = Column(DateTime, nullable=False)
```

### BrowsingSession

```python
class BrowsingSession(Base):
    __tablename__ = "browsing_sessions"
    session_id = Column(String, primary_key=True)
    user_email = Column(String, nullable=False, index=True)
    start_time = Column(DateTime, nullable=False)
    end_time = Column(DateTime, nullable=True)
    duration = Column(Float, nullable=True)
```

### PageVisit

```python
class PageVisit(Base):
    __tablename__ = "page_visits"
    id = Column(Integer, primary_key=True, autoincrement=True)
    session_id = Column(String, ForeignKey("browsing_sessions.session_id"))
    user_email = Column(String, nullable=False, index=True)
    url = Column(String, nullable=False)
    domain = Column(String, nullable=False, index=True)
    title = Column(String, nullable=True)
    start_time = Column(DateTime, nullable=False)
    end_time = Column(DateTime, nullable=True)
    duration_seconds = Column(Float, nullable=True)
```

### Relationships

- `PageVisit.session_id` -> `BrowsingSession.session_id` (Foreign Key)
- `BrowsingSession` has many `PageVisit` (cascade delete)

### Indexes

- `users.email` (unique)
- `browsing_sessions.user_email`
- `browsing_sessions.start_time`
- `page_visits.session_id`
- `page_visits.domain`
- `page_visits.user_email`
- `page_visits.start_time`

## Session Management

### Session Lifecycle

1. **Creation**: Server creates a new session when a tracking request arrives and no active session exists
2. **Active Usage**: Subsequent tracking requests reuse the active session
3. **Inactivity Timeout**: If the last page visit was >30 minutes ago, the stale session is auto-ended and a new one is created
4. **Manual End**: CLI or API can explicitly end a session via `POST /api/session/end`

### How `get_or_create_active_session` Works

```
1. Find active session (end_time IS NULL) for the user
2. If found, check last page visit's end_time
3. If last visit was >30 min ago -> end stale session, create new one
4. If last visit was recent -> return existing session
5. If no active session -> create new one
```

### Stale Session Detection

- Active session = `BrowsingSession` where `end_time IS NULL`
- Stale = last page visit in session was more than 30 minutes ago
- On staleness: `end_time` is set to now, `duration` is calculated, new session is created

### Time Calculations

- Extension sends `timestamp` (when user LEFT page) + `duration` (seconds on page)
- Server calculates: `start_time = timestamp - timedelta(seconds=duration)`
- Example: timestamp=10:02, duration=120 -> start_time=10:00, end_time=10:02

## Error Handling

### HTTP Status Codes

| Code | Meaning | When |
|------|---------|------|
| 200 | Success | Request completed |
| 400 | Bad Request | Invalid timestamp format |
| 404 | Not Found | User not found, session not found |
| 422 | Validation Error | Pydantic validation failure (invalid email, missing fields) |
| 500 | Server Error | Database errors, unexpected exceptions |

### Error Response Format

```json
{
  "detail": "Error message here"
}
```

All errors include:
- Error message in response body
- Full stack trace in server logs (`exc_info=True`)
- Context information (endpoint, request data)

## Logging

### Format

```
%(asctime)s - %(name)s - %(levelname)s - [%(filename)s:%(lineno)d] - %(message)s
```

### Log Levels

- **DEBUG**: Database queries, data transformations, Pydantic validation, session factory operations
- **INFO**: Endpoint calls, user creation, session lifecycle, page visit creation, time calculations
- **WARNING**: HTTPExceptions re-raised, stale sessions detected
- **ERROR**: Database errors, validation failures, with full stack traces

### Logged Events

Every endpoint logs:
- Request received (with all parameters)
- Each database operation
- Session management decisions
- Response body
- Session close

## Testing

### Test Files

| File | Coverage |
|------|----------|
| `test_e2e.py` | Full end-to-end workflow including all 6 fixes |
| `test_steps_1_2_3.py` | Server package structure, FastAPI migration, CORS |
| `test_api_status.py` | Pydantic models and status endpoint |
| `test_api_setup.py` | Setup endpoint (user creation, validation) |
| `test_api_track.py` | Track endpoint (session management, page visits) |

### E2E Test Coverage

The E2E test verifies all fixes:

1. `/api/status` works, `/health` returns 404
2. User created with integer PK
3. Track requires email in request body
4. Track without email rejected (422)
5. Track with unknown email rejected (404)
6. Multiple visits tracked in same session
7. Session can be ended via `/api/session/end`
8. New session created after previous ended
9. Error handling for invalid inputs
10. Data integrity across all tables

### Running Tests

```bash
# Run E2E test
python tests/test_e2e.py

# Run all tests with pytest
python -m pytest tests/ -v
```

## Configuration

### Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `SERVER_HOST` | `127.0.0.1` | Server bind address |
| `SERVER_PORT` | `8000` | Server port |
| `DATABASE_PATH` | `~/.browserfriend/browserfriend.db` | SQLite database path |
| `LOG_LEVEL` | `INFO` | Logging level |
| `LOG_FILE` | None | Optional log file path |

### Starting the Server

```bash
python main.py
# or
uvicorn browserfriend.server.app:app --host 127.0.0.1 --port 8000
```

## Usage Examples

### Setup User

```bash
curl -X POST http://localhost:8000/api/setup \
  -H "Content-Type: application/json" \
  -d '{"email": "user@example.com"}'
```

### Track Page Visit

```bash
curl -X POST http://localhost:8000/api/track \
  -H "Content-Type: application/json" \
  -d '{
    "url": "https://www.example.com",
    "title": "Example Page",
    "duration": 120,
    "timestamp": "2024-01-01T12:02:00Z",
    "email": "user@example.com"
  }'
```

### Check Status

```bash
curl http://localhost:8000/api/status
```

### End Session

```bash
curl -X POST http://localhost:8000/api/session/end \
  -H "Content-Type: application/json" \
  -d '{"session_id": "abc-123-def"}'
```

## Chrome Extension Integration

### CORS

Configured to accept requests from `chrome-extension://*` and `http://localhost:*`.

### Extension Flow

1. Call `/api/setup` once with user email
2. Call `/api/track` for each completed page visit (include email in every request)
3. Use returned `session_id` to track which session visits belong to

### Example Extension Code

```javascript
// Setup
fetch('http://localhost:8000/api/setup', {
  method: 'POST',
  headers: { 'Content-Type': 'application/json' },
  body: JSON.stringify({ email: 'user@example.com' })
});

// Track visit (email required in every request)
const response = await fetch('http://localhost:8000/api/track', {
  method: 'POST',
  headers: { 'Content-Type': 'application/json' },
  body: JSON.stringify({
    url: 'https://www.example.com',
    title: 'Example Page',
    duration: 120,
    timestamp: new Date().toISOString(),
    email: 'user@example.com'
  })
});
const data = await response.json();
console.log('Session ID:', data.session_id);
```

## Issues Fixed

### Fix 1: Session Lifecycle Ambiguity (HIGH)

**Problem**: Sessions stayed active forever because `end_time` was never set.

**Solution**: Implemented `get_or_create_active_session()` with a 30-minute inactivity timeout. When a tracking request arrives:
- If the active session's last page visit was >30 minutes ago, the session is auto-ended
- A new session is created for fresh tracking
- CLI and API can also manually end sessions via `/api/session/end`

### Fix 2: User Model Schema Inconsistency (HIGH)

**Problem**: `User.email` was the primary key (unusual, can't change email, no integer ID for foreign keys).

**Solution**: Changed to standard schema:
```python
id = Column(Integer, primary_key=True, autoincrement=True)
email = Column(String(255), unique=True, nullable=False, index=True)
```

### Fix 3: Redundant Health Endpoints (MEDIUM)

**Problem**: Two endpoints (`/health` and `/api/status`) served similar purposes.

**Solution**: Removed `/health`, kept `/api/status` as the single status/health endpoint.

### Fix 4: No Session End Mechanism (MEDIUM)

**Problem**: No API endpoint to end a session for testing or manual control.

**Solution**: Added `POST /api/session/end` endpoint that:
- Accepts `session_id`
- Sets `end_time` to now
- Calculates and stores session duration
- Returns 400 if session already ended
- Returns 404 if session not found

### Fix 5: Single User Assumption Not Enforced (MEDIUM)

**Problem**: `session.query(User).first()` returned any user. Multiple users in the table would cause ambiguity.

**Solution**: `email` is now a required field in the `TrackingData` model. The server queries the user by email:
```python
user = session.query(User).filter(User.email == tracking_data.email).first()
```
Returns 404 if the email is not found.

### Fix 6: No Session ID in Track Response (MEDIUM)

**Problem**: Server didn't return which `session_id` was used, making debugging difficult.

**Solution**: Added `TrackResponse` model with `session_id` field:
```json
{
  "success": true,
  "message": "Page visit tracked: example.com",
  "session_id": "abc-123-def"
}
```

---

**Last Updated**: February 9, 2026
**Version**: 0.1.0
