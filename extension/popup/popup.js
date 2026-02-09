/**
 * BrowserFriend — Popup Script
 *
 * Manages the popup UI that appears when the user clicks the extension
 * icon.  Handles:
 *   - Checking server connectivity
 *   - Email configuration (save / change)
 *   - Opening the dashboard
 */

// ─── Constants ───────────────────────────────────────────────────────
const API_BASE = "http://localhost:8000";
const API_STATUS = `${API_BASE}/api/status`;
const API_SETUP = `${API_BASE}/api/setup`;

/** Simple email regex — intentionally loose for a quick client-side check. */
const EMAIL_REGEX = /^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$/;

// ─── Logging ─────────────────────────────────────────────────────────
const log = {
  info: (...args) => console.log("[BrowserFriend Popup]", ...args),
  warn: (...args) => console.warn("[BrowserFriend Popup]", ...args),
  error: (...args) => console.error("[BrowserFriend Popup]", ...args),
  debug: (...args) => console.debug("[BrowserFriend Popup]", ...args),
};

// ─── DOM references ──────────────────────────────────────────────────
const serverStatusEl = document.getElementById("serverStatus");
const sessionSectionEl = document.getElementById("sessionSection");
const sessionTimeStartedEl = document.getElementById("sessionTimeStarted");
const sessionCurrentTabEl = document.getElementById("sessionCurrentTab");
const emailSetupSection = document.getElementById("emailSetupSection");
const emailConfiguredSection = document.getElementById("emailConfiguredSection");
const emailInput = document.getElementById("emailInput");
const saveEmailBtn = document.getElementById("saveEmailBtn");
const emailErrorEl = document.getElementById("emailError");
const currentEmailEl = document.getElementById("currentEmail");
const changeEmailBtn = document.getElementById("changeEmailBtn");
const openDashboardBtn = document.getElementById("openDashboardBtn");

// ─── Server status ───────────────────────────────────────────────────

/**
 * Format epoch ms as local time string (e.g. "2:30 PM").
 * @param {number} epochMs
 * @returns {string}
 */
function formatTimeStarted(epochMs) {
  const d = new Date(epochMs);
  return d.toLocaleTimeString(undefined, {
    hour: "numeric",
    minute: "2-digit",
    hour12: true,
  });
}

/**
 * Get domain from URL for display.
 * @param {string} url
 * @returns {string}
 */
function getDomainFromUrl(url) {
  try {
    const u = new URL(url);
    return u.hostname.replace(/^www\./, "") || url;
  } catch {
    return url;
  }
}

/**
 * Load currentTab from storage and update session section (time started, current tab).
 */
function updateSessionInfo() {
  chrome.storage.local.get(["currentTab"], (result) => {
    if (chrome.runtime.lastError) {
      sessionSectionEl.style.display = "none";
      return;
    }
    const currentTab = result.currentTab || null;
    if (!currentTab || !currentTab.url) {
      sessionTimeStartedEl.textContent = "—";
      sessionCurrentTabEl.textContent = "No tab being tracked";
      sessionSectionEl.style.display = "block";
      return;
    }
    sessionTimeStartedEl.textContent = formatTimeStarted(currentTab.startTime);
    const label = currentTab.title || getDomainFromUrl(currentTab.url);
    sessionCurrentTabEl.textContent = label.length > 40 ? label.slice(0, 37) + "…" : label;
    sessionSectionEl.style.display = "block";
  });
}

/**
 * Ping the BrowserFriend server and update the status badge.
 */
async function checkServerStatus() {
  log.info("Checking server status...");
  serverStatusEl.textContent = "Checking...";
  serverStatusEl.className = "status-badge status-badge--checking";
  sessionSectionEl.style.display = "none";

  try {
    const response = await fetch(API_STATUS, { signal: AbortSignal.timeout(3000) });
    if (response.ok) {
      const data = await response.json();
      log.info(`Server is running — database: ${data.database}`);
      serverStatusEl.textContent = "Tracking Active";
      serverStatusEl.className = "status-badge status-badge--active";
      updateSessionInfo();
    } else {
      log.warn(`Server responded with status ${response.status}`);
      serverStatusEl.textContent = "Server Error";
      serverStatusEl.className = "status-badge status-badge--error";
    }
  } catch (err) {
    log.warn(`Server unreachable — ${err.message}`);
    serverStatusEl.textContent = "Server Offline";
    serverStatusEl.className = "status-badge status-badge--offline";
  }
}

// ─── Email management ────────────────────────────────────────────────

/**
 * Load the stored email from chrome.storage.local and update the UI.
 */
async function loadEmail() {
  log.info("Loading stored email...");

  return new Promise((resolve) => {
    chrome.storage.local.get(["email"], (result) => {
      if (chrome.runtime.lastError) {
        log.error("Failed to read storage:", chrome.runtime.lastError.message);
        showEmailSetup();
        resolve(null);
        return;
      }

      const email = result.email || null;
      if (email) {
        log.info(`Email found: ${email}`);
        showEmailConfigured(email);
      } else {
        log.info("No email configured yet");
        showEmailSetup();
      }
      resolve(email);
    });
  });
}

/**
 * Show the email input form.
 */
function showEmailSetup() {
  emailSetupSection.style.display = "block";
  emailConfiguredSection.style.display = "none";
  hideError();
  log.debug("UI: showing email setup form");
}

/**
 * Show the "email already configured" view.
 * @param {string} email
 */
function showEmailConfigured(email) {
  emailSetupSection.style.display = "none";
  emailConfiguredSection.style.display = "block";
  currentEmailEl.textContent = email;
  log.debug(`UI: showing configured email "${email}"`);
}

/**
 * Display an error message below the email input.
 * @param {string} message
 */
function showError(message) {
  emailErrorEl.textContent = message;
  emailErrorEl.style.display = "block";
  emailErrorEl.className = "message message--error";
  log.warn(`UI error: ${message}`);
}

/**
 * Display a success message below the email input.
 * @param {string} message
 */
function showSuccess(message) {
  emailErrorEl.textContent = message;
  emailErrorEl.style.display = "block";
  emailErrorEl.className = "message message--success";
  log.info(`UI success: ${message}`);
}

/**
 * Hide any error / success message.
 */
function hideError() {
  emailErrorEl.style.display = "none";
}

/**
 * Validate and save the email.
 * 1. Client-side validation
 * 2. Call /api/setup on the server
 * 3. Store in chrome.storage.local
 */
async function saveEmail() {
  const email = emailInput.value.trim();
  log.info(`Saving email: "${email}"`);

  // Client-side validation
  if (!email) {
    showError("Please enter an email address.");
    return;
  }
  if (!EMAIL_REGEX.test(email)) {
    showError("Invalid email format. Example: you@example.com");
    return;
  }

  // Disable button while saving
  saveEmailBtn.disabled = true;
  saveEmailBtn.textContent = "Saving...";
  hideError();

  try {
    // Call server setup endpoint
    log.info(`Calling ${API_SETUP} with email="${email}"`);
    const response = await fetch(API_SETUP, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ email }),
    });

    if (!response.ok) {
      const errorData = await response.text();
      log.error(`Server returned ${response.status}: ${errorData}`);
      showError(`Server error (${response.status}). Is the server running?`);
      return;
    }

    const data = await response.json();
    log.info(`Server confirmed email: ${data.email}`);

    // Store in chrome.storage.local
    chrome.storage.local.set({ email }, () => {
      if (chrome.runtime.lastError) {
        log.error("Failed to save email to storage:", chrome.runtime.lastError.message);
        showError("Failed to save email locally.");
        return;
      }
      log.info("Email saved to chrome.storage.local");
      showSuccess("Email saved successfully!");

      // Switch to configured view after a short delay
      setTimeout(() => {
        showEmailConfigured(email);
      }, 1000);
    });
  } catch (err) {
    log.error(`Failed to save email: ${err.message}`);
    showError("Cannot reach server. Start the server with: bf start");
  } finally {
    saveEmailBtn.disabled = false;
    saveEmailBtn.textContent = "Save";
  }
}

// ─── Event listeners ─────────────────────────────────────────────────

saveEmailBtn.addEventListener("click", saveEmail);

// Allow pressing Enter in the email field to save
emailInput.addEventListener("keydown", (e) => {
  if (e.key === "Enter") {
    saveEmail();
  }
});

changeEmailBtn.addEventListener("click", () => {
  log.info("User clicked Change Email");
  // Pre-fill the input with the current email
  emailInput.value = currentEmailEl.textContent;
  showEmailSetup();
  emailInput.focus();
});

openDashboardBtn.addEventListener("click", () => {
  log.info("Opening dashboard in new tab");
  chrome.tabs.create({ url: API_BASE });
});

// ─── Initialization ──────────────────────────────────────────────────

document.addEventListener("DOMContentLoaded", async () => {
  log.info("Popup opened — initializing");
  await Promise.all([checkServerStatus(), loadEmail()]);
  log.info("Popup initialization complete");
});
