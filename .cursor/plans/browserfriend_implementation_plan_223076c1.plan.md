---
name: BrowserFriend Implementation Plan
overview: Build a complete browser activity tracker with Python CLI, Chrome extension, local FastAPI server, SQLite database, LLM-powered insights, HTML dashboard generation, and email delivery.
todos:
  - id: setup-project
    content: Set up project structure, dependencies in pyproject.toml, and package layout
    status: pending
  - id: config-system
    content: Implement configuration management (config.py) with file-based and env var support
    status: pending
  - id: database-models
    content: Create SQLAlchemy models for BrowsingSession and PageVisit in database.py
    status: pending
  - id: cli-commands
    content: Implement Typer CLI with setup, run, and dashboard commands in cli.py
    status: pending
  - id: fastapi-server
    content: Build FastAPI server with /api/track endpoint and CORS in server.py
    status: pending
  - id: chrome-extension
    content: Create Chrome extension with manifest.json and background.js for tab tracking
    status: pending
  - id: dashboard-stats
    content: Implement statistics calculation and database queries in dashboard.py
    status: pending
  - id: llm-integration
    content: Create LLM client supporting Anthropic and OpenAI in llm_client.py
    status: pending
  - id: html-template
    content: Build HTML dashboard template with Chart.js visualizations
    status: pending
  - id: email-service
    content: Implement SendGrid email delivery in email_service.py
    status: pending
  - id: error-handling
    content: Add comprehensive error handling throughout the application
    status: pending
  - id: documentation
    content: Write README.md with installation, setup, and usage instructions
    status: pending
isProject: false
---

# BrowserFriend Implementation Plan

## Project Structure

```
browserfriend/
├── browserfriend/              # Main Python package
│   ├── __init__.py
│   ├── cli.py                 # Typer CLI commands (setup, run, dashboard)
│   ├── server.py              # FastAPI server for receiving extension data
│   ├── database.py            # SQLAlchemy models and database setup
│   ├── config.py              # Configuration management
│   ├── dashboard.py           # Dashboard generation logic
│   ├── llm_client.py          # LLM API integration (Anthropic/OpenAI)
│   ├── email_service.py       # SendGrid email delivery
│   └── utils.py               # Helper functions
├── extension/                 # Chrome extension
│   ├── manifest.json          # Extension manifest
│   ├── background.js          # Background script for tab tracking
│   ├── content.js             # Content script (if needed)
│   └── popup.html/js          # Extension popup UI (optional)
├── templates/                 # HTML dashboard templates
│   └── dashboard.html         # Dashboard template with Chart.js
├── static/                    # CSS and JS assets
│   ├── styles.css
│   └── charts.js
├── tests/                     # Test files
├── pyproject.toml             # Project dependencies
├── README.md                  # Documentation
└── main.py                    # Entry point
```

## Implementation Phases

### Phase 1: Core Infrastructure

**1.1 Project Setup & Dependencies**

- Update `pyproject.toml` with dependencies:
  - `fastapi`, `uvicorn` (web server)
  - `sqlalchemy` (database ORM)
  - `typer` (CLI framework)
  - `pydantic` (data validation)
  - `python-dotenv` (environment variables)
  - `anthropic` or `openai` (LLM client)
  - `sendgrid` (email service)
  - `jinja2` (HTML templating)
- Create package structure with `browserfriend/` directory
- Set up entry points in `pyproject.toml` for `bf` command

**1.2 Configuration Management** (`browserfriend/config.py`)

- Create config class using Pydantic Settings
- Store user email, API keys (LLM, SendGrid), server port
- Configuration file location: `~/.browserfriend/config.json` or environment variables
- Default server port: 8765
- Support for both Anthropic Claude and OpenAI GPT

**1.3 Database Models** (`browserfriend/database.py`)

- SQLAlchemy models:
  - `BrowsingSession`: session_id, start_time, end_time, duration
  - `PageVisit`: id, session_id, url, domain, title, start_time, end_time, duration_seconds
- Database file: `~/.browserfriend/browserfriend.db`
- Database initialization function
- Session management utilities

### Phase 2: CLI Interface

**2.1 CLI Setup** (`browserfriend/cli.py`)

- Use Typer for CLI framework
- Main command group: `bf`
- Commands:
  - `bf setup`: Interactive setup wizard
    - Prompt for email address
    - Prompt for LLM provider (Anthropic/OpenAI) and API key
    - Prompt for SendGrid API key
    - Save configuration
    - Open Chrome extension installation page
  - `bf run --duration <time>`: Start tracking session
    - Parse duration (1d, 5m, 2h, etc.)
    - Create new database session
    - Start FastAPI server in background
    - Keep running until duration expires or Ctrl+C
  - `bf dashboard`: Generate and email dashboard
    - Query all data from database
    - Calculate statistics
    - Generate dashboard HTML
    - Send email

**2.2 Entry Point** (`main.py`)

- Import and call CLI app from `browserfriend.cli`

### Phase 3: FastAPI Server

**3.1 Server Implementation** (`browserfriend/server.py`)

- FastAPI app with CORS enabled for extension
- Endpoints:
  - `POST /api/track`: Receive tracking data from extension
    - Body: `{url, title, timestamp, action}` (action: 'activate' or 'deactivate')
    - Store in database
    - Return success response
  - `GET /api/health`: Health check endpoint
  - `GET /api/session`: Get current session info
- Background task to handle tab switches
- Server runs on localhost (127.0.0.1) for security

**3.2 Server Lifecycle**

- Start server when `bf run` is executed
- Graceful shutdown on Ctrl+C or duration expiry
- Port conflict detection and handling

### Phase 4: Chrome Extension

**4.1 Extension Manifest** (`extension/manifest.json`)

- Manifest V3 format
- Permissions: `tabs`, `activeTab`, `storage`
- Background service worker
- Host permissions for `http://localhost:8765/*`

**4.2 Background Script** (`extension/background.js`)

- Listen to `chrome.tabs.onActivated` and `chrome.tabs.onUpdated`
- Track active tab changes
- Record: URL, page title, timestamp
- Send POST request to `http://localhost:8765/api/track` on tab switch
- Handle previous tab deactivation (calculate duration)
- Error handling for server unavailable

**4.3 Extension Assets**

- Create simple popup UI (optional) showing connection status
- Icons for extension

### Phase 5: Dashboard Generation

**5.1 Statistics Calculation** (`browserfriend/dashboard.py`)

- Query database for all sessions and visits
- Calculate:
  - Total time online
  - Top visited domains (by time and count)
  - Number of tab switches
  - Time distribution by hour/day
  - Average session duration
  - Most active time periods

**5.2 LLM Integration** (`browserfriend/llm_client.py`)

- Support both Anthropic Claude and OpenAI GPT
- Prompt engineering for analysis:
  - Input: browsing statistics and categorized data
  - Output: JSON with insights, productivity score, recommendations
- Categorize websites (productivity, entertainment, social media, news, etc.)
- Generate narrative insights about browsing patterns
- Calculate productivity score (0-100)

**5.3 HTML Dashboard** (`templates/dashboard.html`)

- Use Jinja2 templating
- Embed Chart.js for visualizations:
  - Pie chart: Time by category
  - Bar chart: Top domains
  - Line chart: Activity over time
  - Stats cards: Total time, productivity score, tab switches
- Responsive design with modern CSS
- Include generated insights from LLM
- Self-contained HTML (inline CSS/JS or CDN links)

### Phase 6: Email Delivery

**6.1 Email Service** (`browserfriend/email_service.py`)

- SendGrid integration
- Create HTML email with dashboard embedded
- Subject: "Your BrowserFriend Dashboard - [Date]"
- Attach dashboard as HTML attachment or embed inline
- Error handling for email failures

### Phase 7: Testing & Polish

**7.1 Error Handling**

- Server connection errors in extension
- Database errors
- LLM API failures
- Email delivery failures
- Graceful degradation

**7.2 Documentation**

- Update README.md with:
  - Installation instructions
  - Setup guide
  - Usage examples
  - Troubleshooting

**7.3 Package Distribution**

- Ensure `pyproject.toml` is properly configured
- Test `pip install -e .` locally
- Create distribution package structure

## Key Technical Decisions

1. **Database**: SQLite for simplicity and local storage
2. **Server**: FastAPI for async support and easy CORS
3. **CLI**: Typer for modern Python CLI experience
4. **Extension**: Manifest V3 (latest Chrome standard)
5. **LLM**: Support both providers with configurable choice
6. **Email**: SendGrid for reliable delivery
7. **Dashboard**: Self-contained HTML for easy email embedding

## Data Flow

```
Chrome Extension → POST /api/track → FastAPI Server → SQLite Database
                                                              ↓
User runs bf dashboard → Query DB → Calculate Stats → LLM API → Generate HTML → SendGrid → Email
```

## Configuration Files

- `~/.browserfriend/config.json`: User configuration
- `~/.browserfriend/browserfriend.db`: SQLite database
- Environment variables: API keys (optional, more secure)

