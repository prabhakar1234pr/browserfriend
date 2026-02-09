# Release v0.6.0 - Email Delivery & Extension Tracking

## Overview

This release adds email delivery of AI-generated dashboards and improves the extension so already-open tabs are tracked when the server starts. Completes the MVP workflow: setup, start, browse, stop, dashboard-by-email.

## What's New

### Email Delivery (Issue #10)

- **Dashboard by email**: `bf dashboard` generates insights and sends an HTML dashboard to the user's email (no terminal output; "Check your email!" only).
- **SMTP support**: Default provider is SMTP (e.g. Gmail with App Password). Sends to any email address; no Resend account required.
- **Resend support**: Optional `EMAIL_PROVIDER=resend` in `.env` for Resend API.
- **HTML email template**: Responsive template with statistics cards, productivity breakdown, top domains, time distribution, AI insights, patterns, and recommendations.
- **Dashboard storage**: New `Dashboard` model stores generated dashboards (insights JSON + HTML) for history and future web dashboard.
- **CLI**: `bf dashboard` accepts optional `--session-id` for a specific session; otherwise uses latest.

### Extension Improvements

- **Track already-open tabs**: Service worker polls server status every 5 seconds. When the server goes from offline to online, the extension starts tracking the current active tab so tabs open before `bf start` (e.g. YouTube) are included when you switch away.
- **Session info in popup**: When the server is online, the popup shows "Time started" (local time) and "Tracking" (current tab title or domain).

### Configuration

**Required for email (SMTP, default):**

- `SMTP_USERNAME` – e.g. your Gmail
- `SMTP_PASSWORD` – Gmail App Password from https://myaccount.google.com/apppasswords

**Optional:**

- `EMAIL_PROVIDER` – `smtp` (default) or `resend`
- `SMTP_HOST`, `SMTP_PORT` – default Gmail
- `RESEND_API_KEY`, `RESEND_FROM_EMAIL` – when using Resend

## Bug Fixes

- Tabs that were open before `bf start` are now captured once the server is detected online (polling), so the first tab is no longer missing from the session.

## Testing

- New tests: `tests/test_email.py` (unit), `tests/test_email_e2e.py` (workflow), `tests/send_test_email.py` (manual).
- Existing e2e and email tests passing.

## Files Added

- `browserfriend/email/` – sender, renderer, utils, templates/dashboard_email.html
- `tests/test_email.py`, `tests/test_email_e2e.py`, `tests/send_test_email.py`

## Files Modified

- `browserfriend/database.py` – Dashboard model, `save_dashboard()`
- `browserfriend/config.py` – SMTP and email provider settings
- `browserfriend/cli.py` – dashboard command (email-only output, send + save)
- `extension/background/service-worker.js` – server polling, offline→online capture
- `extension/popup/` – session section (Time started, Tracking)

---

**Full Changelog**: [v0.5.0...v0.6.0](https://github.com/prabhakar1234pr/browserfriend/compare/v0.5.0...v0.6.0)
