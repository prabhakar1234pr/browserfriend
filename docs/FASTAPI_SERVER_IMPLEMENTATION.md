# FastAPI Server Endpoints Implementation

## Overview

This document describes the implementation of the FastAPI server endpoints for BrowserFriend, which receives browsing data from a Chrome extension and stores it in a SQLite database. The server provides RESTful API endpoints for setup, tracking, and status monitoring.

## Table of Contents

1. [Architecture](#architecture)
2. [Implementation Steps](#implementation-steps)
3. [API Endpoints](#api-endpoints)
4. [Database Models](#database-models)
5. [Error Handling](#error-handling)
6. [Logging](#logging)
7. [Testing](#testing)
8. [Configuration](#configuration)
9. [Usage Examples](#usage-examples)

## Architecture

### Server Structure

```
browserfriend/
├── server/
│   ├── __init__.py      # Package initialization, exports app
│   └── app.py           # FastAPI application with all endpoints
├── database.py          # Database models and helpers
├── config.py            # Configuration management
└── main.py              # Entry point for running the server
```

### Key Design Decisions

1. **Package Structure**: Created `browserfriend/server/` package for better organization
2. **Session Management**: Server automatically creates sessions if none exist when tracking visits
3. **User Management**: Single user model stored in database (first user from User table)
4. **CORS Configuration**: Allows Chrome extension origins and localhost for development
5. **Port Configuration**: Default port changed from 8765 to 8000 (standard FastAPI port)

## Implementation Steps

### Step 0: User Model

Added `User` model to the database for storing user emails:

```python
class User(Base):
    __tablename__ = "users"
    email = Column(String, primary_key=True)
    created_at = Column(DateTime, nullable=False, default=lambda: datetime.now(timezone.utc))
```

**Status**: ✅ Completed

### Steps 1-3: Server Package Structure

1. **Step 1**: Created `browserfriend/server/` directory with `__init__.py` and `app.py`
2. **Step 2**: Moved FastAPI app initialization from `main.py` to `server/app.py` with lifespan events
3. **Step 3**: Added CORS middleware to allow Chrome extension and localhost origins

**CORS Configuration**:
- Origins: `chrome-extension://*` and `http://localhost:*`
- Methods: GET, POST, OPTIONS
- Headers: Content-Type, Accept
- Credentials: True

**Status**: ✅ Completed

### Step 4: Pydantic Models

Created request/response models for API validation:

```python
class TrackingData(BaseModel):
    url: str
    title: Optional[str] = None
    duration: int  # seconds spent on page
    timestamp: str  # ISO format timestamp when user LEFT the page

class SetupData(BaseModel):
    email: EmailStr

class SuccessResponse(BaseModel):
    success: bool
    message: str

class StatusResponse(BaseModel):
    status: str
    database: str

class SetupResponse(BaseModel):
    success: bool
    email: str
```

**Status**: ✅ Completed

### Step 5: GET /api/status Endpoint

Implemented status endpoint that checks server and database connectivity:

- Returns server status ("running")
- Checks database connection with a test query
- Returns database connection state ("connected" or error message)

**Status**: ✅ Completed

### Step 6: POST /api/setup Endpoint

Implemented setup endpoint for user email registration:

- Validates email format using Pydantic `EmailStr`
- Queries User table for existing user
- Creates new User record if doesn't exist (idempotent)
- Returns success response with email

**Status**: ✅ Completed

### Step 7: POST /api/track Endpoint

Implemented tracking endpoint for page visits:

**Logic Flow**:
1. Validates request body with `TrackingData` model
2. Parses ISO timestamp string to datetime
3. Gets user email from User table (first user)
4. Gets current active session or creates new one
5. Extracts domain from URL
6. Calculates start_time: `start_time = timestamp - duration`
7. Creates PageVisit record with all fields
8. Returns success response

**Timestamp/Duration Relationship**:
- `timestamp` = when user LEFT the page (end time)
- `duration` = seconds spent on page
- Server calculates: `start_time = timestamp - duration`

**Session Management**:
- Active session = `BrowsingSession` where `end_time IS NULL`
- Server finds existing active session OR creates new one if none exists

**Status**: ✅ Completed

### Step 8: Error Handling

Enhanced error handling throughout all endpoints:

- Comprehensive try/except blocks
- Proper HTTP status codes:
  - 200: Success
  - 400: Bad request (validation errors)
  - 404: Not found (no user/session)
  - 500: Internal server error
- Consistent error response format
- Error logging with stack traces

**Status**: ✅ Completed

### Step 9: Database Initialization

Database initialization in server startup:

- `init_database()` called in lifespan startup event
- Ensures database tables exist before accepting requests
- Logs initialization status

**Status**: ✅ Completed

### Step 10: Main.py Update

Updated `main.py` to import app from server package:

```python
from browserfriend.config import get_config

def main():
    uvicorn.run(
        "browserfriend.server.app:app",
        host=config.server_host,
        port=config.server_port,
        ...
    )
```

**Status**: ✅ Completed

### Step 11: Config Update

Updated default port configuration:

- Changed default port from 8765 to 8000
- Can be overridden via environment variable `SERVER_PORT`

**Status**: ✅ Completed

## API Endpoints

### GET /health

Health check endpoint.

**Response**:
```json
{
  "status": "healthy",
  "service": "BrowserFriend",
  "version": "0.1.0"
}
```

### GET /api/status

Get server and database status.

**Response**:
```json
{
  "status": "running",
  "database": "connected"
}
```

**Error Response** (if database error):
```json
{
  "status": "running",
  "database": "error: <error message>"
}
```

### POST /api/setup

Save user email during setup.

**Request Body**:
```json
{
  "email": "user@example.com"
}
```

**Response**:
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

**Request Body**:
```json
{
  "url": "https://www.example.com",
  "title": "Example Page",
  "duration": 120,
  "timestamp": "2024-01-01T12:02:00Z"
}
```

**Response**:
```json
{
  "success": true,
  "message": "Page visit tracked: example.com"
}
```

**Error Responses**:
- `400`: Invalid timestamp format
- `404`: No user found (setup required)
- `422`: Validation error (missing fields)
- `500`: Database error

## Database Models

### User Model

```python
class User(Base):
    __tablename__ = "users"
    email = Column(String, primary_key=True)
    created_at = Column(DateTime, nullable=False, default=lambda: datetime.now(timezone.utc))
```

### BrowsingSession Model

```python
class BrowsingSession(Base):
    __tablename__ = "browsing_sessions"
    session_id = Column(String, primary_key=True)
    user_email = Column(String, nullable=False, index=True)
    start_time = Column(DateTime, nullable=False)
    end_time = Column(DateTime, nullable=True)
    duration = Column(Float, nullable=True)
```

### PageVisit Model

```python
class PageVisit(Base):
    __tablename__ = "page_visits"
    id = Column(Integer, primary_key=True, autoincrement=True)
    session_id = Column(String, ForeignKey("browsing_sessions.session_id"), nullable=False)
    user_email = Column(String, nullable=False, index=True)
    url = Column(String, nullable=False)
    domain = Column(String, nullable=False, index=True)
    title = Column(String, nullable=True)
    start_time = Column(DateTime, nullable=False)
    end_time = Column(DateTime, nullable=True)
    duration_seconds = Column(Float, nullable=True)
```

## Error Handling

### Error Response Format

All errors return consistent JSON format:

```json
{
  "detail": "Error message here"
}
```

### HTTP Status Codes

- **200 OK**: Successful request
- **400 Bad Request**: Invalid input (e.g., invalid timestamp format)
- **404 Not Found**: Resource not found (e.g., no user)
- **422 Unprocessable Entity**: Validation error (Pydantic)
- **500 Internal Server Error**: Server/database error

### Error Logging

All errors are logged with:
- Error message
- Full stack trace (`exc_info=True`)
- Context information (endpoint, request data)

## Logging

### Logging Configuration

Maximum verbosity logging configured with:
- Format: `%(asctime)s - %(name)s - %(levelname)s - [%(filename)s:%(lineno)d] - %(message)s`
- Level: DEBUG for browserfriend modules
- Output: Console (stdout) and optionally log file

### Log Levels

- **DEBUG**: Detailed operation information (database queries, data transformations)
- **INFO**: Important events (user creation, session creation, page visits)
- **WARNING**: Non-critical issues (HTTPExceptions)
- **ERROR**: Errors with stack traces

### Logged Events

- Server startup/shutdown
- Endpoint calls with request data
- Database operations (queries, commits, rollbacks)
- Session management (creation, retrieval)
- Page visit creation
- Errors with full context

## Testing

### Test Files

1. **test_steps_1_2_3.py**: Tests server package structure, FastAPI migration, CORS
2. **test_api_status.py**: Tests Pydantic models and status endpoint
3. **test_api_setup.py**: Tests setup endpoint (user creation, validation)
4. **test_api_track.py**: Tests track endpoint (session management, page visits)
5. **test_e2e.py**: End-to-end workflow test

### Test Coverage

- ✅ Server package structure
- ✅ FastAPI app migration
- ✅ CORS middleware
- ✅ Pydantic model validation
- ✅ Status endpoint
- ✅ Setup endpoint (new user, existing user, invalid email)
- ✅ Track endpoint (session creation, multiple visits, time calculations)
- ✅ Error handling (invalid inputs, missing data)
- ✅ Data integrity (relationships, constraints)

### Running Tests

```bash
# Run all tests
python -m pytest tests/ -v

# Run specific test
python tests/test_e2e.py
```

## Configuration

### Environment Variables

- `SERVER_HOST`: Server host (default: "127.0.0.1")
- `SERVER_PORT`: Server port (default: 8000)
- `DATABASE_PATH`: Database file path (default: `~/.browserfriend/browserfriend.db`)
- `LOG_LEVEL`: Logging level (default: "INFO")
- `LOG_FILE`: Optional log file path

### Default Configuration

```python
server_host: str = "127.0.0.1"
server_port: int = 8000
database_path: Optional[str] = None  # Auto-generated if not provided
log_level: str = "INFO"
log_file: Optional[str] = None
```

## Usage Examples

### Starting the Server

```bash
# Using main.py
python main.py

# Using uvicorn directly
uvicorn browserfriend.server.app:app --host 127.0.0.1 --port 8000
```

### Setup User Email

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
    "timestamp": "2024-01-01T12:02:00Z"
  }'
```

### Check Status

```bash
curl http://localhost:8000/api/status
```

### Health Check

```bash
curl http://localhost:8000/health
```

## Chrome Extension Integration

The server is designed to receive requests from a Chrome extension:

1. **CORS**: Configured to accept requests from `chrome-extension://*` origins
2. **Setup**: Extension calls `/api/setup` once with user email
3. **Tracking**: Extension calls `/api/track` for each completed page visit
4. **Data Format**: Extension sends ISO timestamp and duration in seconds

### Example Extension Request

```javascript
// Setup
fetch('http://localhost:8000/api/setup', {
  method: 'POST',
  headers: { 'Content-Type': 'application/json' },
  body: JSON.stringify({ email: 'user@example.com' })
});

// Track visit
fetch('http://localhost:8000/api/track', {
  method: 'POST',
  headers: { 'Content-Type': 'application/json' },
  body: JSON.stringify({
    url: 'https://www.example.com',
    title: 'Example Page',
    duration: 120,
    timestamp: new Date().toISOString()
  })
});
```

## Database Schema

### Tables

1. **users**: Stores user emails
2. **browsing_sessions**: Stores browsing sessions
3. **page_visits**: Stores individual page visits

### Relationships

- `PageVisit.session_id` → `BrowsingSession.session_id` (Foreign Key)
- `PageVisit.user_email` → `User.email` (Logical relationship)
- `BrowsingSession.user_email` → `User.email` (Logical relationship)

### Indexes

- `users.email` (Primary Key)
- `browsing_sessions.user_email`
- `browsing_sessions.start_time`
- `page_visits.session_id`
- `page_visits.domain`
- `page_visits.user_email`
- `page_visits.start_time`

## Session Management

### Active Session

An active session is defined as a `BrowsingSession` where `end_time IS NULL`.

### Session Lifecycle

1. **Creation**: Session created automatically when first page visit is tracked
2. **Usage**: All subsequent visits use the same active session
3. **Ending**: Session can be ended by CLI (`bf run` stop) or manually

### Session Auto-Creation

If no active session exists when tracking a visit:
- Server automatically creates a new session
- Session ID is generated (UUID)
- Start time is set to current time
- Session is used for the page visit

## Time Calculations

### Timestamp Handling

- Extension sends `timestamp` as ISO format string (when user LEFT page)
- Extension sends `duration` as integer (seconds spent on page)
- Server calculates `start_time = timestamp - duration`
- Server stores both `start_time` and `end_time` in database

### Example

```
User arrives at: 10:00:00
User leaves at: 10:02:00
Duration: 120 seconds

Extension sends:
- timestamp: "2024-01-01T10:02:00Z"
- duration: 120

Server calculates:
- start_time: 2024-01-01T10:00:00Z
- end_time: 2024-01-01T10:02:00Z
- duration_seconds: 120
```

## Security Considerations

1. **CORS**: Restricted to Chrome extension and localhost origins
2. **Input Validation**: Pydantic models validate all inputs
3. **SQL Injection**: SQLAlchemy ORM prevents SQL injection
4. **Error Messages**: Error messages don't expose sensitive information
5. **Database**: SQLite database stored in user's home directory

## Future Enhancements

Potential improvements:

1. **Authentication**: Add API key or JWT authentication
2. **Rate Limiting**: Prevent abuse with rate limiting
3. **Multiple Users**: Support multiple users with proper authentication
4. **API Versioning**: Add versioning to API endpoints
5. **Metrics**: Add Prometheus metrics endpoint
6. **Health Checks**: More comprehensive health check endpoint
7. **Database Migrations**: Use Alembic for database migrations

## Troubleshooting

### Common Issues

1. **Database Connection Error**
   - Check database path permissions
   - Ensure directory exists

2. **CORS Errors**
   - Verify Chrome extension origin matches CORS regex
   - Check CORS middleware configuration

3. **No User Found**
   - Call `/api/setup` endpoint first
   - Verify user exists in database

4. **Invalid Timestamp**
   - Ensure timestamp is ISO format
   - Include timezone information (Z or +00:00)

## References

- [FastAPI Documentation](https://fastapi.tiangolo.com/)
- [SQLAlchemy Documentation](https://docs.sqlalchemy.org/)
- [Pydantic Documentation](https://docs.pydantic.dev/)

---

**Last Updated**: February 9, 2026  
**Version**: 0.1.0  
**Author**: BrowserFriend Development Team
