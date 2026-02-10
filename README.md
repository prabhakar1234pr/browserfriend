# BrowserFriend

**Track, analyse and understand your browsing habits.** BrowserFriend is a browser analytics tool that silently records your tab activity, generates AI-powered insights, and emails you a dashboard with session summaries.

- **Chrome extension** — tracks tab switches and page visits
- **Local server** — stores data in SQLite on your machine
- **AI insights** — Gemini-powered analysis of your browsing patterns
- **Email dashboard** — HTML report sent to your inbox via Resend or SMTP

---

## Installation

```bash
pip install browserfriend
```

Requires Python 3.12+.

---

## Quick Start

```bash
# 1. Configure your email
bf setup

# 2. Start the tracking server
bf start

# 3. Load the Chrome extension (see below)

# 4. Browse as usual — the extension sends visits to the server

# 5. Stop tracking and get your dashboard
bf stop
bf dashboard   # Generates AI insights and sends to your email
```

---

## Chrome Extension Setup

The extension is **not** included in the PyPI package. You must load it from the repository.

### Option A: Clone the extension directory

1. **Clone or download** the `extension` folder from the repo:
   ```bash
   git clone https://github.com/prabhakar1234pr/browserfriend.git
   cd browserfriend/extension
   ```
   Or download the `extension` folder directly:  
   [https://github.com/prabhakar1234pr/browserfriend/tree/main/extension](https://github.com/prabhakar1234pr/browserfriend/tree/main/extension)

2. **Open Chrome Extensions**  
   Go to `chrome://extensions` in your browser.

3. **Enable Developer mode**  
   Toggle **Developer mode** on (top-right corner).

4. **Load unpacked**  
   Click **Load unpacked** and select the `extension` folder (the one containing `manifest.json`).

5. **Verify**  
   The BrowserFriend icon should appear in your toolbar. Click it to see the popup — it should show "Server Offline" until you run `bf start`.

### Option B: Download as ZIP

1. Go to [https://github.com/prabhakar1234pr/browserfriend](https://github.com/prabhakar1234pr/browserfriend)
2. Click **Code** → **Download ZIP**
3. Extract the archive and navigate to the `extension` folder
4. Follow steps 2–5 from Option A above

---

## CLI Commands

| Command | Description |
|--------|-------------|
| `bf setup` | Configure your email (required before first use) |
| `bf start` | Start the tracking server |
| `bf stop` | Stop the server and show session summary |
| `bf status` | Show server and session status |
| `bf end-sessions` | End all active browsing sessions |
| `bf dashboard` | Generate AI insights and send dashboard to your email |

### `bf setup`

Registers your email so visits and dashboards are associated with you. Run this first.

```bash
bf setup
```

### `bf start`

Starts the local server at `http://localhost:8000`. The extension connects to this server.

```bash
# Run until you stop it
bf start

# Auto-stop after 5 minutes
bf start --duration 5m

# Auto-stop after 2 hours
bf start -d 2h

# Auto-stop after 1 day
bf start -d 1d
```

Duration format: `5m` (minutes), `2h` (hours), `1d` (days).

### `bf stop`

Stops the server and displays a summary of the session (duration, visits, top domains).

```bash
bf stop
```

### `bf status`

Shows whether the server is running and the current session details.

```bash
bf status
```

### `bf end-sessions`

Ends all active (unended) browsing sessions. Useful when sessions are left open for a long time.

```bash
# End active sessions for your user only
bf end-sessions

# End active sessions for all users
bf end-sessions --all-users
```

### `bf dashboard`

Generates an AI-powered dashboard for your latest (or specified) session and sends it to your email.

```bash
# Use latest session
bf dashboard

# Use a specific session
bf dashboard --session-id e939917b-7888-4f5c-8ef8-610ec02a6a22
```

---

## Admin Dashboard

When the server is running, open the **admin dashboard** in your browser:

**http://localhost:8000/admin**

- **Sessions** — All browsing sessions with visit counts and durations
- **Dashboards** — All generated dashboards (view past reports, preview HTML)

The admin URL is also shown when you run `bf start`.

---

## Configuration

Create a `.env` file in your project directory (or current working directory) to customise:

```env
# Required for AI insights
GEMINI_API_KEY=your_gemini_api_key

# Required for email delivery
RESEND_API_KEY=your_resend_api_key
# Or use SMTP:
# EMAIL_PROVIDER=smtp
# SMTP_HOST=smtp.gmail.com
# SMTP_PORT=587
# SMTP_USERNAME=your@email.com
# SMTP_PASSWORD=your_app_password

# Optional
USER_EMAIL=your@email.com
```

Database location: `~/.browserfriend/browserfriend.db`

---

## Links

- [GitHub](https://github.com/prabhakar1234pr/browserfriend)
- [PyPI](https://pypi.org/project/browserfriend/)
